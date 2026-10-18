'use client'

import { useCallback, useEffect, useState } from 'react'
import { useAdminAuth } from '@/lib/admin/auth'
import { Modal, FormField, inputCls, btnPrimary, btnSecondary } from '@/components/admin/Modal'
import { Badge } from '@/components/admin/Badge'
import {
  SpinnerIcon, PlayIcon, CheckIcon, PlusIcon, PencilIcon, TrashIcon, RefreshIcon,
} from '@/components/admin/AdminIcons'
import {
  fetchBriefingSettings,
  updateBriefingSettings,
  warmupBriefingNow,
  fetchTenantAgents,
  listAdminMessages,
  createAdminMessage,
  updateAdminMessage,
  deleteAdminMessage,
  type BriefingSettings,
  type TenantAgent,
  type AdminInboxMessage,
  type AdminMessageCreate,
} from '@/lib/briefingApi'
import { useTranslation, LOCALE_BCP47 } from '@/lib/i18n'

type PriorityFilter = '' | 'P0' | 'P1' | 'P2'

interface MessageFormState {
  target_agent_id: string
  priority: 'P0' | 'P1' | 'P2'
  category: string
  notification_name: string
  receiver_type: string
  raw_content: string
  policy_no: string
  customer_id: string
  customer_name: string
  classify_reason: string
  channel: string
  external_id: string
}

const EMPTY_FORM: MessageFormState = {
  target_agent_id: '',
  priority: 'P0',
  category: '',
  notification_name: '',
  receiver_type: 'Client',
  raw_content: '',
  policy_no: '',
  customer_id: '',
  customer_name: '',
  classify_reason: '',
  channel: 'sms',
  external_id: '',
}

function priorityBadge(p: string) {
  if (p === 'P0') return <Badge variant="error" label="P0" />
  if (p === 'P1') return <Badge variant="warning" label="P1" />
  return <Badge variant="info" label="P2" />
}

