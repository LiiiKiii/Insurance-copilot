'use client'
import { useEffect, useState, useCallback } from 'react'
import { adminApi, type ModelConfig } from '@/lib/admin/api'
import { DataTable, type ColDef } from '@/components/admin/DataTable'
import { Badge } from '@/components/admin/Badge'
import { Modal, FormField, inputCls, btnPrimary, btnSecondary, btnDanger } from '@/components/admin/Modal'
import { PlusIcon, PencilIcon, TrashIcon, SpinnerIcon, RefreshIcon, CheckIcon, EyeIcon, EyeOffIcon } from '@/components/admin/AdminIcons'
import { MODEL_CATEGORY_KEY } from '@/constants/models'
import { cn } from '@/lib/utils'
import { useAdminAuth } from '@/lib/admin/auth'
import { useTranslation } from '@/lib/i18n'

const PROVIDERS = ['openrouter', 'anthropic', 'openai', 'google', 'cohere', 'custom']
const MODEL_TYPES = ['llm', 'embedding', 'reranker', 'image']
const CATEGORY_KEYS = Object.keys(MODEL_CATEGORY_KEY)

type Form = {
  provider: string; model_id: string; display_name: string; model_type: string
  category: string; api_key: string; base_url: string; is_default: boolean
  price_per_1k_input: number; price_per_1k_output: number
}
const empty: Form = {
  provider: 'openrouter', model_id: '', display_name: '', model_type: 'llm',
  category: 'chat', api_key: '', base_url: '', is_default: false,
  price_per_1k_input: 0, price_per_1k_output: 0,
}

