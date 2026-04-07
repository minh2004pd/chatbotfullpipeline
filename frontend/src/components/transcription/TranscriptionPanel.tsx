import React, { useEffect, useRef, useState } from 'react'
import { Mic, ChevronDown, ChevronRight, Trash2, FileText } from 'lucide-react'
import { useChatStore } from '@/store/chatStore'
import { useTranscription } from '@/hooks/useTranscription'
import type { AudioSource, MeetingInfo } from '@/types'
import MeetingControls from './MeetingControls'
import { deleteMeeting, getMeetingTranscript } from '@/api/transcription'

// Màu cho từng speaker
const SPEAKER_COLORS: Record<string, string> = {
  speaker_0: 'text-violet-400',
  speaker_1: 'text-sky-400',
  speaker_2: 'text-emerald-400',
  speaker_3: 'text-amber-400',
  speaker_4: 'text-pink-400',
}

function speakerColor(speaker: string): string {
  return SPEAKER_COLORS[speaker] ?? 'text-[#a0a0a0]'
}

function formatDuration(ms?: number): string {
  if (!ms) return '--'
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const h = Math.floor(m / 60)
  if (h > 0) return `${h}h ${m % 60}m`
  if (m > 0) return `${m}m ${s % 60}s`
  return `${s}s`
}

