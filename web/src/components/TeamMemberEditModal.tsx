'use client'

import { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/i18n'

/* ─── Types ─── */

interface Target {
  id: string
  agent_id: string
  metric_key: string
  metric_label: string
  target_value: number
  unit: string
}

interface Metric {
  current: number
  target: number
  unit: string
  rate?: number
}

interface AgentCompetition {
  entry_id: string
  competition_id: string
  competition_name: string
  target_metric: string
  competition_target: number
  current_value: number
  gap: number
  unit: string
  deadline: string
  days_remaining: number
  status: string
}

interface AllCompetition {
  id: string
  name: string
  type: string
  target_metric: string
  target_value: number | null
  unit: string
  deadline: string
}

interface Props {
  agentId: string
  callerAgentId: string
  memberName: string
  onClose: () => void
  onSave: () => void
}

/* ─── SVG Icons ─── */

function IconX({ className }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  )
}

function IconSave({ className }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
    </svg>
  )
}

function IconSpinner({ className }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={cn('animate-spin', className)}>
      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
    </svg>
  )
}

/* ─── Helpers ─── */

function formatVal(v: number, unit: string): string {
  if (unit === 'HKD') return v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : v >= 1000 ? `${(v / 1000).toFixed(0)}K` : String(v)
  if (unit === '%') return `${(v * 100).toFixed(1)}%`
  return String(v)
}

function formatHKD(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toLocaleString()
}

/* ─── Component ─── */

