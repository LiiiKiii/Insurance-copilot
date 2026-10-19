'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { TargetsTab } from '@/components/TargetsTab'
import { Sidebar } from '@/components/Sidebar'
import { useInsuranceChat } from '@/lib/useWebSocket'
import { useTranslation } from '@/lib/i18n'

export default function TargetsPage() {
  const { t } = useTranslation()
  const chat = useInsuranceChat()

  // Override agentId from URL param if present
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const id = params.get('agent_id')
    if (id && id !== chat.agentId) {
      chat.setAgentId(id)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="relative flex h-dvh flex-col bg-slate-50 dark:bg-[#0f172a]">
      <div className="page-gold-stripe w-full shrink-0" />
      <div className="noise-overlay flex min-h-0 flex-1">
        <Sidebar
          agentId={chat.agentId}
          status={chat.status}
          onNewChat={chat.clearMessages}
          chatSessions={chat.chatSessions}
          onLoadSession={chat.loadSession}
          onDeleteSession={chat.deleteSession}
          activeSessionId={chat.activeSessionId}
        />
        <div className="flex-1 min-w-0 overflow-y-auto">
          <header className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-6 py-4">
            <div className="flex items-center justify-between">
              <h1 className="text-lg font-semibold text-slate-900 dark:text-white">{t('targetsPage.title')}</h1>
              <Link href="/" className="text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400">
                {t('targetsPage.back')}
              </Link>
            </div>
          </header>
          <div className="max-w-4xl mx-auto">
            <TargetsTab agentId={chat.agentId} />
          </div>
        </div>
      </div>
    </div>
  )
}
