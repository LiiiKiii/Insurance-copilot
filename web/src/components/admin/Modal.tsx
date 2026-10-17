'use client'
import { useEffect } from 'react'
import { cn } from '@/lib/utils'
import { XIcon } from './AdminIcons'
import { useTranslation } from '@/lib/i18n'

interface Props {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  footer?: React.ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
}

const SIZE = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
}

export function Modal({ open, onClose, title, children, footer, size = 'md' }: Props) {
  const { t } = useTranslation()
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center md:p-4">
      {/* backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      {/* panel */}
      <div className={cn(
        'relative z-10 w-full bg-white dark:bg-slate-900',
        'shadow-xl border-t md:border border-slate-200/60 dark:border-slate-700/50',
        'flex flex-col',
        'rounded-t-2xl md:rounded-xl',
        'max-h-[92vh] md:max-h-[90vh]',
        'h-[92vh] md:h-auto',
        SIZE[size],
      )}>
        {/* mobile drag handle */}
        <div className="md:hidden mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-slate-300 dark:bg-slate-600" />
        {/* header */}
        <div className="flex items-center justify-between px-4 md:px-6 py-3 md:py-4 border-b border-slate-200/60 dark:border-slate-700/50 shrink-0">
          <h2 className="font-semibold text-slate-900 dark:text-white text-base truncate pr-2">{title}</h2>
          <button
            onClick={onClose}
            aria-label={t('admin.common.close.aria')}
            className="rounded-lg p-2 min-h-11 min-w-11 flex items-center justify-center text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <XIcon size={16} />
          </button>
        </div>
        {/* body */}
        <div className="overflow-y-auto flex-1 px-4 md:px-6 py-4">{children}</div>
        {/* footer */}
        {footer && (
          <div className="shrink-0 flex flex-wrap justify-end gap-2 px-4 md:px-6 py-3 md:py-4 border-t border-slate-200/60 dark:border-slate-700/50 pb-[calc(env(safe-area-inset-bottom)+0.75rem)] md:pb-4">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

// Reusable form field wrapper
export function FormField({ label, error, children, required }: {
  label: string; error?: string; children: React.ReactNode; required?: boolean
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

// Reusable input style
export const inputCls = [
  'w-full rounded-lg border border-slate-200 dark:border-slate-700',
  'bg-white dark:bg-slate-800 px-3 py-2 text-sm',
  'text-slate-900 dark:text-white placeholder:text-slate-400',
  'focus:outline-none focus:ring-2 focus:ring-insurance-blue/30 focus:border-insurance-blue dark:focus:border-blue-500',
  'transition-colors',
].join(' ')

export const btnPrimary = [
  'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium',
  'bg-insurance-blue text-white hover:bg-insurance-blue-light active:bg-insurance-blue-dark',
  'transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
].join(' ')

export const btnSecondary = [
  'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium',
  'border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300',
  'hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors',
].join(' ')

export const btnDanger = [
  'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium',
  'bg-red-600 text-white hover:bg-red-700 transition-colors disabled:opacity-50',
].join(' ')
