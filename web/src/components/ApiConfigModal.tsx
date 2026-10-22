'use client'

import { useState, useEffect } from 'react'
import { useTranslation } from '@/lib/i18n'
import { authFetch } from '@/lib/auth'

const STORAGE_KEY = 'insurance_copilot_config'

export interface ApiConfig {
  apiKey: string
  provider: 'openrouter' | 'anthropic' | 'openai-compat'
  model: string
  baseUrl: string
  enableThinking: boolean
}

const DEFAULTS: ApiConfig = {
  apiKey: '',
  provider: 'openrouter',
  model: 'openai/gpt-5.2',
  baseUrl: 'https://openrouter.ai/api/v1',
  enableThinking: false,
}

// Models that support extended thinking / interleaved thinking
const THINKING_SUPPORTED_MODELS = new Set([
  'anthropic/claude-3.7-sonnet',
  'anthropic/claude-3.7-sonnet:thinking',
  'anthropic/claude-3.5-sonnet-20241022',
  'anthropic/claude-sonnet-4-6',
  'anthropic/claude-opus-4-6',
  // xAI Grok reasoning
  'x-ai/grok-4.20-beta',
  'x-ai/grok-4.20-multi-agent-beta',
  // Qwen3/3.5 thinking
  'qwen/qwen3.5-122b-a10b',
  'qwen/qwen3.5-35b-a3b',
  'qwen/qwen3.5-27b',
  'qwen/qwen3.5-flash-02-23',
  'qwen/qwen3.5-9b',
  'qwen/qwen3-235b-a22b',
  'qwen/qwen3-32b',
  'qwen/qwen3-30b-a3b',
  // Google Gemini thinking
  'google/gemini-3.1-pro-preview-customtools',
  'google/gemini-3.1-flash-lite-preview',
  'google/gemini-2.5-pro-preview',
  // DeepSeek R1 (reasoning)
  'deepseek/deepseek-r1-0528',
  'deepseek/deepseek-r1',
  // MiniMax M2.7
  'minimax/minimax-m2.7',
  // NVIDIA Nemotron
  'nvidia/nemotron-3-super-120b-a12b',
  // Xiaomi MiMo
  'xiaomi/mimo-v2-pro',
  // Z.ai GLM-5
  'z-ai/glm-5-turbo',
  // Inception Mercury
  'inception/mercury-2',
  // ByteDance Seed
  'bytedance-seed/seed-2.0-lite',
  'bytedance-seed/seed-2.0-mini',
  // OpenAI GPT-5.x reasoning
  'openai/gpt-5.4-pro',
  'openai/gpt-5.4',
  'openai/gpt-5.4-mini',
  'openai/gpt-5.4-nano',
  'openai/gpt-5.3-chat',
  'openai/gpt-5.3-codex',
  'openai/gpt-5.2',
])

