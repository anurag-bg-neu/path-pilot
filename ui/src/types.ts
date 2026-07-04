export type Role = 'user' | 'agent'

export interface ChatMessage {
  id: string
  role: Role
  html: string        // rendered markdown/HTML for agent; escaped text for user
  rawText?: string    // original markdown text before rendering
  fileName?: string   // attached file name (user messages)
  isTyping?: boolean
  tableData?: {
    headers: string[]
    rows: string[][]
  }
  preMd?: string      // markdown before the table (heading, description)
  postMd?: string     // markdown after the table (source footer)
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
