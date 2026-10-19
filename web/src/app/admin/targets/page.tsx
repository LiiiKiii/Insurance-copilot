'use client'

import { useState, useEffect, useCallback } from 'react'
import { adminApi, PerformanceTarget } from '@/lib/admin/api'
import { useAdminAuth } from '@/lib/admin/auth'
import { useTranslation, LOCALE_BCP47, type MessageKey, type Locale } from '@/lib/i18n'

interface MetricOption {
  key: string
  labelKey: MessageKey
  unit?: string
  unitKey?: MessageKey
}

const METRIC_OPTIONS: MetricOption[] = [
  { key: 'protection_premium', labelKey: 'admin.targets.metric.protectionPremium', unit: 'Credit' },
  { key: 'submission_count',   labelKey: 'admin.targets.metric.submissionCount',   unitKey: 'admin.targets.unit.cases' },
  { key: 'conversion_rate',    labelKey: 'admin.targets.metric.conversionRate',    unit: '%' },
  { key: 'new_clients',        labelKey: 'admin.targets.metric.newClients',        unitKey: 'admin.targets.unit.persons' },
  { key: 'client_retention',   labelKey: 'admin.targets.metric.clientRetention',   unit: '%' },
  { key: 'ai_training_usage',  labelKey: 'admin.targets.metric.aiTrainingUsage',   unitKey: 'admin.targets.unit.times' },
]

function formatValue(v: number | null | undefined, unit: string, locale: Locale): string {
  if (v == null || Number.isNaN(v)) return '—'
  const bcp47 = LOCALE_BCP47[locale]
  if (unit === 'HKD') return `HKD ${v.toLocaleString(bcp47)}`
  if (unit === '%') return `${(v * 100).toFixed(1)}%`
  return `${v.toLocaleString(bcp47)} ${unit}`
}

