'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { BarChartIcon, TrophyIcon, SearchIcon, BookIcon, ClipboardIcon, GearIcon, CheckCircleIcon, WrenchIcon } from './Icons'
import type { ChatMessage } from '@/lib/chatTypes'
import { useTranslation, type MessageKey } from '@/lib/i18n'

type ToolLayer = 'data' | 'reasoning' | 'knowledge' | 'planning'

interface ToolConfig {
  icon: React.ReactNode
  labelKey: MessageKey
  layer: ToolLayer
}

// Stable identifiers (layer keys) so the layer→color lookup keeps working
// regardless of locale. Translated labels come from `tool.label.*` keys.
const TOOL_CONFIG: Record<string, ToolConfig> = {
  // Data Layer
  get_performance_snapshot:    { icon: <BarChartIcon className="w-3 h-3" size={12} />,  labelKey: 'tool.label.performance',          layer: 'data' },
  get_competition_status:      { icon: <TrophyIcon className="w-3 h-3" size={12} />,    labelKey: 'tool.label.competition',          layer: 'data' },
  get_attribution_analysis:    { icon: <SearchIcon className="w-3 h-3" size={12} />,    labelKey: 'tool.label.attribution',          layer: 'data' },
  get_pending_policies:        { icon: <ClipboardIcon className="w-3 h-3" size={12} />, labelKey: 'tool.label.pendingPolicies',      layer: 'data' },
  get_ranking:                 { icon: <BarChartIcon className="w-3 h-3" size={12} />,  labelKey: 'tool.label.ranking',              layer: 'data' },
  get_period_comparison:       { icon: <BarChartIcon className="w-3 h-3" size={12} />,  labelKey: 'tool.label.periodComparison',     layer: 'data' },
  get_agent_profile:           { icon: <BookIcon className="w-3 h-3" size={12} />,      labelKey: 'tool.label.agentProfile',         layer: 'data' },
  get_subordinate_list:        { icon: <BarChartIcon className="w-3 h-3" size={12} />,  labelKey: 'tool.label.subordinates',         layer: 'data' },
  get_team_summary:            { icon: <BarChartIcon className="w-3 h-3" size={12} />,  labelKey: 'tool.label.teamSummary',          layer: 'data' },
  get_team_target_completion:  { icon: <BarChartIcon className="w-3 h-3" size={12} />,  labelKey: 'tool.label.teamTargetCompletion', layer: 'data' },
  // Reasoning Layer
  calc_gap_analysis:           { icon: <GearIcon className="w-3 h-3" size={12} />,      labelKey: 'tool.label.gapAnalysis',          layer: 'reasoning' },
  calc_run_rate:               { icon: <GearIcon className="w-3 h-3" size={12} />,      labelKey: 'tool.label.runRate',              layer: 'reasoning' },
  calc_feasibility:            { icon: <GearIcon className="w-3 h-3" size={12} />,      labelKey: 'tool.label.feasibility',          layer: 'reasoning' },
  calc_attribution_gap:        { icon: <GearIcon className="w-3 h-3" size={12} />,      labelKey: 'tool.label.attributionGap',       layer: 'reasoning' },
  // Knowledge Layer
  search_competition_rules:    { icon: <BookIcon className="w-3 h-3" size={12} />,      labelKey: 'tool.label.competitionRules',     layer: 'knowledge' },
  search_best_practice:        { icon: <BookIcon className="w-3 h-3" size={12} />,      labelKey: 'tool.label.bestPractice',         layer: 'knowledge' },
  search_sales_scripts:        { icon: <BookIcon className="w-3 h-3" size={12} />,      labelKey: 'tool.label.salesScripts',         layer: 'knowledge' },
  search_knowledge_base:       { icon: <BookIcon className="w-3 h-3" size={12} />,      labelKey: 'tool.label.knowledgeBase',        layer: 'knowledge' },
  // Planning Layer
  generate_chase_plan:         { icon: <ClipboardIcon className="w-3 h-3" size={12} />, labelKey: 'tool.label.chasePlan',            layer: 'planning' },
  generate_improvement_advice: { icon: <ClipboardIcon className="w-3 h-3" size={12} />, labelKey: 'tool.label.improvement',          layer: 'planning' },
  // Tool-name aliases
  get_attribution_data:        { icon: <SearchIcon className="w-3 h-3" size={12} />,    labelKey: 'tool.label.attribution',          layer: 'data' },
  get_team_ranking:            { icon: <BarChartIcon className="w-3 h-3" size={12} />,  labelKey: 'tool.label.ranking',              layer: 'data' },
  performance_query:           { icon: <BarChartIcon className="w-3 h-3" size={12} />,  labelKey: 'tool.label.performanceQuery',     layer: 'data' },
  competition_query:           { icon: <TrophyIcon className="w-3 h-3" size={12} />,    labelKey: 'tool.label.competitionQuery',     layer: 'data' },
  attribution_query:           { icon: <SearchIcon className="w-3 h-3" size={12} />,    labelKey: 'tool.label.attribution',          layer: 'data' },
  knowledge_search:            { icon: <BookIcon className="w-3 h-3" size={12} />,      labelKey: 'tool.label.knowledgeBase',        layer: 'knowledge' },
}

const LAYER_COLORS: Record<ToolLayer, string> = {
  data: 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400',
  reasoning: 'bg-amber-50 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400',
  knowledge: 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400',
  planning: 'bg-violet-50 dark:bg-violet-900/30 text-violet-600 dark:text-violet-400',
}

