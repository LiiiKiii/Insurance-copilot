'use client'

import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/i18n'
import { authenticatedFetch as fetch, authHeaders } from '@/lib/auth'

interface Honor {
  id: string
  name: string
  type: string
  target_value: number | null
  current_value: number | null
  gap: number | null
  unit: string
  deadline: string
  tags: string[]
  days_remaining?: number
}

interface HonorsTabProps {
  agentId: string
}

function formatHKD(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function formatGap(gap: number | null | undefined, unit: string): string {
  if (gap == null) return '—'
  if (['HKD', 'USD'].includes(unit)) return `${unit} ${formatHKD(gap)}`
  return `${formatHKD(gap)}${unit ? ' ' + unit : ''}`
}

export function HonorsTab({ agentId }: HonorsTabProps) {
  const { t } = useTranslation()
  const [honors, setHonors] = useState<Honor[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!agentId) return
    let cancelled = false
    setLoading(true)
    fetch(`/api/competitions?agent_id=${encodeURIComponent(agentId)}`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return
        const list: Honor[] = data?.competitions || []
        setHonors(list.filter((c) => c.type === 'honor'))
        setLoading(false)
      })
      .catch((err) => {
        if (!cancelled && err.name !== 'AbortError') setLoading(false)
      })
    return () => { cancelled = true }
  }, [agentId])

  if (loading) {
    return (
      <div className="p-3 space-y-3">
        {[1, 2].map((i) => (
          <div key={i} className="animate-pulse h-20 bg-slate-100 dark:bg-slate-800 rounded-xl" />
        ))}
      </div>
    )
  }

  if (honors.length === 0) {
    return (
      <div className="flex items-center justify-center h-24 text-slate-400 text-sm">
        {t('tab.honors.empty')}
      </div>
    )
  }

  const achieved = honors.filter((h) => h.gap !== null && h.gap <= 0)
  const outdated = honors.filter(
    (h) => h.gap !== null && h.gap > 0 && h.days_remaining !== undefined && h.days_remaining < 0,
  )
  const active = honors.filter(
    (h) => h.gap !== null && h.gap > 0 && (h.days_remaining === undefined || h.days_remaining >= 0),
  )

  const dotColor = (achievedFlag: boolean, days: number | undefined) => {
    if (achievedFlag) return 'bg-emerald-500'
    if (days !== undefined && days < 30) return 'bg-amber-500'
    return 'bg-slate-400'
  }
  const borderColor = (achievedFlag: boolean, days: number | undefined) => {
    if (achievedFlag) return 'border-emerald-400 dark:border-emerald-500'
    if (days !== undefined && days < 30) return 'border-amber-400 dark:border-amber-500'
    return 'border-slate-300 dark:border-slate-600'
  }
  const daysColor = (days: number | undefined) => {
    if (days === undefined) return 'text-slate-600 dark:text-slate-300'
    if (days < 30) return 'text-amber-600 dark:text-amber-400'
    return 'text-slate-600 dark:text-slate-300'
  }

  return (
    <div className="p-3 space-y-4">
      {/* Active honors - timeline cards */}
      {active.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-3 px-1">
            {t('tab.honors.activeHeading', { count: active.length })}
          </div>
          <div className="relative">
            <div className="absolute left-[11px] top-3 bottom-3 w-px bg-slate-200 dark:bg-slate-700" />
            <div className="space-y-3">
              {active.map((h) => {
                const days = h.days_remaining
                const progress = h.target_value && h.current_value
                  ? Math.min((h.current_value / h.target_value) * 100, 100)
                  : 0
                return (
                  <div key={h.id} className="relative pl-8">
                    <div className={cn(
                      'absolute left-[7px] top-4 w-[9px] h-[9px] rounded-full ring-2 ring-white dark:ring-slate-900',
                      dotColor(false, days),
                    )} />
                    <div className={cn(
                      'rounded-xl border-l-[3px] bg-white dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700/50 p-3',
                      borderColor(false, days),
                    )}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <span className="text-sm font-medium text-slate-800 dark:text-white truncate">
                            {h.name}
                          </span>
                          <div className="mt-1.5 text-xs text-slate-500 dark:text-slate-400 space-y-0.5">
                            <div>{t('metric.gap')} <span className="font-mono font-bold text-slate-700 dark:text-slate-200">{formatGap(h.gap, h.unit)}</span></div>
                            <div className="flex items-center gap-3">
                              <span>{t('metric.target')} <span className="font-mono font-bold text-slate-700 dark:text-slate-200">{formatGap(h.target_value, h.unit)}</span></span>
                              <span>{t('metric.current')} <span className="font-mono font-bold text-slate-700 dark:text-slate-200">{formatGap(h.current_value, h.unit)}</span></span>
                            </div>
                          </div>
                        </div>
                        <div className="text-right shrink-0">
                          <div className={cn('text-xl font-bold font-mono tabular-nums', daysColor(days))}>
                            {days ?? '--'}
                          </div>
                          <div className="text-[10px] text-slate-400">{t('metric.days')}</div>
                        </div>
                      </div>
                      <div className="mt-2.5 flex items-center gap-2">
                        <div className="flex-1 h-1 bg-slate-100 dark:bg-slate-700/50 rounded-full overflow-hidden">
                          <div
                            className={cn(
                              'h-full rounded-full transition-all',
                              progress >= 80 ? 'bg-emerald-500' :
                              progress >= 50 ? 'bg-amber-500' : 'bg-red-500',
                            )}
                            style={{ width: `${progress}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-mono text-slate-400">{progress.toFixed(0)}%</span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Achieved */}
      {achieved.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2 px-1">
            {t('tab.honors.completedHeading', { count: achieved.length })}
          </div>
          <div className="space-y-1.5">
            {achieved.map((h) => (
              <div key={h.id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-50/50 dark:bg-emerald-500/5 border border-emerald-200/50 dark:border-emerald-500/10">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-500 shrink-0">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span className="text-xs text-emerald-700 dark:text-emerald-400 font-medium truncate">{h.name}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Outdated */}
      {outdated.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2 px-1">
            {t('tab.honors.expiredHeading', { count: outdated.length })}
          </div>
          <div className="space-y-1.5">
            {outdated.map((h) => (
              <div key={h.id} className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-200/60 dark:border-slate-700/50 opacity-75">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-400 shrink-0">
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12 6 12 12 16 14" />
                  </svg>
                  <span className="text-xs text-slate-500 dark:text-slate-400 font-medium truncate line-through">{h.name}</span>
                </div>
                <span className="text-[10px] text-slate-400 shrink-0">
                  {t('metric.gap')} <span className="font-mono">{formatGap(h.gap, h.unit)}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
