import { useEffect, useRef, useState, useCallback, KeyboardEvent, useMemo } from 'react'
import { marked } from 'marked'
import type { ChatMessage, AdkPart, SavedSession } from './types'
import { createSession, streamAgent, mimeType, fileToBase64 } from './api'

marked.setOptions({ breaks: true, gfm: true })

function renderMd(text: string): string {
  return marked.parse(text) as string
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function uid(): string {
  return Math.random().toString(36).slice(2)
}

const LS_KEY = 'pp_history'
const MAX_SESSIONS = 25

function fmtDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
    ' · ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function loadHistory(): SavedSession[] {
  try { return JSON.parse(localStorage.getItem(LS_KEY) ?? '[]') }
  catch { return [] }
}

type QuickReplySet = { options: { label: string; value: string }[] } | null

function detectQuickReplies(text: string): QuickReplySet {
  if (/would you like me to prioritize.*faang/i.test(text)) {
    return {
      options: [
        { label: '✅ Yes, Tier 1 tech companies only', value: 'yes' },
        { label: '🌐 No, show all companies',          value: 'no'  },
      ],
    }
  }
  return null
}

interface ExtractedTable {
  headers: string[]
  rows: string[][]
  preMd: string
  postMd: string
}

function extractTableFromMd(md: string): ExtractedTable | null {
  const lines = md.replace(/\r\n/g, '\n').split('\n')

  // Find first line that starts with |
  let tableStart = -1
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim().startsWith('|')) { tableStart = i; break }
  }
  if (tableStart === -1) return null

  // Extend to last consecutive | line
  let tableEnd = tableStart
  for (let i = tableStart + 1; i < lines.length; i++) {
    if (lines[i].trim().startsWith('|')) tableEnd = i
    else break
  }

  // Need at least: header + separator + 1 data row
  if (tableEnd < tableStart + 2) return null

  const parseRow = (line: string): string[] =>
    line.split('|').slice(1, -1).map(c => c.trim())

  const tableLines = lines.slice(tableStart, tableEnd + 1)
  const headers = parseRow(tableLines[0])
  // tableLines[1] is the separator (---|---...), skip it
  const rows = tableLines.slice(2).map(parseRow).filter(r => r.some(c => c !== ''))

  if (rows.length === 0) return null

  return {
    headers,
    rows,
    preMd: lines.slice(0, tableStart).join('\n').trim(),
    postMd: lines.slice(tableEnd + 1).join('\n').trim(),
  }
}

// ── Animated loading indicator ──────────────────────────────────────────────
const SEARCH_MSGS = [
  { icon: '🔍', text: 'Searching online…'   },
  { icon: '🌐', text: 'Parsing the web…'    },
  { icon: '📝', text: 'Filtering response…' },
  { icon: '🎯', text: 'Curating results…'   },
  { icon: '📊', text: 'Ranking data…'       },
  { icon: '⚡', text: 'Almost there…'       },
]

const THINK_MSGS = [
  { icon: '🧠', text: 'Thinking…'             },
  { icon: '✍️', text: 'Composing response…'   },
  { icon: '🔎', text: 'Reviewing results…'    },
  { icon: '📝', text: 'Drafting answer…'      },
  { icon: '⚡', text: 'Almost ready…'         },
]

function TypingIndicator({ lastUserMsg }: { lastUserMsg: string }) {
  const msgs = useMemo(() => {
    return /job|role|internship|position|engineer|swe|find|search|look/i.test(lastUserMsg)
      ? SEARCH_MSGS
      : THINK_MSGS
  }, [lastUserMsg])

  const [idx, setIdx] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setIdx(i => (i + 1) % msgs.length), 2200)
    return () => clearInterval(t)
  }, [msgs])

  const { icon, text } = msgs[idx]

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 2px', minWidth: 230, whiteSpace: 'nowrap' }}>
      <span key={`i${idx}`} style={{ fontSize: 22, display: 'inline-block' }} className="ti-icon">{icon}</span>
      <span key={`t${idx}`} style={{ fontSize: 13, fontWeight: 600, color: '#a78bfa' }} className="ti-text">{text}</span>
      <span style={{ color: '#6c8bff', fontSize: 18, animationDelay: '0s'   }} className="ti-dot">•</span>
      <span style={{ color: '#6c8bff', fontSize: 18, animationDelay: '0.3s' }} className="ti-dot">•</span>
      <span style={{ color: '#6c8bff', fontSize: 18, animationDelay: '0.6s' }} className="ti-dot">•</span>
    </div>
  )
}

// ── Client-side carousel ────────────────────────────────────────────────────
const PAGE_SIZE = 10

