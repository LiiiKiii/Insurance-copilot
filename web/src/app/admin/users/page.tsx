'use client'
import { useEffect, useState, useCallback } from 'react'
import { adminApi, type AdminUser } from '@/lib/admin/api'
import { DataTable, type ColDef } from '@/components/admin/DataTable'
import { Badge } from '@/components/admin/Badge'
import { Modal, FormField, inputCls, btnPrimary, btnSecondary, btnDanger } from '@/components/admin/Modal'
import { PlusIcon, PencilIcon, TrashIcon, SearchIcon2, SpinnerIcon } from '@/components/admin/AdminIcons'
import { ROLES, ROLE_LABEL_KEY, type RoleName } from '@/constants/admin'
import { useAdminAuth } from '@/lib/admin/auth'
import { useTranslation, LOCALE_BCP47 } from '@/lib/i18n'
import { ToastContainer, useToast } from '@/components/admin/Toast'

type Form = { username: string; email: string; display_name: string; password: string; is_active: boolean; role: string; tier: string; supervisor_id: string; daily_call_limit: number }
const empty: Form = { username: '', email: '', display_name: '', password: '', is_active: true, role: 'agent_manager', tier: 'agent', supervisor_id: '', daily_call_limit: 50 }

export default function UsersPage() {
  const { t, locale } = useTranslation()
  const { can } = useAdminAuth()
  const { toasts, toast, dismiss } = useToast()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'edit' | 'delete' | null>(null)
  const [selected, setSelected] = useState<AdminUser | null>(null)
  const [form, setForm] = useState<Form>(empty)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    const r = await adminApi.users.list(page, 20, search)
    if (r.ok) { setUsers(r.data); setTotal(r.meta?.total as number ?? r.data.length) }
    setLoading(false)
  }, [page, search])

  useEffect(() => { load() }, [load])

  const openCreate = () => { setForm(empty); setErr(null); setModal('create') }
  const openEdit = (u: AdminUser) => {
    setSelected(u)
    const firstRole = u.roles[0]
    const roleName = typeof firstRole === 'string' ? firstRole : firstRole?.name ?? 'readonly'
    setForm({ username: u.username, email: u.email, display_name: u.display_name ?? '', password: '', is_active: u.is_active, role: roleName, tier: u.tier || 'agent', supervisor_id: u.supervisor_id || '', daily_call_limit: u.daily_call_limit ?? 50 })
    setErr(null)
    setModal('edit')
  }
  const openDelete = (u: AdminUser) => { setSelected(u); setModal('delete') }

  const save = async () => {
    setSaving(true); setErr(null)
    // The backend rejects unknown fields: `username` is create-only and
    // `is_active` is update-only.
    const common = {
      email: form.email, display_name: form.display_name,
      roles: [form.role], tier: form.tier, supervisor_id: form.supervisor_id || null,
      daily_call_limit: form.daily_call_limit,
      ...(form.password ? { password: form.password } : {}),
    }
    const r = modal === 'create'
      ? await adminApi.users.create({ ...common, username: form.username })
      : await adminApi.users.update(selected!.id, { ...common, is_active: form.is_active })
    setSaving(false)
    if (r.ok) { setModal(null); load(); toast('success', modal === 'create' ? t('admin.users.toast.created') : t('admin.users.toast.updated')) }
    else setErr(r.error?.message ?? t('admin.users.toast.opFailed'))
  }

  const destroy = async () => {
    if (!selected) return
    setSaving(true)
    const r = await adminApi.users.delete(selected.id)
    setSaving(false); setModal(null); load()
    if (r.ok) toast('success', t('admin.users.toast.deleted', { username: selected.username }))
    else toast('error', r.error?.message ?? t('admin.users.toast.deleteFailed'))
  }

  const cols: ColDef<AdminUser>[] = [
    { key: 'username', header: t('admin.users.col.username'), sortable: true, render: u => <span className="font-medium">{u.username}</span> },
    { key: 'email', header: t('admin.users.col.email'), sortable: true },
    { key: 'display_name', header: t('admin.users.col.displayName'), sortable: true },
    { key: 'tier', header: t('admin.users.col.tier'), render: u => {
      const tier = u.tier || 'agent'
      const labelKeys: Record<string, 'admin.users.tier.director' | 'admin.users.tier.team_lead' | 'admin.users.tier.senior_agent' | 'admin.users.tier.agent'> = {
        director: 'admin.users.tier.director',
        team_lead: 'admin.users.tier.team_lead',
        senior_agent: 'admin.users.tier.senior_agent',
        agent: 'admin.users.tier.agent',
      }
      const colors: Record<string, string> = { director: 'info', team_lead: 'active', senior_agent: 'pending', agent: 'default' }
      return <Badge variant={(colors[tier] || 'default') as 'info' | 'active' | 'pending' | 'default'} label={labelKeys[tier] ? t(labelKeys[tier]) : tier} />
    }},
    { key: 'roles', header: t('admin.users.col.roles'), render: u => <span className="text-xs text-slate-500">{u.roles.map(r => { const name = typeof r === 'string' ? r : r.name; return ROLE_LABEL_KEY[name as RoleName] ? t(ROLE_LABEL_KEY[name as RoleName]) : name }).join(', ')}</span> },
    { key: 'supervisor_id', header: t('admin.users.col.supervisor'), render: u => {
      if (!u.supervisor_id) return <span className="text-xs text-slate-300">—</span>
      const sup = users.find(s => s.id === u.supervisor_id)
      return sup
        ? <span className="text-xs text-slate-500">{sup.display_name || sup.username}</span>
        : <span className="text-xs text-slate-300">—</span>
    }},
    { key: 'team', header: t('admin.users.col.team'), render: u => {
      const subs = users.filter(s => s.supervisor_id === u.id)
      if (subs.length === 0) return <span className="text-xs text-slate-300">—</span>
      return (
        <span className="text-xs text-slate-500" title={subs.map(s => s.display_name || s.username).join(', ')}>
          {t('admin.users.team.count', { count: subs.length })}
        </span>
      )
    }},
    { key: 'is_active', header: t('admin.users.col.status'), render: u => <Badge variant={u.is_active ? 'active' : 'inactive'} label={u.is_active ? t('admin.users.status.active') : t('admin.users.status.inactive')} /> },
    {
      key: 'last_login_at',
      header: t('admin.users.col.lastLogin'),
      sortable: true,
      sortAccessor: u => u.last_login_at ? new Date(u.last_login_at).getTime() : 0,
      render: u => u.last_login_at ? new Date(u.last_login_at).toLocaleDateString(LOCALE_BCP47[locale]) : '—',
    },
    ...(can('admin') ? [{
      key: 'actions' as const, header: t('admin.users.col.actions'),
      render: (u: AdminUser) => (
        <div className="flex items-center gap-2">
          <button onClick={() => openEdit(u)} className="rounded-md p-1.5 text-slate-400 hover:text-insurance-blue hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"><PencilIcon /></button>
          {can('super_admin') && <button onClick={() => openDelete(u)} className="rounded-md p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"><TrashIcon /></button>}
        </div>
      ),
    }] : []),
  ]

  const modalFooter = (
    <>
      <button className={btnSecondary} onClick={() => setModal(null)}>{t('admin.common.cancel')}</button>
      <button className={btnPrimary} onClick={save} disabled={saving}>
        {saving && <SpinnerIcon />}{modal === 'create' ? t('admin.common.add') : t('admin.users.button.save')}
      </button>
    </>
  )

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{t('admin.users.title')}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{t('admin.users.subtitle.count', { count: total })}</p>
        </div>
        {can('super_admin') && <button className={btnPrimary} onClick={openCreate}><PlusIcon />{t('admin.users.button.add')}</button>}
      </div>

      {/* Search */}
      <div className="relative mb-4 max-w-sm">
        <SearchIcon2 className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
          placeholder={t('admin.users.search.placeholder')}
          className={`${inputCls} pl-9`}
        />
      </div>

      <DataTable cols={cols} rows={users} keyFn={u => u.id} loading={loading}
        page={page} pageSize={20} total={total} onPageChange={setPage} />

      {/* Create/Edit modal */}
      <Modal open={modal === 'create' || modal === 'edit'} onClose={() => setModal(null)}
        title={modal === 'create' ? t('admin.users.modal.create.title') : t('admin.users.modal.edit.title')}
        footer={modalFooter}
      >
        <div className="flex flex-col gap-4">
          {err && <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 px-3 py-2 text-sm text-red-600">{err}</div>}
          <FormField label={t('admin.users.field.username')} required><input className={inputCls} value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} placeholder="username" disabled={modal === 'edit'} /></FormField>
          <FormField label={t('admin.users.field.email')} required><input className={inputCls} type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="user@example.com" /></FormField>
          <FormField label={t('admin.users.field.displayName')}><input className={inputCls} value={form.display_name} onChange={e => setForm(f => ({ ...f, display_name: e.target.value }))} /></FormField>
          <FormField label={modal === 'create' ? t('admin.users.field.password') : t('admin.users.field.newPassword')} required={modal === 'create'}>
            <input className={inputCls} type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} placeholder="••••••••" />
          </FormField>
          <FormField label={t('admin.users.field.roles')}>
            <select className={inputCls} value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
              {ROLES.map(r => <option key={r} value={r}>{t(ROLE_LABEL_KEY[r])}</option>)}
            </select>
          </FormField>
          <FormField label={t('admin.users.field.tier')}>
            <select className={inputCls} value={form.tier} onChange={e => setForm(f => ({ ...f, tier: e.target.value }))}>
              <option value="agent">{t('admin.users.tier.option.agent')}</option>
              <option value="senior_agent">{t('admin.users.tier.option.senior_agent')}</option>
              <option value="team_lead">{t('admin.users.tier.option.team_lead')}</option>
              <option value="director">{t('admin.users.tier.option.director')}</option>
            </select>
          </FormField>
          <FormField label={t('admin.users.field.supervisor')}>
            <select className={inputCls} value={form.supervisor_id} onChange={e => setForm(f => ({ ...f, supervisor_id: e.target.value }))}>
              <option value="">{t('admin.users.supervisor.none')}</option>
              {users.filter(u => u.id !== selected?.id).map(u => (
                <option key={u.id} value={u.id}>{u.username} - {u.display_name}</option>
              ))}
            </select>
          </FormField>
          <FormField label={t('admin.users.field.dailyCallLimit')}>
            <input className={inputCls} type="number" min={0} value={form.daily_call_limit} onChange={e => setForm(f => ({ ...f, daily_call_limit: parseInt(e.target.value) || 0 }))} placeholder={t('admin.users.dailyCallLimit.placeholder')} />
          </FormField>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="active" checked={form.is_active} onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))} className="rounded border-slate-300" />
            <label htmlFor="active" className="text-sm text-slate-700 dark:text-slate-300">{t('admin.users.field.isActive')}</label>
          </div>
        </div>
      </Modal>

      {/* Delete confirm */}
      <Modal open={modal === 'delete'} onClose={() => setModal(null)} title={t('admin.users.modal.delete.title')}
        footer={<><button className={btnSecondary} onClick={() => setModal(null)}>{t('admin.common.cancel')}</button><button className={btnDanger} onClick={destroy} disabled={saving}>{saving && <SpinnerIcon />}{t('admin.common.delete')}</button></>}
      >
        <p className="text-sm text-slate-600 dark:text-slate-400">{t('admin.users.modal.delete.message', { username: selected?.username ?? '' })}</p>
      </Modal>
    </div>
  )
}
