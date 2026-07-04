import { useEffect, useRef, useState, useCallback, KeyboardEvent, useMemo } from 'react'
import { marked } from 'marked'
import type { ChatMessage, PaginationState, AdkPart, SavedSession } from './types'
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

function detectPagination(text: string): Partial<PaginationState> | null {
  const m = text.match(/page\s+(\d+)\s+of\s+(\d+)/i)
  if (!m) return null
  const current = parseInt(m[1], 10)
  const total   = parseInt(m[2], 10)
  return { visible: true, current, total, hasPrev: current > 1, hasNext: current < total }
}

type QuickReplySet = { options: { label: string; value: string }[] } | null

function detectQuickReplies(text: string): QuickReplySet {
  if (/would you like me to prioritize.*faang/i.test(text)) {
    return {
      options: [
        { label: '✅ Yes, FAANG / Big Tech only', value: 'yes' },
        { label: '🌐 No, show all companies',     value: 'no'  },
      ],
    }
  }
  return null
}

// ── Animated loading indicator ──────────────────────────────────────────────
const SEARCH_MSGS = [
  { icon: '🔍', text: 'Searching LinkedIn…'               },
  { icon: '📋', text: 'Scanning Indeed listings…'         },
  { icon: '🏢', text: 'Checking Glassdoor & ZipRecruiter…' },
  { icon: '🌐', text: 'Filtering F-1 eligible roles…'     },
  { icon: '✨', text: 'Curating top matches…'             },
  { icon: '📊', text: 'Ranking results…'                  },
  { icon: '🎯', text: 'Almost there…'                     },
]