export default function ModelsPage() {
  const { t } = useTranslation()
  const { can } = useAdminAuth()
  const [allModels, setAllModels] = useState<ModelConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<string>('all')
  const [modal, setModal] = useState<'create' | 'edit' | 'delete' | null>(null)
  const [selected, setSelected] = useState<ModelConfig | null>(null)
  const [form, setForm] = useState<Form>(empty)
  const [showKey, setShowKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; ms?: number; err?: string }>>({})
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    const r = await adminApi.models.list()
    if (r.ok) setAllModels(r.data)
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const models = activeTab === 'all' ? allModels : allModels.filter(m => m.category === activeTab)

  const openCreate = () => {
    setForm({ ...empty, category: activeTab !== 'all' ? activeTab : 'chat' })
    setShowKey(false); setErr(null); setModal('create')
  }
  const openEdit = (m: ModelConfig) => {
    setSelected(m)
    setForm({
      provider: m.provider, model_id: m.model_id, display_name: m.display_name,
      model_type: m.model_type, category: m.category, api_key: '',
      base_url: m.base_url ?? '', is_default: m.is_default,
      price_per_1k_input: m.price_per_1k_input, price_per_1k_output: m.price_per_1k_output,
    })
    setShowKey(false); setErr(null); setModal('edit')
  }
  const openDelete = (m: ModelConfig) => { setSelected(m); setModal('delete') }

  const testModel = async (id: string) => {
    setTesting(id)
    const r = await adminApi.models.test(id)
    setTestResults(prev => ({ ...prev, [id]: r.ok ? { ok: true, ms: r.data.latency_ms } : { ok: false, err: r.error?.message ?? t('admin.models.error.failed') } }))
    setTesting(null)
  }

  const setDefault = async (id: string) => {
    await adminApi.models.setDefault(id)
    load()
  }

  const save = async () => {
    setSaving(true); setErr(null)
    const body = { ...form, ...(form.api_key ? {} : {}) }
    const r = modal === 'create'
      ? await adminApi.models.create(body)
      : await adminApi.models.update(selected!.id, body)
    setSaving(false)
    if (r.ok) { setModal(null); load() }
    else setErr(r.error?.message ?? t('admin.models.toast.opFailed'))
  }

  const destroy = async () => {
    if (!selected) return
    setSaving(true)
    await adminApi.models.delete(selected.id)
    setSaving(false); setModal(null); load()
  }

  // Count models per category for tab badges
  const catCounts: Record<string, number> = {}
  for (const m of allModels) {
    catCounts[m.category] = (catCounts[m.category] || 0) + 1
  }

  const cols: ColDef<ModelConfig>[] = [
    { key: 'display_name', header: t('admin.models.col.displayName'), render: m => <div><div className="font-medium text-sm">{m.display_name}</div><div className="text-xs text-slate-400 font-mono">{m.model_id}</div></div> },
    { key: 'provider', header: 'Provider', render: m => <code className="text-xs bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">{m.provider}</code> },
    { key: 'category', header: t('admin.models.col.category'), render: m => <Badge variant="info" label={MODEL_CATEGORY_KEY[m.category] ? t(MODEL_CATEGORY_KEY[m.category]) : m.category} /> },
    { key: 'is_default', header: t('admin.models.col.default'), render: m => m.is_default ? <CheckIcon className="text-emerald-500" size={16} /> : <span className="text-slate-300">&mdash;</span> },
    { key: 'price', header: t('admin.models.col.price'), render: m => <span className="text-xs text-slate-500">${m.price_per_1k_input} / ${m.price_per_1k_output}</span> },
    { key: 'enabled', header: t('admin.models.col.status'), render: m => <Badge variant={m.enabled ? 'active' : 'inactive'} label={m.enabled ? t('admin.users.status.active') : t('admin.users.status.inactive')} /> },
    {
      key: 'actions', header: t('admin.models.col.actions'),
      render: m => (
        <div className="flex items-center gap-1.5 whitespace-nowrap">
          <button
            onClick={() => testModel(m.id)}
            disabled={testing === m.id}
            title={t('admin.models.test.tooltip')}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs border border-slate-200 dark:border-slate-700 text-slate-600 hover:border-insurance-blue hover:text-insurance-blue transition-colors"
          >
            {testing === m.id ? <SpinnerIcon size={12} /> : <RefreshIcon size={12} />}
            {testing === m.id ? t('admin.models.test.testing') : testResults[m.id] ? (testResults[m.id].ok ? `${testResults[m.id].ms}ms` : t('admin.models.test.failed')) : t('admin.models.test.label')}
          </button>
          {can('admin') && !m.is_default && (
            <button onClick={() => setDefault(m.id)} className="rounded-md px-2 py-1 text-xs border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-insurance-blue transition-colors">{t('admin.models.button.setDefault')}</button>
          )}
          {can('admin') && <button onClick={() => openEdit(m)} className="rounded-md p-1.5 text-slate-400 hover:text-insurance-blue hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"><PencilIcon /></button>}
          {can('super_admin') && <button onClick={() => openDelete(m)} className="rounded-md p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"><TrashIcon /></button>}
        </div>
      ),
    },
  ]

  const fi = (field: keyof Form, label: string, type = 'text', ph = '') => (
    <FormField label={label}>
      <input className={inputCls} type={type} value={form[field] as string} placeholder={ph}
        onChange={e => setForm(f => ({ ...f, [field]: type === 'number' ? Number(e.target.value) : e.target.value }))} />
    </FormField>
  )

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{t('admin.models.title')}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{t('admin.models.subtitle')}</p>
        </div>
        {can('super_admin') && <button className={btnPrimary} onClick={openCreate}><PlusIcon />{t('admin.models.button.add')}</button>}
      </div>

      {/* Category tabs */}
      <div className="flex items-center gap-1 mb-5 overflow-x-auto pb-1">
        <button
          onClick={() => setActiveTab('all')}
          className={cn(
            'px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap',
            activeTab === 'all'
              ? 'bg-insurance-blue text-white'
              : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800',
          )}
        >
          {t('admin.models.filter.all')}
          <span className="ml-1.5 text-[10px] opacity-70">{allModels.length}</span>
        </button>
        {CATEGORY_KEYS.map(cat => (
          <button
            key={cat}
            onClick={() => setActiveTab(cat)}
            className={cn(
              'px-3 py-1.5 text-xs font-medium rounded-md transition-colors whitespace-nowrap',
              activeTab === cat
                ? 'bg-insurance-blue text-white'
                : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800',
            )}
          >
            {MODEL_CATEGORY_KEY[cat] ? t(MODEL_CATEGORY_KEY[cat]) : cat}
            {(catCounts[cat] ?? 0) > 0 && (
              <span className="ml-1.5 text-[10px] opacity-70">{catCounts[cat]}</span>
            )}
          </button>
        ))}
      </div>

      <DataTable cols={cols} rows={models} keyFn={m => m.id} loading={loading} />

      <Modal open={modal === 'create' || modal === 'edit'} onClose={() => setModal(null)}
        title={modal === 'create' ? t('admin.models.modal.create.title') : t('admin.models.modal.edit.title')} size="lg"
        footer={<><button className={btnSecondary} onClick={() => setModal(null)}>{t('admin.common.cancel')}</button><button className={btnPrimary} onClick={save} disabled={saving}>{saving && <SpinnerIcon />}{t('admin.users.button.save')}</button></>}
      >
        <div className="grid grid-cols-2 gap-4">
          {err && <div className="col-span-2 rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-600">{err}</div>}
          <FormField label="Provider" required>
            <select className={inputCls} value={form.provider} onChange={e => setForm(f => ({ ...f, provider: e.target.value }))}>
              {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </FormField>
          <FormField label={t('admin.models.field.category')} required>
            <select className={inputCls} value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
              {CATEGORY_KEYS.map(c => <option key={c} value={c}>{MODEL_CATEGORY_KEY[c] ? t(MODEL_CATEGORY_KEY[c]) : c}</option>)}
            </select>
          </FormField>
          <FormField label={t('admin.models.field.modelType')}>
            <select className={inputCls} value={form.model_type} onChange={e => setForm(f => ({ ...f, model_type: e.target.value }))}>
              {MODEL_TYPES.map(mt => <option key={mt} value={mt}>{mt}</option>)}
            </select>
          </FormField>
          {fi('model_id', 'Model ID', 'text', 'anthropic/claude-3.5-sonnet-20241022')}
          {fi('display_name', t('admin.models.field.displayName'), 'text', 'Claude 3.5 Sonnet')}
          {fi('base_url', 'Base URL', 'text', 'https://openrouter.ai/api/v1')}
          <FormField label="API Key">
            <div className="relative">
              <input className={`${inputCls} pr-9`} type={showKey ? 'text' : 'password'} value={form.api_key}
                onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))} placeholder={modal === 'edit' ? t('admin.models.field.apiKey.placeholder.edit') : 'sk-...'} />
              <button type="button" onClick={() => setShowKey(!showKey)} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">
                {showKey ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
          </FormField>
          {fi('price_per_1k_input', t('admin.models.field.priceInput'), 'number')}
          {fi('price_per_1k_output', t('admin.models.field.priceOutput'), 'number')}
          <div className="col-span-2 flex items-center gap-2">
            <input type="checkbox" id="isDefault" checked={form.is_default} onChange={e => setForm(f => ({ ...f, is_default: e.target.checked }))} className="rounded border-slate-300" />
            <label htmlFor="isDefault" className="text-sm text-slate-700 dark:text-slate-300">{t('admin.models.field.isDefault')}</label>
          </div>
        </div>
      </Modal>

      <Modal open={modal === 'delete'} onClose={() => setModal(null)} title={t('admin.models.modal.delete.title')}
        footer={<><button className={btnSecondary} onClick={() => setModal(null)}>{t('admin.common.cancel')}</button><button className={btnDanger} onClick={destroy} disabled={saving}>{saving && <SpinnerIcon />}{t('admin.common.delete')}</button></>}
      >
        <p className="text-sm text-slate-600 dark:text-slate-400">{t('admin.models.modal.delete.message', { name: selected?.display_name ?? '' })}</p>
      </Modal>
    </div>
  )
}