interface TableCarouselProps {
  msgId: string
  data: { headers: string[]; rows: string[][] }
  preMd: string
  postMd: string
  pageMap: Map<string, number>
  setPageMap: (updater: (prev: Map<string, number>) => Map<string, number>) => void
}

function TableCarousel({ msgId, data, preMd, postMd, pageMap, setPageMap }: TableCarouselProps) {
  const page = pageMap.get(msgId) ?? 1
  const totalPages = Math.ceil(data.rows.length / PAGE_SIZE)
  const start = (page - 1) * PAGE_SIZE
  const visibleRows = data.rows.slice(start, start + PAGE_SIZE)

  const goTo = (newPage: number) => {
    setPageMap(m => new Map(m).set(msgId, newPage))
  }

  return (
    <div className="table-carousel">
      {preMd && <div className="md-content" dangerouslySetInnerHTML={{ __html: renderMd(preMd) }} />}
      <div className="table-scroll">
        <table className="carousel-table">
          <thead>
            <tr>
              {data.headers.map((h, i) => (
                <th key={i} dangerouslySetInnerHTML={{ __html: h }} />
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => (
                  <td key={ci} dangerouslySetInnerHTML={{ __html: cell }} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {postMd && <div className="md-content" dangerouslySetInnerHTML={{ __html: renderMd(postMd) }} />}
      {totalPages > 1 && (
        <div className="carousel-nav">
          <button className="btn" disabled={page === 1} onClick={() => goTo(page - 1)}>◀ Prev</button>
          <span className="carousel-page-info">Page {page} of {totalPages} · {data.rows.length} results</span>
          <button className="btn primary" disabled={page === totalPages} onClick={() => goTo(page + 1)}>Next ▶</button>
        </div>
      )}
    </div>
  )
}

const HINTS = [
  '🔍 Find SWE internships or entry-level roles',
  '⭐ Find early career SDE roles in New York',
  '📍 Find mid level SDE roles in California',
  '🎓 Find scholarships for grad students',
  '📄 Upload resume for eligible matches',
  '✉️ Draft a cover letter for a role',
]

export default function App() {
  const [sessionId, setSessionId]       = useState<string | null>(null)
  const [connected, setConnected]       = useState(false)
  const [messages, setMessages]         = useState<ChatMessage[]>([])
  const [input, setInput]               = useState('')
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState<string | null>(null)
  const [pendingFile, setPendingFile]   = useState<File | null>(null)
  const [quickReplies, setQuickReplies] = useState<QuickReplySet>(null)
  const [lastUserMsg, setLastUserMsg]   = useState('')
  const [pageMap, setPageMap]           = useState<Map<string, number>>(new Map())

  // ── Session history ────────────────────────────────────────────────────────
  const [history, setHistory]               = useState<SavedSession[]>(loadHistory)
  const [historyOpen, setHistoryOpen]       = useState(false)
  const [viewingSession, setViewingSession] = useState<SavedSession | null>(null)
  const [leaveNotice, setLeaveNotice]       = useState(false)
  const leaveNoticeShown                    = useRef(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef   = useRef<HTMLInputElement>(null)
  const textareaRef    = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, quickReplies])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const id = await createSession()
        if (!cancelled) { setSessionId(id); setConnected(true) }
      } catch (e) {
        if (!cancelled) setError(`Cannot connect to PathPilot backend: ${(e as Error).message}`)
      }
    })()
    return () => { cancelled = true }
  }, [])

  // ── Persist session to localStorage ────────────────────────────────────────
  const saveSession = useCallback((msgs: ChatMessage[]) => {
    if (!sessionId || msgs.length === 0) return
    const firstUser = msgs.find(m => m.role === 'user')
    const title = (firstUser?.rawText ?? firstUser?.html ?? 'Chat session').slice(0, 80)
    const entry: SavedSession = { id: sessionId, savedAt: new Date().toISOString(), title, messages: msgs }
    setHistory(prev => {
      const next = [entry, ...prev.filter(s => s.id !== sessionId)].slice(0, MAX_SESSIONS)
      localStorage.setItem(LS_KEY, JSON.stringify(next))
      return next
    })
  }, [sessionId])

  useEffect(() => {
    if (messages.length === 0) return
    const t = setTimeout(() => saveSession(messages), 1000)
    return () => clearTimeout(t)
  }, [messages, saveSession])

  useEffect(() => {
    const onUnload = (e: BeforeUnloadEvent) => {
      if (messages.length === 0) return
      saveSession(messages)
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [messages, saveSession])

  useEffect(() => {
    if (!leaveNoticeShown.current && messages.some(m => m.role === 'agent' && !m.isTyping && m.html)) {
      leaveNoticeShown.current = true
      setLeaveNotice(true)
    }
  }, [messages])

  // ── Send ───────────────────────────────────────────────────────────────────
  const send = useCallback(async (text: string, file?: File) => {
    if (!sessionId || loading) return
    const trimmed = text.trim()
    if (!trimmed && !file) return

    setError(null)
    setLoading(true)
    setQuickReplies(null)
    if (trimmed.length > 5 && !/^(yes|no|more|next|prev|show more|sure|ok)$/i.test(trimmed)) {
      setLastUserMsg(trimmed)
    }

    const userMsg: ChatMessage = {
      id: uid(), role: 'user', html: escapeHtml(trimmed), fileName: file?.name,
    }
    setMessages(prev => [...prev, userMsg])

    const parts: AdkPart[] = []
    if (file) {
      const data = await fileToBase64(file)
      parts.push({ inline_data: { mime_type: mimeType(file.name), data } })
    }
    if (trimmed) parts.push({ text: trimmed })
    if (parts.length === 0) parts.push({ text: '' })

    const typingId = uid()
    setMessages(prev => [...prev, { id: typingId, role: 'agent', html: '', isTyping: true }])

    let agentText = ''
    let replaceTyping = true

    try {
      for await (const event of streamAgent(sessionId, parts)) {
        if (event.error) { setError(event.error); break }
        if (!event.content) continue
        // resume_parser output is internal (PII-free profile) — never show it to the user
        if (event.author === 'resume_parser') continue
        for (const part of event.content.parts) {
          if (part.text) agentText += part.text
        }
        // Only update the bubble when we have real text — function_call events
        // arrive with content but no text parts and must not collapse the typing indicator
        if (agentText) {
          const html = renderMd(agentText)
          setMessages(prev => prev.map(m =>
            m.id === typingId ? { ...m, html, isTyping: false, rawText: agentText } : m
          ))
          replaceTyping = false
        }
      }
    } catch (e) {
      setError(`Stream error: ${(e as Error).message}`)
    } finally {
      if (replaceTyping) setMessages(prev => prev.filter(m => m.id !== typingId))
      if (agentText) {
        setQuickReplies(detectQuickReplies(agentText))
        // Parse table for client-side carousel (runs once after stream completes)
        const extracted = extractTableFromMd(agentText)
        if (extracted) {
          setMessages(prev => prev.map(m =>
            m.id === typingId
              ? { ...m, tableData: { headers: extracted.headers, rows: extracted.rows }, preMd: extracted.preMd, postMd: extracted.postMd }
              : m
          ))
        }
      }
      setLoading(false)
    }
  }, [sessionId, loading])

  const handleSend = useCallback(() => {
    if (!input.trim() && !pendingFile) return
    const file = pendingFile ?? undefined
    setPendingFile(null)
    setInput('')
    send(input, file)
  }, [input, pendingFile, send])

  const triggerSend = useCallback((text: string) => {
    send(text)
  }, [send])

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }, [handleSend])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) setPendingFile(file)
    e.target.value = ''
  }, [])

  const handleHint = useCallback((hint: string) => {
    setInput(hint.replace(/^[\p{Emoji}\s]+/u, '').trim())
    textareaRef.current?.focus()
  }, [])

  const autoResize = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 140) + 'px'
  }, [])

  const deleteSession = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setHistory(prev => {
      const next = prev.filter(s => s.id !== id)
      localStorage.setItem(LS_KEY, JSON.stringify(next))
      return next
    })
    if (viewingSession?.id === id) setViewingSession(null)
  }, [viewingSession])

  const canSend = !loading && connected && (!!input.trim() || !!pendingFile)

  return (
    <div className="app">
      <header className="header">
        <span className="header-logo">✈</span>
        <div>
          <div className="header-title">PathPilot</div>
          <div className="header-sub">Career Jobs &amp; Scholarship Assistant</div>
        </div>
        <div className={`status-dot ${connected ? 'connected' : ''}`} />
        <span className="status-label">{connected ? 'Connected' : 'Disconnected'}</span>
        <button
          className="history-btn"
          title="Chat history"
          onClick={() => setHistoryOpen(o => !o)}
        >
          🕐 {history.length > 0 && <span className="history-badge">{history.length}</span>}
        </button>
      </header>

      {leaveNotice && !viewingSession && (
        <div className="leave-notice">
          <span>💾 After leaving this page you can still revisit this conversation, but you won't be able to continue it. It's saved automatically.</span>
          <button onClick={() => setLeaveNotice(false)}>✕</button>
        </div>
      )}

      {viewingSession && (
        <div className="readonly-bar">
          <span>📖 Viewing past session — <strong>read only</strong></span>
          <button className="btn" style={{ padding: '3px 12px', fontSize: 12 }} onClick={() => setViewingSession(null)}>
            ← Back to current chat
          </button>
        </div>
      )}

      <main className="messages">
        {(viewingSession?.messages ?? messages).length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🚀</div>
            <div className="empty-title">Welcome to PathPilot</div>
            <div className="empty-sub">
              Your multi-agent assistant for job searching, scholarships, and application drafts.
            </div>
            <div className="hint-chips">
              {HINTS.map(h => (
                <div key={h} className="hint-chip" onClick={() => handleHint(h)}>{h}</div>
              ))}
            </div>
          </div>
        ) : (
          (viewingSession?.messages ?? messages).map(msg => (
            <div key={msg.id} className={`msg ${msg.role}`}>
              <div className="msg-label">{msg.role === 'user' ? 'You' : 'PathPilot'}</div>
              {msg.fileName && <span className="msg-filename">📎 {msg.fileName}</span>}
              <div
                className="msg-bubble"
                style={msg.isTyping ? {
                  minWidth: '280px',
                  background: 'linear-gradient(135deg, rgba(108,139,255,0.09) 0%, rgba(167,139,250,0.07) 100%)',
                  borderColor: 'rgba(108,139,255,0.35)',
                } : undefined}
              >
                {msg.isTyping ? (
                  <TypingIndicator lastUserMsg={lastUserMsg} />
                ) : msg.role === 'agent' ? (
                  msg.tableData
                    ? <TableCarousel msgId={msg.id} data={msg.tableData} preMd={msg.preMd ?? ''} postMd={msg.postMd ?? ''} pageMap={pageMap} setPageMap={setPageMap} />
                    : <div className="md-content" dangerouslySetInnerHTML={{ __html: msg.html }} />
                ) : (
                  <span style={{ whiteSpace: 'pre-wrap' }}>{msg.html}</span>
                )}
              </div>
            </div>
          ))
        )}

        {quickReplies && !loading && (
          <div className="quick-replies">
            {quickReplies.options.map(opt => (
              <button key={opt.value} className="quick-reply-btn" onClick={() => triggerSend(opt.value)}>
                {opt.label}
              </button>
            ))}
          </div>
        )}

        <div ref={messagesEndRef} />
      </main>

      {error && (
        <div className="error-banner">
          ⚠️ {error}
          <button className="btn" style={{ marginLeft: 'auto', padding: '2px 10px', fontSize: 12 }} onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {viewingSession ? (
        <div className="input-bar" style={{ justifyContent: 'center', opacity: 0.6 }}>
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            📖 This is a read-only session — start a new chat to continue
          </span>
        </div>
      ) : (
        <div className="input-bar">
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt" style={{ display: 'none' }} onChange={handleFileChange} />
          <button className={`file-btn ${pendingFile ? 'file-badge' : ''}`} title="Attach resume" onClick={() => fileInputRef.current?.click()}>
            📎
          </button>
          <div className="input-wrap">
            {pendingFile && (
              <div className="file-chip">
                📄 {pendingFile.name}
                <span className="file-chip-remove" onClick={() => setPendingFile(null)}>✕</span>
              </div>
            )}
            <textarea
              ref={textareaRef}
              value={input}
              placeholder={connected ? 'Ask about jobs, scholarships, or upload your resume…' : 'Connecting to backend…'}
              disabled={!connected || loading}
              onChange={autoResize}
              onKeyDown={handleKeyDown}
              rows={1}
            />
          </div>
          <button className="send-btn" disabled={!canSend} title="Send (Enter)" onClick={handleSend}>➤</button>
        </div>
      )}

      {historyOpen && (
        <div className="history-overlay" onClick={() => setHistoryOpen(false)}>
          <div className="history-panel" onClick={e => e.stopPropagation()}>
            <div className="history-header">
              <span>🕐 Chat History</span>
              <button onClick={() => setHistoryOpen(false)}>✕</button>
            </div>
            {history.length === 0 ? (
              <div className="history-empty">No saved sessions yet.<br/>Conversations are saved automatically after each reply.</div>
            ) : (
              <div className="history-list">
                {history.map(s => (
                  <div
                    key={s.id}
                    className={`session-card ${viewingSession?.id === s.id ? 'active' : ''}`}
                    onClick={() => { setViewingSession(s); setHistoryOpen(false) }}
                  >
                    <div className="session-card-body">
                      <div className="session-title">{s.title}</div>
                      <div className="session-meta">{fmtDate(s.savedAt)} · {s.messages.length} messages</div>
                    </div>
                    <button
                      className="session-delete"
                      title="Delete session"
                      onClick={e => deleteSession(s.id, e)}
                    >✕</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
