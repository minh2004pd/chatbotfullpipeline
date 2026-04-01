import type { ListMemoriesResponse, DeleteMemoryResponse } from '@/types'
import { apiClient } from './client'

export const memoryApi = {
  list: async (userId: string): Promise<ListMemoriesResponse> => {
    const res = await apiClient.get<ListMemoriesResponse>(
      `/api/v1/memory/user/${encodeURIComponent(userId)}`,
    )
    return res.data
  },

  delete: async (memoryId: string): Promise<DeleteMemoryResponse> => {
    const res = await apiClient.delete<DeleteMemoryResponse>(
      `/api/v1/memory/${memoryId}`,
    )
    return res.data
  },

  deleteAll: async (userId: string): Promise<void> => {
    await apiClient.delete(
      `/api/v1/memory/user/${encodeURIComponent(userId)}/all`,
    )
  },
}
