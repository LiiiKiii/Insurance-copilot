'use client'

import { KPIRingCard } from "@/components/KPIRingCard"
import { AlertBanner } from "@/components/AlertBanner"
import { useTranslation } from "@/lib/i18n"

const performanceMetrics = [
  {
    label: "Protection Premium",
    current: 3_150_000,
    target: 3_200_000,
    unit: "HKD",
    rate: 0.984,
    trend: "up" as const,
  },
  {
    label: "Recent Submissions",
    current: 112,
    target: 120,
    unit: "policies",
    rate: 0.933,
    trend: "up" as const,
  },
  {
    label: "Conversion Rate",
    current: 0.42,
    target: 0.75,
    unit: "%",
    rate: 0.56,
    trend: "flat" as const,
  },
  {
    label: "New Clients",
    current: 18,
    target: 25,
    unit: "clients",
    rate: 0.72,
    trend: "up" as const,
  },
]

// A1 dashboard page. These static values represent AGT001 in
// data/mock/performance.json; API-backed tabs are connected during integration.
export default function Home() {
  const { t } = useTranslation()

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-12 dark:bg-slate-950 sm:px-6">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8 text-center">
          <span className="inline-flex rounded-full bg-insurance-blue-100 px-3 py-1 text-xs font-semibold tracking-wide text-insurance-blue dark:bg-insurance-blue/30 dark:text-blue-200">
            A1 Platform and Data Foundation
          </span>
          <h1 className="mt-4 font-display text-3xl font-semibold text-insurance-blue dark:text-white">
            {t("app.title")}
          </h1>
          <p className="mt-2 text-slate-500 dark:text-slate-400">
            {t("app.metaDescription")}
          </p>
        </header>

        <AlertBanner
          agentId="AGT001"
          className="mb-6 rounded-lg border shadow-sm"
        />

        <section aria-labelledby="performance-overview-heading">
          <div className="mb-4 flex items-end justify-between gap-4">
            <div>
              <h2 id="performance-overview-heading" className="text-lg font-semibold text-slate-800 dark:text-white">
                Performance Overview
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Static performance data for AGT001
              </p>
            </div>
            <span className="text-xs text-slate-400">2026 Q1</span>
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {performanceMetrics.map(metric => (
              <KPIRingCard key={metric.label} {...metric} />
            ))}
          </div>
        </section>
      </div>
    </main>
  )
}
