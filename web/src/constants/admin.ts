/**
 * Admin panel constants — roles, plans.
 *
 * Role labels used to live here as Chinese strings (ROLE_LABELS). We now
 * map each role to a translation key (ROLE_LABEL_KEY) so consumers call
 * `t(ROLE_LABEL_KEY[name])` and the label follows the UI locale.
 *
 * The DataTable sort locale is no longer a constant — it's read from the
 * current locale via `LOCALE_BCP47[locale]` inside the component.
 */
import type { MessageKey } from '@/lib/i18n/types'

// ── User roles ───────────────────────────────────────────────────────────────
export const ROLES = ['super_admin', 'admin', 'agent_manager', 'readonly'] as const
export type RoleName = (typeof ROLES)[number]

export const ROLE_LABEL_KEY: Record<RoleName, MessageKey> = {
  super_admin: 'admin.role.super_admin',
  admin: 'admin.role.admin',
  agent_manager: 'admin.role.agent_manager',
  readonly: 'admin.role.readonly',
}

// ── Tenant plans ─────────────────────────────────────────────────────────────
export const PLANS = ['free', 'starter', 'professional', 'enterprise'] as const
export type PlanName = (typeof PLANS)[number]

// ── Default quota for new tenants ────────────────────────────────────────────
export const DEFAULT_TENANT_QUOTA = {
  MAX_USERS: 50,
  MAX_KNOWLEDGE_BASES: 20,
  MAX_TOKENS_PER_MONTH: 10_000_000,
} as const
