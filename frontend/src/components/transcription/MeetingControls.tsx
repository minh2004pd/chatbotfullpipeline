import React from 'react'
import { Mic, Monitor, Layers, Square, Circle, Loader2 } from 'lucide-react'
import type { AudioSource } from '@/types'

interface MeetingControlsProps {
  isRecording: boolean
  isStopping?: boolean
  selectedSource: AudioSource
  onSourceChange: (source: AudioSource) => void
  onStart: () => void
  onStop: () => void
  error?: string | null
  meetingTitle: string
  onTitleChange: (title: string) => void
  enableTranslation: boolean
  onTranslationChange: (enabled: boolean) => void
}

const SOURCE_OPTIONS: { value: AudioSource; label: string; icon: React.ReactNode }[] = [
  { value: 'mic', label: 'Microphone', icon: <Mic size={13} /> },
  { value: 'system', label: 'System Audio', icon: <Monitor size={13} /> },
  { value: 'both', label: 'Mic + System', icon: <Layers size={13} /> },
]

export default function MeetingControls({
  isRecording,
  isStopping,
  selectedSource,
  onSourceChange,
  onStart,
  onStop,
  error,
  meetingTitle,
  onTitleChange,
  enableTranslation,
  onTranslationChange,
}: MeetingControlsProps) {
  return (
    <div className="flex flex-col gap-3 p-3 bg-[#161616] rounded-lg border border-[#2e2e2e]">
      {/* Title input */}
      <input
        value={meetingTitle}
        onChange={(e) => onTitleChange(e.target.value)}
        disabled={isRecording}
        placeholder="Meeting title..."
        className="bg-[#1a1a1a] border border-[#2e2e2e] rounded-md px-3 py-1.5 text-sm text-[#f1f1f1] placeholder-[#555] outline-none focus:border-violet-600 disabled:opacity-50 transition-colors"
      />

      {/* Source selector */}
      <div className="flex gap-1.5">
        {SOURCE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            disabled={isRecording}
            onClick={() => onSourceChange(opt.value)}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-1 justify-center
              ${
                selectedSource === opt.value
                  ? 'bg-violet-700 text-white'
                  : 'bg-[#1e1e1e] text-[#888] hover:bg-[#2a2a2a] hover:text-[#ccc]'
              }`}
          >
            {opt.icon}
            <span className="hidden sm:inline">{opt.label}</span>
          </button>
        ))}
      </div>

      {/* Translation toggle */}
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <div
          onClick={() => !isRecording && onTranslationChange(!enableTranslation)}
          className={`relative w-8 h-4 rounded-full transition-colors ${
            enableTranslation ? 'bg-violet-600' : 'bg-[#333]'
          } ${isRecording ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
        >
          <span
            className={`absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
              enableTranslation ? 'translate-x-4' : 'translate-x-0'
            }`}
          />
        </div>
        <span className="text-xs text-[#888]">Auto-translate</span>
      </label>

      {/* Start / Stop / Processing button */}
      {isStopping ? (
        <button
          disabled
          className="flex items-center justify-center gap-2 py-2 rounded-md bg-amber-700/50 text-amber-200 text-sm font-medium cursor-wait"
        >
          <Loader2 size={14} className="animate-spin" />
          Đang xử lý bản ghi...
        </button>
      ) : isRecording ? (
        <button
          onClick={onStop}
          className="flex items-center justify-center gap-2 py-2 rounded-md bg-red-700 hover:bg-red-600 text-white text-sm font-medium transition-colors"
        >
          <Square size={14} />
          Stop Recording
        </button>
      ) : (
        <button
          onClick={onStart}
          className="flex items-center justify-center gap-2 py-2 rounded-md bg-violet-700 hover:bg-violet-600 text-white text-sm font-medium transition-colors"
        >
          <Circle size={14} className="fill-current" />
          Start Recording
        </button>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-red-400 bg-red-900/20 px-2 py-1.5 rounded border border-red-800/40">
          {error}
        </p>
      )}
    </div>
  )
}
