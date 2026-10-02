'use client'

import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/i18n'

interface Metric {
  label: string
  current: number | string | null
  target: number | null
  rate: number | null
  unit: string
}

interface Assessment {
  subject: string
  target_value: number | null
  current_value: number | null
  status: string | null
  remark: string | null
}

interface PerformanceTabProps {
  agentId: string
}

function formatHKD(n: number | null | undefined): string {
  if (n == null) return '—'
  return `HKD ${n.toLocaleString()}`
}

function formatNum(n: number | null | undefined, unit?: string): string {
  if (n == null) return '—'
  return unit ? `${n.toLocaleString()} ${unit}` : n.toLocaleString()
}

/* ─── Section Card ─── */

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white dark:bg-slate-800/50 overflow-hidden">
      <div className="px-3 py-2 bg-slate-50 dark:bg-slate-800/80 border-b border-slate-200/70 dark:border-slate-700/50">
        <span className="text-[11px] font-semibold text-slate-600 dark:text-slate-300 tracking-wide">{title}</span>
      </div>
      <div className="p-3">{children}</div>
    </div>
  )
}

/* ─── Status Badge ─── */

function StatusBadge({ status }: { status: string | null }) {
  const isPass = status === 'Achieved' || status === 'Met'
  return (
    <span className={cn(
      'text-[10px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap',
      isPass
        ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'
        : 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400'
    )}>
      {status || '—'}
    </span>
  )
}

/* ─── KV Row ─── */

function KVRow({ label, value, highlight }: { label: string; value: string; highlight?: 'green' | 'red' | 'amber' }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-700/30 last:border-0">
      <span className="text-xs text-slate-500 dark:text-slate-400">{label}</span>
      <span className={cn(
        'text-sm font-semibold font-mono',
        highlight === 'green' ? 'text-emerald-600 dark:text-emerald-400' :
        highlight === 'red' ? 'text-red-600 dark:text-red-400' :
        highlight === 'amber' ? 'text-amber-600 dark:text-amber-400' :
        'text-slate-800 dark:text-white'
      )}>
        {value}
      </span>
    </div>
  )
}

/* ─── Main Component ─── */

