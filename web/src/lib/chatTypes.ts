/**
 * Chat data types shared by the chat display components and the
 * WebSocket hook. Kept in a standalone module so display components
 * can be type-checked without pulling in the WebSocket client.
 */

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool_hint' | 'tool_summary' | 'thinking'
  content: string
  timestamp: Date
  isStreaming?: boolean
  /** Filenames of files that travelled with this turn — rendered as pills. */
  attachmentLabels?: string[]
}

/**
 * Sidebar-visible session metadata. Field names match the props consumed by
 * `Sidebar.tsx` — DO NOT rename without auditing every consumer.
 */
export interface ChatSession {
  id: string
  agentId: string
  title: string       // first user message (or "New Chat")
  updatedAt: string   // ISO timestamp
  messageCount: number
}
