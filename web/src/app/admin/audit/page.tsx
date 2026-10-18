'use client'
import { useCallback, useEffect, useState } from 'react'
import { adminApi, type RequestLog, type AiLog, type ErrorLog } from '@/lib/admin/api'
import { DataTable, type ColDef } from '@/components/admin/DataTable'
import { Badge } from '@/components/admin/Badge'
import { cn } from '@/lib/utils'
import { inputCls } from '@/components/admin/Modal'
import { useTranslation, LOCALE_BCP47, type MessageKey, type Locale } from '@/lib/i18n'

type Tab = 'requests' | 'ai' | 'errors'

const TAB_LABEL_KEYS: Record<Tab, MessageKey> = {
  requests: 'admin.audit.tab.requests',
  ai: 'admin.audit.tab.ai',
  errors: 'admin.audit.tab.errors',
}

function statusBadge(code: number) {
  if (code >= 500) return <Badge variant="error" label={String(code)} />
  if (code >= 400) return <Badge variant="warning" label={String(code)} />
  return <Badge variant="active" label={String(code)} />
}

function levelBadge(level: string) {
  const v = level === 'ERROR' ? 'error' : level === 'WARNING' ? 'warning' : 'default'
  return <Badge variant={v as 'error' | 'warning' | 'default'} label={level} />
}