const LAYER_LABEL_KEY: Record<ToolLayer, MessageKey> = {
  data: 'tool.layer.data',
  reasoning: 'tool.layer.reasoning',
  knowledge: 'tool.layer.knowledge',
  planning: 'tool.layer.planning',
}

function matchTool(content: string): string {
  for (const key of Object.keys(TOOL_CONFIG)) {
    if (content.includes(key)) return key
  }
  return ''
}

interface ThinkingProcessProps {
  steps: ChatMessage[]
}

export function ThinkingProcess({ steps }: ThinkingProcessProps) {
  const { t } = useTranslation()
  const [isExpanded, setIsExpanded] = useState(true)

  const uniqueSteps = steps.filter((s, i) => steps.findIndex(x => x.id === s.id) === i)
  if (uniqueSteps.length === 0) return null

  const isStreaming = uniqueSteps.some(s => s.isStreaming)
  const toolCount  = uniqueSteps.filter(s => s.role === 'tool_hint').length

  const getToolConfig = (content: string): ToolConfig | null => {
    const key = matchTool(content)
    return key ? TOOL_CONFIG[key] : null
  }

  return (
    <div className="animate-slide-up my-2">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(e => !e)}
        className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 hover:text-insurance-blue dark:hover:text-insurance-gold-light transition-colors cursor-pointer w-full text-left"
      >
        <span className="relative flex h-2 w-2 shrink-0">
          {isStreaming && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-insurance-gold opacity-75" />}
          <span className={cn('relative inline-flex rounded-full h-2 w-2', isStreaming ? 'bg-insurance-gold' : 'bg-emerald-400')} />
        </span>
        <span className="font-medium flex-1">
          {isStreaming ? t('thinking.analyzing') : t('thinking.completed', { count: toolCount })}
        </span>
        {!isExpanded && toolCount > 0 && (
          <span className="text-[10px] text-slate-400">{t('thinking.steps', { count: toolCount })}</span>
        )}
        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          className={cn('shrink-0 transition-transform', isExpanded ? 'rotate-180' : '')}>
          <path d="m6 9 6 6 6-6"/>
        </svg>
      </button>

      {/* Vertical timeline */}
      {isExpanded && (
        <div className="mt-2 ml-1 relative">
          {/* Timeline line */}
          <div className="absolute left-[7px] top-0 bottom-0 w-px bg-slate-200 dark:bg-slate-700" />

          <div className="space-y-1">
            {uniqueSteps.map((step, idx) => {
              const cfg = step.role === 'tool_hint' ? getToolConfig(step.content) : null
              return (
                <div
                  key={step.id}
                  className="thinking-step-enter relative flex items-start gap-3 pl-5"
                  style={{ animationDelay: `${idx * 40}ms` }}
                >
                  {/* Timeline dot */}
                  <div className={cn(
                    'absolute left-0 top-1.5 w-[15px] h-[15px] rounded-full border-2 flex items-center justify-center z-10',
                    step.role === 'thinking'
                      ? 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900'
                      : step.isStreaming
                        ? 'border-insurance-gold bg-insurance-gold/20'
                        : 'border-emerald-400 bg-emerald-50 dark:bg-emerald-900/30'
                  )}>
                    {step.role === 'tool_hint' && !step.isStreaming && (
                      <CheckCircleIcon className="w-2 h-2 text-emerald-500" size={8} />
                    )}
                    {step.isStreaming && (
                      <span className="w-1.5 h-1.5 rounded-full bg-insurance-gold animate-pulse" />
                    )}
                  </div>

                  {step.role === 'thinking' ? (
                    /* Thinking text — italic, lighter */
                    <div className="py-1 text-[11px] leading-relaxed text-slate-400 dark:text-slate-500 italic">
                      {step.content}
                    </div>
                  ) : (
                    /* Tool call — card style */
                    <div className={cn(
                      'flex items-center gap-2 py-1.5 px-3 rounded-lg border',
                      'bg-white dark:bg-slate-800/80 border-slate-200/80 dark:border-slate-700/50',
                      step.isStreaming && 'border-insurance-gold/40'
                    )}>
                      <span className="text-insurance-gold shrink-0">
                        {cfg ? cfg.icon : <WrenchIcon className="w-3 h-3" size={12} />}
                      </span>
                      <span className="text-[11px] font-medium text-slate-700 dark:text-slate-200">
                        {cfg ? t(cfg.labelKey) : step.content}
                      </span>
                      {cfg && (
                        <span className={cn(
                          'text-[9px] px-1.5 py-0.5 rounded-full font-medium',
                          LAYER_COLORS[cfg.layer],
                        )}>
                          {t(LAYER_LABEL_KEY[cfg.layer])}
                        </span>
                      )}
                      {step.isStreaming ? (
                        <span className="tool-hint-loader shrink-0 ml-auto" />
                      ) : (
                        <CheckCircleIcon className="w-3 h-3 text-emerald-400 shrink-0 ml-auto" size={12} />
                      )}
                    </div>
                  )}
                </div>
              )
            })}

            {/* Done marker */}
            {!isStreaming && uniqueSteps.length > 0 && (
              <div className="thinking-step-enter relative flex items-center gap-3 pl-5" style={{ animationDelay: `${uniqueSteps.length * 40}ms` }}>
                <div className="absolute left-0 top-1.5 w-[15px] h-[15px] rounded-full border-2 border-emerald-400 bg-emerald-400 flex items-center justify-center z-10">
                  <CheckCircleIcon className="w-2.5 h-2.5 text-white" size={10} />
                </div>
                <span className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400 py-1">{t('thinking.done')}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
