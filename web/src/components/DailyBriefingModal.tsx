'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { MarkdownRenderer } from './MarkdownRenderer'
import { useTranslation, LOCALE_BCP47, type Locale, type MessageKey } from '@/lib/i18n'
import {
  acknowledgeBriefing,
  fetchTodayBriefing,
  markMessageHandled,
  markMessageRead,
  type BriefingActionItem,
  type BriefingPayload,
  type ComplianceWarning,
  type InboxMessage,
} from '@/lib/briefingApi'

interface DailyBriefingModalProps {
  agentId: string
  open: boolean
  onClose: () => void
  onAcknowledged?: () => void
}

const PRIORITY_STYLE: Record<string, { labelKey: MessageKey; color: string }> = {
  P0: { labelKey: 'briefing.priority.p0', color: 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-400/40' },
  P1: { labelKey: 'briefing.priority.p1', color: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-400/40' },
  P2: { labelKey: 'briefing.priority.p2', color: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-400/40' },
}

const COMPLIANCE_STYLES: Record<ComplianceWarning['level'], string> = {
  error: 'bg-rose-50 dark:bg-rose-950/30 border-rose-300 dark:border-rose-700 text-rose-700 dark:text-rose-300',
  warning: 'bg-amber-50 dark:bg-amber-950/30 border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-300',
  info: 'bg-sky-50 dark:bg-sky-950/30 border-sky-300 dark:border-sky-700 text-sky-700 dark:text-sky-300',
}

function ComplianceBanner({ warnings, heading }: { warnings: ComplianceWarning[]; heading: string }) {
  if (!warnings.length) return null
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-300">{heading}</h3>
      {warnings.map((w, i) => (
        <div key={i} className={`rounded-lg border px-4 py-3 ${COMPLIANCE_STYLES[w.level] || COMPLIANCE_STYLES.info}`}>
          <div className="text-sm font-semibold mb-0.5">{w.title}</div>
          <div className="text-xs leading-relaxed">{w.message}</div>
        </div>
      ))}
    </section>
  )
}

function formatTime(s: string | null | undefined, locale: Locale): string {
  if (!s) return ''
  try {
    const d = new Date(s)
    return d.toLocaleString(LOCALE_BCP47[locale], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
  } catch { return s }
}

export function DailyBriefingModal({ agentId, open, onClose, onAcknowledged }: DailyBriefingModalProps) {
  const { t, locale } = useTranslation()
  const [data, setData] = useState<BriefingPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set(['P2']))
  const messageRefs = useRef<Map<string, HTMLDivElement>>(new Map())

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setError(null)
    fetchTodayBriefing(agentId)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [open, agentId])

  const grouped = useMemo(() => {
    const g: Record<string, InboxMessage[]> = { P0: [], P1: [], P2: [] }
    for (const m of data?.messages || []) {
      ;(g[m.priority] ||= []).push(m)
    }
    return g
  }, [data])

  if (!open) return null

  const briefing = data?.briefing

  const handleAcknowledge = async () => {
    try {
      await acknowledgeBriefing(agentId)
      onAcknowledged?.()
      onClose()
    } catch (e) { setError((e as Error).message) }
  }

  const toggleExpand = async (id: string) => {
    const next = new Set(expandedIds)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
      try {
        await markMessageRead(id)
        setData((prev) => prev && { ...prev, messages: prev.messages.map((m) => m.id === id ? { ...m, read_at: new Date().toISOString() } : m) })
      } catch { /* ignore */ }
    }
    setExpandedIds(next)
  }

  const toggleGroup = (prio: string) => {
    const next = new Set(collapsedGroups)
    if (next.has(prio)) next.delete(prio)
    else next.add(prio)
    setCollapsedGroups(next)
  }

  const handleHandle = async (id: string) => {
    try {
      await markMessageHandled(id)
      setData((prev) => prev && {
        ...prev,
        messages: prev.messages.map((m) => m.id === id ? { ...m, handled_at: new Date().toISOString(), read_at: m.read_at || new Date().toISOString() } : m),
      })
    } catch (e) { setError((e as Error).message) }
  }

  const jumpToMessage = async (id: string) => {
    if (!expandedIds.has(id)) await toggleExpand(id)
    setTimeout(() => {
      const el = messageRefs.current.get(id)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 50)
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center md:p-4 bg-slate-900/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="relative w-full md:max-w-4xl flex flex-col bg-white dark:bg-slate-900 shadow-2xl border-t md:border border-slate-200 dark:border-slate-700 overflow-hidden rounded-t-2xl md:rounded-2xl max-h-[88vh] max-h-[88dvh] md:max-h-[85vh] md:max-h-[85dvh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Mobile drag handle */}
        <div className="md:hidden mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-slate-300 dark:bg-slate-600" />

        {/* Header — sticky so close button always visible */}
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-4 md:px-6 py-3 md:py-4 border-b border-slate-200 dark:border-slate-700 bg-white/95 dark:bg-slate-900/95 backdrop-blur-sm shrink-0">
          <div className="min-w-0 flex-1">
            <h2 className="font-display text-base md:text-xl font-semibold text-slate-800 dark:text-slate-100 truncate">
              {t('briefing.title')}
              {briefing && <span className="ml-1.5 text-xs md:text-sm font-normal text-slate-500">· {briefing.date}</span>}
            </h2>
            {briefing && (
              <div className="mt-1 flex flex-wrap gap-1.5 items-center text-[10px] md:text-xs">
                <span className="px-1.5 py-0.5 rounded-full border bg-rose-500/15 text-rose-600 border-rose-400/40">P0 {briefing.p0_count}</span>
                <span className="px-1.5 py-0.5 rounded-full border bg-amber-500/15 text-amber-600 border-amber-400/40">P1 {briefing.p1_count}</span>
                <span className="px-1.5 py-0.5 rounded-full border bg-emerald-500/15 text-emerald-600 border-emerald-400/40">P2 {briefing.p2_count}</span>
                <span className="text-slate-500 dark:text-slate-400">{t('briefing.totalCount', { count: briefing.message_count })}</span>
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label={t('briefing.dismiss.aria')}
            className="shrink-0 flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition-colors"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4 md:py-5 space-y-5 md:space-y-6 overscroll-contain">
          {loading && <div className="text-center text-slate-500 py-12">{t('briefing.loading')}</div>}
          {error && <div className="text-rose-600 bg-rose-50 dark:bg-rose-950/30 px-4 py-3 rounded-lg text-sm">{error}</div>}

          {/* Compliance banner — always shown when warnings exist, independent of briefing */}
          <ComplianceBanner warnings={data?.compliance_warnings || []} heading={t('briefing.compliance.heading')} />

          {briefing && briefing.summary_markdown ? (
            <section>
              <div className="prose prose-sm dark:prose-invert max-w-none text-slate-700 dark:text-slate-200">
                <MarkdownRenderer content={briefing.summary_markdown} />
              </div>
            </section>
          ) : !loading && !error ? (
            <section className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600 bg-slate-50/50 dark:bg-slate-800/30 px-6 py-8 text-center">
              <p className="text-sm text-slate-500 dark:text-slate-400">{t('briefing.empty')}</p>
            </section>
          ) : null}

          <section>
            <h3 className="text-sm font-semibold text-slate-600 dark:text-slate-300 mb-3">{t('briefing.messages.heading')}</h3>
            <div className="space-y-3">
              {(['P0', 'P1', 'P2'] as const).map((prio) => {
                const list = grouped[prio] || []
                if (list.length === 0) return null
                const collapsed = collapsedGroups.has(prio)
                return (
                  <div key={prio} className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden">
                    <button
                      onClick={() => toggleGroup(prio)}
                      className="w-full px-4 py-2 flex items-center justify-between bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                    >
                      <span className="text-sm font-medium">
                        <span className={`inline-block px-2 py-0.5 rounded border text-xs mr-2 ${PRIORITY_STYLE[prio]?.color || ''}`}>{t(PRIORITY_STYLE[prio].labelKey)}</span>
                        {t('briefing.group.count', { count: list.length })}
                      </span>
                      <span className="text-slate-400">{collapsed ? '▶' : '▼'}</span>
                    </button>
                    {!collapsed && (
                      <div className="divide-y divide-slate-200 dark:divide-slate-700">
                        {list.map((m) => {
                          const expanded = expandedIds.has(m.id)
                          return (
                            <div
                              key={m.id}
                              ref={(el) => {
                                if (el) messageRefs.current.set(m.id, el)
                              }}
                              className="px-4 py-3"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">{m.notification_name}</span>
                                    {m.policy_no && <span className="text-xs text-slate-500">{m.policy_no}</span>}
                                    {m.customer_name && <span className="text-xs text-slate-500">{m.customer_name}</span>}
                                    {m.read_at && <span className="text-xs text-emerald-500">{t('briefing.message.read')}</span>}
                                    {m.handled_at && <span className="text-xs text-insurance-blue">{t('briefing.message.handled')}</span>}
                                  </div>
                                  <div className="text-xs text-slate-500 mt-0.5">
                                    {m.category} · {formatTime(m.occurred_at, locale)}
                                    {m.deadline_at && <span className="text-rose-500 ml-2">{t('briefing.message.deadline', { time: formatTime(m.deadline_at, locale) })}</span>}
                                  </div>
                                  {m.template_summary && !expanded && (
                                    <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 line-clamp-2">{m.template_summary}</p>
                                  )}
                                  {expanded && (
                                    <div className="mt-2 space-y-1.5 text-xs">
                                      <div><span className="text-slate-500">{t('briefing.message.triggerLogic')}</span>{m.trigger_logic}</div>
                                      <div className="bg-slate-100 dark:bg-slate-800 px-3 py-2 rounded text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{m.raw_content}</div>
                                      {m.classify_reason && <div className="text-slate-500">{t('briefing.message.classifyReason')}{m.classify_reason}</div>}
                                    </div>
                                  )}
                                </div>
                                <div className="flex flex-col gap-1">
                                  <button onClick={() => toggleExpand(m.id)} className="text-xs text-insurance-blue hover:underline cursor-pointer">
                                    {expanded ? t('briefing.message.collapse') : t('briefing.message.expand')}
                                  </button>
                                  {!m.handled_at && (
                                    <button onClick={() => handleHandle(m.id)} className="text-xs text-slate-500 hover:text-insurance-gold cursor-pointer">
                                      {t('briefing.message.markHandled')}
                                    </button>
                                  )}
                                </div>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
              {(!data || data.messages.length === 0) && !loading && (
                <div className="text-center text-slate-500 text-sm py-8">{t('briefing.empty')}</div>
              )}
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="shrink-0 px-4 md:px-6 py-3 border-t border-slate-200 dark:border-slate-700 flex items-center justify-end gap-2 bg-slate-50 dark:bg-slate-900/60 pb-[calc(env(safe-area-inset-bottom)+0.75rem)] md:pb-3">
          <button
            onClick={onClose}
            className="text-sm px-4 py-2 min-h-[40px] rounded-lg border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
          >
            {t('common.close')}
          </button>
          <button
            onClick={handleAcknowledge}
            disabled={!briefing}
            className="text-sm px-4 py-2 min-h-[40px] rounded-lg bg-insurance-gold text-white hover:opacity-90 disabled:opacity-40 cursor-pointer"
          >
            {t('briefing.button.acknowledge')}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
