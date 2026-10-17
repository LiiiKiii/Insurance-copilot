import { cn } from '@/lib/utils'

type Variant = 'active' | 'inactive' | 'pending' | 'warning' | 'error' | 'info' | 'default'

const MAP: Record<Variant, string> = {
  active:   'bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-400 dark:border-emerald-800',
  inactive: 'bg-slate-100 text-slate-500 border border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700',
  pending:  'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800',
  warning:  'bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-800',
  error:    'bg-red-50 text-red-700 border border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800',
  info:     'bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-900/20 dark:text-blue-400 dark:border-blue-800',
  default:  'bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700',
}

interface Props {
  variant?: Variant
  label: string
  className?: string
}

export function Badge({ variant = 'default', label, className }: Props) {
  return (
    <span className={cn(
      'inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium',
      MAP[variant], className,
    )}>
      {label}
    </span>
  )
}
