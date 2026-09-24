# Web Frontend

Next.js frontend for Insurance Performance Intelligence Copilot.

At the A0 stage this directory contains only the frontend skeleton: project configuration, global styles, the root layout, the i18n package (English by default), and a placeholder home page. Chat, dashboard, and admin components will be migrated in later rounds.

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

## Checks

```bash
pnpm lint
pnpm build
```
