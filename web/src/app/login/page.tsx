'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { loginChat, type LoginErrorCode } from '@/lib/auth'
import { EyeIcon, EyeOffIcon } from '@/components/admin/AdminIcons'
import { useTranslation, type MessageKey } from '@/lib/i18n'

const LOGIN_ERROR_KEY: Record<LoginErrorCode, MessageKey> = {
  failed: 'login.error.failed',
  network: 'login.error.network',
}

export default function LoginPage() {
  const router = useRouter()
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) {
      setError(t('login.validation.empty'))
      return
    }
    setLoading(true)
    setError(null)
    const result = await loginChat(username, password)
    setLoading(false)
    if ('error' in result) {
      const e = result.error
      setError(e.detail ?? t(LOGIN_ERROR_KEY[e.code]))
    } else {
      router.replace('/')
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50/30 to-slate-100 dark:from-[#0a0f1a] dark:via-[#0f172a] dark:to-[#0a0f1a] px-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-insurance-blue/5 dark:bg-insurance-blue/10 blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 rounded-full bg-insurance-gold/5 dark:bg-insurance-gold/5 blur-3xl" />
      </div>


      <div className="relative z-10 w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-insurance-blue shadow-lg">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#C9A84C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
          <div className="text-center">
            <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{t('app.title')}</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{t('login.brandSubtitle')}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="rounded-2xl border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-900 shadow-xl p-8 flex flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('login.username')}</label>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="AGT001"
              className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-insurance-blue/30 focus:border-insurance-blue dark:focus:border-blue-500 transition-colors"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('login.password')}</label>
            <div className="relative">
              <input
                type={showPw ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-2.5 pr-10 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-insurance-blue/30 focus:border-insurance-blue dark:focus:border-blue-500 transition-colors"
              />
              <button
                type="button"
                onClick={() => setShowPw(!showPw)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
              >
                {showPw ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
              </button>
            </div>
          </div>

          {error && (
            <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-3 py-2 text-sm text-red-600 dark:text-red-400">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="flex items-center justify-center gap-2 rounded-lg bg-insurance-blue px-4 py-2.5 text-sm font-medium text-white hover:bg-insurance-blue-light active:bg-insurance-blue-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? t('login.submitting') : t('login.submit')}
          </button>
        </form>
      </div>
    </div>
  )
}
