'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { API_CONFIG, RECONNECT } from '@/config'
import type { ChatMessage, ChatSession } from './chatTypes'

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

// Re-exported so existing `@/lib/useWebSocket` imports keep working.
export type { ChatMessage, ChatSession }

/**
 * Server-side wire format for a session — what `/api/chat-sessions` returns.
 * We normalise this into `ChatSession` for the UI.
 */
interface ServerChatSession {
  id: string
  agent_id?: string
  agentId?: string
  title?: string | null
  updated_at?: string | null
  updatedAt?: string | null
  message_count?: number | null
  messageCount?: number | null
}

interface PersistedMessageDTO {
  id?: string
  role?: string
  content?: string
  timestamp?: string | number | Date
  attachment_labels?: string[]
  attachmentLabels?: string[]
  metadata?: Record<string, unknown> | null
}

interface InboundWsEvent {
  type: string
  content?: string
  session_id?: string
  turn_id?: string
  /** Server may echo back per-event metadata used for tool/thinking dedup. */
  metadata?: Record<string, unknown> | null
}

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

// ─────────────────────────────────────────────────────────────────────────────
// URL + auth helpers
// ─────────────────────────────────────────────────────────────────────────────

// WebSocket URL derivation:
//  - NEXT_PUBLIC_WS_URL overrides everything (full ws:// or wss:// URL).
//  - Otherwise use the current page origin: wss:// on HTTPS pages, ws:// on
//    HTTP pages, no explicit port. The Next.js production server proxies
//    `/ws/*` to the backend, so the reverse proxy in front only has to
//    forward WebSocket upgrade headers to the Next.js process.
//  - In Turbopack dev (where WS is not proxied), set NEXT_PUBLIC_WS_URL
//    explicitly (e.g. `ws://localhost:8000/ws/chat`).
function getWsUrl(): string {
  if (typeof window === 'undefined') return `ws://localhost:8000${API_CONFIG.WS_PATH}`
  if (process.env.NEXT_PUBLIC_WS_URL) return process.env.NEXT_PUBLIC_WS_URL
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}${API_CONFIG.WS_PATH}`
}

const WS_URL = getWsUrl()

function getApiBase(): string {
  // Same convention as @/config: empty string in browser → same-origin relative
  // URLs that Next.js proxies to the backend.
  return API_CONFIG.BASE_URL || ''
}

function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return localStorage.getItem('admin_access_token')
  } catch {
    return null
  }
}

function authHeaders(token: string | null): Record<string, string> {
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

function loadAgentId(): string {
  try {
    const raw = localStorage.getItem('ic_user')
    if (raw) {
      const user = JSON.parse(raw)
      if (user?.username) return String(user.username)
    }
  } catch { /* */ }
  return ''
}

/**
 * Map a server-side persisted message (with optional metadata) into the
 * existing role-based ChatMessage model. Roles outside of the existing
 * union are coerced into the closest equivalent, so the UI never sees a
 * shape it can't render.
 */
function dtoToChatMessage(dto: PersistedMessageDTO): ChatMessage {
  const rawRole = (dto.role || 'assistant').toLowerCase()
  // Allow direct passthrough for known roles; otherwise pick the best fit
  // based on metadata.kind hints stored by the server.
  let role: ChatMessage['role']
  switch (rawRole) {
    case 'user':
    case 'assistant':
    case 'tool_hint':
    case 'tool_summary':
    case 'thinking':
      role = rawRole as ChatMessage['role']
      break
    case 'system':
      // Surface as assistant (the UI does not render a "system" role)
      role = 'assistant'
      break
    default: {
      const kind = (dto.metadata && (dto.metadata as { kind?: string }).kind) || ''
      if (kind === 'tool_hint' || kind === 'tool_summary' || kind === 'thinking') {
        role = kind as ChatMessage['role']
      } else {
        role = 'assistant'
      }
    }
  }

  const ts = dto.timestamp
  const timestamp =
    ts instanceof Date ? ts
      : typeof ts === 'string' || typeof ts === 'number' ? new Date(ts)
        : new Date()

  return {
    id: dto.id || uuidv4(),
    role,
    content: dto.content || '',
    timestamp,
    attachmentLabels:
      dto.attachmentLabels ??
      dto.attachment_labels ??
      (Array.isArray((dto.metadata as { attachment_labels?: string[] } | null | undefined)?.attachment_labels)
        ? (dto.metadata as { attachment_labels?: string[] }).attachment_labels
        : undefined),
  }
}

function normaliseServerSession(s: ServerChatSession, fallbackAgentId: string): ChatSession {
  return {
    id: s.id,
    agentId: s.agent_id ?? s.agentId ?? fallbackAgentId,
    title: (s.title ?? '').toString().slice(0, 80) || 'New Chat',
    updatedAt: s.updated_at ?? s.updatedAt ?? new Date().toISOString(),
    messageCount: s.message_count ?? s.messageCount ?? 0,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────────────────────────

export function useInsuranceChat() {
  // Per-session message buckets. `messages` (exposed) is a slice for the active session.
  const [messagesBySession, setMessagesBySession] = useState<Record<string, ChatMessage[]>>({})
  const [typingSessions, setTypingSessions] = useState<Set<string>>(new Set())
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [agentId, setAgentIdState] = useState('')
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string>(() => uuidv4())

  // Hydrate agent id from localStorage after mount (avoids SSR mismatch)
  useEffect(() => {
    const stored = loadAgentId()
    if (stored) setAgentIdState(stored)
  }, [])

  // ── Refs ────────────────────────────────────────────────────────────────────
  const wsRef = useRef<WebSocket | null>(null)
  const sessionIdRef = useRef<string>(activeSessionId)
  const agentIdRef = useRef<string>('')
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const MAX_RECONNECT_ATTEMPTS = RECONNECT.MAX_ATTEMPTS

  // turn_id → session_id routing table. Entries are kept until the response
  // event arrives, then cleared, so the map stays small.
  const turnSessionRef = useRef<Map<string, string>>(new Map())
  // Sessions already hydrated from the server — skip re-fetching on switch.
  const hydratedSessionsRef = useRef<Set<string>>(new Set())

  const connectRef = useRef<() => void>(() => {})

  // Keep refs in sync with state so handlers always see the latest value
  // without re-binding the WS .onmessage closure.
  useEffect(() => { sessionIdRef.current = activeSessionId }, [activeSessionId])
  useEffect(() => { agentIdRef.current = agentId }, [agentId])

  // ── Helpers that operate on the per-session buckets ─────────────────────────
  const updateSessionMessages = useCallback(
    (sessionId: string, updater: (prev: ChatMessage[]) => ChatMessage[]) => {
      setMessagesBySession((all) => {
        const prev = all[sessionId] ?? []
        const next = updater(prev)
        if (next === prev) return all
        return { ...all, [sessionId]: next }
      })
    },
    [],
  )

  const setTypingForSession = useCallback((sessionId: string, typing: boolean) => {
    setTypingSessions((prev) => {
      const hadIt = prev.has(sessionId)
      if (typing && hadIt) return prev
      if (!typing && !hadIt) return prev
      const next = new Set(prev)
      if (typing) next.add(sessionId)
      else next.delete(sessionId)
      return next
    })
  }, [])

  // ── Server session list ─────────────────────────────────────────────────────
  const refreshChatSessions = useCallback(async () => {
    const token = getAuthToken()
    if (!token) {
      setChatSessions([])
      return
    }
    try {
      const res = await fetch(`${getApiBase()}/api/chat-sessions`, {
        headers: authHeaders(token),
      })
      if (!res.ok) return
      const body: unknown = await res.json().catch(() => null)
      // Tolerate either a raw array or the project's `{ ok, data }` envelope.
      let rawList: ServerChatSession[] = []
      if (Array.isArray(body)) {
        rawList = body as ServerChatSession[]
      } else if (body && typeof body === 'object') {
        const env = body as { data?: unknown; sessions?: unknown }
        if (Array.isArray(env.data)) rawList = env.data as ServerChatSession[]
        else if (Array.isArray(env.sessions)) rawList = env.sessions as ServerChatSession[]
      }
      const fallbackAgent = agentIdRef.current
      const list = rawList.map((s) => normaliseServerSession(s, fallbackAgent))
      setChatSessions(list)
    } catch { /* network errors are non-fatal — the local bucket still works */ }
  }, [])

  // Initial fetch (once we are in the browser; token may not be present yet).
  useEffect(() => {
    refreshChatSessions()
  }, [refreshChatSessions])

  // ── Inbound event router ────────────────────────────────────────────────────
  const handleWsEvent = useCallback((data: InboundWsEvent) => {
    // Resolve turn_id → session_id (fall back to the currently-active session
    // if the server didn't echo it back yet, e.g. first event of a turn that
    // started before the server learned the turn_id).
    const turnId = data.turn_id
    let targetSession: string | undefined
    if (turnId) targetSession = turnSessionRef.current.get(turnId)
    if (!targetSession && data.session_id) targetSession = data.session_id
    if (!targetSession) targetSession = sessionIdRef.current
    const sid = targetSession

    switch (data.type) {
      case 'progress': {
        setTypingForSession(sid, true)
        updateSessionMessages(sid, (prev) => {
          const last = prev[prev.length - 1]
          if (last?.role === 'thinking' && last.content === data.content) return prev
          return [
            ...prev,
            {
              id: uuidv4(),
              role: 'thinking',
              content: data.content ?? '',
              timestamp: new Date(),
              isStreaming: true,
            },
          ]
        })
        break
      }

      case 'tool_hint': {
        updateSessionMessages(sid, (prev) => {
          const alreadyExists = prev.some(
            (m) => m.role === 'tool_hint' && m.content === data.content,
          )
          if (alreadyExists) return prev
          return [
            ...prev,
            {
              id: uuidv4(),
              role: 'tool_hint',
              content: data.content ?? '',
              timestamp: new Date(),
            },
          ]
        })
        break
      }

      case 'response': {
        setTypingForSession(sid, false)
        updateSessionMessages(sid, (prev) => {
          const toolHints = prev.filter((m) => m.role === 'tool_hint')
          const filtered = prev.filter(
            (m) => m.role !== 'thinking' && m.role !== 'tool_hint',
          )
          const dedupedHints = Array.from(
            new Set(toolHints.map((h) => h.content).filter(Boolean)),
          )
          const toolSummary: ChatMessage[] = dedupedHints.length > 0
            ? [{
              id: uuidv4(),
              role: 'tool_summary' as const,
              content: dedupedHints.join(' → '),
              timestamp: new Date(),
            }]
            : []
          return [
            ...filtered,
            ...toolSummary,
            {
              id: uuidv4(),
              role: 'assistant',
              content: data.content ?? '',
              timestamp: new Date(),
            },
          ]
        })
        // Server may upgrade a client-generated session_id to its own; keep
        // both refs in sync if so (only for the session that initiated the turn).
        if (data.session_id && data.session_id !== sid) {
          // No remap needed — current implementation keeps client-generated
          // session ids stable, but we still record the route for any
          // late-arriving events on this turn.
        }
        if (turnId) turnSessionRef.current.delete(turnId)
        // The session list on the server now has a new updated_at and possibly
        // a new session — refresh.
        refreshChatSessions()
        // Mark this session as hydrated so we don't re-fetch it.
        hydratedSessionsRef.current.add(sid)
        break
      }

      case 'error': {
        setTypingForSession(sid, false)
        updateSessionMessages(sid, (prev) => {
          const filtered = prev.filter(
            (m) => m.role !== 'thinking' && m.role !== 'tool_hint',
          )
          return [
            ...filtered,
            {
              id: uuidv4(),
              role: 'assistant',
              content: `Sorry, your request could not be processed right now. ${
                data.content ? `Reason: ${data.content}` : 'Please try again later or contact the system administrator.'
              }`,
              timestamp: new Date(),
            },
          ]
        })
        if (turnId) turnSessionRef.current.delete(turnId)
        break
      }

      default:
        // Unknown event type — silently ignore so future server additions are
        // forward-compatible.
        break
    }
  }, [refreshChatSessions, setTypingForSession, updateSessionMessages])

  // ── WebSocket lifecycle ─────────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    // The server rejects sockets that do not authenticate, so skip connecting
    // (and reconnecting) until a login token is available.
    const token = getAuthToken()
    if (!token) {
      setStatus('disconnected')
      return
    }

    setStatus('connecting')
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    // First frame must be the auth handshake; the status flips to
    // 'connected' only after the server replies with `auth_ok`.
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'auth', token }))
    }

    ws.onclose = () => {
      setStatus('disconnected')
      if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = Math.min(
          1000 * Math.pow(2, reconnectAttemptsRef.current),
          RECONNECT.MAX_DELAY_MS,
        )
        reconnectAttemptsRef.current += 1
        reconnectTimeoutRef.current = setTimeout(() => connectRef.current(), delay)
      }
    }

    ws.onerror = () => {
      ws.close()
    }

    ws.onmessage = (event) => {
      let data: InboundWsEvent
      try {
        data = JSON.parse(event.data) as InboundWsEvent
      } catch {
        return
      }
      if (data.type === 'auth_ok') {
        setStatus('connected')
        reconnectAttemptsRef.current = 0
        return
      }
      handleWsEvent(data)
    }
  }, [MAX_RECONNECT_ATTEMPTS, handleWsEvent])

  useEffect(() => { connectRef.current = connect }, [connect])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  // ── Public actions ──────────────────────────────────────────────────────────
  const sendMessage = useCallback(
    (content: string, opts?: { uploadIds?: string[]; attachmentLabels?: string[] }) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

      const sid = sessionIdRef.current
      const turnId = `turn:${uuidv4().slice(0, 12)}`
      turnSessionRef.current.set(turnId, sid)

      const userMessage: ChatMessage = {
        id: uuidv4(),
        role: 'user',
        content,
        timestamp: new Date(),
        attachmentLabels: opts?.attachmentLabels ?? [],
      }
      updateSessionMessages(sid, (prev) => [...prev, userMessage])
      setTypingForSession(sid, true)
      // Mark this bucket as hydrated — we own its state from here on.
      hydratedSessionsRef.current.add(sid)

      wsRef.current.send(
        JSON.stringify({
          message: content,
          agent_id: agentIdRef.current,
          session_id: sid,
          turn_id: turnId,
          upload_ids: opts?.uploadIds ?? [],
        }),
      )
    },
    [setTypingForSession, updateSessionMessages],
  )

  const clearMessages = useCallback(() => {
    const oldId = sessionIdRef.current
    const newId = uuidv4()
    setMessagesBySession((all) => {
      if (!(oldId in all)) return all
      const next = { ...all }
      delete next[oldId]
      return next
    })
    setTypingSessions((prev) => {
      if (!prev.has(oldId)) return prev
      const next = new Set(prev)
      next.delete(oldId)
      return next
    })
    sessionIdRef.current = newId
    setActiveSessionId(newId)
  }, [])

  const setAgentId = useCallback((newAgentId: string) => {
    setAgentIdState(newAgentId)
    agentIdRef.current = newAgentId
    try { localStorage.setItem('ic_agent_id', newAgentId) } catch { /* */ }
    // Switching agents starts a fresh session, mirroring the legacy behaviour.
    const newId = uuidv4()
    sessionIdRef.current = newId
    setActiveSessionId(newId)
    setTypingSessions(new Set())
  }, [])

  const loadSession = useCallback(async (sessionId: string) => {
    sessionIdRef.current = sessionId
    setActiveSessionId(sessionId)

    if (hydratedSessionsRef.current.has(sessionId)) return

    const token = getAuthToken()
    if (!token) return
    try {
      const res = await fetch(`${getApiBase()}/api/chat-sessions/${encodeURIComponent(sessionId)}`, {
        headers: authHeaders(token),
      })
      if (!res.ok) return
      const body: unknown = await res.json().catch(() => null)
      // Accept either { messages: [...] }, a raw array, or an envelope.
      let raw: PersistedMessageDTO[] = []
      if (Array.isArray(body)) {
        raw = body as PersistedMessageDTO[]
      } else if (body && typeof body === 'object') {
        const env = body as { messages?: unknown; data?: { messages?: unknown } | unknown }
        if (Array.isArray(env.messages)) raw = env.messages as PersistedMessageDTO[]
        else if (env.data && typeof env.data === 'object' && Array.isArray((env.data as { messages?: unknown }).messages)) {
          raw = (env.data as { messages: PersistedMessageDTO[] }).messages
        }
      }
      const restored = raw.map(dtoToChatMessage)
      setMessagesBySession((all) => ({ ...all, [sessionId]: restored }))
      hydratedSessionsRef.current.add(sessionId)

      // Restore the agent id from the session metadata if it tells us about it.
      const fromList = chatSessions.find((s) => s.id === sessionId)
      if (fromList?.agentId && fromList.agentId !== agentIdRef.current) {
        agentIdRef.current = fromList.agentId
        setAgentIdState(fromList.agentId)
      }
    } catch { /* swallow — UI shows empty session */ }
  }, [chatSessions])

  const deleteSession = useCallback(async (sessionId: string) => {
    const token = getAuthToken()
    if (token) {
      try {
        await fetch(`${getApiBase()}/api/chat-sessions/${encodeURIComponent(sessionId)}`, {
          method: 'DELETE',
          headers: authHeaders(token),
        })
      } catch { /* ignore — proceed to local cleanup */ }
    }
    setChatSessions((prev) => prev.filter((s) => s.id !== sessionId))
    setMessagesBySession((all) => {
      if (!(sessionId in all)) return all
      const next = { ...all }
      delete next[sessionId]
      return next
    })
    setTypingSessions((prev) => {
      if (!prev.has(sessionId)) return prev
      const next = new Set(prev)
      next.delete(sessionId)
      return next
    })
    hydratedSessionsRef.current.delete(sessionId)
    if (sessionIdRef.current === sessionId) {
      const newId = uuidv4()
      sessionIdRef.current = newId
      setActiveSessionId(newId)
    }
  }, [])

  // ── Derived values for the active session ──────────────────────────────────
  const messages = messagesBySession[activeSessionId] ?? []
  const isTyping = typingSessions.has(activeSessionId)

  return {
    messages,
    status,
    isTyping,
    agentId,
    setAgentId,
    sendMessage,
    clearMessages,
    chatSessions,
    loadSession,
    deleteSession,
    activeSessionId,
  }
}
