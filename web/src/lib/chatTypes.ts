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
  /** Structured retrieval evidence rendered independently of model prose. */
  citations?: RetrievalCitation[]
}

interface RetrievalCitationBase {
  citation_id: string
  tool: string
  file_name: string
  content_excerpt: string
  knowledge_base?: string
  chunk_id?: string
  chunk_index?: number
  section_title?: string
  source_path?: string
  page_range?: number[]
  heading_path?: string[]
  line_range?: number[]
  token_count?: number
}

export type RetrievalCitation =
  | (RetrievalCitationBase & {
      mode: 'keyword'
      keyword: {
        query_terms: string[]
        matched_terms: string[]
        match_locations: Array<{ term: string; start: number; end: number }>
      }
    })
  | (RetrievalCitationBase & {
      mode: 'vector'
      vector: {
        rank: number
        distance: number
        similarity: number
        embedding_model?: string
      }
    })

export type RetrievalMode = 'keyword' | 'vector'

export interface ResultMetric {
  label: string
  value: string
  detail?: string
}

export interface ResultAction {
  priority: 'P0' | 'P1' | 'P2'
  action: string
  /** Recommendation fields sent with the coursework follow-up ranking. */
  rank?: number
  candidate_id?: string
  timing?: string
  priority_score?: number
  score_components?: Record<string, unknown>
  evidence?: Record<string, unknown>
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
      /** Provenance of a backend recommendation; shown so the snapshot date is visible. */
      source?: string
      scenario_id?: string
      as_of_date?: string
      tool_call_id?: string
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
