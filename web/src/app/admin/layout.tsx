'use client'

import { useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'

import { AdminSidebar } from '@/components/admin/AdminLayout'
import { AdminAuthProvider, useAdminAuth } from '@/lib/admin/auth'

function AdminShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAdminAuth()
  const pathname = usePathname()
  const router = useRouter()
  const isLogin = pathname === '/admin/login'

  useEffect(() => {
    if (!loading && !user && !isLogin) router.replace('/admin/login')
  }, [isLogin, loading, router, user])

  if (isLogin) return <>{children}</>

  if (loading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-slate-50 text-sm text-slate-500 dark:bg-slate-950">
        Loading administration console…
      </div>
    )
  }

  if (!user) return null

  return (
    <div className="flex min-h-dvh flex-col bg-slate-50 lg:flex-row dark:bg-slate-950">
      <AdminSidebar />
      <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
    </div>
  )
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminAuthProvider>
      <AdminShell>{children}</AdminShell>
    </AdminAuthProvider>
  )
}
