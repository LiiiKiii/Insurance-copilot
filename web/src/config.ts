/**
 * Centralized frontend configuration.
 *
 * All hardcoded URLs, ports, and reconnect params live here
 * so they can be tuned from a single place.
 */

export const API_CONFIG = {
  /**
   * Base URL for REST calls.
   *  - In the browser: empty string → same-origin relative URLs (`/api/...`,
   *    `/admin/...`), which the Next.js server proxies to the backend via
   *    `next.config.ts` rewrites. Works seamlessly under an HTTPS reverse proxy.
   *  - SSR: defaults to `http://localhost:8000` for direct backend calls.
   *  - Override either with `NEXT_PUBLIC_API_URL` (use a full URL like
   *    `https://api.example.com`).
   */
  BASE_URL:
    process.env.NEXT_PUBLIC_API_URL ||
    (typeof window !== 'undefined' ? '' : 'http://localhost:8000'),

  /** WebSocket path appended to the WS base */
  WS_PATH: '/ws/chat',
} as const

export const RECONNECT = {
  MAX_ATTEMPTS: 10,
  MAX_DELAY_MS: 30_000,
} as const
