import { useCallback, useRef, useState, type DragEvent, type ChangeEvent } from 'react'
import { Upload, FileUp, Loader2 } from 'lucide-react'

interface Props {
  onFiles: (files: File[]) => void
  isUploading: boolean
}

export default function UploadZone({ onFiles, isUploading }: Props) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)

      const files = Array.from(e.dataTransfer.files).filter(
        (f) => f.type === 'application/pdf',
      )
      if (files.length > 0) onFiles(files)
    },
    [onFiles],
  )

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (files.length > 0) onFiles(files)
    e.target.value = ''
  }

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => !isUploading && inputRef.current?.click()}
      className={`
        relative flex flex-col items-center justify-center gap-1.5
        border-2 border-dashed rounded-xl px-3 py-4 cursor-pointer
        transition-all duration-200 select-none
        ${isDragging
          ? 'border-violet-500 bg-violet-900/20'
          : 'border-[#2e2e2e] hover:border-violet-700/50 hover:bg-[#1a1a1a]'
        }
        ${isUploading ? 'cursor-not-allowed opacity-60' : ''}
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        multiple
        className="hidden"
        onChange={handleChange}
        disabled={isUploading}
      />

      {isUploading ? (
        <Loader2 size={20} className="text-violet-400 animate-spin" />
      ) : isDragging ? (
        <FileUp size={20} className="text-violet-400" />
      ) : (
        <Upload size={18} className="text-[#555]" />
      )}

      <span className="text-[11px] text-[#666] text-center leading-tight">
        {isUploading
          ? 'Uploading…'
          : isDragging
          ? 'Drop PDF here'
          : 'Drop PDF or click to upload'
        }
      </span>
    </div>
  )
}
