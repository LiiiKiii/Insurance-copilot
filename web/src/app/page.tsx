'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useInsuranceChat } from '@/lib/useWebSocket'
import { Sidebar, SidebarContent } from '@/components/Sidebar'
import { ConfirmModal } from '@/components/ConfirmModal'
import {
  authenticatedFetch as fetch,
  authHeaders,
  clearAuth,
  getChatUser,
  getRefreshToken,
  getToken,
} from '@/lib/auth'
import { ChatInterface } from '@/components/ChatInterface'
import { AlertBanner } from '@/components/AlertBanner'
import { TargetsTab } from '@/components/TargetsTab'
import { CompetitionTab } from '@/components/CompetitionTab'
import { HonorsTab } from '@/components/HonorsTab'
import { ApiConfigModal, loadApiConfig, type ApiConfig } from '@/components/ApiConfigModal'
import { MobileTopBar } from '@/components/mobile/MobileTopBar'
import { LeftDrawer } from '@/components/mobile/LeftDrawer'
import { DataBottomSheet } from '@/components/mobile/DataBottomSheet'
import { DataFab } from '@/components/mobile/DataFab'
import { useTranslation } from '@/lib/i18n'
import { cn } from '@/lib/utils'

type TabKey = 'performance' | 'competition' | 'honors'

