import { useQuery } from '@tanstack/react-query'
import { wikiApi } from '@/api/wiki'

interface UseWikiGraphOptions {
  userId: string
  showStubs?: boolean
  showSummaries?: boolean
  sourceIds?: string[]
}

export function useWikiGraph({ userId, showStubs = false, showSummaries = false, sourceIds }: UseWikiGraphOptions) {
  return useQuery({
    queryKey: ['wiki-graph', userId, showStubs, showSummaries, sourceIds],
    queryFn: () => wikiApi.getGraph({ showStubs, showSummaries, sourceIds }),
    staleTime: 60_000,
    enabled: !!userId,
  })
}

export function useWikiPage(category: string | null, slug: string | null) {
  return useQuery({
    queryKey: ['wiki-page', category, slug],
    queryFn: () => wikiApi.getPage(category!, slug!),
    enabled: !!category && !!slug,
    staleTime: 120_000,
  })
}
