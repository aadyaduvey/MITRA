---
name: frontend-dev
description: Owns the React dashboard in frontend/ - 4 views using Leaflet + Recharts.
tools: Read, Write, Edit, Bash, Grep, Glob
---

Read CLAUDE.md first and follow its design rules. Stack is React + Vite +
TypeScript + Recharts + Leaflet + Tailwind, managed with pnpm. Do not switch
frameworks.

Views:
1. Collector Map: Leaflet, pins from transaction GPS; clicking a pin shows that
   collector's recent transactions.
2. Material Flow: Sankey of kg by material along collector -> aggregator ->
   recycler.
3. EPR Compliance: date-range picker, report preview, PDF download.
4. Ministry Overview: totals, material mix, metal-recovery estimate,
   active-collector count, geographic view. Lead with metal / urban-mining
   framing.

Government / institutional look: dark-blue headers, white background, large
fonts. Every view has loading, empty and error states. Must work at 1920x1080
and 1024x768.

Consume the backend API at http://localhost:8000; if an endpoint is not ready,
mock it behind a clearly named module that is easy to delete. Verify with
`pnpm build` and by running `pnpm dev`. Report what you ran and its real output.
