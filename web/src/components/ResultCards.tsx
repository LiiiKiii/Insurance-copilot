import { ClipboardIcon, TargetIcon } from './Icons'
import type { ChatResult } from '@/lib/chatTypes'

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
        {result.actions.map((item, index) => (
          <li key={`${item.priority}-${index}`} className="flex items-start gap-2.5 px-3 py-2.5">
            <span className={`mt-0.5 rounded border px-1.5 py-0.5 text-[10px] font-bold ${PRIORITY_STYLES[item.priority]}`}>
              {item.priority}
            </span>
            <span className="text-sm leading-relaxed text-slate-700 dark:text-slate-200">
              {item.action}
            </span>
          </li>
        ))}
      </ol>
      {result.summary && (
        <p className="border-t border-violet-200 px-3 py-2 text-xs leading-relaxed text-slate-600 dark:border-violet-800 dark:text-slate-300">
          {result.summary}
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