// OpenRouter model list — latest models first
const OPENROUTER_MODELS = [
  // ── Anthropic ──────────────────────────────────────────────
  { value: 'anthropic/claude-opus-4-6',             label: 'Claude Opus 4.6 ✦',           group: 'Anthropic' },
  { value: 'anthropic/claude-sonnet-4-6',           label: 'Claude Sonnet 4.6',            group: 'Anthropic' },
  { value: 'anthropic/claude-3.7-sonnet',           label: 'Claude 3.7 Sonnet',            group: 'Anthropic' },
  { value: 'anthropic/claude-3.7-sonnet:thinking',  label: 'Claude 3.7 Sonnet (Thinking)', group: 'Anthropic' },
  { value: 'anthropic/claude-3.5-sonnet-20241022',  label: 'Claude 3.5 Sonnet',            group: 'Anthropic' },
  { value: 'anthropic/claude-3.5-haiku-20241022',   label: 'Claude 3.5 Haiku',             group: 'Anthropic' },
  // ── OpenAI ─────────────────────────────────────────────────
  { value: 'openai/gpt-5.4-pro',                    label: 'GPT-5.4 Pro ✦',               group: 'OpenAI' },
  { value: 'openai/gpt-5.4',                        label: 'GPT-5.4',                      group: 'OpenAI' },
  { value: 'openai/gpt-5.4-mini',                   label: 'GPT-5.4 mini',                 group: 'OpenAI' },
  { value: 'openai/gpt-5.4-nano',                   label: 'GPT-5.4 nano ⚡',              group: 'OpenAI' },
  { value: 'openai/gpt-5.3-chat',                   label: 'GPT-5.3 Chat',                 group: 'OpenAI' },
  { value: 'openai/gpt-5.3-codex',                  label: 'GPT-5.3 Codex',                group: 'OpenAI' },
  { value: 'openai/gpt-5.2',                        label: 'GPT-5.2',                      group: 'OpenAI' },
  { value: 'openai/gpt-4.1',                        label: 'GPT-4.1',                      group: 'OpenAI' },
  { value: 'openai/gpt-4.1-mini',                   label: 'GPT-4.1 mini',                 group: 'OpenAI' },
  { value: 'openai/gpt-4o',                         label: 'GPT-4o',                       group: 'OpenAI' },
  { value: 'openai/gpt-4o-mini',                    label: 'GPT-4o mini',                  group: 'OpenAI' },
  { value: 'openai/o3',                             label: 'o3',                           group: 'OpenAI' },
  { value: 'openai/o4-mini',                        label: 'o4-mini',                      group: 'OpenAI' },
  // ── Google ─────────────────────────────────────────────────
  { value: 'google/gemini-3.1-pro-preview-customtools', label: 'Gemini 3.1 Pro ✦',        group: 'Google' },
  { value: 'google/gemini-3.1-flash-lite-preview',  label: 'Gemini 3.1 Flash Lite',        group: 'Google' },
  { value: 'google/gemini-2.5-pro-preview',         label: 'Gemini 2.5 Pro',               group: 'Google' },
  { value: 'google/gemini-2.0-flash-001',           label: 'Gemini 2.0 Flash',             group: 'Google' },
  // ── xAI (Grok) ────────────────────────────────────────────
  { value: 'x-ai/grok-4.20-beta',                   label: 'Grok 4.20 ✦',                  group: 'xAI' },
  { value: 'x-ai/grok-4.20-multi-agent-beta',       label: 'Grok 4.20 Multi-Agent',        group: 'xAI' },
  // ── DeepSeek ───────────────────────────────────────────────
  { value: 'deepseek/deepseek-r1-0528',             label: 'DeepSeek R1 0528 ✦',           group: 'DeepSeek' },
  { value: 'deepseek/deepseek-r1',                  label: 'DeepSeek R1',                  group: 'DeepSeek' },
  { value: 'deepseek/deepseek-r1-distill-qwen-32b', label: 'DeepSeek R1 Qwen 32B',         group: 'DeepSeek' },
  { value: 'deepseek/deepseek-chat',                label: 'DeepSeek V3',                  group: 'DeepSeek' },
  // ── Qwen ───────────────────────────────────────────────────
  { value: 'qwen/qwen3.5-122b-a10b',               label: 'Qwen3.5 122B ✦',               group: 'Qwen' },
  { value: 'qwen/qwen3.5-35b-a3b',                 label: 'Qwen3.5 35B',                  group: 'Qwen' },
  { value: 'qwen/qwen3.5-27b',                     label: 'Qwen3.5 27B',                  group: 'Qwen' },
  { value: 'qwen/qwen3.5-flash-02-23',             label: 'Qwen3.5 Flash ⚡',             group: 'Qwen' },
  { value: 'qwen/qwen3.5-9b',                      label: 'Qwen3.5 9B',                   group: 'Qwen' },
  { value: 'qwen/qwen3-235b-a22b',                  label: 'Qwen3 235B',                   group: 'Qwen' },
  { value: 'qwen/qwen3-32b',                        label: 'Qwen3 32B',                    group: 'Qwen' },
  { value: 'qwen/qwen3-30b-a3b',                    label: 'Qwen3 30B A3B',                group: 'Qwen' },
  { value: 'qwen/qwq-32b',                          label: 'QwQ 32B',                      group: 'Qwen' },
  { value: 'qwen/qwen-2.5-72b-instruct',            label: 'Qwen 2.5 72B',                 group: 'Qwen' },
  { value: 'qwen/qwen-2.5-coder-32b-instruct',      label: 'Qwen 2.5 Coder 32B',           group: 'Qwen' },
  // ── Moonshot (Kimi) ────────────────────────────────────────
  { value: 'moonshotai/kimi-k2-0905',               label: 'Kimi K2 0905 ✦',               group: 'Moonshot' },
  { value: 'moonshotai/kimi-k2',                    label: 'Kimi K2',                      group: 'Moonshot' },
  // ── MiniMax ───────────────────────────────────────────────
  { value: 'minimax/minimax-m2.7',                  label: 'MiniMax M2.7 ✦',               group: 'MiniMax' },
  // ── ByteDance Seed ────────────────────────────────────────
  { value: 'bytedance-seed/seed-2.0-lite',          label: 'Seed 2.0 Lite ✦',             group: 'ByteDance' },
  { value: 'bytedance-seed/seed-2.0-mini',          label: 'Seed 2.0 Mini ⚡',            group: 'ByteDance' },
  // ── Mistral ───────────────────────────────────────────────
  { value: 'mistralai/mistral-small-2603',          label: 'Mistral Small 4 ✦',            group: 'Mistral' },
  { value: 'mistralai/mistral-large-2411',          label: 'Mistral Large',                group: 'Mistral' },
  { value: 'mistralai/mistral-nemo',                label: 'Mistral Nemo ⚡',              group: 'Mistral' },
  // ── NVIDIA ────────────────────────────────────────────────
  { value: 'nvidia/nemotron-3-super-120b-a12b',     label: 'Nemotron 3 Super 120B ✦',     group: 'NVIDIA' },
  { value: 'nvidia/nemotron-3-super-120b-a12b:free',label: 'Nemotron 3 Super (FREE)',      group: 'NVIDIA' },
  // ── Xiaomi MiMo ───────────────────────────────────────────
  { value: 'xiaomi/mimo-v2-pro',                    label: 'MiMo V2 Pro ✦ (1M ctx)',       group: 'Xiaomi' },
  { value: 'xiaomi/mimo-v2-omni',                   label: 'MiMo V2 Omni (Multimodal)',    group: 'Xiaomi' },
  // ── Z.ai (GLM) ────────────────────────────────────────────
  { value: 'z-ai/glm-5-turbo',                      label: 'GLM-5 Turbo ✦',               group: 'Z.ai' },
  // ── Inception ────────────────────────────────────────────
  { value: 'inception/mercury-2',                   label: 'Mercury 2 ⚡ (1000 tok/s)',    group: 'Inception' },
  // ── Meta ───────────────────────────────────────────────────
  { value: 'meta-llama/llama-4-scout',              label: 'Llama 4 Scout ✦',             group: 'Meta' },
  { value: 'meta-llama/llama-3.3-70b-instruct',     label: 'Llama 3.3 70B',               group: 'Meta' },
]