const THINK_MSGS = [
  { icon: '🧠', text: 'Thinking…'               },
  { icon: '✍️',  text: 'Composing response…'     },
  { icon: '🔎', text: 'Reviewing your profile…' },
  { icon: '📝', text: 'Drafting answer…'         },
  { icon: '⚡', text: 'Almost ready…'           },
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

  // Inline styles guarantee visibility regardless of external CSS state
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

const HINTS = [
  '🔍 Find SWE internships for F-1 students',
  '📍 Find mid level SDE roles in California',
  '🎓 Find scholarships for grad students',
  '📄 Upload resume for eligible matches',
  '✉️  Draft a cover letter for a role',
]

export default function App() {
  const [sessionId, setSessionId]           = useState<string | null>(null)
  const [connected, setConnected]           = useState(false)
  const [messages, setMessages]             = useState<ChatMessage[]>([])
  const [input, setInput]                   = useState('')
  const [loading, setLoading]               = useState(false)
  const [error, setError]                   = useState<string | null>(null)
  const [pendingFile, setPendingFile]       = useState<File | null>(null)
  const [quickReplies, setQuickReplies]     = useState<QuickReplySet>(null)
  const [lastUserMsg, setLastUserMsg]       = useState('')
  const [pagination, setPagination]         = useState<PaginationState>({
    visible: false, current: 1, total: 1, hasNext: false, hasPrev: false,
  })
  // ID of the message bubble that owns the current paginated results table
  const [resultsMessageId, setResultsMessageId] = useState<string | null>(null)
  // While navigating pages, show a shimmer on the results bubble instead of a spinner
  const [isNavigating, setIsNavigating]     = useState(false)

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

  // Auto-save 1 s after messages settle (debounced to avoid mid-stream saves)
  useEffect(() => {
    if (messages.length === 0) return
    const t = setTimeout(() => saveSession(messages), 1000)
    return () => clearTimeout(t)
  }, [messages, saveSession])

  // Save immediately on page unload and show browser's leave confirmation
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

  // Show leave-notice banner once after the first assistant reply arrives
  useEffect(() => {
    if (!leaveNoticeShown.current && messages.some(m => m.role === 'agent' && !m.isTyping && m.html)) {
      leaveNoticeShown.current = true
      setLeaveNotice(true)
    }
  }, [messages])

  // ── Normal send (adds a user bubble + a new agent bubble) ──────────────────
  const send = useCallback(async (text: string, file?: File) => {
    if (!sessionId || loading) return
    const trimmed = text.trim()
    if (!trimmed && !file) return

    setError(null)
    setLoading(true)
    setQuickReplies(null)
    // Preserve job-search intent across short replies (yes / no / ok)
    if (trimmed.length > 5 && !/^(yes|no|more|next|prev|show more|sure|ok)$/i.test(trimmed)) {
      setLastUserMsg(trimmed)
      setResultsMessageId(null)  // new search → reset carousel
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
        // resume_parser output is an internal PII-free profile — never show it to the user.
        // eligibility (and every other agent) renders normally.
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
          const pg = detectPagination(agentText)
          if (pg) setPagination(prev => ({ ...prev, ...pg, visible: true }))
        }
      }
    } catch (e) {
      setError(`Stream error: ${(e as Error).message}`)
    } finally {
      if (replaceTyping) setMessages(prev => prev.filter(m => m.id !== typingId))
      if (agentText) setQuickReplies(detectQuickReplies(agentText))
      // Register this bubble as the carousel target if it contains paginated results
      if (detectPagination(agentText)) setResultsMessageId(typingId)
      setLoading(false)
    }
  }, [sessionId, loading])

  // ── Navigate pages — no new bubbles, update results message in-place ───────
  const navigatePage = useCallback(async (cmd: 'show more' | 'prev') => {
    if (!sessionId || loading || !resultsMessageId) return

    setError(null)
    setLoading(true)
    setIsNavigating(true)

    const parts: AdkPart[] = [{ text: cmd }]
    let agentText = ''

    try {
      for await (const event of streamAgent(sessionId, parts)) {
        if (event.error) { setError(event.error); break }
        if (!event.content) continue
        for (const part of event.content.parts) {
          if (part.text) agentText += part.text
        }
        // Stream new content directly into the existing results bubble
        const html = renderMd(agentText)
        setMessages(prev => prev.map(m =>
          m.id === resultsMessageId ? { ...m, html, rawText: agentText } : m
        ))
      }
    } catch (e) {
      setError(`Stream error: ${(e as Error).message}`)
    } finally {
      setIsNavigating(false)
      setLoading(false)
      const pg = detectPagination(agentText)
      if (pg) {
        setPagination(prev => ({ ...prev, ...pg, visible: true }))
      } else if (/All \*\*\d+\*\* results shown/i.test(agentText)) {
        setPagination(prev => ({ ...prev, hasNext: false }))
      }
    }
  }, [sessionId, loading, resultsMessageId])

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

  const canSend = !loading && connected && (!!input.trim() || !!pendingFile)

  return (
    <div className="app">
      <header className="header">
        <span className="header-logo">✈</span>
        <div>
          <div className="header-title">PathPilot</div>
          <div className="header-sub">F-1 Career &amp; Scholarship Assistant</div>
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

      {/* ── Leave notice — shown once after first reply ── */}
      {leaveNotice && !viewingSession && (
        <div className="leave-notice">
          <span>💾 After leaving this page you can still read this conversation, but you won't be able to continue it. It's saved automatically.</span>
          <button onClick={() => setLeaveNotice(false)}>✕</button>
        </div>
      )}

      {/* ── Read-only bar — shown when browsing history ── */}
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
            <div className="empty-icon">🧭</div>
            <div className="empty-title">Welcome to PathPilot</div>
            <div className="empty-sub">
              Your privacy-first assistant for F-1 job searches, scholarships, and application drafts.
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
                className={`msg-bubble ${isNavigating && msg.id === resultsMessageId ? 'carousel-updating' : ''}`}
                style={msg.isTyping ? {
                  minWidth: '280px',
                  background: 'linear-gradient(135deg, rgba(108,139,255,0.09) 0%, rgba(167,139,250,0.07) 100%)',
                  borderColor: 'rgba(108,139,255,0.35)',
                } : undefined}
              >
                {msg.isTyping ? (
                  <TypingIndicator lastUserMsg={lastUserMsg} />
                ) : msg.role === 'agent' ? (
                  <div className="md-content" dangerouslySetInnerHTML={{ __html: msg.html }} />
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

      {/* ── Carousel pagination bar — navigates in-place ── */}
      {pagination.visible && (
        <div className="pagination-bar">
          <button
            className="btn"
            disabled={!pagination.hasPrev || loading}
            onClick={() => navigatePage('prev')}
          >
            ◀ Previous
          </button>
          <span className="page-info">
            {isNavigating
              ? <span className="page-updating">Updating…</span>
              : <>Page {pagination.current} of {pagination.total}</>
            }
          </span>
          <button
            className="btn primary"
            disabled={!pagination.hasNext || loading}
            onClick={() => navigatePage('show more')}
          >
            Next ▶
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

      {/* ── History side panel ── */}
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
                    <div className="session-title">{s.title}</div>
                    <div className="session-meta">{fmtDate(s.savedAt)} · {s.messages.length} messages</div>
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
