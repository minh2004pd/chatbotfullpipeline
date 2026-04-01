import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { memoryApi } from '@/api/memory'
import { useChatStore } from '@/store/chatStore'

export const MEMORY_QUERY_KEY = ['memory']

export function useMemory() {
  const queryClient = useQueryClient()
  const { addToast, userId } = useChatStore()

  const memoriesQuery = useQuery({
    queryKey: [...MEMORY_QUERY_KEY, userId],
    queryFn: () => memoryApi.list(userId),
    staleTime: 30_000,
    enabled: !!userId,
  })

  const deleteMutation = useMutation({
    mutationFn: (memoryId: string) => memoryApi.delete(memoryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: MEMORY_QUERY_KEY })
      addToast({ type: 'success', message: 'Memory deleted.' })
    },
    onError: () => {
      addToast({ type: 'error', message: 'Failed to delete memory.' })
    },
  })

  const deleteAllMutation = useMutation({
    mutationFn: () => memoryApi.deleteAll(userId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: MEMORY_QUERY_KEY })
      addToast({ type: 'success', message: 'All memories cleared.' })
    },
    onError: () => {
      addToast({ type: 'error', message: 'Failed to clear memories.' })
    },
  })

  return {
    memories: memoriesQuery.data?.memories ?? [],
    total: memoriesQuery.data?.total ?? 0,
    isLoading: memoriesQuery.isLoading,
    isError: memoriesQuery.isError,
    refetch: memoriesQuery.refetch,
    deleteMemory: deleteMutation.mutate,
    isDeleting: deleteMutation.isPending,
    deleteAll: deleteAllMutation.mutate,
    isDeletingAll: deleteAllMutation.isPending,
  }
}
