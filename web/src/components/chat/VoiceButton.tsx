'use client'

import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'
import { useVoiceRecorder, type RecorderError } from '@/lib/recorder'
import { useTranslation, type MessageKey } from '@/lib/i18n'

/**
 * Status emitted to the parent so it can render a full-width banner that
 * doesn't clip long Chinese / English labels. `phase` lets the parent pick
 * a color (red while recording, amber while uploading) without parsing
 * the localised label.
 */
export interface VoiceStatus {
  phase: 'recording' | 'uploading'
  label: string
}

interface VoiceButtonProps {
  /** Called with the transcribed text after a successful, non-silent recording. */
  onTranscribed: (text: string) => void
  /** Called when the recorder hits an error or the recording is silent.
   *  Parent should render a visible toast — this prevents the cramped
   *  inside-the-button toast from being cut off. */
  onError?: (message: string) => void
  /** Called whenever the busy status changes — `null` means idle. */
  onStatusChange?: (status: VoiceStatus | null) => void
  /** Disable while the connection is not ready or another send is in flight. */
  disabled?: boolean
  className?: string
}

type Phase = 'idle' | 'recording' | 'uploading' | 'error'

const RECORDER_ERROR_KEY: Record<RecorderError, MessageKey> = {
  permission_denied: 'voice.error.permissionDenied',
  unsupported: 'voice.error.unsupported',
  no_data: 'voice.error.startFailed',
  unknown: 'voice.error.startFailed',
}

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000)
  const m = Math.floor(total / 60).toString().padStart(2, '0')
  const s = (total % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

/**
 * Push-to-talk recorder. Hold the button to record, release to
 * upload + transcribe + auto-send via `onTranscribed`.
 *
 * Permissions are requested lazily on first press.
 */
export function VoiceButton({ onTranscribed, onError, onStatusChange, disabled = false, className }: VoiceButtonProps) {
  const { t } = useTranslation()
  const recorder = useVoiceRecorder()
  const [phase, setPhase] = useState<Phase>('idle')
  const [elapsedMs, setElapsedMs] = useState(0)
  const startedAtRef = useRef<number | null>(null)
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (phase === 'recording') {
      startedAtRef.current = Date.now()
      setElapsedMs(0)
      tickRef.current = setInterval(() => {
        if (startedAtRef.current) setElapsedMs(Date.now() - startedAtRef.current)
      }, 200)
    } else {
      if (tickRef.current) clearInterval(tickRef.current)
      tickRef.current = null
      startedAtRef.current = null
    }
    return () => {
      if (tickRef.current) clearInterval(tickRef.current)
    }
  }, [phase])

  useEffect(() => {
    if (!onStatusChange) return
    if (phase === 'recording') {
      onStatusChange({
        phase: 'recording',
        label: t('voice.recording', { time: formatElapsed(elapsedMs) }),
      })
    } else if (phase === 'uploading') {
      onStatusChange({ phase: 'uploading', label: t('voice.uploading') })
    } else {
      onStatusChange(null)
    }
  }, [phase, elapsedMs, onStatusChange, t])

  const showError = (text: string) => {
    onError?.(text)
    setPhase('error')
    window.setTimeout(() => setPhase('idle'), 1500)
  }

  const begin = async () => {
    if (disabled || phase !== 'idle') return
    const ok = await recorder.start()
    if (!ok) {
      const err = recorder.error
      const key: MessageKey = err && RECORDER_ERROR_KEY[err]
        ? RECORDER_ERROR_KEY[err]
        : 'voice.error.startFailed'
      showError(t(key))
      return
    }
    setPhase('recording')
  }

  // RMS threshold for "voice present" — empirically picked to distinguish
  // typical Cantonese / Mandarin speech from ambient room noise. RMS is on
  // a 0..1 scale; idle laptop mic floor is usually < 0.01, conversational
  // speech peaks above 0.05.
  const VOICE_RMS_THRESHOLD = 0.015
  const MIN_DURATION_MS = 350

  const end = async () => {
    if (phase !== 'recording') return
    setPhase('uploading')
    const result = await recorder.stop()
    if (!result) {
      showError(t('voice.error.noAudio'))
      return
    }
    if (result.durationMs < MIN_DURATION_MS) {
      showError(t('voice.error.tooShort'))
      return
    }
    if (result.maxRms < VOICE_RMS_THRESHOLD) {
      showError(t('voice.error.notDetected'))
      return
    }

    const form = new FormData()
    form.append('file', result.blob, 'clip.webm')
    try {
      const resp = await fetch('/api/audio/transcribe', { method: 'POST', body: form })
      if (!resp.ok) {
        const body = await resp.text().catch(() => '')
        console.error('[voice] /api/audio/transcribe failed:', resp.status, body)
        throw new Error(`transcribe failed: ${resp.status}`)
      }
      const json = await resp.json()
      const text: string = json?.data?.text ?? ''
      // Strip whitespace + ASCII / Unicode punctuation + symbols. If the
      // remaining text is empty, the STT model only returned filler like "."
      // or "。" for silence — don't auto-send.
      const meaningful = text.replace(/[\s\p{P}\p{S}]/gu, '')
      if (meaningful.length > 0) {
        onTranscribed(text.trim())
        setPhase('idle')
      } else {
        showError(t('voice.error.noText'))
      }
    } catch (err) {
      console.error('[voice] transcribe request error:', err)
      showError(t('voice.error.transcribeFailed'))
    }
  }

  const label =
    phase === 'recording' ? t('voice.recording', { time: formatElapsed(elapsedMs) })
    : phase === 'uploading' ? t('voice.uploading')
    : phase === 'error' ? t('voice.failed')
    : t('voice.holdToTalk')

  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled || phase === 'uploading'}
      onPointerDown={(e) => { e.preventDefault(); void begin() }}
      onPointerUp={(e) => { e.preventDefault(); void end() }}
      onPointerLeave={() => { if (phase === 'recording') void end() }}
      onPointerCancel={() => { if (phase === 'recording') void end() }}
      onContextMenu={(e) => e.preventDefault()}
      className={cn(
        'relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors select-none',
        'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
        'hover:bg-slate-200 dark:hover:bg-slate-700',
        'active:scale-95',
        phase === 'recording' && 'bg-red-500 text-white animate-pulse',
        phase === 'uploading' && 'bg-amber-500 text-white',
        phase === 'error' && 'bg-rose-500 text-white',
        disabled && 'opacity-50 cursor-not-allowed',
        className,
      )}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 1 0 6 0V5a3 3 0 0 0-3-3z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="23" />
        <line x1="8" y1="23" x2="16" y2="23" />
      </svg>
    </button>
  )
}
