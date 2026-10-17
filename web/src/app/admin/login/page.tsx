'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

import { EyeIcon, EyeOffIcon, SpinnerIcon } from '@/components/admin/AdminIcons'
import { useAdminAuth } from '@/lib/admin/auth'

export default function AdminLoginPage() {
  const { login } = useAdminAuth()
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!username || !password) {
      setError('Please enter your username and password')
      return
    }

    setLoading(true)
    setError(null)
    const loginError = await login(username, password)
    setLoading(false)
    if (loginError) {
      setError(loginError)
      return
    }

    const requested = new URLSearchParams(window.location.search).get('next')
    const destination = requested?.startsWith('/') && !requested.startsWith('//')
      ? requested
      : '/admin/knowledge'
    router.replace(destination)
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-slate-50 px-4 dark:bg-slate-950">
      <div className="w-full max-w-sm">
        <div className="mb-7 text-center">
          <div className="text-xl font-semibold text-slate-900 dark:text-white">Insurance Copilot</div>
          <div className="mt-1 text-sm text-slate-500">Knowledge administration</div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-5 rounded-2xl border border-slate-200 bg-white p-8 shadow-xl dark:border-slate-700 dark:bg-slate-900"
        >
          <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">
            Username
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 font-normal text-slate-900 outline-none focus:border-insurance-blue focus:ring-2 focus:ring-insurance-blue/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
          </label>

          <label className="flex flex-col gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">
            Password
            <span className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 pr-10 font-normal text-slate-900 outline-none focus:border-insurance-blue focus:ring-2 focus:ring-insurance-blue/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              />
              <button
                type="button"
                onClick={() => setShowPassword((value) => !value)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
              >
                {showPassword ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
              </button>
            </span>
          </label>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="flex items-center justify-center gap-2 rounded-lg bg-insurance-blue px-4 py-2.5 text-sm font-medium text-white hover:bg-insurance-blue-light disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading && <SpinnerIcon size={16} />}
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
