'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { useAdminAuth, type MinimumRole } from '@/lib/admin/auth'
import { useTranslation, type MessageKey } from '@/lib/i18n'
import {
  CpuIcon, DatabaseIcon, FileTextIcon, LogOutIcon, SlidersIcon,
  TargetIcon, TrophyIcon, UsersIcon,
} from './AdminIcons'

interface NavItem {
  href: string
  labelKey: MessageKey
  icon: typeof DatabaseIcon
  minRole?: MinimumRole
}

const NAV: NavItem[] = [
  { href: '/admin/users',             labelKey: 'admin.nav.users',            icon: UsersIcon,    minRole: 'admin' },
  { href: '/admin/knowledge',         labelKey: 'admin.nav.knowledge',        icon: DatabaseIcon },
  { href: '/admin/models',            labelKey: 'admin.nav.models',           icon: CpuIcon,      minRole: 'admin' },
  { href: '/admin/briefing-settings', labelKey: 'admin.nav.briefingSettings', icon: FileTextIcon, minRole: 'super_admin' },
  { href: '/admin/config',            labelKey: 'admin.nav.config',           icon: SlidersIcon,  minRole: 'admin' },
  { href: '/admin/competitions',      labelKey: 'admin.nav.competitions',     icon: TrophyIcon },
  { href: '/admin/targets',           labelKey: 'admin.nav.targets',          icon: TargetIcon },
  { href: '/admin/audit',             labelKey: 'admin.nav.audit',            icon: FileTextIcon },
]

export function AdminSidebar() {
  const pathname = usePathname()
  const { t } = useTranslation()
  const { user, roleLabel, logout, can } = useAdminAuth()

  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-slate-200 bg-white lg:h-dvh lg:w-64 lg:border-b-0 lg:border-r dark:border-slate-700 dark:bg-slate-900">
      <div className="flex items-center gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-700">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-insurance-blue text-white">
          <DatabaseIcon size={18} />
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-900 dark:text-white">Insurance Copilot</div>
          <div className="text-xs text-slate-500">Administration</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {NAV.filter((item) => !item.minRole || can(item.minRole)).map(({ href, labelKey, icon: Icon }) => {
          const active = pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? 'bg-insurance-blue text-white'
                  : 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              <Icon size={17} />
              {t(labelKey)}
            </Link>
          )
        })}
      </nav>

      <div className="flex items-center gap-3 border-t border-slate-200 px-4 py-3 dark:border-slate-700">
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-slate-900 dark:text-white">
            {user?.display_name || user?.username}
          </div>
          <div className="truncate text-xs text-slate-500">{roleLabel}</div>
        </div>
        <button
          type="button"
          onClick={logout}
          aria-label="Sign out"
          className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          <LogOutIcon size={17} />
        </button>
      </div>
    </aside>
  )
}
