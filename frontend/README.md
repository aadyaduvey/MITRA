# MITRA dashboard

React + Vite + TypeScript + Tailwind + Recharts + Leaflet. Four views:
Collector Map (live, refreshes every 5 s), Material Flow (Sankey), EPR Compliance
(report preview + PDF/CSV/JSON download), Ministry Overview (urban-mining summary).

```bash
pnpm install
pnpm dev          # http://localhost:5173 (backend must be running on :8000)
pnpm build        # type-check + production build
pnpm lint
```

The app calls relative `/api/*` URLs; in dev Vite proxies them to
`http://127.0.0.1:8000` (override with `MITRA_API_URL`). Map tiles come from
OpenStreetMap and need internet; the pins and every other view work offline.

Material colours are a fixed, colourblind-validated palette (`src/theme.ts`):
colour always follows the material, and every chart has a text legend and a
"View as table" twin.
