import {
  useRef,
  useState,
  useCallback,
  type ChangeEvent,
  type KeyboardEvent,
} from 'react'
import { Send, Square, ImagePlus, X, Loader2 } from 'lucide-react'

interface Props {
  onSend: (
    text: string,
    imageBase64?: string,
    imageMimeType?: string,
    imagePreview?: string,
  ) => void
  onStop: () => void
  isStreaming: boolean
}

const ACCEPTED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']

export default function MessageInput({ onSend, onStop, isStreaming }: Props) {
  const [text, setText] = useState('')
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [isConverting, setIsConverting] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Auto-resize textarea
  const adjustHeight = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [])

  const handleTextChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value)
    adjustHeight()
  }

  const handleImageSelect = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!ACCEPTED_MIME_TYPES.includes(file.type)) return

    setImageFile(file)

    // Create preview URL
    const reader = new FileReader()
    reader.onload = (ev) => {
      setImagePreview(ev.target?.result as string)
    }
    reader.readAsDataURL(file)

    // Reset file input so same file can be re-selected
    e.target.value = ''
  }

  const removeImage = () => {
    setImageFile(null)
    setImagePreview(null)
  }

  const getBase64 = (file: File): Promise<{ base64: string; mimeType: string }> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = (e) => {
        const dataUrl = e.target?.result as string
        // Strip "data:image/...;base64," prefix
        const base64 = dataUrl.split(',')[1]
        resolve({ base64, mimeType: file.type })
      }
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
  }

  const handleSend = useCallback(async () => {
    const trimmed = text.trim()
    if (!trimmed || isStreaming) return

    let imageBase64: string | undefined
    let imageMimeType: string | undefined
    let previewUrl: string | undefined

    if (imageFile) {
      setIsConverting(true)
      try {
        const result = await getBase64(imageFile)
        imageBase64 = result.base64
        imageMimeType = result.mimeType
        previewUrl = imagePreview ?? undefined
      } finally {
        setIsConverting(false)
      }
    }

    onSend(trimmed, imageBase64, imageMimeType, previewUrl)

    setText('')
    setImageFile(null)
    setImagePreview(null)

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    textareaRef.current?.focus()
  }, [text, isStreaming, imageFile, imagePreview, onSend])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const canSend = text.trim().length > 0 && !isStreaming && !isConverting

  return (
    <div className="px-4 py-3">
      {/* Image preview */}
      {imagePreview && (
        <div className="mb-2 flex items-center gap-2">
          <div className="relative inline-block">
            <img
              src={imagePreview}
              alt="Preview"
              className="h-16 w-16 object-cover rounded-lg border border-[#2e2e2e]"
            />
            <button
              onClick={removeImage}
              className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-[#333] rounded-full flex items-center justify-center text-[#aaa] hover:text-white hover:bg-[#555] transition-colors"
            >
              <X size={9} />
            </button>
          </div>
          <span className="text-xs text-[#666] truncate max-w-[180px]">
            {imageFile?.name}
          </span>
        </div>
      )}

      {/* Input row */}
      <div className="flex items-end gap-2 bg-[#1a1a1a] border border-[#2e2e2e] rounded-2xl px-3 py-2.5 focus-within:border-violet-700/60 transition-colors">
        {/* Image button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isStreaming}
          className="flex-shrink-0 p-1.5 text-[#555] hover:text-[#a0a0a0] disabled:opacity-30 disabled:cursor-not-allowed transition-colors rounded-lg hover:bg-[#2a2a2a] mb-0.5"
          title="Attach image"
        >
          <ImagePlus size={17} />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_MIME_TYPES.join(',')}
          className="hidden"
          onChange={handleImageSelect}
        />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          placeholder={isStreaming ? 'Waiting for response...' : 'Message MemRAG… (Enter to send, Shift+Enter for newline)'}
          disabled={isStreaming}
          rows={1}
          className="flex-1 bg-transparent resize-none outline-none text-sm text-[#f1f1f1] placeholder-[#444] leading-relaxed max-h-[200px] disabled:opacity-50 py-0.5"
          style={{ scrollbarWidth: 'thin', scrollbarColor: '#2e2e2e transparent' }}
        />

        {/* Send / Stop button */}
        {isStreaming ? (
          <button
            onClick={onStop}
            className="flex-shrink-0 p-2 bg-[#2a2a2a] hover:bg-[#333] text-[#a0a0a0] hover:text-white rounded-lg transition-colors mb-0.5"
            title="Stop generating"
          >
            <Square size={14} fill="currentColor" />
          </button>
        ) : (
          <button
            onClick={() => void handleSend()}
            disabled={!canSend}
            className="flex-shrink-0 p-2 bg-violet-600 hover:bg-violet-500 disabled:bg-[#2a2a2a] disabled:text-[#444] text-white rounded-lg transition-colors disabled:cursor-not-allowed mb-0.5"
            title="Send message"
          >
            {isConverting ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={14} />
            )}
          </button>
        )}
      </div>

      <p className="text-[10px] text-[#333] text-center mt-1.5">
        MemRAG may make mistakes. Verify important information.
      </p>
    </div>
  )
}
