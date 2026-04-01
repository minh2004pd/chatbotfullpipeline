// ─── Chat types ────────────────────────────────────────────────────────────────

export interface Citation {
  document_id: string
  document_name: string
  chunk_text: string
  score: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
  citations?: Citation[]
  imagePreview?: string // base64 data URL for display
  createdAt: Date
}

export interface ChatRequest {
  message: string
  user_id: string
  session_id?: string
  image_base64?: string
  image_mime_type?: string
}

export interface SSEChunk {
  content: string
  done: boolean
  citations?: Citation[]
}

// ─── Document types ─────────────────────────────────────────────────────────────

export interface Document {
  document_id: string
  filename: string
  user_id: string
  chunk_count: number
  uploaded_at: string
}

export interface UploadDocumentResponse {
  document_id: string
  filename: string
  user_id: string
  chunk_count: number
  message: string
  uploaded_at: string
}

export interface ListDocumentsResponse {
  documents: Document[]
  total: number
}

export interface DeleteDocumentResponse {
  document_id: string
  message: string
}

// ─── Memory types ───────────────────────────────────────────────────────────────

export interface Memory {
  id: string
  memory: string
  user_id: string
  score?: number
  created_at?: string
}

export interface ListMemoriesResponse {
  user_id: string
  memories: Memory[]
  total: number
}

export interface DeleteMemoryResponse {
  memory_id: string
  message: string
}

// ─── UI / Store types ────────────────────────────────────────────────────────────

export interface Toast {
  id: string
  type: 'success' | 'error' | 'info' | 'warning'
  message: string
}

export interface ChatStore {
  messages: Message[]
  sessionId: string
  userId: string
  isStreaming: boolean
  toasts: Toast[]

  addMessage: (message: Message) => void
  updateStreamingMessage: (id: string, content: string) => void
  finalizeStreamingMessage: (id: string, citations?: Citation[]) => void
  clearMessages: () => void
  setUserId: (userId: string) => void
  resetSession: () => void
  addToast: (toast: Omit<Toast, 'id'>) => void
  removeToast: (id: string) => void
  setIsStreaming: (value: boolean) => void
}

export interface UploadProgress {
  filename: string
  progress: number
  status: 'uploading' | 'done' | 'error'
  error?: string
}
