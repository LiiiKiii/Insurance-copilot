'use client'

import { useRef } from 'react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/i18n'
import type { UploadPillState } from './UploadPill'

const ACCEPT = '.pdf,.jpg,.jpeg,.png,.webp'
const MAX_BYTES = 50 * 1024 * 1024

interface FileButtonProps {
  sessionKey: string
  onUploadStarted: (state: UploadPillState) => void
  onError?: (msg: string) => void
  disabled?: boolean
  className?: string
}

/**
 * Hidden file input + paperclip button. On select, POSTs to
 * /api/uploads/parse and emits an UploadPillState upward so the
 * parent can render an UploadPill and poll for completion.
 */
export function FileButton({ sessionKey, onUploadStarted, onError, disabled, className }: FileButtonProps) {
  const { t } = useTranslation()
  const inputRef = useRef<HTMLInputElement>(null)

  const onChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = '' // allow re-selecting same file
    if (!f) return
    if (f.size > MAX_BYTES) {
      onError?.(t('upload.error.tooLarge'))
      return
    }

    const form = new FormData()
    form.append('file', f, f.name)
    form.append('session_key', sessionKey)
    try {
      const resp = await fetch('/api/uploads/parse', { method: 'POST', body: form })
      if (!resp.ok) {
        const json = await resp.json().catch(() => ({}))
        onError?.(
          json?.detail?.error?.message ||
            t('upload.error.failedWithStatus', { status: resp.status }),
        )
        return
      }
      const json = await resp.json()
      onUploadStarted({
        uploadId: json.data.upload_id,
        filename: json.data.filename,
        size: json.data.size,
        status: 'parsing',
      })
    } catch (err) {
      onError?.(err instanceof Error ? err.message : t('upload.error.failed'))
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        onChange={onChange}
        className="hidden"
      />
      <button
        type="button"
        aria-label={t('upload.attach.aria')}
        title={t('upload.attach.title')}
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        className={cn(
          'flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors select-none',
          'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
          'hover:bg-slate-200 dark:hover:bg-slate-700',
          'active:scale-95',
          disabled && 'opacity-50 cursor-not-allowed',
          className,
        )}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
        </svg>
      </button>
    </>
  )
}
