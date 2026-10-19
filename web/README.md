# Web Frontend

Next.js frontend for Insurance Performance Intelligence Copilot: the agent-facing chat and dashboard (`/`, `/login`, `/targets`) and the administration console (`/admin/*`).

## Requirements

- Node.js 20+
- pnpm 9

## Getting Started

```bash
pnpm install
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) in a browser.

`/api/*` and `/ws/*` requests are proxied to the backend defined by `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

The chat WebSocket is proxied as well, so the backend sees the frontend's origin. Allow it in the backend environment, otherwise the socket is rejected with 403:

```bash
WS_ALLOWED_ORIGINS=http://localhost:3000
```

## Checks

```bash
pnpm check
```

`check` runs `pnpm lint`, `pnpm build` and `pnpm typecheck` in that order. If `typecheck` reports errors under `.next/`, delete the `.next` directory left by an earlier `pnpm dev` and run it again.
