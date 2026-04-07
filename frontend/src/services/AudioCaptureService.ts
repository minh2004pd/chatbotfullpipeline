/**
 * AudioCaptureService — quản lý audio capture từ mic / system / cả hai.
 *
 * Flow 2 bước để tránh Soniox WS timeout:
 *   1. prepare(source)          → xin quyền mic/screen (có thể show dialog)
 *   2. startStreaming(onChunk)  → tạo AudioContext + worklet, bắt đầu gửi PCM16
 *   3. stop()                  → dọn dẹp
 */

import type { AudioSource } from '@/types'

// AudioWorklet processor code (inline blob để tránh phức tạp Vite worklet setup)
const WORKLET_CODE = /* js */ `
class PCM16Processor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = [];
    this._bufferSize = 8000;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const samples = input[0]; // Float32Array, mono
    for (let i = 0; i < samples.length; i++) {
      this._buffer.push(samples[i]);
    }

    while (this._buffer.length >= this._bufferSize) {
      const chunk = this._buffer.splice(0, this._bufferSize);
      const pcm16 = this._float32ToPCM16(chunk);
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }

    return true;
  }

  _float32ToPCM16(float32) {
    const int16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const clamped = Math.max(-1, Math.min(1, float32[i]));
      int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7FFF;
    }
    return int16;
  }
}

registerProcessor('pcm16-processor', PCM16Processor);
`

export default class AudioCaptureService {
  private audioContext: AudioContext | null = null
  private workletNode: AudioWorkletNode | null = null
  private micStream: MediaStream | null = null
  private displayStream: MediaStream | null = null
  private capturedStream: MediaStream | null = null

  /**
   * Bước 1: Xin quyền, lấy media stream, và pre-load AudioWorklet.
   * Pre-load worklet ở đây để startStreaming() không có độ trễ async →
   * tránh Soniox WS timeout (408) do không nhận được audio kịp thời.
   */
  async prepare(source: AudioSource): Promise<void> {
    this.capturedStream = await this._getStream(source)

    // Pre-create AudioContext + load worklet ngay trong bước prepare
    this.audioContext = new AudioContext({ sampleRate: 16000 })
    const blob = new Blob([WORKLET_CODE], { type: 'application/javascript' })
    const workletUrl = URL.createObjectURL(blob)
    await this.audioContext.audioWorklet.addModule(workletUrl)
    URL.revokeObjectURL(workletUrl)
  }

  /**
   * Bước 2: Kết nối stream → worklet, bắt đầu gửi PCM16 chunks qua callback.
   * Gọi SAU khi Soniox session đã được mở — worklet đã sẵn sàng (không await).
   */
  startStreaming(onChunk: (data: ArrayBuffer) => void): void {
    if (!this.capturedStream || !this.audioContext) {
      throw new Error('prepare() chưa được gọi')
    }

    const sourceNode = this.audioContext.createMediaStreamSource(this.capturedStream)
    this.workletNode = new AudioWorkletNode(this.audioContext, 'pcm16-processor')

    this.workletNode.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
      onChunk(e.data)
    }

    sourceNode.connect(this.workletNode)
    this.workletNode.connect(this.audioContext.destination)
  }

  stop(): void {
    this.workletNode?.disconnect()
    this.workletNode = null

    this.micStream?.getTracks().forEach((t) => t.stop())
    this.micStream = null

    this.displayStream?.getTracks().forEach((t) => t.stop())
    this.displayStream = null

    this.capturedStream = null

    this.audioContext?.close()
    this.audioContext = null
  }

  private async _getStream(source: AudioSource): Promise<MediaStream> {
    if (source === 'mic') {
      this.micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      return this.micStream
    }

    if (source === 'system') {
      // getDisplayMedia cần video: true để Chrome cho phép capture audio
      this.displayStream = await navigator.mediaDevices.getDisplayMedia({
        audio: true,
        video: true,
      })
      // Tắt video track ngay để không record video
      this.displayStream.getVideoTracks().forEach((t) => t.stop())
      return this.displayStream
    }

    // source === 'both': mix mic + system
    this.micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    this.displayStream = await navigator.mediaDevices.getDisplayMedia({
      audio: true,
      video: true,
    })
    this.displayStream.getVideoTracks().forEach((t) => t.stop())

    // Merge hai streams bằng AudioContext tạm
    const ctx = new AudioContext({ sampleRate: 16000 })
    const micSrc = ctx.createMediaStreamSource(this.micStream)
    const sysSrc = ctx.createMediaStreamSource(this.displayStream)
    const dest = ctx.createMediaStreamDestination()
    micSrc.connect(dest)
    sysSrc.connect(dest)
    // Giữ ctx để close sau trong stop()
    ;(this as unknown as Record<string, unknown>)['_mergeCtx'] = ctx
    return dest.stream
  }
}
