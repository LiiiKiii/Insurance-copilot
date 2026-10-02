'use client'

import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { useTranslation, type MessageKey } from '@/lib/i18n'

// Frontend-side mapping from the backend's feasibility-hint enum
// to translation keys, so the badge text follows the UI locale. Unknown
// values fall through and are rendered verbatim.
const STATUS_KEY: Record<string, MessageKey> = {
  'Achieved': 'status.met',
  'Covered': 'status.covered',
  'Achievable': 'status.achievable',
  'Challenging': 'status.challenging',
  'Very difficult': 'status.difficult',
}

interface Competition {
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
  feasibility_hint?: string
  urgency_level?: string
}

interface CompetitionTabProps {
  agentId: string
}

function formatHKD(n: number | null | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { maximumFractionDigits: 0 })
}

function formatGap(gap: number | null | undefined, unit: string): string {
  if (gap == null) return '—'
  if (unit === 'HKD') return `HKD ${formatHKD(gap)}`
  return `${gap} ${unit}`
}

function getUrgencyColor(urgencyLevel: string | undefined): string {
  switch (urgencyLevel) {
    case 'critical': return 'border-red-400 dark:border-red-500'
    case 'important': return 'border-amber-400 dark:border-amber-500'
    default: return 'border-slate-300 dark:border-slate-600'
  }
}

function getDotColor(urgencyLevel: string | undefined): string {
  switch (urgencyLevel) {
    case 'critical': return 'bg-red-500'
    case 'important': return 'bg-amber-500'
    default: return 'bg-slate-400'
  }
}

function getDaysColor(urgencyLevel: string | undefined): string {
  switch (urgencyLevel) {
    case 'critical': return 'text-red-600 dark:text-red-400'
    case 'important': return 'text-amber-600 dark:text-amber-400'
    default: return 'text-slate-600 dark:text-slate-300'
  }
}

// Style table is keyed by the backend's stable Chinese enum so the colour
// follows the data even when the rendered label is translated.
const FEASIBILITY_STYLE: Record<string, string> = {
  'Achieved': 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400',
  'Covered': 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400',
  'Achievable': 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400',
  'Challenging': 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
  'Very difficult': 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400',
}

function FeasibilityBadge({ hint }: { hint: string | undefined }) {
  const { t } = useTranslation()
  if (!hint) return null
  const label = STATUS_KEY[hint] ? t(STATUS_KEY[hint]) : hint
  return (
    <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-medium whitespace-nowrap shrink-0', FEASIBILITY_STYLE[hint] || 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300')}>
      {label}
    </span>
  )
}

