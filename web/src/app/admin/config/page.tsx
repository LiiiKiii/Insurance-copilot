'use client'
import { useEffect, useState, useCallback } from 'react'
import { adminApi, type SystemConfig } from '@/lib/admin/api'
import { Badge } from '@/components/admin/Badge'
import { inputCls } from '@/components/admin/Modal'
import { CheckIcon, XIcon, SearchIcon2, SpinnerIcon } from '@/components/admin/AdminIcons'
import { useAdminAuth } from '@/lib/admin/auth'
import { useTranslation } from '@/lib/i18n'

const GROUPS = ['system', 'agent', 'compliance', 'rag', 'ui', 'session', 'other']

function groupOf(key: string) {
  const prefix = key.split('.')[0]
  return GROUPS.includes(prefix) ? prefix : 'other'
}

function InlineEdit({ config, onSave }: { config: SystemConfig; onSave: (id: string, val: string) => Promise<void> }) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(config.config_value)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true)
    await onSave(config.id, val)
    setSaving(false); setEditing(false)
  }
  const cancel = () => { setVal(config.config_value); setEditing(false) }

  if (config.config_type === 'bool' && !editing) {
    return (
      <div className="flex items-center gap-2">
        <span className={`text-sm ${config.config_value === 'true' ? 'text-emerald-600' : 'text-slate-400'}`}>
          {config.config_value}
        </span>
        <button onClick={() => setEditing(true)} className="text-xs text-slate-400 hover:text-insurance-blue underline">{t('admin.config.edit')}</button>
      </div>
    )
  }

  if (editing) {
    const isLong = config.config_value.length > 80 || config.config_type === 'json'
    return (
      <div className="flex items-start gap-2 w-full">
        {isLong
          ? <textarea className={`${inputCls} text-xs font-mono resize-y flex-1 min-h-[60px]`} value={val} onChange={e => setVal(e.target.value)} autoFocus />
          : <input className={`${inputCls} text-xs flex-1`} value={val} onChange={e => setVal(e.target.value)} autoFocus onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancel() }} />
        }
        <button onClick={save} disabled={saving} className="mt-0.5 rounded-md p-1.5 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 transition-colors">
          {saving ? <SpinnerIcon size={14} /> : <CheckIcon size={14} />}
        </button>
        <button onClick={cancel} className="mt-0.5 rounded-md p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"><XIcon size={14} /></button>
      </div>
    )
  }

  const display = config.config_value.length > 100 ? config.config_value.slice(0, 100) + '...' : config.config_value
  return (
    <button
      onClick={() => setEditing(true)}
      className="text-left text-sm text-slate-700 dark:text-slate-300 hover:text-insurance-blue dark:hover:text-blue-400 transition-colors group"
      title={t('admin.config.editTitle')}
    >
      <span className="font-mono text-xs">{display || t('admin.config.empty')}</span>
      <span className="ml-2 text-xs text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity">{t('admin.config.editHint')}</span>
    </button>
  )
}

export default function ConfigPage() {
  const { t } = useTranslation()
  const { can } = useAdminAuth()
  const [configs, setConfigs] = useState<SystemConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set(GROUPS))

  const load = useCallback(async () => {
    setLoading(true)
    const r = await adminApi.config.list(search || undefined)
    if (r.ok) setConfigs(r.data)
    setLoading(false)
  }, [search])

  useEffect(() => { load() }, [load])

  const saveConfig = async (id: string, val: string) => {
    await adminApi.config.update(id, { config_value: val })
    setConfigs(prev => prev.map(c => c.id === id ? { ...c, config_value: val } : c))
  }

  const toggleGroup = (g: string) => {
    setOpenGroups(prev => {
      const next = new Set(prev)
      if (next.has(g)) next.delete(g); else next.add(g)
      return next
    })
  }

  const grouped = GROUPS.reduce((acc, g) => {
    acc[g] = configs.filter(c => groupOf(c.config_key) === g)
    return acc
  }, {} as Record<string, SystemConfig[]>)

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{t('admin.config.title')}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{t('admin.config.subtitle')}</p>
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-5 max-w-sm">
        <SearchIcon2 className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder={t('admin.config.search.placeholder')} className={`${inputCls} pl-9`} />
      </div>

      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-10 rounded-lg bg-slate-200 dark:bg-slate-800 animate-pulse" />)}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {GROUPS.map(g => {
            const items = grouped[g]
            if (!items.length) return null
            const open = openGroups.has(g)
            return (
              <div key={g} className="rounded-xl border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-900 overflow-hidden">
                <button
                  onClick={() => toggleGroup(g)}
                  className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <code className="text-xs font-semibold text-insurance-blue dark:text-blue-400 bg-insurance-blue/8 dark:bg-insurance-blue/20 px-2 py-0.5 rounded">{g}.*</code>
                    <span className="text-xs text-slate-400">{t('admin.config.itemsCount', { count: items.length })}</span>
                  </div>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={`text-slate-400 transition-transform ${open ? '' : '-rotate-90'}`}><polyline points="6 9 12 15 18 9"/></svg>
                </button>
                {open && (
                  <div className="divide-y divide-slate-100 dark:divide-slate-800">
                    {items.map(c => (
                      <div key={c.id} className="grid grid-cols-[2fr_3fr_80px_80px] gap-4 px-5 py-3 items-start hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition-colors">
                        <div>
                          <code className="text-xs text-slate-700 dark:text-slate-300">{c.config_key}</code>
                          {c.description && <p className="text-xs text-slate-400 mt-0.5">{c.description}</p>}
                        </div>
                        {can('super_admin') ? <InlineEdit config={c} onSave={saveConfig} /> : <span className="font-mono text-xs text-slate-500">{c.config_value.length > 100 ? c.config_value.slice(0, 100) + '...' : c.config_value || t('admin.config.empty')}</span>}
                        <span className="text-xs text-slate-400 pt-0.5">{c.config_type}</span>
                        <span className="pt-0.5">{c.is_public ? <Badge variant="active" label={t('admin.config.public')} /> : <Badge variant="inactive" label={t('admin.config.private')} />}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
