import { ClipboardIcon, TargetIcon } from './Icons'
import type { ChatResult } from '@/lib/chatTypes'

const SCORE_LABELS: Record<string, string> = {
  expected_contribution: 'Contribution',
  urgency: 'Urgency',
  actionability: 'Actionability',
  business_fit: 'Fit',
}

function text(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined
}

/** "Urgency 36.0 (×0.40)" for each backend score component, in backend order. */
function scoreBreakdown(components: Record<string, unknown> | undefined): string[] {
  if (!components) return []
  return Object.entries(components).flatMap(([name, raw]) => {
    const c = raw as { weight?: unknown; weighted_points?: unknown } | null
    if (!c || typeof c.weighted_points !== 'number') return []
    const weight = typeof c.weight === 'number' ? ` (×${c.weight.toFixed(2)})` : ''
    return [`${SCORE_LABELS[name] ?? name} ${c.weighted_points.toFixed(1)}${weight}`]
  })
}

const PRIORITY_STYLES = {
  P0: 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300',
  P1: 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300',
  P2: 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300',
} as const

function MetricResultCard({ result }: { result: Extract<ChatResult, { kind: 'metrics' }> }) {
  return (
    <section className="overflow-hidden rounded-lg border border-blue-200 bg-blue-50/40 dark:border-blue-800 dark:bg-blue-950/20">
      <header className="flex items-center gap-2 border-b border-blue-200 px-3 py-2 text-sm font-semibold text-insurance-blue dark:border-blue-800 dark:text-blue-300">
        <TargetIcon size={16} />
        {result.title}
      </header>
      <dl className="grid gap-px bg-slate-200/70 sm:grid-cols-2 dark:bg-slate-700/60">
        {result.metrics.map(metric => (
          <div key={metric.label} className="bg-white px-3 py-2.5 dark:bg-slate-900">
            <dt className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {metric.label}
            </dt>
            <dd className="mt-0.5 text-base font-semibold text-slate-900 dark:text-white">
              {metric.value}
            </dd>
            {metric.detail && (
              <dd className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                {metric.detail}
              </dd>
            )}
          </div>
        ))}
      </dl>
      {result.summary && (
        <p className="border-t border-blue-200 px-3 py-2 text-xs leading-relaxed text-slate-600 dark:border-blue-800 dark:text-slate-300">
          {result.summary}
        </p>
      )}
    </section>
  )
}

function ActionPlanResultCard({ result }: { result: Extract<ChatResult, { kind: 'action_plan' }> }) {
  return (
    <section className="overflow-hidden rounded-lg border border-violet-200 bg-violet-50/40 dark:border-violet-800 dark:bg-violet-950/20">
      <header className="flex items-center gap-2 border-b border-violet-200 px-3 py-2 text-sm font-semibold text-violet-700 dark:border-violet-800 dark:text-violet-300">
        <ClipboardIcon size={16} />
        {result.title}
      </header>
      <ol className="divide-y divide-slate-200 bg-white dark:divide-slate-700 dark:bg-slate-900">
        {result.actions.map((item, index) => {
          const signal = text(item.evidence?.action_signal)
          const actBy = text(item.evidence?.action_deadline)
          const credit = text(item.evidence?.expected_realization_date)
          const breakdown = scoreBreakdown(item.score_components)
          return (
          <li key={`${item.priority}-${index}`} className="flex items-start gap-2.5 px-3 py-2.5">
            <span className={`mt-0.5 rounded border px-1.5 py-0.5 text-[10px] font-bold ${PRIORITY_STYLES[item.priority]}`}>
              {item.priority}
            </span>
            <div className="min-w-0 flex-1">
              {(item.rank !== undefined || item.candidate_id) && (
                <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-slate-500 dark:text-slate-400">
                  {item.rank !== undefined && <span className="font-semibold">#{item.rank}</span>}
                  {item.candidate_id && <span className="font-mono">{item.candidate_id}</span>}
                  {typeof item.priority_score === 'number' && (
                    <span>Score {item.priority_score.toFixed(1)}</span>
                  )}
                </div>
              )}
              <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-200">
                {item.action}
              </p>
              {item.timing && (
                <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{item.timing}</p>
              )}
              {(signal || actBy || credit) && (
                <div className="mt-1.5 rounded border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300">
                  {signal && <p className="break-words">{signal}</p>}
                  {(actBy || credit) && (
                    <p className="mt-0.5 flex flex-wrap gap-x-3 text-slate-500 dark:text-slate-400">
                      {actBy && <span>Act by <span className="font-mono">{actBy}</span></span>}
                      {credit && <span>Expected credit <span className="font-mono">{credit}</span></span>}
                    </p>
                  )}
                </div>
              )}
              {breakdown.length > 0 && (
                <p className="mt-1 flex flex-wrap gap-x-2 text-[11px] text-slate-400 dark:text-slate-500">
                  {breakdown.map(part => <span key={part}>{part}</span>)}
                </p>
              )}
            </div>
          </li>
          )
        })}
      </ol>
      {result.summary && (
        <p className="border-t border-violet-200 px-3 py-2 text-xs leading-relaxed text-slate-600 dark:border-violet-800 dark:text-slate-300">
          {result.summary}
        </p>
      )}
      {(result.source || result.as_of_date) && (
        <p className="border-t border-violet-200 px-3 py-2 text-[11px] text-slate-500 dark:border-violet-800 dark:text-slate-400">
          {result.as_of_date && <>Historical snapshot as of {result.as_of_date}</>}
          {result.as_of_date && result.source && ' · '}
          {result.source && <>Source: <span className="font-mono">{result.source}</span></>}
          {result.planning_horizon_start && result.planning_horizon_end && (
            <span className="block">
              Planning horizon {result.planning_horizon_start} to {result.planning_horizon_end}
              {typeof result.normalization_denominator?.value === 'number' && (
                <> · Horizon gap {result.normalization_denominator.value.toLocaleString('en-US')}</>
              )}
            </span>
          )}
          {result.ranking_version && (
            <span className="block">Ranking <span className="font-mono">{result.ranking_version}</span></span>
          )}
        </p>
      )}
    </section>
  )
}

export function ResultCard({ result }: { result: ChatResult }) {
  return result.kind === 'metrics'
    ? <MetricResultCard result={result} />
    : <ActionPlanResultCard result={result} />
}
