/** A4 admin API client limited to authentication and knowledge management. */

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
}
