/**
 * Main chat authentication — reuses Admin JWT tokens.
 * Provides user identity (username as agent_id) for the chat interface.
 */

import { API_CONFIG } from '@/config'

const TOKEN_KEY = 'admin_access_token'
const REFRESH_KEY = 'admin_refresh_token'
const USER_KEY = 'ic_user'

export interface ChatUser {
  id: string
  username: string          // = agent_id
  display_name: string
  tier: string
  is_superadmin: boolean
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

/** Bearer header for protected backend routes; empty when signed out. */
export function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

let tokenRefreshPromise: Promise<string | null> | null = null

export function getAccessTokenExpiration(token: string): number | null {
  try {
    const encoded = token.split('.')[1]
    if (!encoded) return null
    const base64 = encoded.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')
    const payload = JSON.parse(atob(padded)) as { exp?: unknown }
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null
  } catch {
    return null
  }
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem(REFRESH_KEY)
  if (!refreshToken) return null
  try {
    const response = await window.fetch(`${API_CONFIG.BASE_URL}/api/admin/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    const body = await response.json().catch(() => null)
    const accessToken = body?.data?.access_token
    if (!response.ok || !body?.ok || typeof accessToken !== 'string') return null
    localStorage.setItem(TOKEN_KEY, accessToken)
    return accessToken
  } catch {
    return null
  }
}

export async function getValidAccessToken(forceRefresh = false): Promise<string | null> {
  const token = getToken()
  const expiresAt = token ? getAccessTokenExpiration(token) : null
  if (!forceRefresh && token && expiresAt !== null && expiresAt > Date.now() + 30_000) {
    return token
  }
  if (!tokenRefreshPromise) {
    const pending = refreshAccessToken()
    tokenRefreshPromise = pending
    pending.finally(() => {
      if (tokenRefreshPromise === pending) tokenRefreshPromise = null
    })
  }
  return tokenRefreshPromise
}

function redirectToLogin(): void {
  clearAuth()
  if (window.location.pathname === '/login') return
  const next = encodeURIComponent(window.location.pathname + window.location.search)
  window.location.href = `/login?next=${next}`
}

/** Fetch a protected endpoint, refreshing an expired access token once. */
export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = await getValidAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response = await window.fetch(input, { ...init, headers })
  if (response.status !== 401) return response

  const refreshed = await getValidAccessToken(true)
  if (!refreshed) {
    redirectToLogin()
    return response
  }
  headers.set('Authorization', `Bearer ${refreshed}`)
  response = await window.fetch(input, { ...init, headers })
  if (response.status === 401) redirectToLogin()
  return response
}

export function getChatUser(): ChatUser | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

export function setChatUser(u: ChatUser) {
  localStorage.setItem(USER_KEY, JSON.stringify(u))
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
  localStorage.removeItem('ic_agent_id')  // clear the previous user's selected agent so it does not leak across logins
}

export type LoginErrorCode = 'failed' | 'network'

export interface LoginError {
  /** Error category — login page maps this to a translated label. */
  code: LoginErrorCode
  /** Optional backend-supplied detail (already localised — surface as-is). */
  detail?: string
}

export async function loginChat(
  username: string,
  password: string,
): Promise<{ user: ChatUser } | { error: LoginError }> {
  try {
    const res = await fetch(`${API_CONFIG.BASE_URL}/api/admin/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const data = await res.json()
    if (data.ok) {
      // when switching users, clear the previous user's agent selection first
      localStorage.removeItem('ic_agent_id')
      localStorage.setItem(TOKEN_KEY, data.data.access_token)
      localStorage.setItem(REFRESH_KEY, data.data.refresh_token)
      const user: ChatUser = {
        id: data.data.user.id,
        username: data.data.user.username,
        display_name: data.data.user.display_name || data.data.user.username,
        tier: data.data.user.tier || 'agent',
        is_superadmin: data.data.user.is_superadmin || false,
      }
      setChatUser(user)
      return { user }
    }
    const detail: string | undefined =
      data?.detail?.error?.message || data?.error?.message
    return { error: { code: 'failed', detail } }
  } catch {
    return { error: { code: 'network' } }
  }
}
