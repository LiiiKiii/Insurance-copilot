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
