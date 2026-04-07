import { apiClient } from './client'
import type { MeetingInfo, MeetingTranscript } from '@/types'

export interface StartTranscriptionRequest {
  title?: string
  language_hints?: string[]
  enable_translation?: boolean
  translation_target_language?: string
  enable_speaker_diarization?: boolean
  num_speakers?: number
}

export async function startTranscription(
  req: StartTranscriptionRequest,
  userId: string,
): Promise<{ meeting_id: string; status: string }> {
  const resp = await apiClient.post('/api/v1/transcription/start', req, {
    headers: { 'X-User-ID': userId },
  })
  return resp.data
}

export async function sendAudioChunk(
  meetingId: string,
  audioData: ArrayBuffer,
  userId: string,
): Promise<void> {
  await apiClient.post(`/api/v1/transcription/audio/${meetingId}`, audioData, {
    headers: {
      'X-User-ID': userId,
      'Content-Type': 'application/octet-stream',
    },
  })
}

export async function stopTranscription(
  meetingId: string,
  userId: string,
): Promise<{ meeting_id: string; status: string; utterance_count: number }> {
  const resp = await apiClient.post(
    `/api/v1/transcription/stop/${meetingId}`,
    {},
    { headers: { 'X-User-ID': userId } },
  )
  return resp.data
}

export function openTranscriptionStream(meetingId: string): EventSource {
  const url = `/api/v1/transcription/stream/${meetingId}`
  // EventSource không hỗ trợ custom headers → dùng query param cho user_id
  // Backend đọc từ header X-User-ID; với SSE dùng proxy vite nên cùng origin
  return new EventSource(url)
}

export async function listMeetings(userId: string): Promise<{ meetings: MeetingInfo[]; total: number }> {
  const resp = await apiClient.get('/api/v1/meetings', {
    headers: { 'X-User-ID': userId },
  })
  return resp.data
}

export async function getMeetingTranscript(
  meetingId: string,
  userId: string,
): Promise<MeetingTranscript> {
  const resp = await apiClient.get(`/api/v1/meetings/${meetingId}/transcript`, {
    headers: { 'X-User-ID': userId },
  })
  return resp.data
}

export async function deleteMeeting(meetingId: string, userId: string): Promise<void> {
  await apiClient.delete(`/api/v1/meetings/${meetingId}`, {
    headers: { 'X-User-ID': userId },
  })
}
