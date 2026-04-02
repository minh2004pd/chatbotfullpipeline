import { apiClient } from './client'
import type { Session, SessionMessages } from '@/types'

export const getSessions = async (): Promise<Session[]> => {
  const { data } = await apiClient.get<Session[]>('/api/v1/sessions')
  return data
}

export const getSessionMessages = async (sessionId: string): Promise<SessionMessages> => {
  const { data } = await apiClient.get<SessionMessages>(`/api/v1/sessions/${sessionId}`)
  return data
}

export const deleteSession = async (sessionId: string): Promise<void> => {
  await apiClient.delete(`/api/v1/sessions/${sessionId}`)
}
