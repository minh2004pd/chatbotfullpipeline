import { useEffect, useState } from 'react'
import { CheckCircle, XCircle, Info, AlertTriangle, X } from 'lucide-react'
import type { Toast } from '@/types'

interface Props {
  toasts: Toast[]
  onRemove: (id: string) => void
}

export default function ToastContainer({ toasts, onRemove }: Props) {
  if (toasts.length === 0) return null

  return (
    <div
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"
      aria-live="polite"
      aria-atomic="false"
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onRemove={onRemove} />
      ))}
    </div>
  )
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: string) => void }) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    // Small delay to trigger CSS transition
    const t = requestAnimationFrame(() => setVisible(true))
    return () => cancelAnimationFrame(t)
  }, [])

  const config = {
    success: {
      icon: <CheckCircle size={15} />,
      classes: 'bg-[#0d1f0f] border-green-800/60 text-green-300',
      iconClass: 'text-green-400',
    },
    error: {
      icon: <XCircle size={15} />,
      classes: 'bg-[#1f0d0d] border-red-800/60 text-red-300',
      iconClass: 'text-red-400',
    },
    info: {
      icon: <Info size={15} />,
      classes: 'bg-[#0d0f1f] border-blue-800/60 text-blue-300',
      iconClass: 'text-blue-400',
    },
    warning: {
      icon: <AlertTriangle size={15} />,
      classes: 'bg-[#1f1a0d] border-yellow-800/60 text-yellow-300',
      iconClass: 'text-yellow-400',
    },
  }[toast.type]

  return (
    <div
      className={`
        pointer-events-auto flex items-start gap-2.5 px-3.5 py-2.5
        border rounded-xl shadow-xl backdrop-blur-sm
        text-sm max-w-[320px] min-w-[220px]
        transition-all duration-300
        ${config.classes}
        ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'}
      `}
    >
      <span className={`flex-shrink-0 mt-0.5 ${config.iconClass}`}>
        {config.icon}
      </span>
      <span className="flex-1 leading-snug text-xs">{toast.message}</span>
      <button
        onClick={() => onRemove(toast.id)}
        className="flex-shrink-0 opacity-50 hover:opacity-100 transition-opacity mt-0.5"
        aria-label="Dismiss"
      >
        <X size={12} />
      </button>
    </div>
  )
}