export function PerformanceTab({ agentId }: PerformanceTabProps) {
  const { t } = useTranslation()
  const [metrics, setMetrics] = useState<Record<string, Metric>>({})
  const [assessments, setAssessments] = useState<Assessment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!agentId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    fetch(`/api/performance?agent_id=${agentId}`, {})
      .then(r => r.json())
      .then(data => {
        if (cancelled) return
        if (data.error) { setError(data.error); setLoading(false); return }
        setMetrics(data.metrics || {})
        setAssessments(data.assessments || [])
        setLoading(false)
      })
      .catch(() => { if (!cancelled) { setError(t('tab.performance.error')); setLoading(false) } })
    return () => { cancelled = true }
  }, [agentId, t])

  if (loading) {
    return (
      <div className="p-4 space-y-3">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="animate-pulse h-24 bg-slate-100 dark:bg-slate-800 rounded-xl" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-32 text-red-500 text-sm px-4">
        {error}
      </div>
    )
  }

  const m = (key: string) => metrics[key] || {}

  return (
    <div className="p-3 space-y-3">

      {/* ── 1. Core targets (assessment) ── */}
      <SectionCard title={t('tab.performance.section.coreTargets')}>
        {assessments.length === 0 ? (
          <p className="text-xs text-slate-400 py-2">{t('tab.performance.empty.assessment')}</p>
        ) : (
          <div className="space-y-3">
            {assessments.map((a, idx) => {
              const target = a.target_value || 0
              const current = a.current_value || 0
              const rate = target > 0 ? Math.min(current / target, 1) : 0
              return (
                <div key={idx} className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-700 dark:text-slate-200 font-medium">{a.subject}</span>
                    <StatusBadge status={a.status} />
                  </div>
                  <div className="h-1.5 bg-slate-100 dark:bg-slate-700/50 rounded-full overflow-hidden">
                    <div
                      className={cn(
                        'h-full rounded-full transition-all duration-500',
                        rate >= 1 ? 'bg-emerald-500' : rate >= 0.8 ? 'bg-amber-500' : 'bg-red-500'
                      )}
                      style={{ width: `${rate * 100}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] text-slate-400">
                    <span>{t('metric.current')} {formatHKD(current)}</span>
                    <span>{t('metric.target')} {formatHKD(target)}</span>
                  </div>
                  {a.remark && <p className="text-[10px] text-slate-400">{a.remark}</p>}
                </div>
              )
            })}
          </div>
        )}
      </SectionCard>

      {/* ── 2. Sales & productivity ── */}
      <SectionCard title={t('tab.performance.section.salesProductivity')}>
        <div className="space-y-0">
          <KVRow label={t('tab.performance.metric.policyCount')} value={formatNum(m('policy_count').current as number, t('metric.unit.items'))} />
          <KVRow label={t('tab.performance.metric.submissionCount')} value={formatNum(m('submission_count').current as number, t('metric.unit.items'))} />
          <KVRow label={t('tab.performance.metric.quarterFyc')} value={formatHKD(m('quarter_fyc').current as number)} />
          <KVRow label={t('tab.performance.metric.fyc')} value={formatHKD(m('fyc').current as number)} />
          <KVRow label={t('tab.performance.metric.dailyFyc')} value={formatHKD(m('daily_fyc').current as number)} />
        </div>
      </SectionCard>

      {/* ── 3. Clients & renewals ── */}
      <SectionCard title={t('tab.performance.section.clients')}>
        {(() => {
          const retentionVal = m('client_retention').current as number | null
          const churnVal = m('churn_rate').current as number | null
          const retentionHighlight = retentionVal != null ? (retentionVal >= 0.9 ? 'green' : retentionVal >= 0.8 ? 'amber' : 'red') : undefined
          const churnHighlight = churnVal != null ? (churnVal <= 0.03 ? 'green' : churnVal <= 0.05 ? 'amber' : 'red') : undefined
          return (
            <div className="space-y-0">
              <KVRow label={t('tab.performance.metric.totalClients')} value={formatNum(m('total_clients').current as number, t('metric.unit.persons'))} />
              <KVRow label={t('tab.performance.metric.newClients')} value={formatNum(m('new_clients').current as number, t('metric.unit.persons'))} />
              <KVRow label={t('tab.performance.metric.churnClients')} value={formatNum(m('churn_clients').current as number, t('metric.unit.persons'))} />
              <KVRow label={t('tab.performance.metric.churnRate')} value={churnVal != null ? `${(churnVal * 100).toFixed(1)}%` : '—'} highlight={churnHighlight} />
              <KVRow label={t('tab.performance.metric.renewalDue')} value={formatNum(m('renewal_due_clients').current as number, t('metric.unit.persons'))} />
              <KVRow label={t('tab.performance.metric.retentionRate')} value={retentionVal != null ? `${(retentionVal * 100).toFixed(1)}%` : '—'} highlight={retentionHighlight} />
            </div>
          )
        })()}
      </SectionCard>

      {/* ── 4. Learning & compliance ── */}
      <SectionCard title={t('tab.performance.section.learning')}>
        {(() => {
          const aiRate = m('ai_practice_rate').current as number | null
          const aiUsage = m('ai_training_usage').current as number | null
          const university = m('online_university').current as string | null
          const uniPass = university === 'Completed'
          return (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500 dark:text-slate-400">{t('tab.performance.metric.aiTraining')}</span>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold font-mono text-slate-800 dark:text-white">
                    {aiRate != null ? `${(aiRate * 100).toFixed(0)}%` : '—'}
                  </span>
                  {aiUsage != null && (
                    <span className="text-[10px] text-slate-400">{t('tab.performance.metric.aiUsage', { count: aiUsage })}</span>
                  )}
                </div>
              </div>
              {aiRate != null && (
                <div className="h-1.5 bg-slate-100 dark:bg-slate-700/50 rounded-full overflow-hidden">
                  <div
                    className={cn(
                      'h-full rounded-full transition-all duration-500',
                      aiRate >= 0.9 ? 'bg-emerald-500' : aiRate >= 0.7 ? 'bg-amber-500' : 'bg-red-500'
                    )}
                    style={{ width: `${Math.min(aiRate * 100, 100)}%` }}
                  />
                </div>
              )}
              <div className="flex items-center justify-between pt-1">
                <span className="text-xs text-slate-500 dark:text-slate-400">{t('tab.performance.metric.university')}</span>
                <span className={cn(
                  'text-[11px] font-medium px-2 py-0.5 rounded-full',
                  uniPass
                    ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'
                    : 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400'
                )}>
                  {university || '—'}
                </span>
              </div>
            </div>
          )
        })()}
      </SectionCard>
    </div>
  )
}
