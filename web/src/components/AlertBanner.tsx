'use client'

import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/i18n'

interface Alert {
  competition_name: string
  days_remaining: number
  gap: number
  unit: string
  message: string
  urgency: string
}

interface AlertBannerProps {
  agentId: string
  className?: string
}

export function AlertBanner({ agentId, className }: AlertBannerProps) {
  const { t } = useTranslation()
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    setDismissed(false)
    fetch(`/api/proactive-alerts?agent_id=${encodeURIComponent(agentId)}`)
      .then(response => response.json())
      .then(data => setAlerts(data.alerts || []))
      .catch(() => setAlerts([]))
  }, [agentId])

  if (dismissed || alerts.length === 0) return null

  const topAlert = alerts[0]
  const isUrgent = topAlert.urgency === 'urgent'

  return (
    <div className={cn(
      'relative flex items-center gap-3 overflow-hidden border-b px-4 py-2.5 text-sm font-medium',
      isUrgent
        ? 'border-amber-500/30 bg-gradient-to-r from-amber-500/15 via-amber-500/10 to-transparent text-amber-800 dark:text-amber-200'
        : 'border-blue-500/25 bg-gradient-to-r from-blue-500/12 via-blue-500/8 to-transparent text-blue-800 dark:text-blue-200',
      className,
    )}>
      <span
        aria-hidden="true"
        className={cn(
          'absolute bottom-0 left-0 top-0 w-1',
          isUrgent
            ? 'bg-gradient-to-b from-amber-400 to-amber-600'
            : 'bg-gradient-to-b from-blue-400 to-blue-600',
        )}
      />
      <span className={cn(
        'flex h-8 w-8 shrink-0 items-center justify-center rounded-full ring-1',
        isUrgent
          ? 'bg-amber-500/20 text-amber-700 ring-amber-500/40 dark:text-amber-200'
          : 'bg-blue-500/20 text-blue-700 ring-blue-500/40 dark:text-blue-200',
      )}>
        {isUrgent ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
        )}
      </span>
      <span className="min-w-0 flex-1 leading-tight">
        <span className="inline-block max-w-full truncate align-middle font-bold">
          {topAlert.competition_name}
        </span>
        <span className="mx-1 opacity-75">·</span>
        <span className="font-semibold">
          {topAlert.unit === 'HKD'
            ? t('alert.gap.hkd', { amount: topAlert.gap?.toLocaleString() ?? '—' })
            : t('alert.gap.unit', { amount: topAlert.gap ?? '—', unit: topAlert.unit })}
        </span>
        <span className="mx-1 opacity-75">·</span>
        <span className={cn('font-bold', isUrgent && 'text-red-600 dark:text-red-400')}>
          {t('alert.daysRemaining', { days: topAlert.days_remaining })}
        </span>
        {alerts.length > 1 && (
          <span className="ml-2 hidden text-[11px] opacity-70 sm:inline">
            +{alerts.length - 1}
          </span>
        )}
      </span>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md opacity-60 transition-all hover:bg-white/10 hover:opacity-100"
        aria-label={t('alert.dismiss.aria')}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  )
}
