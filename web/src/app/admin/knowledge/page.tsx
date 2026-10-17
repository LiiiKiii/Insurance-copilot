'use client'
import { useEffect, useState, useCallback } from 'react'
import { adminApi, type DocumentChunk, type KnowledgeBase, type KBDocument } from '@/lib/admin/api'
import { Badge } from '@/components/admin/Badge'
import { Modal, FormField, inputCls, btnPrimary, btnSecondary, btnDanger } from '@/components/admin/Modal'
import { DataTable, type ColDef } from '@/components/admin/DataTable'
import { PlusIcon, TrashIcon, SpinnerIcon, DatabaseIcon, FileTextIcon } from '@/components/admin/AdminIcons'
import { useAdminAuth } from '@/lib/admin/auth'
import { useTranslation, LOCALE_BCP47 } from '@/lib/i18n'

export default function KnowledgePage() {
  const { t, locale } = useTranslation()
  const { can } = useAdminAuth()
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<KnowledgeBase | null>(null)
  const [docs, setDocs] = useState<KBDocument[]>([])
  const [docsLoading, setDocsLoading] = useState(false)
  const [modal, setModal] = useState<'create' | 'addDoc' | 'deleteKb' | 'deleteDoc' | 'viewDoc' | null>(null)
  const [kbForm, setKbForm] = useState({ name: '', description: '' })
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [selectedDoc, setSelectedDoc] = useState<KBDocument | null>(null)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [viewChunks, setViewChunks] = useState<{ doc: KBDocument; chunks: DocumentChunk[] } | null>(null)
  const [chunksLoading, setChunksLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    const r = await adminApi.knowledge.list()
    if (r.ok) setKbs(r.data)
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const loadDocs = async (kb: KnowledgeBase) => {
    setSelected(kb); setDocsLoading(true)
    const r = await adminApi.knowledge.docs(kb.id)
    if (r.ok) setDocs(r.data as KBDocument[])
    setDocsLoading(false)
  }

  const createKb = async () => {
    setSaving(true); setErr(null)
    const r = await adminApi.knowledge.create(kbForm)
    setSaving(false)
    if (r.ok) { setModal(null); load() }
    else setErr(r.error?.message ?? t('admin.knowledge.error.failed'))
  }

  const deleteKb = async () => {
    if (!selected) return
    setSaving(true)
    await adminApi.knowledge.delete(selected.id)
    setSaving(false); setModal(null); setSelected(null); load()
  }

  const addDoc = async () => {
    if (!selected || !uploadFile) return
    setSaving(true); setErr(null)
    const r = await adminApi.knowledge.uploadDoc(selected.id, uploadFile)
    setSaving(false)
    if (r.ok) { setModal(null); setUploadFile(null); loadDocs(selected) }
    else setErr(r.error?.message ?? t('admin.knowledge.error.failed'))
  }

  const deleteDoc = async () => {
    if (!selected || !selectedDoc) return
    setSaving(true)
    await adminApi.knowledge.deleteDoc(selected.id, selectedDoc.id)
    setSaving(false); setModal(null); loadDocs(selected)
  }

  const viewDoc = async (doc: KBDocument) => {
    if (!selected) return
    setChunksLoading(true)
    setViewChunks({ doc, chunks: [] })
    setModal('viewDoc')
    const r = await adminApi.knowledge.chunks(selected.id, doc.id)
    if (r.ok) setViewChunks({ doc, chunks: r.data })
    setChunksLoading(false)
  }

  const docCols: ColDef<KBDocument>[] = [
    { key: 'filename', header: t('admin.knowledge.col.filename'), render: d => <button onClick={() => viewDoc(d)} className="flex items-center gap-2 hover:text-insurance-blue transition-colors text-left"><FileTextIcon size={14} className="text-slate-400 shrink-0" /><span className="font-medium text-sm underline decoration-dotted underline-offset-2">{d.filename}</span></button> },
    { key: 'file_type', header: t('admin.knowledge.col.fileType'), render: d => <code className="text-xs bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">{d.file_type}</code> },
    { key: 'status', header: t('admin.knowledge.col.status'), render: d => <Badge variant={d.status === 'indexed' ? 'active' : d.status === 'processing' ? 'pending' : 'default'} label={d.status} /> },
    { key: 'chunk_count', header: t('admin.knowledge.col.chunkCount'), render: d => d.chunk_count ?? '—' },
    { key: 'created_at', header: t('admin.knowledge.col.createdAt'), render: d => new Date(d.created_at).toLocaleDateString(LOCALE_BCP47[locale]) },
    ...(can('admin') ? [{ key: 'actions' as const, header: t('admin.knowledge.col.actions'), render: (d: KBDocument) => <button onClick={() => { setSelectedDoc(d); setModal('deleteDoc') }} className="rounded-md p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"><TrashIcon /></button> }] : []),
  ]

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{t('admin.knowledge.title')}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{t('admin.knowledge.subtitle')}</p>
        </div>
        {can('agent_manager') && <button className={btnPrimary} onClick={() => { setKbForm({ name: '', description: '' }); setErr(null); setModal('create') }}>
          <PlusIcon />{t('admin.knowledge.button.create')}
        </button>}
      </div>

      {/* KB Grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-32 rounded-xl bg-slate-200 dark:bg-slate-800 animate-pulse" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          {kbs.map(kb => (
            <button
              key={kb.id}
              onClick={() => loadDocs(kb)}
              className={`text-left rounded-xl border p-4 transition-all hover:shadow-md ${selected?.id === kb.id ? 'border-insurance-blue bg-insurance-blue/5 dark:bg-insurance-blue/10' : 'border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-900'}`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <DatabaseIcon size={16} className={selected?.id === kb.id ? 'text-insurance-blue' : 'text-slate-400'} />
                  <span className="font-medium text-sm text-slate-900 dark:text-white">{kb.name}</span>
                </div>
                <Badge variant={kb.status === 'active' ? 'active' : 'inactive'} label={kb.status === 'active' ? t('admin.knowledge.kb.statusActive') : t('admin.knowledge.kb.statusInactive')} />
              </div>
              {kb.description && <p className="mt-2 text-xs text-slate-500 line-clamp-2">{kb.description}</p>}
              <div className="mt-3 flex items-center justify-between">
                <span className="text-xs text-slate-400">{t('admin.knowledge.kb.docCount', { count: kb.document_count })}</span>
                <span className="text-xs text-slate-400">{new Date(kb.created_at).toLocaleDateString(LOCALE_BCP47[locale])}</span>
              </div>
            </button>
          ))}
          {kbs.length === 0 && (
            <div className="col-span-3 rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-10 text-center text-sm text-slate-400">
              {t('admin.knowledge.kb.empty')}
            </div>
          )}
        </div>
      )}

      {/* Selected KB docs */}
      {selected && (
        <div className="rounded-xl border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-900 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-medium text-slate-900 dark:text-white">{t('admin.knowledge.docs.heading', { name: selected.name })}</h2>
            <div className="flex gap-2">
              {can('agent_manager') && <button className={btnPrimary} onClick={() => { setUploadFile(null); setErr(null); setModal('addDoc') }}>
                <PlusIcon size={14} />{t('admin.knowledge.button.addDoc')}
              </button>}
              {can('admin') && <button
                onClick={() => setModal('deleteKb')}
                className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm border border-red-200 text-red-600 hover:bg-red-50 transition-colors"
              >
                <TrashIcon size={14} />{t('admin.knowledge.button.deleteKb')}
              </button>}
            </div>
          </div>
          <DataTable cols={docCols} rows={docs} keyFn={d => d.id} loading={docsLoading} emptyText={t('admin.knowledge.docs.empty')} />
        </div>
      )}

      {/* Create KB */}
      <Modal open={modal === 'create'} onClose={() => setModal(null)} title={t('admin.knowledge.modal.create')}
        footer={<><button className={btnSecondary} onClick={() => setModal(null)}>{t('admin.knowledge.modal.cancel')}</button><button className={btnPrimary} onClick={createKb} disabled={saving}>{saving && <SpinnerIcon />}{t('admin.knowledge.modal.confirmCreate')}</button></>}
      >
        <div className="flex flex-col gap-4">
          {err && <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-600">{err}</div>}
          <FormField label={t('admin.knowledge.field.kbName')} required><input className={inputCls} value={kbForm.name} onChange={e => setKbForm(f => ({ ...f, name: e.target.value }))} /></FormField>
          <FormField label={t('admin.knowledge.field.description')}><textarea className={`${inputCls} resize-none`} rows={3} value={kbForm.description} onChange={e => setKbForm(f => ({ ...f, description: e.target.value }))} /></FormField>
        </div>
      </Modal>

      {/* Add Doc */}
      <Modal open={modal === 'addDoc'} onClose={() => setModal(null)} title={t('admin.knowledge.modal.addDoc')}
        footer={<><button className={btnSecondary} onClick={() => setModal(null)}>{t('admin.knowledge.modal.cancel')}</button><button className={btnPrimary} onClick={addDoc} disabled={saving || !uploadFile}>{saving && <SpinnerIcon />}{t('admin.knowledge.modal.confirmAdd')}</button></>}
      >
        <div className="flex flex-col gap-4">
          {err && <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-600">{err}</div>}
          <FormField label={t('admin.knowledge.field.upload')}>
            <input
              type="file"
              accept=".pdf,application/pdf"
              onChange={e => setUploadFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-500 file:mr-3 file:rounded-lg file:border-0 file:bg-insurance-blue/10 file:px-3 file:py-2 file:text-sm file:font-medium file:text-insurance-blue hover:file:bg-insurance-blue/20 transition-colors"
            />
            <p className="text-xs text-slate-400 mt-1">{t('admin.knowledge.field.uploadHint')}</p>
          </FormField>
        </div>
      </Modal>

      {/* Delete KB confirm */}
      <Modal open={modal === 'deleteKb'} onClose={() => setModal(null)} title={t('admin.knowledge.modal.deleteKb')}
        footer={<><button className={btnSecondary} onClick={() => setModal(null)}>{t('admin.knowledge.modal.cancel')}</button><button className={btnDanger} onClick={deleteKb} disabled={saving}>{saving && <SpinnerIcon />}{t('admin.knowledge.modal.confirmDelete')}</button></>}
      >
        <p className="text-sm text-slate-600 dark:text-slate-400">{t('admin.knowledge.confirm.deleteKbPrefix')}<strong>{selected?.name}</strong>{t('admin.knowledge.confirm.deleteKbSuffix')}</p>
      </Modal>

      {/* Delete Doc confirm */}
      <Modal open={modal === 'deleteDoc'} onClose={() => setModal(null)} title={t('admin.knowledge.modal.deleteDoc')}
        footer={<><button className={btnSecondary} onClick={() => setModal(null)}>{t('admin.knowledge.modal.cancel')}</button><button className={btnDanger} onClick={deleteDoc} disabled={saving}>{saving && <SpinnerIcon />}{t('admin.knowledge.modal.confirmDelete')}</button></>}
      >
        <p className="text-sm text-slate-600 dark:text-slate-400">{t('admin.knowledge.confirm.deleteDocPrefix')}<strong>{selectedDoc?.filename}</strong>{t('admin.knowledge.confirm.deleteDocSuffix')}</p>
      </Modal>

      {/* View Doc chunks */}
      <Modal open={modal === 'viewDoc'} onClose={() => { setModal(null); setViewChunks(null) }} title={viewChunks?.doc.filename ?? t('admin.knowledge.modal.docContent')}
        footer={<button className={btnSecondary} onClick={() => { setModal(null); setViewChunks(null) }}>{t('admin.knowledge.modal.close')}</button>}
      >
        <div className="flex flex-col gap-3 max-h-[60vh] overflow-y-auto overflow-x-hidden min-w-0">
          {chunksLoading ? (
            <div className="flex items-center justify-center py-8 text-sm text-slate-400"><SpinnerIcon />{t('admin.knowledge.chunks.loading')}</div>
          ) : viewChunks?.chunks.length ? (
            viewChunks.chunks.map((chunk) => (
              <div key={chunk.id} className="rounded-lg border border-slate-200 dark:border-slate-700 p-3 min-w-0">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-slate-400">{t('admin.knowledge.chunks.section', { index: chunk.chunk_index + 1 })}</span>
                  <span className="text-xs text-slate-400">{t('admin.knowledge.chunks.tokens', { count: chunk.token_count })}</span>
                </div>
                <div className="text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap wrap-break-word leading-relaxed">{chunk.content}</div>
              </div>
            ))
          ) : (
            <div className="text-center py-8 text-sm text-slate-400">{t('admin.knowledge.chunks.empty')}</div>
          )}
        </div>
      </Modal>
    </div>
  )
}
