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
  /** Optional structured A2 analysis or recommendation result. */
  result?: ChatResult
}

export interface ResultMetric {
  label: string
  value: string
  detail?: string
}

export interface ResultAction {
  priority: 'P0' | 'P1' | 'P2'
  action: string
}

export type ChatResult =
  | {
      kind: 'metrics'
      title: string
      metrics: ResultMetric[]
      summary?: string
    }
  | {
      kind: 'action_plan'
      title: string
      actions: ResultAction[]
      summary?: string
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
