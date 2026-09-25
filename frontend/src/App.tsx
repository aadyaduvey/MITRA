import { useEffect, useState } from 'react'
import { useApi } from './api'
import { CollectorMap } from './views/CollectorMap'
import { EprCompliance } from './views/EprCompliance'
import { MaterialFlow } from './views/MaterialFlow'
import { MinistryOverview } from './views/MinistryOverview'

const VIEWS = [
  { id: 'map', label: 'Collector Map', blurb: 'First-mile lots, logged by chat with GPS', el: CollectorMap },
  { id: 'flow', label: 'Material Flow', blurb: 'Chain of custody from collector to authorised recycler', el: MaterialFlow },
  { id: 'epr', label: 'EPR Compliance', blurb: 'Report a producer can file with CPCB', el: EprCompliance },
  { id: 'ministry', label: 'Ministry Overview', blurb: 'Urban-mining intelligence for the Ministry of Mines', el: MinistryOverview },
] as const
type ViewId = (typeof VIEWS)[number]['id']

function viewFromHash(): ViewId {
  const h = window.location.hash.replace('#', '')
  return (VIEWS.find((v) => v.id === h)?.id ?? 'map') as ViewId
}

export default function App() {
  const [view, setView] = useState<ViewId>(viewFromHash)
  useEffect(() => {
    const onHash = () => setView(viewFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const current = VIEWS.find((v) => v.id === view)!
  const View = current.el

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 bg-navy-900 text-white shadow">
        <div className="mx-auto flex max-w-[1680px] flex-wrap items-center gap-x-8 gap-y-2 px-6 pt-3">
          <div className="flex items-baseline gap-3">
            <span className="text-2xl font-bold tracking-wide">MITRA</span>
            <span className="text-[0.9rem] text-white/75">Material Intelligence, Traceability &amp; Recovery Architecture</span>
          </div>
          <ApiStatus />
        </div>
        <nav className="mx-auto flex max-w-[1680px] gap-1 overflow-x-auto px-4 pt-2" aria-label="Views">
          {VIEWS.map((v) => (
            <a
              key={v.id}
              href={`#${v.id}`}
              aria-current={v.id === view ? 'page' : undefined}
              className={`whitespace-nowrap rounded-t-md px-4 py-2.5 text-[1rem] font-semibold transition-colors ${
                v.id === view ? 'bg-page text-navy-900' : 'text-white/85 hover:bg-white/10 hover:text-white'
              }`}
            >
              {v.label}
            </a>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-[1680px] px-6 py-6">
        <div className="mb-5">
          <h1 className="text-[1.75rem] font-semibold text-navy-900">{current.label}</h1>
          <p className="text-ink-2">{current.blurb}</p>
        </div>
        <View />
      </main>
      <footer className="mx-auto max-w-[1680px] px-6 pb-8 text-[0.85rem] text-muted">
        Proof of concept for SIH26229 (Ministry of Mines). Demo data is synthetic; aggregator and recycler names marked "(synthetic)".
      </footer>
    </div>
  )
}

function ApiStatus() {
  const health = useApi<{ status: string }>('/health', 10000)
  const ok = health.data?.status === 'ok' && !health.error
  return (
    <div className="ml-auto flex items-center gap-2 text-[0.85rem] text-white/85" role="status">
      <span className={`h-2.5 w-2.5 rounded-full ${ok ? 'bg-[#0ca30c]' : health.error ? 'bg-[#d03b3b]' : 'bg-white/40'}`} />
      {ok ? 'API connected' : health.error ? 'API offline' : 'Connecting…'}
    </div>
  )
}
