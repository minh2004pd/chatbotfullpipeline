import { useCallback, useEffect, useRef, useState } from 'react'
import {
  listMeetings,
  openTranscriptionStream,
  startTranscription,
  stopTranscription,
} from '@/api/transcription'
import type { AudioSource, LiveUtterance, MeetingInfo, TranscriptionEvent } from '@/types'
import AudioCaptureService from '@/services/AudioCaptureService'

interface UseTranscriptionOptions {
  userId: string
}

export function useTranscription({ userId }: UseTranscriptionOptions) {
  const [isRecording, setIsRecording] = useState(false)
  const [meetingId, setMeetingId] = useState<string | null>(null)
  const [liveUtterances, setLiveUtterances] = useState<LiveUtterance[]>([])
  const [partialText, setPartialText] = useState('')
  const [partialTranslation, setPartialTranslation] = useState('')
  const [meetings, setMeetings] = useState<MeetingInfo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isLoadingMeetings, setIsLoadingMeetings] = useState(false)

  const captureServiceRef = useRef<AudioCaptureService | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const meetingIdRef = useRef<string | null>(null)
  // Ref để tránh stale closure khi gọi stopRecording từ trong startRecording
  const stopRecordingRef = useRef<() => void>(() => {})

  // Sync meetingId to ref for use in callbacks
  useEffect(() => {
    meetingIdRef.current = meetingId
  }, [meetingId])

  const fetchMeetings = useCallback(async () => {
    setIsLoadingMeetings(true)
    try {
      const data = await listMeetings(userId)
      setMeetings(data.meetings)
    } catch (e) {
      console.error('Failed to load meetings', e)
    } finally {
      setIsLoadingMeetings(false)
    }
  }, [userId])

  const stopRecording = useCallback(async () => {
    const mid = meetingIdRef.current
    if (!mid) return

    // 1. Dừng audio capture
    captureServiceRef.current?.stop()
    captureServiceRef.current = null

    // 2. Đóng SSE
    eventSourceRef.current?.close()
    eventSourceRef.current = null

    // Clear meeting ID trước để tránh gọi lại
    meetingIdRef.current = null
    setIsRecording(false)
    setMeetingId(null)
    setPartialText('')
    setPartialTranslation('')

    // 3. Báo backend stop (fire-and-forget nếu session đã expired)
    try {
      await stopTranscription(mid, userId)
    } catch (e) {
      console.error('Stop transcription error', e)
    }

    // Refresh meetings list
    fetchMeetings()
  }, [userId, fetchMeetings])

  // Giữ ref luôn trỏ tới stopRecording mới nhất
  useEffect(() => {
    stopRecordingRef.current = stopRecording
  }, [stopRecording])

  const startRecording = useCallback(
    async (source: AudioSource = 'mic', title?: string, enableTranslation = true) => {
      setError(null)
      setLiveUtterances([])
      setPartialText('')
      setPartialTranslation('')

      try {
        // 1. Xin quyền audio TRƯỚC (có thể show browser dialog) — làm trước
        //    để Soniox WS không bị timeout chờ audio
        const capture = new AudioCaptureService()
        captureServiceRef.current = capture
        await capture.prepare(source)

        // 2. Bắt đầu session trên backend (mở Soniox WS)
        const { meeting_id } = await startTranscription(
          { title, language_hints: ['vi', 'en'], enable_translation: enableTranslation },
          userId,
        )
        setMeetingId(meeting_id)
        meetingIdRef.current = meeting_id // cập nhật ref ngay (không đợi useEffect)

        // 3. Subscribe SSE stream
        const es = openTranscriptionStream(meeting_id)
        eventSourceRef.current = es

        es.onmessage = (e) => {
          try {
            const event: TranscriptionEvent = JSON.parse(e.data)
            handleTranscriptionEvent(event)
            // Tự động dừng khi nhận end/error từ server
            if (event.type === 'end' || event.type === 'error') {
              stopRecordingRef.current()
            }
          } catch {
            // ignore parse errors
          }
        }
        es.onerror = () => {
          setError('SSE connection error')
          stopRecordingRef.current()
        }

        // 4. Bắt đầu stream audio (worklet đã pre-loaded, không có độ trễ async)
        capture.startStreaming(async (chunk) => {
          try {
            await fetch(`/api/v1/transcription/audio/${meeting_id}`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/octet-stream',
                'X-User-ID': userId,
              },
              body: chunk,
            })
          } catch {
            // non-fatal, tiếp tục
          }
        })

        setIsRecording(true)
      } catch (e: unknown) {
        // Dọn dẹp nếu start thất bại
        captureServiceRef.current?.stop()
        captureServiceRef.current = null
        const msg = e instanceof Error ? e.message : String(e)
        setError(msg)
        throw e
      }
    },
    [userId],
  )

  function handleTranscriptionEvent(event: TranscriptionEvent) {
    if (event.type === 'partial') {
      const text = event.tokens.map((t) => t.text).join('')
      setPartialText(text)
      setPartialTranslation(event.translation ?? '')
    } else if (event.type === 'final') {
      const text = event.tokens.map((t) => t.text).join('').trim()
      if (!text) return
      const speakerNum = event.tokens[0]?.speaker ?? 0
      setLiveUtterances((prev) => [
        ...prev,
        {
          speaker: `speaker_${speakerNum}`,
          text,
          translation: event.translation,
          isFinal: true,
        },
      ])
      setPartialText('')
      setPartialTranslation('')
    } else if (event.type === 'error') {
      setError('Transcription error from server')
    }
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      captureServiceRef.current?.stop()
      eventSourceRef.current?.close()
    }
  }, [])

  return {
    isRecording,
    meetingId,
    liveUtterances,
    partialText,
    partialTranslation,
    meetings,
    error,
    isLoadingMeetings,
    startRecording,
    stopRecording,
    fetchMeetings,
  }
}