function fmtTime(s: string | null, locale: Locale) {
  if (!s) return '—'
  return new Date(s).toLocaleString(LOCALE_BCP47[locale], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function AuditPage() {
  const { t, locale } = useTranslation()
  const [tab, setTab] = useState<Tab>('requests')
  const [reqLogs, setReqLogs] = useState<RequestLog[]>([])
  const [aiLogs, setAiLogs] = useState<AiLog[]>([])
  const [errLogs, setErrLogs] = useState<ErrorLog[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [reqMethod, setReqMethod] = useState('')
  const [reqStatus, setReqStatus] = useState('')
  const [reqEndpoint, setReqEndpoint] = useState('')

  const load = useCallback(async (currentTab: Tab, p: number) => {
    setLoading(true)
    if (currentTab === 'requests') {
      const r = await adminApi.audit.requests(p, 50, {
        method: reqMethod || undefined,
        status_code: reqStatus ? Number(reqStatus) : undefined,
        endpoint: reqEndpoint || undefined,
      })
      if (r.ok) { setReqLogs(r.data); setTotal(r.meta?.total as number ?? r.data.length) }
    } else if (currentTab === 'ai') {
      const r = await adminApi.audit.aiAudit(p)
      if (r.ok) { setAiLogs(r.data); setTotal(r.meta?.total as number ?? r.data.length) }
    } else {
      const r = await adminApi.audit.errors(p)
      if (r.ok) { setErrLogs(r.data); setTotal(r.meta?.total as number ?? r.data.length) }
    }
    setLoading(false)
  }, [reqEndpoint, reqMethod, reqStatus])

  useEffect(() => {
    setPage((prev) => (prev === 1 ? prev : 1))
  }, [tab])
  useEffect(() => { load(tab, page) }, [load, tab, page])

  const reqCols: ColDef<RequestLog>[] = [
    {
      key: 'created_at',
      header: t('admin.audit.col.time'),
      sortable: true,
      sortAccessor: r => new Date(r.created_at).getTime(),
      render: r => <span className="text-xs text-slate-500 whitespace-nowrap">{fmtTime(r.created_at, locale)}</span>,
    },
    { key: 'method', header: t('admin.audit.col.method'), render: r => <code className="text-xs bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono">{r.method}</code> },
    { key: 'endpoint', header: t('admin.audit.col.endpoint'), render: r => <span className="text-xs font-mono text-slate-700 dark:text-slate-300 break-all">{r.endpoint}</span> },
    { key: 'status_code', header: t('admin.audit.col.statusCode'), render: r => statusBadge(r.status_code) },
    { key: 'latency_ms', header: t('admin.audit.col.latency'), render: r => <span className={cn('text-xs tabular-nums', r.latency_ms > 2000 ? 'text-red-500 font-medium' : r.latency_ms > 500 ? 'text-amber-500' : 'text-slate-500')}>{r.latency_ms}ms</span> },
    { key: 'user_id', header: t('admin.audit.col.userId'), render: r => <span className="text-xs text-slate-400 font-mono">{r.user_id ? r.user_id.slice(0, 8) + '…' : '—'}</span> },
    { key: 'ip_address', header: t('admin.audit.col.ip'), render: r => <span className="text-xs text-slate-400">{r.ip_address ?? '—'}</span> },
  ]

  const aiCols: ColDef<AiLog>[] = [
    { key: 'created_at', header: t('admin.audit.col.time'), render: r => <span className="text-xs text-slate-500 whitespace-nowrap">{fmtTime(r.created_at, locale)}</span> },
    { key: 'model_id', header: t('admin.audit.col.model'), render: r => <code className="text-xs bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">{r.model_id ?? '—'}</code> },
    { key: 'user_query', header: t('admin.audit.col.userQuery'), render: r => <span className="text-xs text-slate-600 dark:text-slate-400 line-clamp-2">{r.user_query}</span> },
    { key: 'tokens', header: 'Tokens', render: r => <span className="text-xs tabular-nums text-slate-500">{r.prompt_tokens ?? 0} / {r.completion_tokens ?? 0}</span> },
    {
      key: 'has_compliance_issue', header: t('admin.audit.col.compliance'),
      render: r => r.has_compliance_issue
        ? <Badge variant="error" label={t('admin.audit.compliance.issue')} />
        : <Badge variant="active" label={t('admin.audit.compliance.normal')} />,
    },
    {
      key: 'compliance_notes', header: t('admin.audit.col.notes'),
      render: r => r.compliance_notes ? <span className="text-xs text-red-600 dark:text-red-400 line-clamp-1">{r.compliance_notes}</span> : <span className="text-xs text-slate-300">—</span>,
    },
  ]

  const errCols: ColDef<ErrorLog>[] = [
    { key: 'created_at', header: t('admin.audit.col.time'), render: r => <span className="text-xs text-slate-500 whitespace-nowrap">{fmtTime(r.created_at, locale)}</span> },
    { key: 'level', header: t('admin.audit.col.level'), render: r => levelBadge(r.level) },
    { key: 'message', header: t('admin.audit.col.message'), render: r => <span className="text-xs text-slate-700 dark:text-slate-300 line-clamp-2 font-mono">{r.message}</span> },
    { key: 'tenant_id', header: t('admin.audit.col.tenant'), render: r => <span className="text-xs text-slate-400 font-mono">{r.tenant_id ? r.tenant_id.slice(0, 8) + '…' : '—'}</span> },
  ]

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{t('admin.audit.title')}</h1>
        <p className="text-sm text-slate-500 mt-0.5">{t('admin.audit.subtitle')}</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 border-b border-slate-200 dark:border-slate-700">
        {(['requests', 'ai', 'errors'] as Tab[]).map(tabKey => (
          <button
            key={tabKey}
            onClick={() => setTab(tabKey)}
            className={cn(
              'px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px',
              tab === tabKey
                ? 'border-insurance-blue text-insurance-blue dark:text-blue-400 dark:border-blue-400'
                : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300',
            )}
          >
            {t(TAB_LABEL_KEYS[tabKey])}
          </button>
        ))}
      </div>

      {tab === 'requests' && (
        <div className="mb-4 grid grid-cols-1 md:grid-cols-4 gap-2">
          <select className={inputCls} value={reqMethod} onChange={e => setReqMethod(e.target.value)}>
            <option value="">{t('admin.audit.filter.allMethods')}</option>
            <option value="GET">GET</option>
            <option value="POST">POST</option>
            <option value="PUT">PUT</option>
            <option value="DELETE">DELETE</option>
          </select>
          <select className={inputCls} value={reqStatus} onChange={e => setReqStatus(e.target.value)}>
            <option value="">{t('admin.audit.filter.allStatusCodes')}</option>
            <option value="200">200</option>
            <option value="400">400</option>
            <option value="401">401</option>
            <option value="403">403</option>
            <option value="404">404</option>
            <option value="500">500</option>
          </select>
          <input
            className={inputCls}
            placeholder={t('admin.audit.filter.endpointPlaceholder')}
            value={reqEndpoint}
            onChange={e => setReqEndpoint(e.target.value)}
          />
          <button
            className="rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm text-slate-600 dark:text-slate-300"
            onClick={() => { setReqMethod(''); setReqStatus(''); setReqEndpoint('') }}
          >
            {t('admin.audit.filter.clear')}
          </button>
        </div>
      )}

      {tab === 'requests' && (
        <DataTable cols={reqCols} rows={reqLogs} keyFn={r => r.id} loading={loading}
          page={page} pageSize={50} total={total} onPageChange={setPage} />
      )}
      {tab === 'ai' && (
        <DataTable cols={aiCols} rows={aiLogs} keyFn={r => r.id} loading={loading}
          page={page} pageSize={20} total={total} onPageChange={setPage} />
      )}
      {tab === 'errors' && (
        <DataTable cols={errCols} rows={errLogs} keyFn={r => r.id} loading={loading}
          page={page} pageSize={50} total={total} onPageChange={setPage} />
      )}
    </div>
  )
}