export default function TargetsPage() {
  const { t, locale } = useTranslation()
  const { can } = useAdminAuth()
  const [targets, setTargets] = useState<PerformanceTarget[]>([])
  const [agents, setAgents] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [filterAgent, setFilterAgent] = useState<string>('')
  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState<string>('')
  const [form, setForm] = useState({
    agent_id: '', metric_key: 'protection_premium', target_value: '',
    period_start: '2026-01-01', period_end: '2026-12-31',
  })

  // Load agents from API
  useEffect(() => {
    adminApi.agents.list()
      .then(d => {
        if (d?.ok && Array.isArray(d.data)) {
          const ids = d.data.map((a: { agent_id: string }) => a.agent_id)
          setAgents(ids)
          if (ids.length > 0 && !form.agent_id) {
            setForm(f => ({ ...f, agent_id: ids[0] }))
          }
        }
      })
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await adminApi.targets.list(filterAgent || undefined)
      setTargets(Array.isArray(res) ? res : (res as { data?: PerformanceTarget[] }).data || [])
    } catch { setTargets([]) }
    setLoading(false)
  }, [filterAgent])

  useEffect(() => { load() }, [load])

  const resolveUnit = (mo: MetricOption | undefined): string => {
    if (!mo) return 'HKD'
    if (mo.unitKey) return t(mo.unitKey)
    return mo.unit || 'HKD'
  }

  const handleCreate = async () => {
    const mo = METRIC_OPTIONS.find(m => m.key === form.metric_key)
    try {
      await adminApi.targets.create({
        agent_id: form.agent_id,
        metric_key: form.metric_key,
        metric_label: mo ? t(mo.labelKey) : form.metric_key,
        target_value: parseFloat(form.target_value),
        unit: resolveUnit(mo),
        period_type: 'annual',
        period_start: form.period_start,
        period_end: form.period_end,
      })
      setShowCreate(false)
      setForm({ ...form, target_value: '' })
      load()
    } catch (e) {
      alert(e instanceof Error ? e.message : t('admin.targets.error.createFailed'))
    }
  }

  const handleInlineEdit = async (target: PerformanceTarget) => {
    const newVal = parseFloat(editValue)
    if (isNaN(newVal)) { setEditingId(null); return }
    try {
      await adminApi.targets.update(target.id, { target_value: newVal })
      setEditingId(null)
      load()
    } catch { setEditingId(null) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm(t('admin.targets.confirm.delete'))) return
    try {
      await adminApi.targets.delete(id)
      load()
    } catch { /* ignore */ }
  }

  const grouped = agents.reduce<Record<string, PerformanceTarget[]>>((acc, aid) => {
    acc[aid] = targets.filter(target => target.agent_id === aid)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 dark:text-white">{t('admin.targets.title')}</h1>
          <p className="text-sm text-slate-500 mt-1">{t('admin.targets.subtitle')}</p>
        </div>
        {can('admin') && <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          {t('admin.targets.button.add')}
        </button>}
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-500">{t('admin.targets.filter.label')}</span>
        <select
          value={filterAgent}
          onChange={e => setFilterAgent(e.target.value)}
          className="px-3 py-1.5 text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-800 text-slate-800 dark:text-white"
        >
          <option value="">{t('admin.targets.filter.all')}</option>
          {agents.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <span className="text-xs text-slate-400 ml-auto">{t('admin.targets.summary.count', { count: targets.length })}</span>
      </div>

      {loading ? (
        <div className="py-12 text-center text-slate-400">{t('admin.targets.loading')}</div>
      ) : (
        <div className="space-y-6">
          {(filterAgent ? [filterAgent] : agents).map(agentId => {
            const agentTargets = grouped[agentId] || []
            if (agentTargets.length === 0) return null
            return (
              <div key={agentId} className="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
                <div className="bg-slate-50 dark:bg-slate-800/80 px-4 py-3 border-b border-slate-200 dark:border-slate-700">
                  <span className="font-semibold text-sm text-slate-700 dark:text-slate-200">{agentId}</span>
                  <span className="text-xs text-slate-400 ml-2">{t('admin.targets.group.metricCount', { count: agentTargets.length })}</span>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-900">
                      <th className="text-left px-4 py-2 font-medium">{t('admin.targets.col.metric')}</th>
                      <th className="text-right px-4 py-2 font-medium">{t('admin.targets.col.targetValue')}</th>
                      <th className="text-center px-4 py-2 font-medium">{t('admin.targets.col.unit')}</th>
                      <th className="text-center px-4 py-2 font-medium">{t('admin.targets.col.period')}</th>
                      {can('admin') && <th className="text-right px-4 py-2 font-medium">{t('admin.targets.col.actions')}</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {agentTargets.map(target => (
                      <tr key={target.id} className="border-t border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/30">
                        <td className="px-4 py-3 text-slate-700 dark:text-slate-200">
                          {target.metric_label || target.metric_key}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {editingId === target.id ? (
                            <input
                              type="number"
                              value={editValue}
                              onChange={e => setEditValue(e.target.value)}
                              onBlur={() => handleInlineEdit(target)}
                              onKeyDown={e => e.key === 'Enter' && handleInlineEdit(target)}
                              autoFocus
                              className="w-32 px-2 py-1 text-right text-sm border border-blue-400 rounded bg-white dark:bg-slate-800 text-slate-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                          ) : can('admin') ? (
                            <button
                              onClick={() => { setEditingId(target.id); setEditValue(String(target.target_value)) }}
                              className="group/edit inline-flex items-center gap-1.5 font-mono font-bold text-slate-800 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors cursor-pointer"
                              title={t('admin.targets.action.editHint')}
                            >
                              {formatValue(target.target_value, target.unit, locale)}
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="opacity-0 group-hover/edit:opacity-60 transition-opacity"><path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>
                            </button>
                          ) : (
                            <span className="font-mono font-bold text-slate-800 dark:text-white">{formatValue(target.target_value, target.unit, locale)}</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center text-slate-500">{target.unit}</td>
                        <td className="px-4 py-3 text-center text-xs text-slate-400">{target.period_start} ~ {target.period_end}</td>
                        {can('admin') && <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => handleDelete(target.id)}
                            className="text-red-500 hover:text-red-700 transition-colors p-1"
                            title={t('admin.targets.action.delete')}
                          >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                          </button>
                        </td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          })}
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setShowCreate(false)}>
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
            <h2 className="text-lg font-bold text-slate-800 dark:text-white mb-4">{t('admin.targets.modal.create.title')}</h2>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">{t('admin.targets.field.agent')}</label>
                <select value={form.agent_id} onChange={e => setForm({...form, agent_id: e.target.value})}
                  className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-900 text-slate-800 dark:text-white">
                  {agents.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">{t('admin.targets.field.metric')}</label>
                <select value={form.metric_key} onChange={e => setForm({...form, metric_key: e.target.value})}
                  className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-900 text-slate-800 dark:text-white">
                  {METRIC_OPTIONS.map(m => <option key={m.key} value={m.key}>{t(m.labelKey)}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">{t('admin.targets.field.targetValue')}</label>
                <input type="number" value={form.target_value} onChange={e => setForm({...form, target_value: e.target.value})}
                  placeholder={t('admin.targets.field.targetValue.placeholder')}
                  className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-900 text-slate-800 dark:text-white" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-500 mb-1">{t('admin.targets.field.periodStart')}</label>
                  <input type="date" value={form.period_start} onChange={e => setForm({...form, period_start: e.target.value})}
                    className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-900 text-slate-800 dark:text-white" />
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1">{t('admin.targets.field.periodEnd')}</label>
                  <input type="date" value={form.period_end} onChange={e => setForm({...form, period_end: e.target.value})}
                    className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-900 text-slate-800 dark:text-white" />
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors">{t('admin.targets.button.cancel')}</button>
              <button onClick={handleCreate} disabled={!form.target_value} className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">{t('admin.targets.button.create')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
