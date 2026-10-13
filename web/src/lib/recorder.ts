'use client'

import { useCallback, useRef, useState } from 'react'

export type RecorderError =
  | 'permission_denied'
  | 'unsupported'
  | 'no_data'
  | 'unknown'

export interface RecordingResult {
  blob: Blob
  /** Peak RMS amplitude on a 0..1 scale, sampled every ~100ms during recording. */
  maxRms: number
  /** Recording duration in milliseconds. */
  durationMs: number
}

export interface VoiceRecorder {
  isRecording: boolean
  /** Resolves true when recording actually began, false on any failure. */
  start: () => Promise<boolean>
  /** Resolves with the recording (blob + voice-activity stats) or null on failure. */
  stop: () => Promise<RecordingResult | null>
  error: RecorderError | null
}

const PREFERRED_MIME = 'audio/webm;codecs=opus'

function pickMime(): string {
  if (typeof MediaRecorder === 'undefined') return PREFERRED_MIME
  if (MediaRecorder.isTypeSupported(PREFERRED_MIME)) return PREFERRED_MIME
  if (MediaRecorder.isTypeSupported('audio/webm')) return 'audio/webm'
  if (MediaRecorder.isTypeSupported('audio/mp4')) return 'audio/mp4'
  return ''
}

/**
 * Push-to-talk MediaRecorder wrapper. `start()` requests mic permission
 * lazily, then begins recording AND tapping the audio level via an
 * AnalyserNode for voice activity detection. `stop()` resolves with the
 * captured blob plus the peak RMS observed during recording, so the
 * caller can decide whether to send a silent clip.
 */
export function useVoiceRecorder(): VoiceRecorder {
  const [isRecording, setIsRecording] = useState(false)
  const [error, setError] = useState<RecorderError | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const rmsTickRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const maxRmsRef = useRef<number>(0)
  const startedAtRef = useRef<number>(0)

  const teardownAnalyser = () => {
    if (rmsTickRef.current) {
      clearInterval(rmsTickRef.current)
      rmsTickRef.current = null
    }
    analyserRef.current?.disconnect()
    analyserRef.current = null
    if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
      // Best effort; closing an AudioContext can throw if already closed.
      audioCtxRef.current.close().catch(() => undefined)
    }
    audioCtxRef.current = null
  }

  const start = useCallback(async (): Promise<boolean> => {
    setError(null)
    if (typeof navigator === 'undefined' || !navigator.mediaDevices) {
      console.error('[recorder] navigator.mediaDevices unavailable (insecure context?)')
      setError('unsupported')
      return false
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      const mime = pickMime()
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
      chunksRef.current = []
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorderRef.current = rec

      // Voice-activity probe: AnalyserNode samples the input every 100ms,
      // tracking the peak RMS across the whole recording.
      const AudioCtxCtor =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (AudioCtxCtor) {
        try {
          const ctx = new AudioCtxCtor()
          const source = ctx.createMediaStreamSource(stream)
          const analyser = ctx.createAnalyser()
          analyser.fftSize = 512
          source.connect(analyser)
          audioCtxRef.current = ctx
          analyserRef.current = analyser
          maxRmsRef.current = 0
          const buf = new Float32Array(analyser.fftSize)
          rmsTickRef.current = setInterval(() => {
            if (!analyserRef.current) return
            analyserRef.current.getFloatTimeDomainData(buf)
            let sumSq = 0
            for (let i = 0; i < buf.length; i++) sumSq += buf[i] * buf[i]
            const rms = Math.sqrt(sumSq / buf.length)
            if (rms > maxRmsRef.current) maxRmsRef.current = rms
          }, 100)
        } catch (analyserErr) {
          // VAD is best-effort. If AudioContext fails, recording still works
          // but we'll always report maxRms=0 → caller decides what to do.
          console.warn('[recorder] analyser setup failed; VAD disabled:', analyserErr)
        }
      }

      startedAtRef.current = Date.now()
      rec.start()
      setIsRecording(true)
      return true
    } catch (e: unknown) {
      const name = (e as { name?: string }).name
      const msg = (e as { message?: string }).message
      console.error('[recorder] getUserMedia failed:', name, msg, e)
      setError(name === 'NotAllowedError' || name === 'SecurityError' ? 'permission_denied' : 'unknown')
      return false
    }
  }, [])

  const stop = useCallback(async (): Promise<RecordingResult | null> => {
    const rec = recorderRef.current
    if (!rec) {
      setIsRecording(false)
      teardownAnalyser()
      return null
    }
    return new Promise<RecordingResult | null>((resolve) => {
      rec.onstop = () => {
        const mime = rec.mimeType || 'audio/webm'
        const blob = chunksRef.current.length
          ? new Blob(chunksRef.current, { type: mime })
          : null
        chunksRef.current = []
        recorderRef.current = null

        // Stop all tracks so the mic indicator turns off.
        streamRef.current?.getTracks().forEach((t) => t.stop())
        streamRef.current = null

        const maxRms = maxRmsRef.current
        const durationMs = startedAtRef.current ? Date.now() - startedAtRef.current : 0
        teardownAnalyser()
        setIsRecording(false)

        if (!blob || blob.size === 0) {
          setError('no_data')
          resolve(null)
        } else {
          resolve({ blob, maxRms, durationMs })
        }
      }
      try {
        rec.stop()
      } catch {
        teardownAnalyser()
        setIsRecording(false)
        resolve(null)
      }
    })
  }, [])

  return { isRecording, start, stop, error }
}
