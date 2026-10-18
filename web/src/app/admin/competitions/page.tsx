'use client'
import { useEffect, useState } from 'react'
import { adminApi, type CompetitionDef } from '@/lib/admin/api'
import { useTranslation } from '@/lib/i18n'

export default function CompetitionsPage() {
  const { t } = useTranslation()
  const [competitions, setCompetitions] = useState<CompetitionDef[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    adminApi.competitions.list().then(r => {
      if (cancelled) return
      if (r.ok) setCompetitions(r.data)
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [])

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            {t('admin.competitions.title')}
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {t('admin.competitions.subtitle')}
          </p>
        </div>
      </div>

      {loading ? (
        <div className="text-sm text-slate-500">Loading...</div>
      ) : competitions.length === 0 ? (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-8 text-center text-sm text-slate-500">
          {t('admin.competitions.empty')}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
          <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-700">
            <thead className="bg-slate-50 dark:bg-slate-800/50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">{t('admin.competitions.col.name')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">{t('admin.competitions.col.type')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">{t('admin.competitions.col.metric')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">{t('admin.competitions.col.targetValue')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">{t('admin.competitions.col.deadline')}</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">{t('admin.competitions.col.status')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {competitions.map(c => (
                <tr key={c.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30">
                  <td className="px-4 py-3 text-sm text-slate-900 dark:text-white">
                    <div>{c.name}</div>
                    {c.name_en && <div className="text-xs text-slate-400">{c.name_en}</div>}
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-300">{c.type}</td>
                  <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-300">{c.target_metric}</td>
                  <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-300">
                    {c.target_value != null ? `${c.target_value.toLocaleString()} ${c.unit}` : '-'}
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-300">{c.deadline}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      c.is_active
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                        : 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400'
                    }`}>
                      {c.is_active ? t('admin.competitions.status.active') : t('admin.competitions.status.ended')}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