export function TeamMemberEditModal({ agentId, callerAgentId, memberName, onClose, onSave }: Props) {
  const { t } = useTranslation()
  const [targets, setTargets] = useState<Target[]>([])
  const [metrics, setMetrics] = useState<Record<string, Metric>>({})
  const [editedTargets, setEditedTargets] = useState<Record<string, string>>({})
  const [agentComps, setAgentComps] = useState<AgentCompetition[]>([])
  const [allComps, setAllComps] = useState<AllCompetition[]>([])
  const [editedCompValues, setEditedCompValues] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [enrolling, setEnrolling] = useState<string | null>(null)

  // Load all data
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([
      fetch(`/api/targets?agent_id=${agentId}`).then(r => r.json()).catch(() => ({ data: [] })),
      fetch(`/api/performance?agent_id=${agentId}`).then(r => r.json()).catch(() => ({ metrics: {} })),
      fetch(`/api/agent-competitions?agent_id=${agentId}`).then(r => r.json()).catch(() => ({ data: [] })),
      fetch(`/api/all-competitions`).then(r => r.json()).catch(() => ({ data: [] })),
    ]).then(([tData, pData, acData, allCData]) => {
      if (cancelled) return
      setTargets(Array.isArray(tData.data) ? tData.data : [])
      setMetrics(pData.metrics || {})
      setAgentComps(Array.isArray(acData.data) ? acData.data : [])
      setAllComps(Array.isArray(allCData.data) ? allCData.data : [])
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [agentId])

  // ESC to close
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const enrolledCompIds = new Set(agentComps.map(ac => ac.competition_id))

  const handleToggleCompetition = async (comp: AllCompetition) => {
    const existing = agentComps.find(ac => ac.competition_id === comp.id)
    setEnrolling(comp.id)
    try {
      if (existing) {
        // Remove
        await fetch(`/api/agent-competitions/${existing.entry_id}`, { method: 'DELETE' })
        setAgentComps(prev => prev.filter(ac => ac.entry_id !== existing.entry_id))
      } else {
        // Add
        const res = await fetch('/api/agent-competitions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ agent_id: agentId, competition_id: comp.id }),
        }).then(r => r.json())
        if (res.ok) {
          // Reload agent competitions to get full data
          const acRes = await fetch(`/api/agent-competitions?agent_id=${agentId}`).then(r => r.json())
          if (acRes?.ok && Array.isArray(acRes?.data)) setAgentComps(acRes.data)
        }
      }
    } catch { /* ignore */ }
    setEnrolling(null)
  }

  const handleSaveAll = async () => {
    setSaving(true)
    try {
      // Save edited targets
      const targetPromises = Object.entries(editedTargets).map(([targetId, val]) => {
        const numVal = parseFloat(val)
        if (isNaN(numVal)) return Promise.resolve()
        return fetch(`/api/targets/${targetId}?agent_id=${callerAgentId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_value: numVal }),
        })
      })
      // Save edited competition current values
      const compPromises = Object.entries(editedCompValues).map(([entryId, val]) => {
        const numVal = parseFloat(val)
        if (isNaN(numVal)) return Promise.resolve()
        return fetch(`/api/agent-competitions/${entryId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ current_value: numVal }),
        })
      })
      await Promise.all([...targetPromises, ...compPromises])
      onSave()
      onClose()
    } catch { /* ignore */ }
    setSaving(false)
  }

  const hasChanges = Object.keys(editedTargets).length > 0 || Object.keys(editedCompValues).length > 0

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
        <div className="relative z-10 bg-white dark:bg-slate-900 rounded-xl p-8 shadow-xl">
          <IconSpinner className="w-6 h-6 text-blue-500 mx-auto" />
          <p className="text-sm text-slate-500 mt-2">{t('team.loading')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      {/* panel */}
      <div className="relative z-10 w-full max-w-2xl rounded-xl bg-white dark:bg-slate-900 shadow-xl border border-slate-200/60 dark:border-slate-700/50 flex flex-col max-h-[90vh]">
        {/* header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200/60 dark:border-slate-700/50 shrink-0">
          <h2 className="font-semibold text-slate-900 dark:text-white text-base">
            {t('team.title', { name: memberName })}
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <IconX />
          </button>
        </div>

        {/* body */}
        <div className="overflow-y-auto flex-1 px-6 py-4 space-y-6">
          {/* Section A: Performance Targets */}
          <div>
            <h3 className="text-sm font-semibold text-slate-800 dark:text-white mb-3 flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-500">
                <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>
              </svg>
              {t('team.targets.heading')}
            </h3>
            {targets.length > 0 ? (
              <div className="rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400">
                      <th className="text-left px-3 py-2">{t('team.targets.col.metric')}</th>
                      <th className="text-right px-3 py-2">{t('team.targets.col.current')}</th>
                      <th className="text-right px-3 py-2">{t('team.targets.col.target')}</th>
                      <th className="text-center px-3 py-2">{t('team.targets.col.unit')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {targets.map(t => {
                      const m = metrics[t.metric_key]
                      const current = m?.current ?? 0
                      const editVal = editedTargets[t.id]
                      const displayTarget = editVal !== undefined ? editVal : String(t.target_value)
                      return (
                        <tr key={t.id} className="border-t border-slate-100 dark:border-slate-800">
                          <td className="px-3 py-2 text-slate-700 dark:text-slate-200">
                            {t.metric_label || t.metric_key}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-slate-600 dark:text-slate-300">
                            {formatVal(current, t.unit)}
                          </td>
                          <td className="px-3 py-2 text-right">
                            <input
                              type="number"
                              value={displayTarget}
                              onChange={e => setEditedTargets(prev => ({ ...prev, [t.id]: e.target.value }))}
                              className="w-24 px-2 py-1 text-right text-xs border border-slate-200 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-800 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
                            />
                          </td>
                          <td className="px-3 py-2 text-center text-slate-400">{t.unit}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-xs text-slate-400 text-center py-4 border border-dashed border-slate-200 dark:border-slate-700 rounded-lg">
                {t('team.targets.empty')}
              </div>
            )}
          </div>

          {/* Section B: Competition Management */}
          <div>
            <h3 className="text-sm font-semibold text-slate-800 dark:text-white mb-3 flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-amber-500">
                <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>
              </svg>
              {t('team.competitions.heading')}
            </h3>

            {/* Competition checkbox list */}
            <div className="mb-4 space-y-1.5 max-h-40 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-700 p-2">
              {allComps.length === 0 && (
                <div className="text-xs text-slate-400 text-center py-2">{t('team.competitions.empty')}</div>
              )}
              {allComps.map(comp => {
                const enrolled = enrolledCompIds.has(comp.id)
                const isEnrolling = enrolling === comp.id
                return (
                  <label
                    key={comp.id}
                    className={cn(
                      'flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg cursor-pointer transition-colors text-xs',
                      enrolled
                        ? 'bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300'
                        : 'hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={enrolled}
                      onChange={() => handleToggleCompetition(comp)}
                      disabled={isEnrolling}
                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                    />
                    {isEnrolling ? (
                      <IconSpinner className="w-3 h-3 text-blue-500" />
                    ) : null}
                    <span className="flex-1 truncate font-medium">{comp.name}</span>
                    <span className="text-[10px] text-slate-400 shrink-0">{comp.deadline}</span>
                  </label>
                )
              })}
            </div>

            {/* Enrolled competitions detail */}
            {agentComps.length > 0 && (
              <div className="space-y-2">
                <div className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-500 px-1">
                  {t('team.competitions.joined.heading', { count: agentComps.length })}
                </div>
                {agentComps.map(ac => {
                  const editVal = editedCompValues[ac.entry_id]
                  const displayCurrent = editVal !== undefined ? editVal : String(ac.current_value)
                  const currentNum = editVal !== undefined ? (parseFloat(editVal) || 0) : ac.current_value
                  const progress = ac.competition_target > 0
                    ? Math.min((currentNum / ac.competition_target) * 100, 100)
                    : 0
                  const gap = ac.competition_target - currentNum
                  return (
                    <div
                      key={ac.entry_id}
                      className="rounded-lg border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-800/30 p-3"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-medium text-slate-800 dark:text-white">{ac.competition_name}</span>
                        <span className={cn(
                          'text-xs font-mono font-bold tabular-nums',
                          ac.days_remaining <= 14 ? 'text-red-600 dark:text-red-400' :
                          ac.days_remaining <= 30 ? 'text-amber-600 dark:text-amber-400' :
                          'text-slate-500'
                        )}>
                          {t('team.competitions.daysRemaining', { days: ac.days_remaining })}
                        </span>
                      </div>
                      {/* Editable current value row */}
                      <div className="flex items-center gap-3 text-[11px]">
                        <span className="text-slate-500 dark:text-slate-400 shrink-0">{t('team.competitions.currentValue')}</span>
                        <input
                          type="number"
                          value={displayCurrent}
                          onChange={e => setEditedCompValues(prev => ({ ...prev, [ac.entry_id]: e.target.value }))}
                          className="w-24 px-2 py-1 text-right text-xs border border-slate-200 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-800 dark:text-white focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono"
                        />
                        <span className="text-slate-400">/ {formatHKD(ac.competition_target)} {ac.unit}</span>
                        {gap > 0 ? (
                          <span className="text-red-500 font-medium">
                            {ac.unit === 'HKD'
                              ? t('team.competitions.gap.hkd', { amount: formatHKD(gap) })
                              : t('team.competitions.gap.unit', { amount: formatHKD(gap) })}
                          </span>
                        ) : (
                          <span className="text-emerald-500 font-medium">{t('team.competitions.met')}</span>
                        )}
                      </div>
                      {/* Progress bar */}
                      <div className="mt-2 h-1.5 bg-slate-100 dark:bg-slate-700/50 rounded-full overflow-hidden">
                        <div
                          className={cn('h-full rounded-full transition-all',
                            progress >= 80 ? 'bg-emerald-500' : progress >= 50 ? 'bg-amber-500' : 'bg-red-500'
                          )}
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                      <div className="text-right text-[9px] text-slate-400 mt-0.5 font-mono">{progress.toFixed(1)}%</div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {/* footer */}
        <div className="shrink-0 flex justify-end gap-2 px-6 py-4 border-t border-slate-200/60 dark:border-slate-700/50">
          <button
            onClick={onClose}
            className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          >
            {t('common.cancel')}
          </button>
          <button
            onClick={handleSaveAll}
            disabled={saving || !hasChanges}
            className={cn(
              'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors cursor-pointer',
              hasChanges
                ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                : 'bg-slate-200 dark:bg-slate-700 text-slate-400 dark:text-slate-500 cursor-not-allowed',
            )}
          >
            {saving ? <IconSpinner className="w-4 h-4" /> : <IconSave />}
            {saving ? t('team.button.saving') : t('team.button.save')}
          </button>
        </div>
      </div>
    </div>
  )
}
