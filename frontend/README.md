# PlanChat frontend

Next.js 16 (App Router) + TypeScript + Tailwind CSS. Two pages:

- `/` — upload a PDF
- `/chat/<document_id>` — ask questions; tap a `p. N` button to see the source text from that page

See the main [README](../README.md#run-the-frontend) for how to run it.

| Command | What it does |
|---|---|
| `npm run dev` | Start the dev server on http://localhost:3000 |
| `npm test` | Run unit tests (Vitest) |
| `npm run lint` | Check code style (ESLint) |
| `npm run build` | Production build (also checks TypeScript) |

Config: copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_URL` to the backend address. `NEXT_PUBLIC_` values are baked in at **build time**, so rebuild after changing it.
