'use client'
import { useCallback, useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

export interface ToastItem {
  id: string
  type: 'success' | 'error'
  message: string
}

const ICONS = {
  success: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  ),
  error: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" />
    </svg>
  ),
}

const STYLES = {
  success: 'bg-emerald-50 dark:bg-emerald-900/30 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300',
  error: 'bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300',
}

function ToastBar({ item, onDismiss }: { item: ToastItem; onDismiss: (id: string) => void }) {
  useEffect(() => {
    const t = setTimeout(() => onDismiss(item.id), 3000)
    return () => clearTimeout(t)
  }, [item.id, onDismiss])

  return (
    <div className={cn('flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm shadow-lg', STYLES[item.type])}>
      {ICONS[item.type]}
      <span>{item.message}</span>
      <button onClick={() => onDismiss(item.id)} className="ml-2 opacity-50 hover:opacity-100 transition-opacity">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
      </button>
    </div>
  )
}

export function ToastContainer({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: string) => void }) {
  if (toasts.length === 0) return null
  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map(t => <ToastBar key={t.id} item={t} onDismiss={onDismiss} />)}
    </div>
  )
}

let _counter = 0

export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const toast = useCallback((type: 'success' | 'error', message: string) => {
    const id = `toast-${++_counter}`
    setToasts(prev => [...prev, { id, type, message }])
  }, [])

  return { toasts, toast, dismiss }
}
