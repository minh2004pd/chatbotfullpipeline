import type { ChatRequest, SSEChunk, Citation } from '@/types'
import { getApiBaseUrl, getUserId } from './client'

export interface StreamChatOptions {
  request: ChatRequest
  onChunk: (content: string) => void
  onCitations: (citations: Citation[]) => void
  onDone: () => void
  onError: (error: string) => void
  signal?: AbortSignal
}

/**
 * Stream chat using SSE via fetch ReadableStream.
 * Format: `data: {"content": "...", "done": false}\n\n`
 */
export async function streamChat({
  request,
  onChunk,
  onCitations,
  onDone,
  onError,
  signal,
}: StreamChatOptions): Promise<void> {
  const url = `${getApiBaseUrl()}/api/v1/chat/stream`

  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': getUserId(),
      },
      body: JSON.stringify(request),
      signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    onError('Failed to connect to server. Please check your connection.')
    return
  }

  if (!response.ok) {
    let message = `Server error: ${response.status}`
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) message = body.detail
    } catch {
      // ignore parse error
    }
    onError(message)
    return
  }

  if (!response.body) {
    onError('No response body from server.')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Process all complete SSE messages in the buffer
      const lines = buffer.split('\n')
      // Keep the last potentially incomplete line in buffer
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed.startsWith('data:')) continue

        const jsonStr = trimmed.slice(5).trim()
        if (!jsonStr) continue

        let chunk: SSEChunk
        try {
          chunk = JSON.parse(jsonStr) as SSEChunk
        } catch {
          continue
        }

        if (chunk.done) {
          if (chunk.citations && chunk.citations.length > 0) {
            onCitations(chunk.citations)
          }
          onDone()
          return
        }

        if (chunk.content) {
          onChunk(chunk.content)
        }

        if (chunk.citations && chunk.citations.length > 0) {
          onCitations(chunk.citations)
        }
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    onError('Stream interrupted unexpectedly.')
  } finally {
    reader.releaseLock()
  }

  // If we exit the loop without a done signal, call onDone anyway
  onDone()
}
