'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

import { adminApi, clearTokens, getToken, type AdminUser } from './api'

const ROLE_RANK: Record<string, number> = {
  readonly: 0,
  agent_manager: 1,
  admin: 2,
  super_admin: 3,
}

export type MinimumRole = keyof typeof ROLE_RANK

function userRank(user: AdminUser | null): number {
  if (!user) return -1
  if (user.is_superadmin) return ROLE_RANK.super_admin
  const roles = user.roles.map((role) => typeof role === 'string' ? role : role.name)
  return Math.max(-1, ...roles.map((role) => ROLE_RANK[role] ?? -1))
}

interface AdminAuthContextValue {
  user: AdminUser | null
  loading: boolean
  login: (username: string, password: string) => Promise<string | null>
  logout: () => void
  can: (minimumRole: MinimumRole) => boolean
  roleLabel: string
}

const AdminAuthContext = createContext<AdminAuthContextValue>({
  user: null,
  loading: true,
  login: async () => null,
  logout: () => undefined,
  can: () => false,
  roleLabel: '',
})

export function AdminAuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [user, setUser] = useState<AdminUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const loadUser = async () => {
      if (!getToken()) {
        if (!cancelled) setLoading(false)
        return
      }
      try {
        const result = await adminApi.auth.me()
        if (!cancelled && result.ok) setUser(result.data)
        if (!result.ok) clearTokens()
      } catch {
        clearTokens()
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void loadUser()
    return () => { cancelled = true }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    try {
      const result = await adminApi.auth.login(username, password)
      if (!result.ok) return result.error?.message ?? 'Sign-in failed'
      setUser(result.data.user)
      return null
    } catch {
      return 'Could not reach the server'
    }
  }, [])

  const logout = useCallback(() => {
    void adminApi.auth.logout()
    setUser(null)
    router.push('/admin/login')
  }, [router])

  const can = useCallback(
    (minimumRole: MinimumRole) => userRank(user) >= ROLE_RANK[minimumRole],
    [user],
  )

  const roleLabel = useMemo(() => {
    if (!user) return ''
    if (user.is_superadmin) return 'Super admin'
    const roles = user.roles.map((role) => typeof role === 'string' ? role : role.name)
    return roles.sort((a, b) => (ROLE_RANK[b] ?? -1) - (ROLE_RANK[a] ?? -1))[0] ?? 'User'
  }, [user])

  return (
    <AdminAuthContext.Provider value={{ user, loading, login, logout, can, roleLabel }}>
      {children}
    </AdminAuthContext.Provider>
  )
}

export function useAdminAuth(): AdminAuthContextValue {
  return useContext(AdminAuthContext)
}