const ANTHROPIC_MODELS = [
  { value: 'claude-3-7-sonnet-20250219',  label: 'Claude 3.7 Sonnet ✦', group: 'Anthropic' },
  { value: 'claude-3-5-sonnet-20241022',  label: 'Claude 3.5 Sonnet',  group: 'Anthropic' },
  { value: 'claude-3-5-haiku-20241022',   label: 'Claude 3.5 Haiku',   group: 'Anthropic' },
  { value: 'claude-opus-4-6',             label: 'Claude Opus 4.6',    group: 'Anthropic' },
  { value: 'claude-sonnet-4-6',           label: 'Claude Sonnet 4.6',  group: 'Anthropic' },
]


export function loadApiConfig(): ApiConfig {
  if (typeof window === 'undefined') return DEFAULTS
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULTS
    return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch {
    return DEFAULTS
  }
}

export function saveApiConfig(cfg: ApiConfig) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg))
}

// ---- Icons (inline SVG, no emoji) ----

function IconKey({ className = 'w-4 h-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="7.5" cy="15.5" r="5.5" />
      <path d="M21 2l-9.6 9.6" />
      <path d="M15.5 7.5l3 3L22 7l-3-3" />
    </svg>
  )
}

function IconEye({ open, className = 'w-4 h-4' }: { open: boolean; className?: string }) {
  return open ? (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  ) : (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function IconX({ className = 'w-5 h-5' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function IconCheck({ className = 'w-4 h-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function IconAlert({ className = 'w-4 h-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  )
}

function IconWifi({ className = 'w-4 h-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12.55a11 11 0 0114.08 0" />
      <path d="M1.42 9a16 16 0 0121.16 0" />
      <path d="M8.53 16.11a6 6 0 016.95 0" />
      <line x1="12" y1="20" x2="12.01" y2="20" />
    </svg>
  )
}

function IconBrain({ className = 'w-4 h-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.44-4.14" />
      <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.44-4.14" />
    </svg>
  )
}

function Spinner({ className = 'w-4 h-4' }) {
  return (
    <svg className={`${className} animate-spin`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

// ---- Feature model types ----

interface FeatureModelEntry {
  slug: string
  label: string
  desc: string
  model: string
}

function IconSliders({ className = 'w-4 h-4' }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>
      <line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>
      <line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>
      <line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/>
      <line x1="17" y1="16" x2="23" y2="16"/>
    </svg>
  )
}

// ---- Component ----

interface Props {
  open: boolean
  onClose: () => void
  onSave: (cfg: ApiConfig) => void
}

export function ApiConfigModal({ open, onClose, onSave }: Props) {
  const { t } = useTranslation()
  const [cfg, setCfg]                 = useState<ApiConfig>(DEFAULTS)
  const [showKey, setShowKey]         = useState(false)
  const [customModel, setCustomModel] = useState('')
  const [testing, setTesting]         = useState(false)
  const [testResult, setTestResult]   = useState<{ ok: boolean; msg: string } | null>(null)
  const [activeTab, setActiveTab]     = useState<'api' | 'features'>('api')
  const [featureModels, setFeatureModels] = useState<FeatureModelEntry[]>([])
  const [featureSaving, setFeatureSaving] = useState<string | null>(null)

  // Load feature models from backend
  const loadFeatureModels = async () => {
    try {
      const res = await authFetch('/api/feature-models')
      const data = await res.json()
      if (data.ok) setFeatureModels(data.data)
    } catch { /* silent */ }
  }

  useEffect(() => {
    if (open) {
      const saved = loadApiConfig()
      setCfg(saved)
      setTestResult(null)
      setCustomModel('')
      loadFeatureModels()
    }
  }, [open])

  const modelList = cfg.provider === 'openrouter' ? OPENROUTER_MODELS : cfg.provider === 'anthropic' ? ANTHROPIC_MODELS : []
  const isCustom = !modelList.some(m => m.value === cfg.model)

  // Group models for display
  const groups = modelList.reduce<Record<string, typeof OPENROUTER_MODELS>>((acc, m) => {
    ;(acc[m.group] ??= []).push(m)
    return acc
  }, {})

  const supportsThinking = THINKING_SUPPORTED_MODELS.has(cfg.model) ||
    cfg.model.includes('claude-3.7') ||
    cfg.model.includes('claude-3-7') ||
    cfg.model.endsWith(':thinking')

  const handleProviderChange = (p: ApiConfig['provider']) => {
    const defaults = p === 'openrouter'
      ? { baseUrl: 'https://openrouter.ai/api/v1', model: 'openai/gpt-5.2' }
      : p === 'anthropic'
      ? { baseUrl: 'https://api.anthropic.com', model: 'claude-3-7-sonnet-20250219' }
      : { baseUrl: '', model: '' }
    setCfg(c => ({ ...c, provider: p, ...defaults, enableThinking: false }))
    setTestResult(null)
  }

  const handleModelSelect = (val: string) => {
    if (val === '__custom__') {
      setCfg(c => ({ ...c, model: customModel || '' }))
    } else {
      // Auto-disable thinking if model doesn't support it
      const nextSupports = THINKING_SUPPORTED_MODELS.has(val) ||
        val.includes('claude-3.7') || val.includes('claude-3-7') || val.endsWith(':thinking')
      setCfg(c => ({ ...c, model: val, enableThinking: nextSupports ? c.enableThinking : false }))
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await authFetch('/api/config/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      })
      const data = await res.json()
      const rawMsg = data.message || (data.ok ? t('apiConfig.test.success') : t('apiConfig.test.failure'))
      const msg = data.ok
        ? t('apiConfig.test.successWithModel', { model: cfg.model })
        : rawMsg
            .replace('Connection failed:', `${t('apiConfig.test.failure')}:`)
            .replace('Connected:', `${t('apiConfig.test.success')}:`)
      setTestResult({ ok: data.ok, msg })
    } catch {
      setTestResult({ ok: false, msg: t('apiConfig.test.networkError') })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = () => {
    saveApiConfig(cfg)
    onSave(cfg)
    onClose()
  }

  if (!open) return null

  const selectValue = isCustom ? '__custom__' : cfg.model

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center md:p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* Modal — bottom sheet on mobile, centered on desktop */}
      <div className="relative w-full max-w-lg rounded-t-2xl md:rounded-2xl bg-white dark:bg-slate-900 border-t md:border border-slate-200 dark:border-slate-700 shadow-2xl p-4 md:p-6 space-y-4 md:space-y-5 max-h-[88vh] md:max-h-[90vh] overflow-y-auto overscroll-contain">

        {/* Mobile drag handle */}
        <div className="md:hidden mx-auto -mt-2 mb-1 h-1 w-10 shrink-0 rounded-full bg-slate-300 dark:bg-slate-600" />

        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-insurance-blue/10 dark:bg-insurance-gold/10 flex items-center justify-center text-insurance-blue dark:text-insurance-gold">
              {activeTab === 'api' ? <IconKey className="w-4 h-4" /> : <IconSliders className="w-4 h-4" />}
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-900 dark:text-white leading-none">
                {activeTab === 'api' ? t('apiConfig.tab.api.title') : t('apiConfig.tab.featureModels.title')}
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                {activeTab === 'api' ? t('apiConfig.tab.api.subtitle') : t('apiConfig.tab.featureModels.subtitle')}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <IconX className="w-4 h-4" />
          </button>
        </div>

        {/* Tab switcher */}
        <div className="flex gap-1 p-1 rounded-lg bg-slate-100 dark:bg-slate-800">
          {(['api', 'features'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 flex items-center justify-center gap-1.5 rounded-md py-1.5 text-xs font-medium transition-all ${
                activeTab === tab
                  ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
              }`}
            >
              {tab === 'api' ? <IconKey className="w-3 h-3" /> : <IconSliders className="w-3 h-3" />}
              {tab === 'api' ? t('apiConfig.tab.api.label') : t('apiConfig.tab.featureModels.label')}
            </button>
          ))}
        </div>

        {activeTab === 'features' ? (
          /* ── Feature Models Tab ── */
          <div className="space-y-3">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {t('apiConfig.featureModels.help')}
            </p>

            {featureModels.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-400">{t('briefing.loading')}</div>
            ) : (
              <div className="space-y-2">
                {featureModels.map(entry => (
                  <div
                    key={entry.slug}
                    className="flex items-start gap-3 p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/40"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-1">
                        <span className="text-xs font-semibold text-slate-800 dark:text-slate-100">{entry.label}</span>
                        <span className="text-[10px] text-slate-400 dark:text-slate-500">{entry.desc}</span>
                      </div>
                      <select
                        value={entry.model || '__global__'}
                        onChange={async (e) => {
                          const newModel = e.target.value === '__global__' ? '' : e.target.value
                          // Optimistic update
                          setFeatureModels(prev => prev.map(m =>
                            m.slug === entry.slug ? { ...m, model: newModel } : m
                          ))
                          setFeatureSaving(entry.slug)
                          try {
                            await authFetch('/api/feature-models', {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ slug: entry.slug, model: newModel }),
                            })
                          } catch { /* silent */ } finally {
                            setFeatureSaving(null)
                          }
                        }}
                        className="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-2.5 py-1.5 text-xs text-slate-800 dark:text-slate-100 focus:outline-none focus:border-insurance-blue dark:focus:border-insurance-gold"
                      >
                        <option value="__global__">{t('apiConfig.featureModels.useDefault')}</option>
                        {OPENROUTER_MODELS.map(m => (
                          <option key={m.value} value={m.value}>{m.label}</option>
                        ))}
                      </select>
                    </div>
                    <div className="shrink-0 mt-5">
                      {featureSaving === entry.slug ? (
                        <Spinner className="w-3.5 h-3.5 text-insurance-gold" />
                      ) : entry.model ? (
                        <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" title={t('apiConfig.featureModels.set')} />
                      ) : (
                        <span className="w-2 h-2 rounded-full bg-slate-300 dark:bg-slate-600 inline-block" title={t('apiConfig.featureModels.usingDefault')} />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={async () => {
                await authFetch('/api/feature-models/reset', { method: 'POST' })
                await loadFeatureModels()
              }}
              className="w-full py-2 text-xs text-slate-500 dark:text-slate-400 hover:text-red-500 dark:hover:text-red-400 border border-dashed border-slate-300 dark:border-slate-600 rounded-lg transition-colors"
            >
              {t('apiConfig.featureModels.reset')}
            </button>
          </div>
        ) : (
          <>
        {/* Provider */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">{t('apiConfig.field.provider')}</label>
          <div className="grid grid-cols-3 gap-2">
            {(['openrouter', 'anthropic', 'openai-compat'] as const).map(p => (
              <button
                key={p}
                onClick={() => handleProviderChange(p)}
                className={`rounded-lg border px-3 py-2.5 text-sm font-medium text-left transition-all ${
                  cfg.provider === p
                    ? 'border-insurance-blue dark:border-insurance-gold bg-insurance-blue/5 dark:bg-insurance-gold/5 text-insurance-blue dark:text-insurance-gold'
                    : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-600'
                }`}
              >
                {p === 'openrouter' ? 'OpenRouter' : p === 'anthropic' ? 'Anthropic' : t('apiConfig.provider.openaiCompat')}
              </button>
            ))}
          </div>
        </div>

        {/* API Key */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">API Key</label>
          <div className="relative">
            <input
              type={showKey ? 'text' : 'password'}
              value={cfg.apiKey}
              onChange={e => setCfg(c => ({ ...c, apiKey: e.target.value }))}
              placeholder={cfg.provider === 'openrouter' ? 'sk-or-v1-...' : cfg.provider === 'anthropic' ? 'sk-ant-...' : 'sk-...'}
              className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2.5 pr-10 text-sm font-mono text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:border-insurance-blue dark:focus:border-insurance-gold focus:outline-none focus:ring-1 focus:ring-insurance-blue/20 dark:focus:ring-insurance-gold/20"
            />
            <button
              type="button"
              onClick={() => setShowKey(s => !s)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
            >
              <IconEye open={showKey} className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Base URL */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">Base URL</label>
          <input
            type="text"
            value={cfg.baseUrl}
            onChange={e => setCfg(c => ({ ...c, baseUrl: e.target.value }))}
            placeholder={cfg.provider === 'openai-compat' ? 'https://api.deepseek.com' : ''}
            className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm font-mono text-slate-900 dark:text-slate-100 focus:border-insurance-blue dark:focus:border-insurance-gold focus:outline-none focus:ring-1 focus:ring-insurance-blue/20"
          />
          {cfg.provider === 'openai-compat' && (
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {t('apiConfig.field.baseUrl.help')}
            </p>
          )}
        </div>

        {/* Model — grouped optgroup */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
            {t('apiConfig.field.model.label')} <span className="normal-case text-slate-400">{t('apiConfig.field.model.recommended')}</span>
          </label>
          {cfg.provider === 'openai-compat' ? (
            <input
              type="text"
              value={cfg.model}
              placeholder={t('apiConfig.field.model.placeholderSimple')}
              className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm font-mono text-slate-900 dark:text-slate-100 focus:border-insurance-blue dark:focus:border-insurance-gold focus:outline-none"
              onChange={e => setCfg(c => ({ ...c, model: e.target.value }))}
            />
          ) : (
            <>
              <select
                value={selectValue}
                onChange={e => handleModelSelect(e.target.value)}
                className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm text-slate-900 dark:text-slate-100 focus:border-insurance-blue dark:focus:border-insurance-gold focus:outline-none"
              >
                {Object.entries(groups).map(([group, models]) => (
                  <optgroup key={group} label={group}>
                    {models.map(m => (
                      <option key={m.value} value={m.value}>{m.label}</option>
                    ))}
                  </optgroup>
                ))}
                <optgroup label={t('apiConfig.field.model.customGroup')}>
                  <option value="__custom__">{t('apiConfig.field.model.customOption')}</option>
                </optgroup>
              </select>
              {(isCustom || selectValue === '__custom__') && (
                <input
                  type="text"
                  value={isCustom ? cfg.model : customModel}
                  placeholder={t('apiConfig.field.model.placeholderOpenrouter')}
                  className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2.5 text-sm font-mono text-slate-900 dark:text-slate-100 focus:border-insurance-blue dark:focus:border-insurance-gold focus:outline-none mt-1.5"
                  onChange={e => {
                    setCustomModel(e.target.value)
                    setCfg(c => ({ ...c, model: e.target.value }))
                  }}
                />
              )}
            </>
          )}
        </div>

        {/* Enable Thinking toggle */}
        <div className={`rounded-xl border p-4 transition-all ${
          supportsThinking
            ? 'border-violet-200 dark:border-violet-700/50 bg-violet-50/50 dark:bg-violet-950/20'
            : 'border-slate-200 dark:border-slate-700 opacity-50'
        }`}>
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-2.5">
              <div className={`mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center flex-none ${
                supportsThinking && cfg.enableThinking
                  ? 'bg-violet-100 dark:bg-violet-900/40 text-violet-600 dark:text-violet-400'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-400'
              }`}>
                <IconBrain className="w-4 h-4" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-900 dark:text-white">{t('apiConfig.thinking.title')}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {supportsThinking
                    ? t('apiConfig.thinking.help.enabled')
                    : t('apiConfig.thinking.help.disabled')
                  }
                </p>
              </div>
            </div>
            <button
              role="switch"
              aria-checked={cfg.enableThinking}
              disabled={!supportsThinking}
              onClick={() => supportsThinking && setCfg(c => ({ ...c, enableThinking: !c.enableThinking }))}
              className={`flex-none relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                cfg.enableThinking && supportsThinking
                  ? 'bg-violet-500'
                  : 'bg-slate-300 dark:bg-slate-600'
              } ${!supportsThinking ? 'cursor-not-allowed' : 'cursor-pointer'}`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform ${
                cfg.enableThinking && supportsThinking ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </button>
          </div>
          {cfg.enableThinking && supportsThinking && (
            <div className="mt-3 flex items-center gap-1.5 text-xs text-violet-600 dark:text-violet-400">
              <IconBrain className="w-3 h-3" />
              <span>{t('apiConfig.thinking.note')} <code className="font-mono bg-violet-100 dark:bg-violet-900/40 px-1 rounded">{'betas=["interleaved-thinking"]'}</code></span>
            </div>
          )}
        </div>

        {/* Test result */}
        {testResult && (
          <div className={`flex items-start gap-2 rounded-lg px-3 py-2.5 text-xs border ${
            testResult.ok
              ? 'bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800'
              : 'bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800'
          }`}>
            {testResult.ok
              ? <IconCheck className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              : <IconAlert className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            }
            <span>{testResult.msg}</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 pt-1">
          <button
            onClick={handleTest}
            disabled={!cfg.apiKey || testing}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-slate-200 dark:border-slate-700 px-4 py-2.5 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40 transition-colors"
          >
            {testing ? <Spinner className="w-4 h-4" /> : <IconWifi className="w-4 h-4" />}
            {testing ? t('apiConfig.test.testing') : t('apiConfig.test.button')}
          </button>
          <button
            onClick={handleSave}
            disabled={!cfg.apiKey}
            className="flex-1 rounded-lg bg-insurance-blue dark:bg-insurance-gold px-4 py-2.5 text-sm font-semibold text-white dark:text-slate-900 hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            {t('apiConfig.save')}
          </button>
        </div>
          </>
        )}
      </div>
    </div>
  )
}
