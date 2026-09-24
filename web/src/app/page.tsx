'use client'

import { useTranslation } from "@/lib/i18n"

// A0 placeholder home page. The full chat interface and dashboard will
// replace this once the chat components are migrated in later rounds.
export default function Home() {
  const { t } = useTranslation()

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 px-4 text-center">
      <h1 className="font-display text-3xl font-semibold text-insurance-blue dark:text-white">
        {t("app.title")}
      </h1>
      <p className="text-slate-500 dark:text-slate-400">{t("app.metaDescription")}</p>
      <p className="text-sm text-slate-400">Frontend skeleton (A0)</p>
    </main>
  )
}
