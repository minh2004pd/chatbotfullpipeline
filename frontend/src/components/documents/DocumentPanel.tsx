import { useState } from 'react'
import { FileText, Trash2, RefreshCw, Loader2, AlertCircle, Layers, CheckCircle2 } from 'lucide-react'
import { useDocuments } from '@/hooks/useDocuments'
import UploadZone from './UploadZone'
import type { UploadProgress } from '@/types'

export default function DocumentPanel() {
  const {
    documents,
    total,
    isLoading,
    isError,
    refetch,
    uploadFile,
    uploadProgresses,
    deleteDocument,
    isDeleting,
  } = useDocuments()

  const [deletingId, setDeletingId] = useState<string | null>(null)

  const handleFiles = async (files: File[]) => {
    for (const file of files) {
      await uploadFile(file)
    }
  }

  const handleDelete = (documentId: string) => {
    setDeletingId(documentId)
    deleteDocument(documentId, {
      onSettled: () => setDeletingId(null),
    })
  }

  const uploadingEntries = Object.entries(uploadProgresses)
  const isAnyUploading = uploadingEntries.some(([, p]) => p.status === 'uploading')

  return (
    <div className="space-y-2">
      <UploadZone onFiles={handleFiles} isUploading={isAnyUploading} />

      {/* Upload progress list */}
      {uploadingEntries.length > 0 && (
        <div className="space-y-1">
          {uploadingEntries.map(([id, progress]) => (
            <UploadProgressRow key={id} progress={progress} />
          ))}
        </div>
      )}

      {/* Document list */}
      <div>
        <div className="flex items-center justify-between mb-1.5 px-0.5">
          <span className="text-[10px] text-[#555] font-medium">
            {total > 0 ? `${total} document${total !== 1 ? 's' : ''}` : 'No documents'}
          </span>
          <button
            onClick={() => void refetch()}
            disabled={isLoading}
            className="p-1 text-[#444] hover:text-[#a0a0a0] transition-colors rounded disabled:opacity-30"
            title="Refresh"
          >
            <RefreshCw size={11} className={isLoading ? 'animate-spin' : ''} />
          </button>
        </div>

        {isLoading && (
          <div className="flex items-center justify-center py-4">
            <Loader2 size={16} className="text-[#555] animate-spin" />
          </div>
        )}

        {isError && (
          <div className="flex items-center gap-1.5 text-[11px] text-red-400/80 bg-red-900/10 border border-red-900/30 rounded-lg px-2.5 py-2">
            <AlertCircle size={12} />
            <span>Failed to load documents</span>
          </div>
        )}

        {!isLoading && !isError && documents.length === 0 && (
          <p className="text-[11px] text-[#444] text-center py-2">
            Upload PDFs to use RAG search
          </p>
        )}

        {documents.length > 0 && (
          <div className="space-y-1">
            {documents.map((doc) => (
              <div
                key={doc.document_id}
                className="flex items-center gap-2 px-2.5 py-2 bg-[#111] border border-[#1e1e1e] rounded-lg group hover:border-[#2a2a2a] transition-colors"
              >
                <FileText size={12} className="text-violet-500/70 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] text-[#c0c0c0] truncate font-medium">
                    {doc.filename}
                  </p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="flex items-center gap-0.5 text-[9px] text-[#555]">
                      <Layers size={8} />
                      {doc.chunk_count} chunks
                    </span>
                    <span className="text-[9px] text-[#444]">
                      {formatDate(doc.uploaded_at)}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(doc.document_id)}
                  disabled={isDeleting && deletingId === doc.document_id}
                  className="p-1 text-[#444] hover:text-red-400 opacity-0 group-hover:opacity-100 disabled:opacity-50 transition-all rounded"
                  title="Delete document"
                >
                  {isDeleting && deletingId === doc.document_id ? (
                    <Loader2 size={11} className="animate-spin" />
                  ) : (
                    <Trash2 size={11} />
                  )}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function UploadProgressRow({ progress }: { progress: UploadProgress }) {
  const isUploading = progress.status === 'uploading'
  const isPostUpload = ['rag_done', 'wiki_processing', 'done', 'error'].includes(progress.status)
  const isWikiDone = progress.status === 'done'
  const isError = progress.status === 'error'

  return (
    <div className="px-2.5 py-2 bg-[#111] border border-[#1e1e1e] rounded-lg space-y-1.5">
      {/* Filename */}
      <p className="text-[10px] text-[#a0a0a0] truncate">{progress.filename}</p>

      {/* Stage: file upload progress */}
      {isUploading && (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-0.5 bg-[#2a2a2a] rounded-full overflow-hidden">
            <div
              className="h-full bg-violet-500 rounded-full transition-all duration-200"
              style={{ width: `${progress.progress}%` }}
            />
          </div>
          <span className="text-[9px] text-[#555] flex-shrink-0">{progress.progress}%</span>
        </div>
      )}

      {/* Stages: RAG + Wiki (post-upload) */}
      {isPostUpload && (
        <div className="space-y-1">
          {/* RAG — luôn done khi đến đây */}
          <div className="flex items-center gap-1.5">
            <CheckCircle2 size={9} className="text-green-500 flex-shrink-0" />
            <span className="text-[9px] text-[#555]">
              RAG index
              {progress.chunkCount != null && (
                <span className="text-[#444]"> — {progress.chunkCount} chunks</span>
              )}
            </span>
          </div>

          {/* Wiki */}
          <div className="flex items-center gap-1.5">
            {isWikiDone ? (
              <CheckCircle2 size={9} className="text-green-500 flex-shrink-0" />
            ) : isError ? (
              <AlertCircle size={9} className="text-red-400 flex-shrink-0" />
            ) : (
              <Loader2 size={9} className="text-violet-400 animate-spin flex-shrink-0" />
            )}
            <span
              className={`text-[9px] ${
                isError ? 'text-red-400' : isWikiDone ? 'text-[#555]' : 'text-violet-400'
              }`}
            >
              {isWikiDone ? 'Wiki index' : isError ? 'Wiki — lỗi' : 'Wiki đang xây dựng...'}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

function formatDate(dateStr: string): string {
  try {
    return new Intl.DateTimeFormat('en', {
      month: 'short',
      day: 'numeric',
    }).format(new Date(dateStr))
  } catch {
    return ''
  }
}