export default function TranscriptionPanel() {
  const userId = useChatStore((s) => s.userId)
  const [source, setSource] = useState<AudioSource>('mic')
  const [title, setTitle] = useState('')
  const [enableTranslation, setEnableTranslation] = useState(true)
  const [showMeetings, setShowMeetings] = useState(true)
  const [expandedMeeting, setExpandedMeeting] = useState<string | null>(null)
  const [transcriptData, setTranscriptData] = useState<Record<string, { text: string }[]>>({})
  const liveEndRef = useRef<HTMLDivElement>(null)

  const {
    isRecording,
    liveUtterances,
    partialText,
    partialTranslation,
    meetings,
    error,
    isLoadingMeetings,
    startRecording,
    stopRecording,
    fetchMeetings,
  } = useTranscription({ userId })

  // Load meetings on mount
  useEffect(() => {
    fetchMeetings()
  }, [fetchMeetings])

  // Auto-scroll live transcript
  useEffect(() => {
    liveEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [liveUtterances, partialText])

  const handleStart = async () => {
    try {
      await startRecording(source, title || undefined, enableTranslation)
    } catch {
      // error hiển thị từ hook
    }
  }

  const handleStop = async () => {
    await stopRecording()
    setTitle('')
  }

  const handleLoadTranscript = async (meeting: MeetingInfo) => {
    if (expandedMeeting === meeting.meeting_id) {
      setExpandedMeeting(null)
      return
    }
    setExpandedMeeting(meeting.meeting_id)
    if (!transcriptData[meeting.meeting_id]) {
      try {
        const data = await getMeetingTranscript(meeting.meeting_id, userId)
        setTranscriptData((prev) => ({
          ...prev,
          [meeting.meeting_id]: data.utterances.map((u) => ({
            text: `[${u.speaker}] ${u.text}${u.translated_text ? ` → ${u.translated_text}` : ''}`,
          })),
        }))
      } catch {
        // ignore
      }
    }
  }

  const handleDeleteMeeting = async (meetingId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await deleteMeeting(meetingId, userId)
      fetchMeetings()
      if (expandedMeeting === meetingId) setExpandedMeeting(null)
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex flex-col h-full bg-[#0f0f0f] text-[#f1f1f1]">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#2e2e2e] flex-shrink-0 bg-[#0f0f0f]/80">
        <Mic size={16} className="text-violet-400" />
        <span className="text-sm font-medium text-[#a0a0a0]">Realtime Transcription</span>
        {isRecording && (
          <span className="ml-2 flex items-center gap-1.5 text-xs text-red-400">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            Recording
          </span>
        )}
      </div>

      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {/* Controls */}
        <div className="px-3 pt-3 pb-2 flex-shrink-0">
          <MeetingControls
            isRecording={isRecording}
            selectedSource={source}
            onSourceChange={setSource}
            onStart={handleStart}
            onStop={handleStop}
            error={error}
            meetingTitle={title}
            onTitleChange={setTitle}
            enableTranslation={enableTranslation}
            onTranslationChange={setEnableTranslation}
          />
        </div>

        {/* Live transcript */}
        {isRecording && (
          <div className="mx-3 mb-2 flex-shrink-0 max-h-60 overflow-y-auto bg-[#131313] rounded-lg border border-[#2e2e2e] p-3">
            <p className="text-xs text-[#555] mb-2 uppercase tracking-wider">Live</p>
            {liveUtterances.map((u, i) => (
              <div key={i} className="mb-1.5">
                <span className={`text-xs font-semibold mr-1.5 ${speakerColor(u.speaker)}`}>
                  {u.speaker}:
                </span>
                <span className="text-sm text-[#e0e0e0]">{u.text}</span>
                {u.translation && (
                  <span className="block text-xs text-[#666] italic ml-0 mt-0.5 pl-2 border-l border-[#333]">
                    {u.translation}
                  </span>
                )}
              </div>
            ))}
            {partialText && (
              <div className="opacity-60">
                <span className="text-xs text-[#555] mr-1.5">...</span>
                <span className="text-sm text-[#bbb]">{partialText}</span>
                {partialTranslation && (
                  <span className="block text-xs text-[#555] italic ml-2">{partialTranslation}</span>
                )}
              </div>
            )}
            <div ref={liveEndRef} />
          </div>
        )}

        {/* Meetings history */}
        <div className="flex-1 min-h-0 flex flex-col border-t border-[#2e2e2e] mx-0">
          <button
            onClick={() => setShowMeetings((v) => !v)}
            className="flex items-center gap-2 w-full px-3 py-2.5 text-left hover:bg-[#1e1e1e] transition-colors flex-shrink-0"
          >
            <FileText size={13} className="text-violet-400 flex-shrink-0" />
            <span className="text-xs font-medium text-[#a0a0a0] uppercase tracking-wider flex-1">
              Meetings {meetings.length > 0 && `(${meetings.length})`}
            </span>
            {isLoadingMeetings ? (
              <span className="text-xs text-[#555]">Loading...</span>
            ) : showMeetings ? (
              <ChevronDown size={12} className="text-[#555]" />
            ) : (
              <ChevronRight size={12} className="text-[#555]" />
            )}
          </button>

          {showMeetings && (
            <div className="flex-1 overflow-y-auto">
              {meetings.length === 0 ? (
                <p className="text-xs text-[#555] px-3 py-2">No meetings recorded yet</p>
              ) : (
                meetings.map((m) => (
                  <div key={m.meeting_id} className="border-b border-[#1e1e1e] last:border-b-0">
                    <div
                      className="flex items-center gap-2 px-3 py-2.5 cursor-pointer hover:bg-[#1a1a1a] transition-colors group"
                      onClick={() => handleLoadTranscript(m)}
                    >
                      {expandedMeeting === m.meeting_id ? (
                        <ChevronDown size={11} className="text-[#555] flex-shrink-0" />
                      ) : (
                        <ChevronRight size={11} className="text-[#555] flex-shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-[#e0e0e0] truncate">{m.title}</p>
                        <p className="text-xs text-[#555]">
                          {formatDuration(m.duration_ms)} · {m.utterance_count} utterances ·{' '}
                          {new Date(m.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <button
                        onClick={(e) => handleDeleteMeeting(m.meeting_id, e)}
                        className="p-1 text-[#444] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all rounded flex-shrink-0"
                        title="Delete meeting"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>

                    {expandedMeeting === m.meeting_id && (
                      <div className="px-3 pb-3 bg-[#0d0d0d]">
                        {transcriptData[m.meeting_id] ? (
                          <div className="max-h-48 overflow-y-auto space-y-1 pt-1">
                            {transcriptData[m.meeting_id].map((u, i) => (
                              <p key={i} className="text-xs text-[#bbb] leading-relaxed">
                                {u.text}
                              </p>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-[#555] py-2">Loading transcript...</p>
                        )}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