export default function BriefingSettingsPage() {
  const { t, locale } = useTranslation()
  const { user } = useAdminAuth()
  const username = user?.username || ''

  // ── settings ──
  const [settings, setSettings] = useState<BriefingSettings | null>(null)
  const [settingsLoading, setSettingsLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [okMsg, setOkMsg] = useState<string | null>(null)

  const flashOk = (msg: string) => {
    setOkMsg(msg)
    setTimeout(() => setOkMsg(null), 2500)
  }

  const loadSettings = useCallback(async () => {
    if (!username) return
    setSettingsLoading(true)
    setError(null)
    try {
      setSettings(await fetchBriefingSettings(username))
    } catch (e) { setError((e as Error).message) }
    finally { setSettingsLoading(false) }
  }, [username])

  useEffect(() => { loadSettings() }, [loadSettings])

  const updateSettingsLocal = (patch: Partial<BriefingSettings>) => {
    if (!settings) return
    setSettings({ ...settings, ...patch })
  }

  const saveSettings = async () => {
    if (!settings) return
    setSaving(true); setError(null)
    try {
      const updated = await updateBriefingSettings(username, {
        auto_generate_enabled: settings.auto_generate_enabled,
        auto_generate_time: settings.auto_generate_time,
        auto_generate_scope: settings.auto_generate_scope,
        min_messages_to_generate: settings.min_messages_to_generate,
      })
      setSettings(updated)
      flashOk(t('admin.briefing.toast.saved'))
    } catch (e) { setError((e as Error).message) }
    finally { setSaving(false) }
  }

  const runNow = async () => {
    setRunning(true); setError(null)
    try {
      const r = await warmupBriefingNow(username)
      flashOk(t('admin.briefing.toast.runDone', {
        generated: r.generated,
        skipped: r.skipped,
        failed: r.failed,
        total: r.agents_total,
      }))
      await loadSettings()
    } catch (e) { setError((e as Error).message) }
    finally { setRunning(false) }
  }

  // ── agents ──
  const [agents, setAgents] = useState<TenantAgent[]>([])
  useEffect(() => {
    if (!username) return
    fetchTenantAgents(username)
      .then((r) => setAgents(r.agents))
      .catch((e) => setError((e as Error).message))
  }, [username])

  // ── messages list ──
  const [messages, setMessages] = useState<AdminInboxMessage[]>([])
  const [total, setTotal] = useState(0)
  const [msgLoading, setMsgLoading] = useState(false)
  const [filterAgent, setFilterAgent] = useState('')
  const [filterPriority, setFilterPriority] = useState<PriorityFilter>('')
  const [filterSource, setFilterSource] = useState('')
  const [limit] = useState(50)
  const [offset, setOffset] = useState(0)

  const reloadMessages = useCallback(async () => {
    if (!username) return
    setMsgLoading(true); setError(null)
    try {
      const r = await listAdminMessages(username, {
        target_agent_id: filterAgent || undefined,
        priority: filterPriority || undefined,
        source_system: filterSource || undefined,
        limit,
        offset,
      })
      setMessages(r.items)
      setTotal(r.total)
    } catch (e) { setError((e as Error).message) }
    finally { setMsgLoading(false) }
  }, [username, filterAgent, filterPriority, filterSource, limit, offset])

  useEffect(() => { reloadMessages() }, [reloadMessages])

  // ── create/edit modal ──
  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<MessageFormState>(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)

  const openCreate = () => {
    setEditingId(null)
    setForm({ ...EMPTY_FORM, target_agent_id: filterAgent || agents[0]?.username || '' })
    setModalOpen(true)
  }

  const openEdit = (m: AdminInboxMessage) => {
    setEditingId(m.id)
    setForm({
      target_agent_id: m.agent_id,
      priority: m.priority,
      category: m.category,
      notification_name: m.notification_name,
      receiver_type: m.receiver_type,
      raw_content: m.raw_content,
      policy_no: m.policy_no || '',
      customer_id: m.customer_id || '',
      customer_name: m.customer_name || '',
      classify_reason: m.classify_reason || '',
      channel: m.channel,
      external_id: m.external_id,
    })
    setModalOpen(true)
  }

  const submitForm = async () => {
    setSubmitting(true); setError(null)
    try {
      if (editingId) {
        await updateAdminMessage(username, editingId, {
          priority: form.priority,
          category: form.category,
          notification_name: form.notification_name,
          receiver_type: form.receiver_type,
          raw_content: form.raw_content,
          policy_no: form.policy_no || null,
          customer_id: form.customer_id || null,
          customer_name: form.customer_name || null,
          classify_reason: form.classify_reason || null,
          channel: form.channel,
        })
        flashOk(t('admin.briefing.toast.updated'))
      } else {
        const payload: AdminMessageCreate = {
          target_agent_id: form.target_agent_id,
          priority: form.priority,
          category: form.category,
          notification_name: form.notification_name,
          receiver_type: form.receiver_type,
          raw_content: form.raw_content,
          policy_no: form.policy_no || null,
          customer_id: form.customer_id || null,
          customer_name: form.customer_name || null,
          classify_reason: form.classify_reason || null,
          channel: form.channel,
          external_id: form.external_id || null,
          source_system: 'manual',
        }
        await createAdminMessage(username, payload)
        flashOk(t('admin.briefing.toast.created'))
      }
      setModalOpen(false)
      await reloadMessages()
    } catch (e) { setError((e as Error).message) }
    finally { setSubmitting(false) }
  }

  const [deletingId, setDeletingId] = useState<string | null>(null)
  const handleDelete = async (m: AdminInboxMessage) => {
    if (!confirm(t('admin.briefing.confirm.delete', { name: m.notification_name }))) return
    setDeletingId(m.id); setError(null)
    try {
      await deleteAdminMessage(username, m.id)
      flashOk(t('admin.briefing.toast.deleted'))
      await reloadMessages()
    } catch (e) { setError((e as Error).message) }
    finally { setDeletingId(null) }
  }

  // ── render ──
  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{t('admin.briefing.title')}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{t('admin.briefing.subtitle')}</p>
        </div>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg border border-rose-200/60 dark:border-rose-900/40 bg-rose-50 dark:bg-rose-950/30 text-rose-600 text-sm">
          {error}
        </div>
      )}
      {okMsg && (
        <div className="mb-4 px-4 py-3 rounded-lg border border-emerald-200/60 dark:border-emerald-900/40 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 text-sm">
          {okMsg}
        </div>
      )}

      <div className="flex flex-col gap-4">
        {/* Main settings card */}
        <div className="rounded-xl border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-900 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
            <code className="text-xs font-semibold text-insurance-blue dark:text-blue-400 bg-insurance-blue/8 dark:bg-insurance-blue/20 px-2 py-0.5 rounded">briefing.*</code>
            <span className="text-xs text-slate-400">{t('admin.briefing.section.warmupCaption')}</span>
          </div>

          {settingsLoading || !settings ? (
            <div className="p-5 space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-12 rounded-lg bg-slate-200 dark:bg-slate-800 animate-pulse" />
              ))}
            </div>
          ) : (
            <>
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                <div className="grid grid-cols-[2fr_3fr] gap-4 px-5 py-4 items-center">
                  <div>
                    <code className="text-xs text-slate-700 dark:text-slate-300">auto_generate_enabled</code>
                    <p className="text-xs text-slate-400 mt-0.5">{t('admin.briefing.field.autoEnabled.desc')}</p>
                  </div>
                  <label className="inline-flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={settings.auto_generate_enabled}
                      onChange={(e) => updateSettingsLocal({ auto_generate_enabled: e.target.checked })}
                      className="w-4 h-4 rounded border-slate-300 dark:border-slate-600 text-insurance-blue focus:ring-insurance-blue/30 cursor-pointer"
                    />
                    <span className={`text-sm ${settings.auto_generate_enabled ? 'text-emerald-600' : 'text-slate-400'}`}>
                      {settings.auto_generate_enabled ? t('admin.briefing.field.autoEnabled.on') : t('admin.briefing.field.autoEnabled.off')}
                    </span>
                  </label>
                </div>

                <div className="grid grid-cols-[2fr_3fr] gap-4 px-5 py-4 items-center">
                  <div>
                    <code className="text-xs text-slate-700 dark:text-slate-300">auto_generate_time</code>
                    <p className="text-xs text-slate-400 mt-0.5">{t('admin.briefing.field.autoTime.desc')}</p>
                  </div>
                  <input
                    type="time"
                    value={settings.auto_generate_time}
                    onChange={(e) => updateSettingsLocal({ auto_generate_time: e.target.value })}
                    className={`${inputCls} max-w-[160px]`}
                  />
                </div>

                <div className="grid grid-cols-[2fr_3fr] gap-4 px-5 py-4 items-center">
                  <div>
                    <code className="text-xs text-slate-700 dark:text-slate-300">auto_generate_scope</code>
                    <p className="text-xs text-slate-400 mt-0.5">{t('admin.briefing.field.autoScope.desc')}</p>
                  </div>
                  <select
                    value={settings.auto_generate_scope}
                    onChange={(e) => updateSettingsLocal({ auto_generate_scope: e.target.value as BriefingSettings['auto_generate_scope'] })}
                    className={`${inputCls} max-w-[240px] cursor-pointer`}
                  >
                    <option value="all">{t('admin.briefing.field.autoScope.all')}</option>
                    <option value="active_7d">{t('admin.briefing.field.autoScope.active7d')}</option>
                    <option value="active_30d">{t('admin.briefing.field.autoScope.active30d')}</option>
                  </select>
                </div>

                <div className="grid grid-cols-[2fr_3fr] gap-4 px-5 py-4 items-center">
                  <div>
                    <code className="text-xs text-slate-700 dark:text-slate-300">min_messages_to_generate</code>
                    <p className="text-xs text-slate-400 mt-0.5">{t('admin.briefing.field.minMessages.desc')}</p>
                  </div>
                  <input
                    type="number"
                    min={0}
                    value={settings.min_messages_to_generate}
                    onChange={(e) => updateSettingsLocal({ min_messages_to_generate: parseInt(e.target.value) || 0 })}
                    className={`${inputCls} max-w-[120px]`}
                  />
                </div>
              </div>

              <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800 flex items-center gap-3 bg-slate-50/50 dark:bg-slate-800/30">
                <button onClick={saveSettings} disabled={saving} className={btnPrimary}>
                  {saving ? <SpinnerIcon size={14} /> : <CheckIcon size={14} />}
                  {saving ? t('admin.briefing.button.saving') : t('admin.briefing.button.save')}
                </button>
                <button onClick={runNow} disabled={running} className={btnSecondary}>
                  {running ? <SpinnerIcon size={14} /> : <PlayIcon size={14} />}
                  {running ? t('admin.briefing.button.running') : t('admin.briefing.button.runNow')}
                </button>
              </div>
            </>
          )}
        </div>

        {/* Last run card */}
        {settings?.last_run_at && (
          <div className="rounded-xl border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-900 overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
              <code className="text-xs font-semibold text-insurance-blue dark:text-blue-400 bg-insurance-blue/8 dark:bg-insurance-blue/20 px-2 py-0.5 rounded">last_run.*</code>
              <span className="text-xs text-slate-400">{t('admin.briefing.section.lastRunCaption')}</span>
            </div>
            <div className="divide-y divide-slate-100 dark:divide-slate-800 text-sm">
              <div className="grid grid-cols-[2fr_3fr] gap-4 px-5 py-3">
                <code className="text-xs text-slate-700 dark:text-slate-300">last_run_at</code>
                <span className="text-slate-700 dark:text-slate-300 font-mono text-xs">{settings.last_run_at}</span>
              </div>
              <div className="grid grid-cols-[2fr_3fr] gap-4 px-5 py-3 items-center">
                <code className="text-xs text-slate-700 dark:text-slate-300">last_run_status</code>
                <div>
                  <Badge
                    variant={settings.last_run_status === 'success' ? 'active' : 'inactive'}
                    label={settings.last_run_status || '-'}
                  />
                </div>
              </div>
              {settings.last_run_summary && (
                <div className="grid grid-cols-[2fr_3fr] gap-4 px-5 py-3">
                  <code className="text-xs text-slate-700 dark:text-slate-300">last_run_summary</code>
                  <div className="flex flex-wrap gap-3 text-xs text-slate-600 dark:text-slate-400">
                    <span>{t('admin.briefing.summary.generated')} <b className="text-emerald-600">{settings.last_run_summary.generated}</b></span>
                    <span>{t('admin.briefing.summary.skipped')} <b className="text-slate-500">{settings.last_run_summary.skipped}</b></span>
                    <span>{t('admin.briefing.summary.failed')} <b className="text-rose-600">{settings.last_run_summary.failed}</b></span>
                    <span>{t('admin.briefing.summary.total', { count: settings.last_run_summary.agents_total })}</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Message list card */}
        <div className="rounded-xl border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-900 overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <code className="text-xs font-semibold text-insurance-blue dark:text-blue-400 bg-insurance-blue/8 dark:bg-insurance-blue/20 px-2 py-0.5 rounded">inbox_messages</code>
              <span className="text-xs text-slate-400">{t('admin.briefing.inbox.totalCount', { total })}</span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={reloadMessages} className={btnSecondary}>
                <RefreshIcon size={14} />{t('admin.briefing.button.refresh')}
              </button>
              <button onClick={openCreate} className={btnPrimary}>
                <PlusIcon size={14} />{t('admin.briefing.button.create')}
              </button>
            </div>
          </div>

          {/* Filter bar */}
          <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800 flex flex-wrap items-end gap-3 bg-slate-50/50 dark:bg-slate-800/30">
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t('admin.briefing.filter.agent')}</label>
              <select
                value={filterAgent}
                onChange={(e) => { setFilterAgent(e.target.value); setOffset(0) }}
                className={`${inputCls} min-w-[160px] cursor-pointer`}
              >
                <option value="">{t('admin.briefing.filter.all')}</option>
                {agents.map((a) => (
                  <option key={a.username} value={a.username}>{a.display_name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t('admin.briefing.filter.priority')}</label>
              <select
                value={filterPriority}
                onChange={(e) => { setFilterPriority(e.target.value as PriorityFilter); setOffset(0) }}
                className={`${inputCls} min-w-[100px] cursor-pointer`}
              >
                <option value="">{t('admin.briefing.filter.all')}</option>
                <option value="P0">P0</option>
                <option value="P1">P1</option>
                <option value="P2">P2</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">{t('admin.briefing.filter.source')}</label>
              <input
                type="text"
                placeholder={t('admin.briefing.filter.sourcePlaceholder')}
                value={filterSource}
                onChange={(e) => { setFilterSource(e.target.value); setOffset(0) }}
                className={`${inputCls} min-w-[160px]`}
              />
            </div>
          </div>

          {/* Table */}
          {msgLoading ? (
            <div className="p-5 space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-10 rounded bg-slate-200 dark:bg-slate-800 animate-pulse" />
              ))}
            </div>
          ) : messages.length === 0 ? (
            <div className="p-10 text-center text-sm text-slate-400">{t('admin.briefing.empty')}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 bg-slate-50/60 dark:bg-slate-800/40 border-b border-slate-100 dark:border-slate-800">
                    <th className="px-4 py-2 font-medium">{t('admin.briefing.col.priority')}</th>
                    <th className="px-4 py-2 font-medium">{t('admin.briefing.col.notification')}</th>
                    <th className="px-4 py-2 font-medium">{t('admin.briefing.col.category')}</th>
                    <th className="px-4 py-2 font-medium">{t('admin.briefing.col.agent')}</th>
                    <th className="px-4 py-2 font-medium">{t('admin.briefing.col.customer')}</th>
                    <th className="px-4 py-2 font-medium">{t('admin.briefing.col.occurredAt')}</th>
                    <th className="px-4 py-2 font-medium w-[120px]">{t('admin.briefing.col.actions')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {messages.map((m) => (
                    <tr key={m.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/30">
                      <td className="px-4 py-2">{priorityBadge(m.priority)}</td>
                      <td className="px-4 py-2">
                        <div className="text-slate-800 dark:text-slate-100">{m.notification_name}</div>
                        <div className="text-xs text-slate-400 line-clamp-1 max-w-[280px]">{m.raw_content}</div>
                      </td>
                      <td className="px-4 py-2 text-slate-600 dark:text-slate-300">{m.category}</td>
                      <td className="px-4 py-2 font-mono text-xs text-slate-500">{m.agent_id}</td>
                      <td className="px-4 py-2 text-xs text-slate-500">
                        <div>{m.customer_name || '-'}</div>
                        <div className="font-mono">{m.policy_no || '-'}</div>
                      </td>
                      <td className="px-4 py-2 text-xs text-slate-500 font-mono">
                        {m.occurred_at ? new Date(m.occurred_at).toLocaleString(LOCALE_BCP47[locale], { hour12: false }) : '-'}
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => openEdit(m)}
                            className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 hover:text-insurance-blue"
                            title={t('admin.briefing.action.edit')}
                          >
                            <PencilIcon size={14} />
                          </button>
                          <button
                            onClick={() => handleDelete(m)}
                            disabled={deletingId === m.id}
                            className="p-1.5 rounded hover:bg-rose-50 dark:hover:bg-rose-900/20 text-slate-500 hover:text-rose-600 disabled:opacity-50"
                            title={t('admin.briefing.action.delete')}
                          >
                            {deletingId === m.id ? <SpinnerIcon size={14} /> : <TrashIcon size={14} />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > limit && (
            <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs text-slate-500">
              <span>{t('admin.briefing.pagination.range', { from: offset + 1, to: Math.min(offset + limit, total), total })}</span>
              <div className="flex gap-2">
                <button
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                  disabled={offset === 0}
                  className={btnSecondary}
                >
                  {t('admin.briefing.pagination.prev')}
                </button>
                <button
                  onClick={() => setOffset(offset + limit)}
                  disabled={offset + limit >= total}
                  className={btnSecondary}
                >
                  {t('admin.briefing.pagination.next')}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create / edit modal */}
      <Modal
        open={modalOpen}
        onClose={() => !submitting && setModalOpen(false)}
        title={editingId ? t('admin.briefing.modal.edit') : t('admin.briefing.modal.create')}
        size="lg"
        footer={
          <>
            <button onClick={() => setModalOpen(false)} disabled={submitting} className={btnSecondary}>
              {t('admin.briefing.modal.cancel')}
            </button>
            <button onClick={submitForm} disabled={submitting} className={btnPrimary}>
              {submitting && <SpinnerIcon size={14} />}
              {editingId ? t('admin.briefing.modal.save') : t('admin.briefing.modal.createBtn')}
            </button>
          </>
        }
      >
        <div className="grid grid-cols-2 gap-4">
          <FormField label={t('admin.briefing.field.targetAgent')} required>
            <select
              value={form.target_agent_id}
              disabled={!!editingId}
              onChange={(e) => setForm({ ...form, target_agent_id: e.target.value })}
              className={`${inputCls} cursor-pointer`}
            >
              <option value="">-</option>
              {agents.map((a) => (
                <option key={a.username} value={a.username}>{t('admin.briefing.field.agentOption', { name: a.display_name, username: a.username })}</option>
              ))}
            </select>
          </FormField>

          <FormField label={t('admin.briefing.field.priority')} required>
            <select
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value as 'P0' | 'P1' | 'P2' })}
              className={`${inputCls} cursor-pointer`}
            >
              <option value="P0">{t('admin.briefing.field.priority.p0')}</option>
              <option value="P1">{t('admin.briefing.field.priority.p1')}</option>
              <option value="P2">{t('admin.briefing.field.priority.p2')}</option>
            </select>
          </FormField>

          <FormField label={t('admin.briefing.field.notificationName')} required>
            <input
              type="text"
              value={form.notification_name}
              onChange={(e) => setForm({ ...form, notification_name: e.target.value })}
              className={inputCls}
              placeholder={t('admin.briefing.field.notificationName.ph')}
            />
          </FormField>

          <FormField label={t('admin.briefing.field.category')} required>
            <input
              type="text"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className={inputCls}
              placeholder={t('admin.briefing.field.category.ph')}
            />
          </FormField>

          <FormField label={t('admin.briefing.field.receiverType')} required>
            <input
              type="text"
              value={form.receiver_type}
              onChange={(e) => setForm({ ...form, receiver_type: e.target.value })}
              className={inputCls}
              placeholder={t('admin.briefing.field.receiverType.ph')}
            />
          </FormField>

          <FormField label={t('admin.briefing.field.channel')}>
            <select
              value={form.channel}
              onChange={(e) => setForm({ ...form, channel: e.target.value })}
              className={`${inputCls} cursor-pointer`}
            >
              <option value="sms">{t('admin.briefing.field.channel.sms')}</option>
              <option value="inapp">{t('admin.briefing.field.channel.inapp')}</option>
            </select>
          </FormField>

          <FormField label={t('admin.briefing.field.policyNo')}>
            <input
              type="text"
              value={form.policy_no}
              onChange={(e) => setForm({ ...form, policy_no: e.target.value })}
              className={inputCls}
              placeholder="HK-10000020"
            />
          </FormField>

          <FormField label={t('admin.briefing.field.customerId')}>
            <input
              type="text"
              value={form.customer_id}
              onChange={(e) => setForm({ ...form, customer_id: e.target.value })}
              className={inputCls}
              placeholder="C001"
            />
          </FormField>

          <FormField label={t('admin.briefing.field.customerName')}>
            <input
              type="text"
              value={form.customer_name}
              onChange={(e) => setForm({ ...form, customer_name: e.target.value })}
              className={inputCls}
            />
          </FormField>

          <FormField label={t('admin.briefing.field.externalId')}>
            <input
              type="text"
              value={form.external_id}
              disabled={!!editingId}
              onChange={(e) => setForm({ ...form, external_id: e.target.value })}
              className={inputCls}
              placeholder={t('admin.briefing.field.externalId.ph')}
            />
          </FormField>

          <div className="col-span-2">
            <FormField label={t('admin.briefing.field.rawContent')} required>
              <textarea
                value={form.raw_content}
                onChange={(e) => setForm({ ...form, raw_content: e.target.value })}
                className={`${inputCls} min-h-[120px] font-mono text-xs`}
                placeholder={t('admin.briefing.field.rawContent.ph')}
              />
            </FormField>
          </div>

          <div className="col-span-2">
            <FormField label={t('admin.briefing.field.classifyReason')}>
              <textarea
                value={form.classify_reason}
                onChange={(e) => setForm({ ...form, classify_reason: e.target.value })}
                className={`${inputCls} min-h-[60px] text-xs`}
              />
            </FormField>
          </div>
        </div>
      </Modal>
    </div>
  )
}
