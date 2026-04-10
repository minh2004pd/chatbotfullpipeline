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

// ─── Session types ───────────────────────────────────────────────────────────────

export interface Session {
  session_id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface SessionMessage {
  role: 'user' | 'model'
  content: string
  timestamp: string
}

export interface SessionMessages {
  session_id: string
  title: string
  messages: SessionMessage[]
}

// ─── Transcription / Meeting types ───────────────────────────────────────────────

export type AudioSource = 'mic' | 'system' | 'both'

export interface TranscriptionToken {
  text: string
  speaker?: number
  start_ms?: number
  end_ms?: number
}

export interface TranscriptionEvent {
  type: 'partial' | 'final' | 'error' | 'end' | 'keepalive'
  meeting_id: string
  tokens: TranscriptionToken[]
  translation?: string
}

export interface MeetingInfo {
  meeting_id: string
  title: string
  user_id: string
  status: 'recording' | 'completed'
  duration_ms?: number
  speakers: string[]
  languages: string[]
  utterance_count: number
  created_at: string
  updated_at?: string
}

export interface UtteranceItem {
  speaker: string
  language?: string
  text: string
  translated_text?: string
  confidence?: number
  start_ms?: number
  end_ms?: number
  created_at?: string
}

export interface MeetingTranscript {
  meeting_id: string
  title: string
  utterances: UtteranceItem[]
  total: number
}

export interface LiveUtterance {
  speaker: string
  text: string
  translation?: string
  isFinal: boolean
}

// ─── Wiki Graph types ────────────────────────────────────────────────────────────

export interface WikiGraphNode {
  key: string     // unique React Flow id: "{category}/{slug}"
  id: string      // slug only, for API calls
  title: string
  type: string
  category: 'entities' | 'topics' | 'summaries'
  source_count: number
  backlink_count: number
  is_stub: boolean
}

export interface WikiGraphEdge {
  id: string
  source: string
  target: string
}

export interface WikiGraphData {
  nodes: WikiGraphNode[]
  edges: WikiGraphEdge[]
}

export interface WikiPage {
  slug: string
  category: string
  content: string
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
  loadSession: (sessionId: string, messages: Message[]) => void
  addToast: (toast: Omit<Toast, 'id'>) => void
  removeToast: (id: string) => void
  setIsStreaming: (value: boolean) => void
}

export interface UploadProgress {
  filename: string
  progress: number
  status: 'uploading' | 'rag_done' | 'wiki_processing' | 'done' | 'error'
  documentId?: string   // set sau khi upload API trả về
  chunkCount?: number   // set từ RAG result
  error?: string
}
