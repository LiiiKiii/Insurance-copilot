'use client'

import { formatDate } from '@/lib/utils'
import { MarkdownRenderer } from './MarkdownRenderer'
import type { ChatMessage } from '@/lib/chatTypes'
import { useTranslation, type MessageKey } from '@/lib/i18n'

// Detect if message content contains a structured competition table.
// These heuristics inspect the agent's response (English), matched
// case-insensitively.
function hasCompetitionTable(content: string): boolean {
  const text = content.toLowerCase()
  return (
    (text.includes('competition') || text.includes('mdrt') || text.includes('starlight')) &&
    text.includes('|') &&
    (text.includes('gap') || text.includes('deadline') || text.includes('days'))
  )
}

// Detect if message contains an action plan (text-based, no emoji).
function hasActionPlan(content: string): boolean {
  const text = content.toLowerCase()
  const hasPriority = text.includes('urgent') || text.includes('important') || text.includes('recommend')
  const hasStructure = text.includes('action') || text.includes('plan') || text.includes('step') || text.includes('priority')
  return hasPriority && hasStructure
}

// Substring match → loading-text translation key.
const TOOL_LOADING_PATTERNS: { match: string[]; key: MessageKey }[] = [
  // Data layer
  { match: ['get_performance_snapshot', 'performance_query'], key: 'tool.loading.performance' },
  { match: ['get_competition_status', 'competition_query'], key: 'tool.loading.competition' },
  { match: ['get_attribution_data', 'attribution_query'], key: 'tool.loading.attribution' },
  { match: ['get_pending_policies', 'pending_policies'], key: 'tool.loading.pendingPolicies' },
  { match: ['get_team_ranking'], key: 'tool.loading.ranking' },
  { match: ['get_period_comparison'], key: 'tool.loading.periodComparison' },
  { match: ['get_agent_profile'], key: 'tool.loading.agentProfile' },
  // Reasoning layer
  { match: ['calc_gap_analysis'], key: 'tool.loading.gapAnalysis' },
  { match: ['calc_run_rate'], key: 'tool.loading.runRate' },
  { match: ['calc_feasibility'], key: 'tool.loading.feasibility' },
  { match: ['calc_attribution_gap'], key: 'tool.loading.attributionGap' },
  // Knowledge layer
  { match: ['search_competition_rules', 'knowledge_search'], key: 'tool.loading.competitionRules' },
  { match: ['search_best_practice'], key: 'tool.loading.bestPractice' },
  { match: ['search_sales_scripts'], key: 'tool.loading.salesScripts' },
  // Planning layer
  { match: ['generate_chase_plan', 'chase_plan'], key: 'tool.loading.chasePlan' },
  { match: ['generate_improvement_advice'], key: 'tool.loading.improvement' },
]

interface MessageBubbleProps {
  message: ChatMessage
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const { t, locale } = useTranslation()
  const { role, content, timestamp } = message

  if (role === 'tool_hint') {
    const matched = TOOL_LOADING_PATTERNS.find((p) => p.match.some((m) => content.includes(m)))
    const label = matched ? t(matched.key) : t('tool.loading.fallback', { tool: content.split('(')[0] })
    return (
      <div className="animate-slide-up flex justify-center py-2">
        <div className="shimmer-bg inline-flex items-center gap-2.5 px-4 py-2 rounded-lg text-xs text-slate-600 dark:text-slate-300 bg-white/85 dark:bg-slate-900/70 border border-slate-200/80 dark:border-slate-700/70 shadow-sm">
          <span className="tool-hint-loader" aria-hidden="true" />
          <span>{label}</span>
        </div>
      </div>
    )
  }

  if (role === 'tool_summary') {
    // Collapsed single-line summary of all tools used
    const toolCount = content.split('→').length
    return (
      <div className="flex justify-center py-1.5">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-xs text-slate-500 dark:text-slate-400 bg-slate-50/80 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-700/50">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
          <span>{t('thinking.completed', { count: toolCount })}</span>
        </div>
      </div>
    )
  }

  if (role === 'thinking') {
    return (
      <div className="animate-slide-up flex py-2 px-4">
        <p className="text-xs italic text-slate-500 dark:text-slate-400">{content}</p>
      </div>
    )
  }

  if (role === 'user') {
    const labels = message.attachmentLabels ?? []
    return (
      <div className="animate-slide-up flex justify-end py-2">
        <div className="max-w-[90%] md:max-w-[70%]">
          <div className="rounded-lg rounded-br-sm px-4 py-2.5 bg-gradient-to-br from-insurance-gold via-insurance-gold-light to-[#E58A3A] text-white shadow-[0_8px_18px_rgba(201,168,76,0.35)]">
            {labels.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-1">
                {labels.map((name) => (
                  <span key={name} className="inline-flex items-center gap-1 rounded-full bg-white/20 px-2 py-0.5 text-[10px] text-white/95">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                    <span className="max-w-[180px] truncate">{name}</span>
                  </span>
                ))}
              </div>
            )}
            {content && <p className="text-sm leading-relaxed whitespace-pre-wrap">{content}</p>}
          </div>
          <p className="text-[10px] text-slate-400 dark:text-slate-500 text-right mt-1 mr-1">{formatDate(timestamp, locale)}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="animate-slide-up flex py-2 min-w-0">
      <div className="max-w-[95%] md:max-w-full min-w-0 flex-1">
          <div className={`rounded-lg rounded-bl-sm pl-4 pr-4 py-3 bg-white dark:bg-[rgba(30,58,95,0.5)] border shadow-sm border-l-[3px] ${
            hasCompetitionTable(content)
              ? 'border-amber-300 dark:border-amber-600 border-l-amber-500 bg-amber-50/30 dark:bg-amber-950/10'
              : hasActionPlan(content)
              ? 'border-blue-200 dark:border-blue-800 border-l-insurance-blue'
              : 'border-slate-200 dark:border-slate-700 border-l-insurance-gold'
          }`}>
            {hasCompetitionTable(content) && (
              <div className="flex items-center gap-1.5 mb-2 pb-2 border-b border-amber-200/60 dark:border-amber-800/40">
                <span className="text-[10px] font-semibold tracking-wide text-amber-600 dark:text-amber-400 uppercase">{t('bubble.competition.label')}</span>
                <span className="w-1 h-1 rounded-full bg-amber-400"></span>
                <span className="text-[10px] text-amber-500 dark:text-amber-500">{t('bubble.competition.tag')}</span>
              </div>
            )}
            {hasActionPlan(content) && (
              <div className="flex items-center gap-1.5 mb-2 pb-2 border-b border-blue-200/60 dark:border-blue-800/40">
                <span className="text-[10px] font-semibold tracking-wide text-insurance-blue dark:text-blue-400 uppercase">{t('bubble.actionPlan.label')}</span>
                <span className="w-1 h-1 rounded-full bg-insurance-blue/60"></span>
                <span className="text-[10px] text-slate-400">{t('bubble.actionPlan.tag')}</span>
              </div>
            )}
            <div className="markdown-content text-sm text-slate-700 dark:text-slate-200 leading-relaxed">
              <MarkdownRenderer content={content} />
            </div>
          </div>
          <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1 ml-1">{formatDate(timestamp, locale)}</p>
      </div>
    </div>
  )
}
