import type { ListMemoriesResponse, DeleteMemoryResponse } from '@/types'
import { apiClient } from './client'

export const memoryApi = {
  list: async (): Promise<ListMemoriesResponse> => {
    // Backend dùng authenticated user_id từ JWT/header — không cần truyền userId
    const res = await apiClient.get<ListMemoriesResponse>('/api/v1/memory')
    return res.data
  },

  delete: async (memoryId: string): Promise<DeleteMemoryResponse> => {
    const res = await apiClient.delete<DeleteMemoryResponse>(
      `/api/v1/memory/${memoryId}`,
    )
    return res.data
  },

  deleteAll: async (): Promise<void> => {
    await apiClient.delete('/api/v1/memory/all')
  },
}
