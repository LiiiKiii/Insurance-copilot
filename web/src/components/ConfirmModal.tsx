'use client'
import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from '@/lib/i18n'

interface Props {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}

export function ConfirmModal({ open, onClose, onConfirm, title, message, confirmText, cancelText, danger = false }: Props) {
  const { t } = useTranslation()
  const resolvedConfirmText = confirmText ?? t('common.confirm')
  const resolvedCancelText = cancelText ?? t('common.cancel')

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    if (open) document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-sm rounded-xl bg-white dark:bg-slate-900 shadow-xl border border-slate-200/60 dark:border-slate-700/50">
        <div className="px-6 py-5">
          <h3 className="text-base font-semibold text-slate-900 dark:text-white">{title}</h3>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{message}</p>
        </div>
        <div className="flex justify-end gap-2 px-6 py-4 border-t border-slate-200/60 dark:border-slate-700/50">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          >
            {resolvedCancelText}
          </button>
          <button
            onClick={() => { onConfirm(); onClose() }}
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors ${danger ? 'bg-red-600 hover:bg-red-700' : 'bg-insurance-blue hover:bg-insurance-blue-light'}`}
          >
            {resolvedConfirmText}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