export function CompetitionTab({ agentId }: CompetitionTabProps) {
  const { t } = useTranslation()
  const [competitions, setCompetitions] = useState<Competition[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!agentId) return
    let cancelled = false
    setLoading(true)
    fetch(`/api/competitions?agent_id=${agentId}`, {})
      .then(r => r.json())
      .then(data => {
        if (cancelled) return
        const comps = data?.competitions || []
        // Backend already sorts by deadline; no need to re-sort here
        setCompetitions(comps)
        setLoading(false)
      })
      .catch((err) => { if (!cancelled && err.name !== 'AbortError') setLoading(false) })
    return () => { cancelled = true }
  }, [agentId])

  if (loading) {
    return (
      <div className="p-4 space-y-3">
        {[1,2,3].map(i => (
          <div key={i} className="animate-pulse h-20 bg-slate-100 dark:bg-slate-800 rounded-xl" />
        ))}
      </div>
    )
  }

  // Whitelist: only real competitions belong in this tab.
  // Honors/certifications/monthly/null all stay out.
  const comps = competitions.filter(c => c.type === 'competition')

  // Aggregate totals by unit — exclude competitions past their deadline so
  // the summary reflects only what's still actionable (active + completed).
  const summaryComps = comps.filter(
    c => c.days_remaining == null || c.days_remaining >= 0,
  )
  const summaryByUnit = summaryComps.reduce<Record<string, { current: number; target: number; gap: number; count: number }>>((acc, c) => {
    const unit = c.unit || ''
    if (!acc[unit]) acc[unit] = { current: 0, target: 0, gap: 0, count: 0 }
    acc[unit].current += c.current_value ?? 0
    acc[unit].target += c.target_value ?? 0
    acc[unit].gap += Math.max(c.gap ?? 0, 0)
    acc[unit].count += 1
    return acc
  }, {})
  const summaryUnits = Object.keys(summaryByUnit)

  // Competitions already met (gap <= 0 and gap is known)
  const completedComps = comps.filter(c => c.gap != null && c.gap <= 0)
  // Not met (or gap unknown) AND past deadline
  const outdatedComps = comps.filter(
    c => (c.gap == null || c.gap > 0) && c.days_remaining != null && c.days_remaining < 0,
  )
  // Not met (or gap unknown) AND still open (deadline today or future or unknown)
  const activeComps = comps.filter(
    c => (c.gap == null || c.gap > 0) && (c.days_remaining == null || c.days_remaining >= 0),
  )
  // Exclude completed from active/outdated (gap=0 should only be in completedComps)


  return (
    <div className="p-3 space-y-4">
      {/* Competition summary - three KPI cards per unit (team-summary card style) */}
      {summaryComps.length > 0 && summaryUnits.map((unit) => {
        const s = summaryByUnit[unit]
        const rate = s.target > 0 ? (s.current / s.target) * 100 : 0
        const rateColor = rate >= 80 ? 'text-emerald-600 dark:text-emerald-400'
          : rate >= 50 ? 'text-amber-600 dark:text-amber-400'
          : 'text-red-600 dark:text-red-400'
        return (
          <div key={unit || 'none'} className="relative overflow-hidden rounded-xl border border-slate-200/80 dark:border-white/10 bg-gradient-to-br from-white to-slate-50/70 dark:from-slate-800/60 dark:to-slate-900/60 p-3">
            {/* Gold top hairline */}
            <div aria-hidden="true" className="absolute inset-x-3 top-0 h-[1.5px] bg-gradient-to-r from-transparent via-insurance-gold/60 to-transparent" />
            <div className="grid grid-cols-3 gap-2">
              {/* Total target */}
              <div className="text-center">
                <div className="text-[10px] text-slate-500 dark:text-slate-400 mb-0.5">{t('tab.competition.totalTarget')}</div>
                <div className="text-sm font-bold font-mono text-slate-700 dark:text-slate-200 tabular-nums leading-tight">
                  {formatHKD(s.target)}
                </div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400 dark:text-slate-500 mt-0.5">{unit || '—'}</div>
              </div>
              {/* Achieved */}
              <div className="text-center border-x border-slate-200/60 dark:border-slate-700/40">
                <div className="text-[10px] text-slate-500 dark:text-slate-400 mb-0.5">{t('tab.competition.totalAchieved')}</div>
                <div className={cn('text-sm font-bold font-mono tabular-nums leading-tight', rateColor)}>
                  {formatHKD(s.current)}
                </div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400 dark:text-slate-500 mt-0.5">{unit || '—'}</div>
              </div>
              {/* Total gap */}
              <div className="text-center">
                <div className="text-[10px] text-slate-500 dark:text-slate-400 mb-0.5">{t('tab.competition.totalGap')}</div>
                <div className={cn(
                  'text-sm font-bold font-mono tabular-nums leading-tight',
                  s.gap <= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400',
                )}>
                  {s.gap <= 0 ? t('metric.metShort') : formatHKD(s.gap)}
                </div>
                <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400 dark:text-slate-500 mt-0.5">{s.gap <= 0 ? '\u00A0' : (unit || '—')}</div>
              </div>
            </div>
          </div>
        )
      })}

      {/* Active competitions - timeline style */}
      {activeComps.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-3 px-1">
            {t('tab.competition.activeHeading', { count: activeComps.length })}
          </div>
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute left-[11px] top-3 bottom-3 w-px bg-slate-200 dark:bg-slate-700" />

            <div className="space-y-3">
              {activeComps.map(comp => {
                const days = comp.days_remaining
                const progress = comp.target_value && comp.current_value
                  ? Math.min((comp.current_value / comp.target_value) * 100, 100)
                  : 0

                return (
                  <div key={comp.id} className="relative pl-8">
                    {/* Timeline dot */}
                    <div className={cn(
                      'absolute left-[7px] top-4 w-[9px] h-[9px] rounded-full ring-2 ring-white dark:ring-slate-900',
                      getDotColor(comp.urgency_level),
                      comp.urgency_level === 'critical' ? 'animate-pulse' : ''
                    )} />

                    {/* Card */}
                    <div className={cn(
                      'rounded-xl border-l-[3px] bg-white dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700/50 p-3',
                      getUrgencyColor(comp.urgency_level)
                    )}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-slate-800 dark:text-white truncate">
                              {comp.name}
                            </span>
                            <FeasibilityBadge hint={comp.feasibility_hint} />
                          </div>
                          <div className="mt-1.5 text-xs text-slate-500 dark:text-slate-400 space-y-0.5">
                            <div>{t('metric.gap')} <span className="font-mono font-bold text-slate-700 dark:text-slate-200">{formatGap(comp.gap!, comp.unit)}</span></div>
                            <div className="flex items-center gap-3">
                              <span>{t('metric.target')} <span className="font-mono font-bold text-slate-700 dark:text-slate-200">{formatGap(comp.target_value, comp.unit)}</span></span>
                              <span>{t('metric.current')} <span className="font-mono font-bold text-slate-700 dark:text-slate-200">{formatGap(comp.current_value, comp.unit)}</span></span>
                            </div>
                          </div>
                        </div>
                        <div className="text-right shrink-0">
                          <div className={cn('text-xl font-bold font-mono tabular-nums', getDaysColor(comp.urgency_level))}>
                            {days ?? '--'}
                          </div>
                          <div className="text-[10px] text-slate-400">{t('metric.days')}</div>
                        </div>
                      </div>

                      {/* Mini progress bar */}
                      <div className="mt-2.5 flex items-center gap-2">
                        <div className="flex-1 h-1 bg-slate-100 dark:bg-slate-700/50 rounded-full overflow-hidden">
                          <div
                            className={cn(
                              'h-full rounded-full transition-all',
                              progress >= 80 ? 'bg-emerald-500' :
                              progress >= 50 ? 'bg-amber-500' : 'bg-red-500'
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

      {/* Completed / on-track */}
      {completedComps.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2 px-1">
            {t('tab.competition.completedHeading', { count: completedComps.length })}
          </div>
          <div className="space-y-1.5">
            {completedComps.map(comp => (
              <div key={comp.id} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-50/50 dark:bg-emerald-500/5 border border-emerald-200/50 dark:border-emerald-500/10">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-500 shrink-0">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span className="text-xs text-emerald-700 dark:text-emerald-400 font-medium truncate">{comp.name}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Outdated / past deadline (not met) */}
      {outdatedComps.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2 px-1">
            {t('tab.competition.expiredHeading', { count: outdatedComps.length })}
          </div>
          <div className="space-y-1.5">
            {outdatedComps.map(comp => (
              <div key={comp.id} className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-800/40 border border-slate-200/60 dark:border-slate-700/50 opacity-75">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-400 shrink-0">
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12 6 12 12 16 14" />
                  </svg>
                  <span className="text-xs text-slate-500 dark:text-slate-400 font-medium truncate line-through">{comp.name}</span>
                </div>
                <span className="text-[10px] text-slate-400 shrink-0">
                  {t('metric.gap')} <span className="font-mono">{formatGap(comp.gap!, comp.unit)}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {competitions.length === 0 && (
        <div className="flex items-center justify-center h-24 text-slate-400 text-sm">
          {t('tab.competition.empty')}
        </div>
      )}
    </div>
  )
}
