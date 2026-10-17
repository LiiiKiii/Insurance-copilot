'use client'

import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/i18n'

export type UploadStatus = 'parsing' | 'ready' | 'failed'

export interface UploadPillState {
  uploadId: string
  filename: string
  size: number
  status: UploadStatus
  error?: string
}

interface UploadPillProps {
  state: UploadPillState
  onUpdate: (next: UploadPillState) => void
  onCancel: (uploadId: string) => void
}

const POLL_INTERVAL_MS = 1500

function bytesHuman(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

/**
 * Polls /api/uploads/{id} until the row reaches a terminal state. The
 * parent owns the state — this component reports updates upward via
 * `onUpdate` so siblings (e.g. the send button) can react.
 */
export function UploadPill({ state, onUpdate, onCancel }: UploadPillProps) {
  const { t } = useTranslation()
  const [, force] = useState(0)

  useEffect(() => {
    if (state.status !== 'parsing') return
    let cancelled = false
    const tick = async () => {
      try {
        const resp = await fetch(`/api/uploads/${state.uploadId}`)
        if (!resp.ok) throw new Error(`status ${resp.status}`)
        const json = await resp.json()
        const nextStatus: UploadStatus = json?.data?.status ?? 'parsing'
        if (cancelled) return
        if (nextStatus !== state.status) {
          onUpdate({
            ...state,
            status: nextStatus,
            error: json?.data?.error_message ?? undefined,
          })
        } else {
          force((n) => n + 1) // keep poll loop alive
        }
      } catch {
        if (!cancelled) force((n) => n + 1)
      }
    }
    const t = setInterval(tick, POLL_INTERVAL_MS)
    void tick()
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [state.uploadId, state.status, onUpdate])

  const tone =
    state.status === 'parsing' ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
    : state.status === 'ready' ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300'
    : 'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300'

  const statusLabel =
    state.status === 'parsing' ? t('upload.pill.parsing')
    : state.status === 'ready' ? t('upload.pill.ready')
    : t('upload.pill.failed')

  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs', tone)}>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
      </svg>
      <span className="max-w-[140px] truncate" title={state.filename}>{state.filename}</span>
      <span className="text-[10px] text-slate-500">{bytesHuman(state.size)}</span>
      <span className="text-[10px]">·</span>
      <span className="text-[10px]">{statusLabel}</span>
      <button
        type="button"
        aria-label={t('upload.pill.remove.aria')}
        onClick={() => onCancel(state.uploadId)}
        className="ml-1 -mr-1 flex h-4 w-4 items-center justify-center rounded-full hover:bg-black/10 dark:hover:bg-white/10"
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </span>
  )
}
