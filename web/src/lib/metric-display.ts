/** Format the supplied unit without converting or relabelling the value. */
export function formatMetricValue(
  value: number | null | undefined,
  unit = '',
  compact = false,
): string {
  if (value == null || !Number.isFinite(value)) return '—'
  if (unit === '%') return `${(value * 100).toFixed(1)}%`
  const amount = compact && Math.abs(value) >= 1_000_000
    ? `${(value / 1_000_000).toFixed(1)}M`
    : compact && Math.abs(value) >= 1_000
      ? `${(value / 1_000).toFixed(0)}K`
      : value.toLocaleString('en-US')
  if (unit === 'HKD' || unit === 'USD') return `${unit} ${amount}`
  return unit ? `${amount} ${unit}` : amount
}

interface SummaryMetric {
  current: number | null
  target: number | null
  unit: string
}

/** Keep incompatible currencies and credit measures in separate totals. */
export function summarizeMetricsByUnit(metrics: SummaryMetric[]) {
  const totals = new Map<string, { unit: string; current: number; target: number }>()
  for (const metric of metrics) {
    if (metric.current == null || metric.target == null
      || !Number.isFinite(metric.current) || !Number.isFinite(metric.target)) continue
    const total = totals.get(metric.unit) ?? { unit: metric.unit, current: 0, target: 0 }
    total.current += metric.current
    total.target += metric.target
    totals.set(metric.unit, total)
  }
  return [...totals.values()]
}

/** A target cannot compare an HKD value with USD, Credit or a count. */
export function metricCurrentForUnit(
  metric: { current: number | null; unit: string } | undefined,
  unit: string,
): number | null {
  if (!metric || metric.unit !== unit || metric.current == null
    || !Number.isFinite(metric.current)) return null
  return metric.current
}
