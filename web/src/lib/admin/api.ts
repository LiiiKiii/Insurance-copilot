/** A4 admin API client: authentication, knowledge and business management. */

import { API_CONFIG } from '@/config'

const TOKEN_KEY = 'admin_access_token'
const REFRESH_KEY = 'admin_refresh_token'

function getAdminBase(): string {
  return `${API_CONFIG.BASE_URL}/api/admin`
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(TOKEN_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export interface ApiResponse<T> {
  ok: boolean
  data: T
  meta?: { page?: number; page_size?: number; total?: number }
  error?: { code: string; message: string }
}

export interface AdminUser {
  id: string
  username: string
  email: string
  display_name: string | null
  tenant_id: string
  is_superadmin: boolean
  is_admin: boolean
  tier: string
  roles: (string | { id: string; name: string })[]
  is_active: boolean
  supervisor_id: string | null
  daily_call_limit: number
  last_login_at: string | null
  created_at: string
}

export interface ModelConfig {
  id: string; provider: string; model_id: string; display_name: string
  model_type: string; category: string; base_url: string | null; is_default: boolean; enabled: boolean
  max_tokens: number; temperature: number; price_per_1k_input: number; price_per_1k_output: number
  tenant_id: string | null; created_at: string
}
export interface SystemConfig {
  id: string; config_key: string; config_value: string; config_type: string
  description: string; is_public: boolean; tenant_id: string | null; updated_at: string
}
export interface RequestLog {
  id: string; tenant_id: string | null; user_id: string | null
  endpoint: string; method: string; status_code: number; latency_ms: number
  ip_address: string | null; created_at: string
}
export interface AiLog {
  id: string; session_id: string | null; agent_id: string | null
  user_query: string; ai_response: string; model_id: string | null
  prompt_tokens: number | null; completion_tokens: number | null
  has_compliance_issue: boolean; compliance_notes: string | null; created_at: string
}
export interface ErrorLog {
  id: string; tenant_id: string | null; level: string
  message: string; stack_trace: string | null; created_at: string
}

export interface CompetitionDef {
  id: string
  tenant_id: string | null
  name: string
  name_en: string
  type: string
  target_metric: string
  target_value: number | null
  unit: string
  deadline: string
  reward: string
  description: string
  is_active: boolean
  created_at: string | null
}

export interface CompetitionEntryDef {
  id: string
  competition_id: string
  agent_id: string
  current_value: number | null
  gap: number | null
  status: string
  created_at: string | null
}

export interface PerformanceTarget {
  id: string
  tenant_id: string | null
  agent_id: string
  metric_key: string
  metric_label: string
  target_value: number
  unit: string
  period_type: string
  period_start: string
  period_end: string
  created_by: string | null
  created_at: string | null
  updated_at: string | null
}

export interface KnowledgeBase {
  id: string
  tenant_id: string
  name: string
  description: string
  kb_type: string
  status: string
  document_count: number
  chunk_count: number
  created_at: string
}

export interface KBDocument {
  id: string
  filename: string
  file_type: string
  file_size: number
  status: string
  chunk_count: number
  error_message?: string | null
  created_at: string
}

export interface DocumentChunk {
  id: string
  chunk_index: number
  content: string
  token_count: number
}

let refreshing: Promise<boolean> | null = null

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_KEY)
  if (!refreshToken) return false
  try {
    const response = await fetch(`${getAdminBase()}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    const body = await response.json()
    if (!response.ok || !body.ok) return false
    localStorage.setItem(TOKEN_KEY, body.data.access_token)
    return true
  } catch {
    return false
  }
}

function redirectToLogin(): void {
  clearTokens()
  if (typeof window === 'undefined' || window.location.pathname === '/admin/login') return
  const next = encodeURIComponent(window.location.pathname + window.location.search)
  window.location.href = `/admin/login?next=${next}`
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let response = await fetch(`${getAdminBase()}${path}`, { ...init, headers })
  if (response.status === 401) {
    if (!refreshing) refreshing = refreshAccessToken()
    const refreshed = await refreshing
    refreshing = null
    if (refreshed) {
      headers.Authorization = `Bearer ${getToken()}`
      response = await fetch(`${getAdminBase()}${path}`, { ...init, headers })
    } else {
      redirectToLogin()
    }
  }

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const error = body?.detail?.error ?? body?.error
    return {
      ok: false,
      data: null as T,
      error: {
        code: error?.code ?? `HTTP_${response.status}`,
        message: error?.message ?? 'The request failed',
      },
    }
  }
  if (body) return body as ApiResponse<T>
  return {
    ok: false,
    data: null as T,
    error: { code: 'INVALID_RESPONSE', message: 'The server returned invalid JSON' },
  }
}

async function uploadDocument(kbId: string, file: File): Promise<ApiResponse<KBDocument>> {
  const form = new FormData()
  form.append('file', file)
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`${getAdminBase()}/knowledge-bases/${kbId}/documents/upload`, {
    method: 'POST',
    headers,
    body: form,
  })
  if (response.status === 401) redirectToLogin()
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const error = body?.detail?.error ?? body?.error
    return {
      ok: false,
      data: null as unknown as KBDocument,
      error: {
        code: error?.code ?? `HTTP_${response.status}`,
        message: error?.message ?? 'The upload failed',
      },
    }
  }
  return body as ApiResponse<KBDocument>
}

export const adminApi = {
  auth: {
    login: async (username: string, password: string) => {
      const result = await apiFetch<{
        access_token: string
        refresh_token: string
        user: AdminUser
      }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      if (result.ok) setTokens(result.data.access_token, result.data.refresh_token)
      return result
    },
    me: () => apiFetch<AdminUser>('/auth/me'),
    logout: async () => {
      try {
        return await apiFetch<{ message: string }>('/auth/logout', { method: 'POST' })
      } finally {
        clearTokens()
      }
    },
  },
  knowledge: {
    list: (page = 1) => apiFetch<KnowledgeBase[]>(`/knowledge-bases/?page=${page}`),
    create: (body: { name: string; description: string }) =>
      apiFetch<KnowledgeBase>('/knowledge-bases/', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    delete: (id: string) => apiFetch<{ message: string }>(`/knowledge-bases/${id}`, { method: 'DELETE' }),
    docs: (kbId: string, page = 1) =>
      apiFetch<KBDocument[]>(`/knowledge-bases/${kbId}/documents?page=${page}`),
    deleteDoc: (kbId: string, docId: string) =>
      apiFetch<{ message: string }>(`/knowledge-bases/${kbId}/documents/${docId}`, { method: 'DELETE' }),
    chunks: (kbId: string, docId: string, page = 1) =>
      apiFetch<DocumentChunk[]>(`/knowledge-bases/${kbId}/documents/${docId}/chunks?page=${page}&page_size=50`),
    uploadDoc: uploadDocument,
  },

  users: {
    list: (page = 1, pageSize = 20, search?: string) =>
      apiFetch<AdminUser[]>(`/users/?page=${page}&page_size=${pageSize}${search ? `&search=${encodeURIComponent(search)}` : ''}`),
    get: (id: string) => apiFetch<AdminUser>(`/users/${id}`),
    create: (body: unknown) => apiFetch<AdminUser>('/users/', { method: 'POST', body: JSON.stringify(body) }),
    update: (id: string, body: unknown) => apiFetch<AdminUser>(`/users/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
    delete: (id: string) => apiFetch(`/users/${id}`, { method: 'DELETE' }),
  },

  models: {
    list: () => apiFetch<ModelConfig[]>('/model-configs/'),
    create: (body: unknown) => apiFetch<ModelConfig>('/model-configs/', { method: 'POST', body: JSON.stringify(body) }),
    update: (id: string, body: unknown) => apiFetch<ModelConfig>(`/model-configs/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
    delete: (id: string) => apiFetch(`/model-configs/${id}`, { method: 'DELETE' }),
    test: (id: string) => apiFetch<{ latency_ms: number; model: string }>(`/model-configs/${id}/test`, { method: 'POST' }),
    setDefault: (id: string) => apiFetch<ModelConfig>(`/model-configs/${id}/set-default`, { method: 'POST' }),
  },

  config: {
    list: (search?: string) => apiFetch<SystemConfig[]>(`/configs/${search ? `?search=${encodeURIComponent(search)}` : ''}`),
    update: (id: string, body: unknown) =>
      apiFetch<SystemConfig>(`/configs/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
    create: (body: unknown) => apiFetch<SystemConfig>('/configs/', { method: 'POST', body: JSON.stringify(body) }),
    delete: (id: string) => apiFetch(`/configs/${id}`, { method: 'DELETE' }),
  },

  audit: {
    requests: (
      page = 1,
      pageSize = 50,
      filters?: { method?: string; status_code?: number; endpoint?: string },
    ) => {
      const q = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      })
      if (filters?.method) q.set('method', filters.method)
      if (typeof filters?.status_code === 'number') q.set('status_code', String(filters.status_code))
      if (filters?.endpoint) q.set('endpoint', filters.endpoint)
      return apiFetch<RequestLog[]>(`/logs/requests?${q.toString()}`)
    },
    aiAudit: (page = 1) => apiFetch<AiLog[]>(`/logs/ai-audit?page=${page}`),
    errors: (page = 1) => apiFetch<ErrorLog[]>(`/logs/errors?page=${page}`),
  },

  targets: {
    list: (agentId?: string) =>
      apiFetch<PerformanceTarget[]>(`/targets/${agentId ? `?agent_id=${agentId}` : ''}`),
    create: (body: unknown) =>
      apiFetch<PerformanceTarget>('/targets/', { method: 'POST', body: JSON.stringify(body) }),
    batchCreate: (targets: unknown[]) =>
      apiFetch<PerformanceTarget[]>('/targets/batch', { method: 'POST', body: JSON.stringify(targets) }),
    update: (id: string, body: unknown) =>
      apiFetch<PerformanceTarget>(`/targets/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
    delete: (id: string) =>
      apiFetch(`/targets/${id}`, { method: 'DELETE' }),
  },

  competitions: {
    list: (isActive?: boolean) =>
      apiFetch<CompetitionDef[]>(`/competitions/${isActive !== undefined ? `?is_active=${isActive}` : ''}`),
    get: (id: string) =>
      apiFetch<CompetitionDef>(`/competitions/${id}`),
    create: (body: unknown) =>
      apiFetch<CompetitionDef>('/competitions/', { method: 'POST', body: JSON.stringify(body) }),
    update: (id: string, body: unknown) =>
      apiFetch<CompetitionDef>(`/competitions/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
    delete: (id: string) =>
      apiFetch(`/competitions/${id}`, { method: 'DELETE' }),
    entries: (compId: string) =>
      apiFetch<CompetitionEntryDef[]>(`/competitions/${compId}/entries`),
    createEntry: (body: unknown) =>
      apiFetch<CompetitionEntryDef>('/competitions/entries', { method: 'POST', body: JSON.stringify(body) }),
    updateEntry: (entryId: string, body: unknown) =>
      apiFetch<CompetitionEntryDef>(`/competitions/entries/${entryId}`, { method: 'PUT', body: JSON.stringify(body) }),
    deleteEntry: (entryId: string) =>
      apiFetch(`/competitions/entries/${entryId}`, { method: 'DELETE' }),
  },
}