export default function Home() {
  const router = useRouter()
  const { t } = useTranslation()
  const chat = useInsuranceChat()
  const [activeTab, setActiveTab] = useState<TabKey>('competition')
  const [configOpen, setConfigOpen] = useState(false)
  const [apiConfig, setApiConfig] = useState<ApiConfig | null>(null)
  const [ready, setReady] = useState(false)
  const [leftDrawerOpen, setLeftDrawerOpen] = useState(false)
  const [dataSheetOpen, setDataSheetOpen] = useState(false)
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const [chatUser, setChatUser] = useState<ReturnType<typeof getChatUser>>(null)

  // Auth guard: redirect to /login if not logged in
  useEffect(() => {
    const user = getChatUser()
    if (!user || (!getToken() && !getRefreshToken())) {
      clearAuth()
      router.replace('/login')
      return
    }
    setChatUser(user)
    // agentId is picked by the sidebar (first agent), not taken from the logged-in user
    setReady(true)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Load saved config on mount. Trust local apiKey — only auto-open modal when there is
  // truly no key saved. Backend auto-apply runs silently and does NOT force the modal
  // open on failure (users can click the API Config button or send a message to retry).
  useEffect(() => {
    if (!chatUser) return
    if (!chatUser.is_superadmin) {
      setApiConfig(null)
      setConfigOpen(false)
      return
    }
    const cfg = loadApiConfig()
    setApiConfig(cfg)
    if (!cfg.apiKey) {
      setConfigOpen(true)
      return
    }
    // Silent background verify + auto-apply; do not force-open modal on failure
    fetch('/api/config/status', { headers: authHeaders() })
      .then(r => r.json())
      .then(async (data) => {
        if (data.configured) return
        await fetch('/api/config/apply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify(cfg),
        }).catch(() => {})
      })
      .catch(() => {})
  }, [chatUser])

  const handleConfigSave = (cfg: ApiConfig) => {
    setApiConfig(cfg)
    // Notify backend to use the new key (fire-and-forget)
    fetch('/api/config/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(cfg),
    }).catch(() => {/* best effort */})
  }

  if (!ready) return null

  return (
    <div className="relative flex h-[100vh] h-dvh flex-col bg-slate-50 dark:bg-[#0f172a]">
      <div className="page-gold-stripe w-full shrink-0 hidden lg:block" />

      {/* Mobile top bar (< lg only) */}
      <MobileTopBar
        title={t('app.title')}
        subtitle={t('app.subtitle')}
        onMenuClick={() => setLeftDrawerOpen(true)}
        rightSlot={
          <div className="flex items-center gap-2">
            {chatUser?.is_superadmin && <button
            onClick={() => setConfigOpen(true)}
            aria-label={apiConfig?.apiKey ? t('apiConfig.configured.aria') : t('apiConfig.notConfigured.aria')}
            className={cn(
              'flex h-11 w-11 items-center justify-center rounded-lg transition-colors',
              apiConfig?.apiKey
                ? 'text-white/70 hover:text-white hover:bg-white/10'
                : 'text-amber-300 hover:text-amber-200 hover:bg-amber-400/10 animate-pulse',
            )}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>}
          </div>
        }
      />

      {/* Left drawer — vaul portal; only meaningful on < lg. Still mounted on lg but closed. */}
      <LeftDrawer open={leftDrawerOpen} onOpenChange={setLeftDrawerOpen}>
        <SidebarContent
          variant="drawer"
          agentId={chat.agentId}
          status={chat.status}
          onNewChat={chat.clearMessages}
          chatSessions={chat.chatSessions}
          onLoadSession={chat.loadSession}
          onDeleteSession={chat.deleteSession}
          activeSessionId={chat.activeSessionId}
          onRequestClose={() => setLeftDrawerOpen(false)}
          onLogoutRequest={() => setShowLogoutConfirm(true)}
          onDeleteRequest={(id) => setPendingDeleteId(id)}
        />
      </LeftDrawer>

      <main className="noise-overlay flex min-h-0 flex-1">
        {/* Sidebar - desktop only */}
        <div className="hidden lg:flex shrink-0">
          <Sidebar
            agentId={chat.agentId}
            status={chat.status}
            onNewChat={chat.clearMessages}
            onSend={chat.sendMessage}
            chatSessions={chat.chatSessions}
            onLoadSession={chat.loadSession}
            onDeleteSession={chat.deleteSession}
            activeSessionId={chat.activeSessionId}
          />
        </div>

        {/* Left panel - Performance/Competition/Targets tabs */}
        <div className="hidden lg:flex w-80 flex-col min-h-0 border-r border-slate-200/60 dark:border-slate-700/50 bg-white/50 dark:bg-slate-900/50">
          {/* Tab header */}
          <div className="flex border-b border-slate-200/70 dark:border-slate-700/50">
            <button
              onClick={() => setActiveTab('competition')}
              className={cn(
                'flex-1 px-4 py-3 text-xs font-semibold transition-colors cursor-pointer',
                activeTab === 'competition'
                  ? 'text-insurance-blue dark:text-insurance-gold border-b-2 border-insurance-blue dark:border-insurance-gold'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
              )}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="inline -mt-0.5"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" /><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" /><path d="M4 22h16" /><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" /><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" /><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z" /></svg> {t('tab.competition')}
            </button>
            <button
              onClick={() => setActiveTab('honors')}
              className={cn(
                'flex-1 px-4 py-3 text-xs font-semibold transition-colors cursor-pointer',
                activeTab === 'honors'
                  ? 'text-insurance-blue dark:text-insurance-gold border-b-2 border-insurance-blue dark:border-insurance-gold'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
              )}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="inline -mt-0.5"><circle cx="12" cy="8" r="7" /><polyline points="8.21 13.89 7 22 12 19 17 22 15.79 13.88" /></svg> {t('tab.honors')}
            </button>
            <button
              onClick={() => setActiveTab('performance')}
              className={cn(
                'flex-1 px-4 py-3 text-xs font-semibold transition-colors cursor-pointer',
                activeTab === 'performance'
                  ? 'text-insurance-blue dark:text-insurance-gold border-b-2 border-insurance-blue dark:border-insurance-gold'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
              )}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="inline -mt-0.5"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg> {t('tab.targets')}
            </button>
            {/* Team tab - temporarily hidden */}
          </div>

          {/* Tab content */}
          <div className="flex-1 min-h-0 overflow-y-auto">
            {activeTab === 'performance' ? (
              <TargetsTab agentId={chat.agentId} />
            ) : activeTab === 'honors' ? (
              <HonorsTab agentId={chat.agentId} />
            ) : (
              <CompetitionTab agentId={chat.agentId} />
            )}
          </div>
        </div>

        {/* Right panel - Alert + Chat */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          <AlertBanner agentId={chat.agentId} />
          <ChatInterface
            messages={chat.messages}
            isTyping={chat.isTyping}
            status={chat.status}
            onSend={chat.sendMessage}
            onOpenConfig={chatUser?.is_superadmin ? () => setConfigOpen(true) : undefined}
            apiConfigured={!!apiConfig?.apiKey}
            agentId={chat.agentId}
            sessionKey={chat.activeSessionId ?? 'default'}
          />
        </div>
      </main>

      {/* Mobile FAB + data bottom sheet (< lg) */}
      <DataFab onClick={() => setDataSheetOpen(true)} active={dataSheetOpen} />
      <DataBottomSheet
        open={dataSheetOpen}
        onOpenChange={setDataSheetOpen}
        agentId={chat.agentId}
        activeTab={activeTab}
        onActiveTabChange={setActiveTab}
      />

      {/* Delete session confirm — rendered outside drawer */}
      <ConfirmModal
        open={!!pendingDeleteId}
        onClose={() => setPendingDeleteId(null)}
        title={t('confirm.deleteSession.title')}
        message={t('confirm.deleteSession.message')}
        confirmText={t('common.delete')}
        danger
        onConfirm={() => { if (pendingDeleteId) chat.deleteSession(pendingDeleteId); }}
      />

      {/* Logout confirm — rendered outside drawer so it survives drawer close */}
      <ConfirmModal
        open={showLogoutConfirm}
        onClose={() => setShowLogoutConfirm(false)}
        title={t('confirm.logout.title')}
        message={t('confirm.logout.message')}
        confirmText={t('common.logout')}
        danger
        onConfirm={() => { clearAuth(); window.location.href = '/login' }}
      />

      {/* API Config Modal */}
      {chatUser?.is_superadmin && <ApiConfigModal
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        onSave={handleConfigSave}
      />}
    </div>
  )
}
