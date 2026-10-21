/**
 * Daily briefing API client.
 */

import { API_CONFIG } from '@/config'
import { authenticatedFetch as fetch, getToken } from './auth'

export interface ComplianceWarning {
  type: string
  level: 'error' | 'warning' | 'info'
  title: string
  message: string
}

export interface BriefingSummary {
  message_count: number
  p0_count: number
  p1_count: number
  p2_count: number
  acknowledged_at: string | null
  is_stale: boolean
  has_briefing: boolean
  compliance_warnings: ComplianceWarning[]
}

export interface BriefingActionItem {
  priority: string
  policy_no: string
  customer_name: string
  action: string
  deadline: string | null
  source_message_id: string
  suggested_script?: string
}

export interface InboxMessage {
  id: string
  external_id: string
  priority: 'P0' | 'P1' | 'P2'
  category: string
  notification_name: string
  receiver_type: string
  trigger_logic?: string | null
  template_summary?: string | null
  policy_no?: string | null
  customer_id?: string | null
  customer_name?: string | null
  product_name?: string | null
  business_type?: string | null
  raw_content: string
  classify_reason?: string | null
  channel: string
  deadline_at?: string | null
  occurred_at?: string | null
  received_at?: string | null
  read_at?: string | null
  handled_at?: string | null
  source_system?: string | null
}

export interface DailyBriefing {
  date: string
  message_count: number
  p0_count: number
  p1_count: number
  p2_count: number
  summary_markdown: string | null
  action_items: BriefingActionItem[]
  model_id?: string | null
  model_display_name?: string | null
  generated_at?: string | null
  acknowledged_at?: string | null
}

export interface BriefingPayload {
  briefing: DailyBriefing | null
  messages: InboxMessage[]
  compliance_warnings: ComplianceWarning[]
  is_stale: boolean
}

export interface BriefingSettings {
  tenant_id: string
  auto_generate_enabled: boolean
  auto_generate_time: string
  auto_generate_scope: 'all' | 'active_7d' | 'active_30d'
  min_messages_to_generate: number
  last_run_at: string | null
  last_run_status: string | null
  last_run_summary: { generated: number; skipped: number; failed: number; agents_total: number } | null
}

function buildHeaders(): HeadersInit {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  const tok = getToken()
  if (tok) h['Authorization'] = `Bearer ${tok}`
  return h
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_CONFIG.BASE_URL}${path}`, {
    ...init,
    headers: { ...buildHeaders(), ...(init?.headers || {}) },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`API ${path} failed: ${res.status} ${text}`)
  }
  return res.json()
}

export function fetchBriefingSummary(agentId: string): Promise<BriefingSummary> {
  return api<BriefingSummary>(`/api/briefing/today/summary?agent_id=${encodeURIComponent(agentId)}`)
}

export function fetchTodayBriefing(agentId: string): Promise<BriefingPayload> {
  return api<BriefingPayload>(`/api/briefing/today?agent_id=${encodeURIComponent(agentId)}`)
}

export function regenerateBriefing(agentId: string): Promise<BriefingPayload> {
  return api<BriefingPayload>(`/api/briefing/today/regenerate?agent_id=${encodeURIComponent(agentId)}`, {
    method: 'POST',
  })
}

export function acknowledgeBriefing(agentId: string): Promise<{ acknowledged_at: string }> {
  return api<{ acknowledged_at: string }>(
    `/api/briefing/today/acknowledge?agent_id=${encodeURIComponent(agentId)}`,
    { method: 'POST' },
  )
}

export function markMessageRead(messageId: string): Promise<{ read_at: string }> {
  return api(`/api/briefing/messages/${messageId}/read`, { method: 'POST' })
}

export function markMessageHandled(messageId: string): Promise<{ handled_at: string; read_at: string }> {
  return api(`/api/briefing/messages/${messageId}/handled`, { method: 'POST' })
}

export function fetchBriefingSettings(agentId: string): Promise<BriefingSettings> {
  return api(`/api/briefing/admin/settings?agent_id=${encodeURIComponent(agentId)}`)
}

export function updateBriefingSettings(
  agentId: string,
  body: Partial<Pick<BriefingSettings, 'auto_generate_enabled' | 'auto_generate_time' | 'auto_generate_scope' | 'min_messages_to_generate'>>,
): Promise<BriefingSettings> {
  return api(`/api/briefing/admin/settings?agent_id=${encodeURIComponent(agentId)}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function warmupBriefingNow(agentId: string): Promise<{ generated: number; skipped: number; failed: number; agents_total: number }> {
  return api(`/api/briefing/admin/warmup-now?agent_id=${encodeURIComponent(agentId)}`, {
    method: 'POST',
  })
}

// ── admin: sample seeding + inbox CRUD ──────────────────────────────────────

export interface TenantAgent {
  username: string
  display_name: string
  tier?: string | null
}

export interface AdminInboxMessage extends InboxMessage {
  agent_id: string
}

export interface AdminMessagesPage {
  total: number
  limit: number
  offset: number
  items: AdminInboxMessage[]
}

export interface AdminMessageCreate {
  target_agent_id: string
  priority: 'P0' | 'P1' | 'P2'
  category: string
  notification_name: string
  receiver_type: string
  raw_content: string
  trigger_logic?: string | null
  template_summary?: string | null
  policy_no?: string | null
  customer_id?: string | null
  customer_name?: string | null
  classify_reason?: string | null
  channel?: string
  deadline_at?: string | null
  occurred_at?: string | null
  external_id?: string | null
  source_system?: string | null
}

export type AdminMessageUpdate = Partial<Omit<AdminMessageCreate, 'target_agent_id'>>

export function fetchTenantAgents(agentId: string): Promise<{ agents: TenantAgent[] }> {
  return api(`/api/briefing/admin/agents?agent_id=${encodeURIComponent(agentId)}`)
}

export function listAdminMessages(
  agentId: string,
  params: {
    target_agent_id?: string
    priority?: 'P0' | 'P1' | 'P2'
    source_system?: string
    limit?: number
    offset?: number
  } = {},
): Promise<AdminMessagesPage> {
  const qs = new URLSearchParams({ agent_id: agentId })
  if (params.target_agent_id) qs.set('target_agent_id', params.target_agent_id)
  if (params.priority) qs.set('priority', params.priority)
  if (params.source_system) qs.set('source_system', params.source_system)
  if (params.limit != null) qs.set('limit', String(params.limit))
  if (params.offset != null) qs.set('offset', String(params.offset))
  return api(`/api/briefing/admin/messages?${qs.toString()}`)
}

export function createAdminMessage(
  agentId: string,
  body: AdminMessageCreate,
): Promise<AdminInboxMessage> {
  return api(`/api/briefing/admin/messages?agent_id=${encodeURIComponent(agentId)}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateAdminMessage(
  agentId: string,
  messageId: string,
  body: AdminMessageUpdate,
): Promise<AdminInboxMessage> {
  return api(`/api/briefing/admin/messages/${messageId}?agent_id=${encodeURIComponent(agentId)}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function deleteAdminMessage(
  agentId: string,
  messageId: string,
): Promise<{ deleted: string }> {
  return api(`/api/briefing/admin/messages/${messageId}?agent_id=${encodeURIComponent(agentId)}`, {
    method: 'DELETE',
  })
}
