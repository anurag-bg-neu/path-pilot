export type Role = 'user' | 'agent'

export interface ChatMessage {
  id: string
  role: Role
  html: string        // rendered markdown/HTML for agent; escaped text for user
  rawText?: string    // original text (used for pagination detection)
  fileName?: string   // attached file name (user messages)
  isTyping?: boolean
}

export interface PaginationState {
  visible: boolean
  current: number
  total: number
  hasNext: boolean
  hasPrev: boolean
}

export interface SavedSession {
  id: string
  savedAt: string      // ISO timestamp
  title: string        // first user message (truncated)
  messages: ChatMessage[]
}

// ADK API shapes
export interface AdkPart {
  text?: string
  inline_data?: { mime_type: string; data: string }
}

export interface AdkContent {
  role: string
  parts: AdkPart[]
}

export interface AdkSseEvent {
  content?: AdkContent
  author?: string
  turn_complete?: boolean
  error?: string
}
