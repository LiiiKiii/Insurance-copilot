'use client'
import { useMemo, useState } from 'react'
import { cn } from '@/lib/utils'
import { ChevronLeftIcon, ChevronRightIcon } from './AdminIcons'
import { useTranslation, LOCALE_BCP47 } from '@/lib/i18n'

export interface ColDef<T> {
  key: string
  header: string
  render?: (row: T) => React.ReactNode
  className?: string
  sortable?: boolean
  sortAccessor?: (row: T) => string | number | null
}

interface Props<T> {
  cols: ColDef<T>[]
  rows: T[]
  keyFn: (row: T) => string
  loading?: boolean
  page?: number
  pageSize?: number
  total?: number
  onPageChange?: (p: number) => void
  emptyText?: string
  className?: string
  /** Number of primary fields to show prominently in mobile card mode. Default 3. */
  mobileCardMaxPrimary?: number
  /** Opt out of mobile card mode (keep table with overflow-x-auto on all viewports). */
  disableMobileCard?: boolean
}

function Skeleton({ cols }: { cols: number }) {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <tr key={i}>
          {Array.from({ length: cols }).map((_, j) => (
            <td key={j} className="px-4 py-3">
              <div className="h-4 rounded bg-slate-200 dark:bg-slate-700 animate-pulse" style={{ width: `${60 + (i * j * 7) % 40}%` }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

export function DataTable<T>({
  cols, rows, keyFn, loading, page = 1, pageSize = 20, total = 0,
  onPageChange, emptyText, className,
  mobileCardMaxPrimary = 3, disableMobileCard = false,
}: Props<T>) {
  const { t, locale } = useTranslation()
  const resolvedEmptyText = emptyText ?? t('admin.common.empty')
  const sortLocale = LOCALE_BCP47[locale]
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const sortedRows = useMemo(() => {
    if (!sortKey) return rows
    const col = cols.find((c) => c.key === sortKey)
    if (!col) return rows
    const getVal = col.sortAccessor ?? ((row: T) => (row as Record<string, unknown>)[sortKey] as string | number | null)
    return [...rows].sort((a, b) => {
      const av = getVal(a)
      const bv = getVal(b)
      const aNorm = av == null ? '' : av
      const bNorm = bv == null ? '' : bv
      if (typeof aNorm === 'number' && typeof bNorm === 'number') {
        return sortDir === 'asc' ? aNorm - bNorm : bNorm - aNorm
      }
      const cmp = String(aNorm).localeCompare(String(bNorm), sortLocale)
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [cols, rows, sortDir, sortKey, sortLocale])

  const onSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortKey(key)
    setSortDir('asc')
  }

  // Mobile card mode — split cols into primary/secondary/actions
  const actionsCol = cols.find(c => c.key === 'actions')
  const nonActionCols = cols.filter(c => c.key !== 'actions')
  const primaryCols = nonActionCols.slice(0, mobileCardMaxPrimary)
  const secondaryCols = nonActionCols.slice(mobileCardMaxPrimary)

  const renderCell = (col: ColDef<T>, row: T) =>
    col.render ? col.render(row) : (row as Record<string, unknown>)[col.key] as React.ReactNode

  return (
    <div className={cn('flex flex-col gap-0', className)}>
      {/* Mobile card mode — only visible on <md */}
      {!disableMobileCard && (
        <div className="md:hidden space-y-3">
          {loading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="rounded-lg border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-800 p-4 shadow-sm space-y-2">
                <div className="h-4 w-1/2 rounded bg-slate-200 dark:bg-slate-700 animate-pulse" />
                <div className="h-3 w-3/4 rounded bg-slate-200 dark:bg-slate-700 animate-pulse" />
                <div className="h-3 w-2/5 rounded bg-slate-200 dark:bg-slate-700 animate-pulse" />
              </div>
            ))
          ) : sortedRows.length === 0 ? (
            <div className="rounded-lg border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-800 py-10 text-center text-sm text-slate-400">
              {resolvedEmptyText}
            </div>
          ) : (
            sortedRows.map(row => (
              <div
                key={keyFn(row)}
                className="rounded-lg border border-slate-200/60 dark:border-slate-700/50 bg-white dark:bg-slate-800 p-4 shadow-sm"
              >
                {/* Primary fields */}
                <div className="space-y-2">
                  {primaryCols.map((col, i) => (
                    <div key={col.key}>
                      <div className="text-[10px] uppercase tracking-wide text-slate-400 mb-0.5">{col.header}</div>
                      <div className={cn(
                        'text-slate-900 dark:text-white',
                        i === 0 ? 'text-base font-semibold' : 'text-sm',
                      )}>
                        {renderCell(col, row)}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Secondary fields — collapsible */}
                {secondaryCols.length > 0 && (
                  <details className="mt-3 group">
                    <summary className="flex items-center gap-1 text-xs text-insurance-blue dark:text-insurance-gold cursor-pointer list-none min-h-11">
                      <span className="group-open:hidden">{t('admin.dataTable.showMore')}</span>
                      <span className="hidden group-open:inline">{t('admin.dataTable.showLess')}</span>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="group-open:rotate-180 transition-transform">
                        <path d="m6 9 6 6 6-6" />
                      </svg>
                    </summary>
                    <div className="mt-2 space-y-2">
                      {secondaryCols.map(col => (
                        <div key={col.key} className="flex justify-between gap-4">
                          <span className="text-xs text-slate-500 shrink-0">{col.header}</span>
                          <span className="text-xs text-slate-700 dark:text-slate-300 text-right min-w-0 truncate">
                            {renderCell(col, row)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                {/* Actions row */}
                {actionsCol && (
                  <div className="mt-3 pt-3 border-t border-slate-200/60 dark:border-slate-700/50">
                    {renderCell(actionsCol, row)}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Desktop table mode — visible on md+ (or all if disabled) */}
      <div className={cn(
        'overflow-x-auto rounded-xl border border-slate-200/60 dark:border-slate-700/50',
        !disableMobileCard && 'hidden md:block',
      )}>
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200/60 dark:border-slate-700/50">
              {cols.map(c => (
                <th key={c.key} className={cn(
                  'px-4 py-3 text-left text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide whitespace-nowrap',
                  c.className,
                )}>
                  {c.sortable ? (
                    <button
                      type="button"
                      onClick={() => onSort(c.key)}
                      className="inline-flex items-center gap-1 hover:text-slate-700 dark:hover:text-slate-200 transition-colors"
                    >
                      {c.header}
                      <span className="inline-flex ml-0.5">{sortKey === c.key ? (sortDir === 'asc' ? (
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m18 15-6-6-6 6"/></svg>
                      ) : (
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
                      )) : (
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="opacity-40"><path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/></svg>
                      )}</span>
                    </button>
                  ) : c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {loading ? (
              <Skeleton cols={cols.length} />
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={cols.length} className="py-12 text-center text-sm text-slate-400">
                  {resolvedEmptyText}
                </td>
              </tr>
            ) : (
              sortedRows.map(row => (
                <tr key={keyFn(row)} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                  {cols.map(c => (
                    <td key={c.key} className={cn('px-4 py-3 text-slate-700 dark:text-slate-300', c.className)}>
                      {c.render ? c.render(row) : (row as Record<string, unknown>)[c.key] as React.ReactNode}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {onPageChange && total > pageSize && (
        <div className="flex items-center justify-between px-1 pt-3">
          <span className="text-xs text-slate-400">
            {t('admin.dataTable.pageInfo', { total, page, totalPages })}
          </span>
          <div className="flex items-center gap-1">
            <button
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
              className="rounded-lg p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeftIcon size={16} />
            </button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              let p = i + 1
              if (totalPages > 5) {
                if (page <= 3) p = i + 1
                else if (page >= totalPages - 2) p = totalPages - 4 + i
                else p = page - 2 + i
              }
              return (
                <button
                  key={p}
                  onClick={() => onPageChange(p)}
                  className={cn(
                    'rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
                    p === page
                      ? 'bg-insurance-blue text-white'
                      : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800',
                  )}
                >
                  {p}
                </button>
              )
            })}
            <button
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              className="rounded-lg p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRightIcon size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
