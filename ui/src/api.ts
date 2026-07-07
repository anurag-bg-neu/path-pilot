import type { AdkPart, AdkSseEvent } from './types'

const APP = 'pathpilot'
const UID = 'user'

export async function createSession(): Promise<string> {
  const r = await fetch(`/apps/${APP}/users/${UID}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  if (!r.ok) throw new Error(`Session creation failed: HTTP ${r.status}`)
  const data = await r.json() as { id: string }
  if (!data.id) throw new Error('No session id in response')
  return data.id
}

export async function* streamAgent(
  sessionId: string,
  parts: AdkPart[],
): AsyncGenerator<AdkSseEvent> {
  const r = await fetch('/run_sse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      app_name: APP,
      user_id: UID,
      session_id: sessionId,
      new_message: { role: 'user', parts },
      streaming: false,
    }),
  })

  if (!r.ok) throw new Error(`Agent call failed: HTTP ${r.status}`)
  if (!r.body) throw new Error('No response body')

  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })

      const events = buf.split('\n\n')
      buf = events.pop() ?? ''   // keep incomplete trailing fragment

      for (const raw of events) {
        const line = raw.trim()
        if (!line.startsWith('data:')) continue
        const json = line.slice(5).trim()
        if (!json || json === '[DONE]') continue
        try {
          yield JSON.parse(json) as AdkSseEvent
        } catch {
          // malformed JSON, skip
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export function mimeType(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() ?? ''
  const map: Record<string, string> = {
    pdf:  'application/pdf',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    txt:  'text/plain',
  }
  return map[ext] ?? 'application/octet-stream'
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload  = () => resolve((reader.result as string).split(',')[1])
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}
