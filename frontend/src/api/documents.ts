import type {
  ListDocumentsResponse,
  UploadDocumentResponse,
  DeleteDocumentResponse,
} from '@/types'
import { apiClient } from './client'

interface IndexingStatusResponse {
  document_id: string
  rag: string   // "done"
  wiki: string  // "processing" | "done" | "error" | "disabled"
}

export const documentsApi = {
  list: async (): Promise<ListDocumentsResponse> => {
    const res = await apiClient.get<ListDocumentsResponse>('/api/v1/documents')
    return res.data
  },

  upload: async (
    file: File,
    onProgress?: (progress: number) => void,
  ): Promise<UploadDocumentResponse> => {
    const formData = new FormData()
    formData.append('file', file)

    const res = await apiClient.post<UploadDocumentResponse>(
      '/api/v1/documents/upload',
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (event) => {
          if (event.total && onProgress) {
            onProgress(Math.round((event.loaded / event.total) * 100))
          }
        },
      },
    )
    return res.data
  },

  delete: async (documentId: string): Promise<DeleteDocumentResponse> => {
    const res = await apiClient.delete<DeleteDocumentResponse>(
      `/api/v1/documents/${documentId}`,
    )
    return res.data
  },

  getIndexingStatus: async (documentId: string): Promise<IndexingStatusResponse> => {
    const res = await apiClient.get<IndexingStatusResponse>(
      `/api/v1/documents/${documentId}/status`,
    )
    return res.data
  },
}
