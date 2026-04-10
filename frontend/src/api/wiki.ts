import type { WikiGraphData, WikiPage } from '@/types'
import { apiClient } from './client'

interface WikiGraphParams {
  showStubs?: boolean
  showSummaries?: boolean
  sourceIds?: string[]
}

export const wikiApi = {
  getGraph: async (params: WikiGraphParams = {}): Promise<WikiGraphData> => {
    const res = await apiClient.get<WikiGraphData>('/api/v1/wiki/graph', {
      params: {
        show_stubs: params.showStubs ?? false,
        show_summaries: params.showSummaries ?? false,
        // axios serializes array as repeated params: source_ids=a&source_ids=b
        ...(params.sourceIds?.length ? { source_ids: params.sourceIds } : {}),
      },
    })
    return res.data
  },

  getPage: async (category: string, slug: string): Promise<WikiPage> => {
    const res = await apiClient.get<WikiPage>(`/api/v1/wiki/pages/${category}/${slug}`)
    return res.data
  },
}
