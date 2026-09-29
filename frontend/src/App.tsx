import { useEffect, useState } from 'react'
import { useApi } from './api'
import { CollectorMap } from './views/CollectorMap'
import { EprCompliance } from './views/EprCompliance'
import { MaterialFlow } from './views/MaterialFlow'
import { MinistryOverview } from './views/MinistryOverview'
import { Prices } from './views/Prices'

const VIEWS = [
  { id: 'map', label: 'Collector Map', hi: 'संग्राहक मानचित्र', blurb: 'First-mile lots, logged by chat with GPS', el: CollectorMap },
  { id: 'flow', label: 'Material Flow', hi: 'सामग्री प्रवाह', blurb: 'Chain of custody from collector to authorised recycler', el: MaterialFlow },
  { id: 'epr', label: 'EPR Compliance', hi: 'ईपीआर अनुपालन', blurb: 'Report a producer can file with CPCB', el: EprCompliance },
  { id: 'ministry', label: 'Ministry Overview', hi: 'मंत्रालय अवलोकन', blurb: 'Urban-mining intelligence for the Ministry of Mines', el: MinistryOverview },
  { id: 'prices', label: 'Reference Prices', hi: 'संदर्भ मूल्य', blurb: 'Reference prices shown to collectors: set by hand or from the live metal feed', el: Prices },
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
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-navy-900">
        Skip to main content
      </a>
      <Tricolour />
      <UtilityBar />
      <Masthead />
      <nav className="sticky top-0 z-20 bg-navy-900 shadow-md" aria-label="Main menu">
        <div className="mx-auto flex max-w-[1680px] overflow-x-auto px-4">
          {VIEWS.map((v) => (
            <a
              key={v.id}
              href={`#${v.id}`}
              aria-current={v.id === view ? 'page' : undefined}
              className={`whitespace-nowrap border-b-4 px-4 pt-3 pb-2 text-[0.95rem] font-semibold transition-colors ${
                v.id === view
                  ? 'border-saffron bg-white/10 text-white'
                  : 'border-transparent text-white/85 hover:border-white/40 hover:bg-white/5 hover:text-white'
              }`}
            >
              {v.label}
            </a>
          ))}
        </div>
      </nav>

      <div className="border-b border-grid bg-white">
        <div className="mx-auto max-w-[1680px] px-6 py-4">
          <ol className="flex flex-wrap items-center gap-1.5 text-[0.85rem] text-ink-2" aria-label="Breadcrumb">
            <li><a href="#map" className="text-navy-700 hover:underline">Home</a></li>
            <li aria-hidden>›</li>
            <li>Dashboards</li>
            <li aria-hidden>›</li>
            <li aria-current="page" className="font-medium text-ink">{current.label}</li>
          </ol>
          <h1 className="mt-1.5 text-[1.75rem] leading-tight font-bold text-navy-900">
            {current.label}
            <span className="ml-3 align-middle font-hindi text-[1.05rem] font-medium text-ink-2" lang="hi">{current.hi}</span>
          </h1>
          <p className="mt-0.5 text-ink-2">{current.blurb}</p>
        </div>
      </div>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1680px] flex-1 px-6 py-6">
        <View />
      </main>

      <Footer />
      <Tricolour />
    </div>
  )
}

function Tricolour() {
  return (
    <div className="flex h-1" aria-hidden>
      <span className="flex-1 bg-saffron" />
      <span className="flex-1 bg-white" />
      <span className="flex-1 bg-india-green" />
    </div>
  )
}

const TEXT_SIZES = [
  { id: 'sm', label: 'A-', px: 15, name: 'Decrease text size' },
  { id: 'md', label: 'A', px: 17, name: 'Normal text size' },
  { id: 'lg', label: 'A+', px: 19, name: 'Increase text size' },
] as const
type TextSize = (typeof TEXT_SIZES)[number]['id']

function readTextSize(): TextSize {
  try {
    const s = localStorage.getItem('mitra-text-size')
    return TEXT_SIZES.some((t) => t.id === s) ? (s as TextSize) : 'md'
  } catch {
    return 'md'
  }
}

/** Thin top bar, as on government portals: who it is for, skip link, text size. */
function UtilityBar() {
  const [size, setSize] = useState<TextSize>(readTextSize)
  useEffect(() => {
    document.documentElement.style.fontSize = `${TEXT_SIZES.find((t) => t.id === size)!.px}px`
    try { localStorage.setItem('mitra-text-size', size) } catch { /* storage blocked: size still applies */ }
  }, [size])

  return (
    <div className="bg-navy-950 text-[0.8rem] text-white/85">
      <div className="mx-auto flex max-w-[1680px] flex-wrap items-center justify-between gap-x-6 gap-y-1 px-6 py-1.5">
        <div className="flex flex-wrap items-center gap-x-2">
          <span className="font-hindi" lang="hi">खान मंत्रालय</span>
          <span aria-hidden className="text-white/40">|</span>
          <span>Ministry of Mines</span>
          <span aria-hidden className="text-white/40">·</span>
          <span className="text-white/65">SIH26229 prototype</span>
        </div>
        <div className="flex items-center gap-4">
          <a href="#main" className="hover:text-white hover:underline">Skip to main content</a>
          <span aria-hidden className="text-white/30">|</span>
          <div className="flex items-center gap-1" role="group" aria-label="Text size">
            {TEXT_SIZES.map((t) => (
              <button
                key={t.id}
                onClick={() => setSize(t.id)}
                aria-pressed={size === t.id}
                aria-label={t.name}
                title={t.name}
                className={`min-w-7 rounded px-1.5 py-0.5 font-semibold ${
                  size === t.id ? 'bg-white text-navy-900' : 'hover:bg-white/15 hover:text-white'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function Masthead() {
  return (
    <header className="bg-white">
      <div className="mx-auto flex max-w-[1680px] flex-wrap items-center justify-between gap-4 px-6 py-3">
        <a href="#map" className="flex items-center gap-4" aria-label="MITRA home">
          <LogoMark />
          <div className="leading-tight">
            <div className="flex items-baseline gap-2.5">
              <span className="text-[1.9rem] font-bold tracking-wide text-navy-900">MITRA</span>
              <span className="font-hindi text-[1.35rem] font-semibold text-navy-800" lang="hi">मित्र</span>
            </div>
            <div className="text-[0.9rem] text-ink-2">Material Intelligence, Traceability &amp; Recovery Architecture</div>
            <div className="mt-0.5 text-[0.8rem] font-semibold uppercase tracking-wider text-saffron-dark">
              Kabadiwala Connect · Urban Mining Data Platform
            </div>
          </div>
        </a>
        <ApiStatus />
      </div>
    </header>
  )
}

/** Monogram (Devanagari "म") ringed in the tricolour. Deliberately not a state emblem. */
function LogoMark() {
  return (
    <svg viewBox="0 0 64 64" className="h-16 w-16 shrink-0" aria-hidden>
      <circle cx="32" cy="32" r="30" fill="none" stroke="#ff9933" strokeWidth="4" strokeDasharray="62.8 125.6" transform="rotate(-90 32 32)" />
      <circle cx="32" cy="32" r="30" fill="none" stroke="#d9d9d9" strokeWidth="4" strokeDasharray="62.8 125.6" strokeDashoffset="-62.8" transform="rotate(-90 32 32)" />
      <circle cx="32" cy="32" r="30" fill="none" stroke="#138808" strokeWidth="4" strokeDasharray="62.8 125.6" strokeDashoffset="-125.6" transform="rotate(-90 32 32)" />
      <circle cx="32" cy="32" r="25" fill="#0b2a4a" />
      <text x="32" y="43" textAnchor="middle" fontSize="30" fontWeight="700" fill="#fff" fontFamily="'Noto Sans Devanagari', sans-serif">म</text>
    </svg>
  )
}

function ApiStatus() {
  const health = useApi<{ status: string }>('/health', 10000)
  const ok = health.data?.status === 'ok' && !health.error
  return (
    <div className="flex items-center gap-2 rounded-full border border-black/10 bg-page px-3 py-1 text-[0.85rem] text-ink-2" role="status">
      <span className={`h-2.5 w-2.5 rounded-full ${ok ? 'bg-[#0ca30c]' : health.error ? 'bg-[#d03b3b]' : 'bg-black/25'}`} />
      {ok ? 'System online' : health.error ? 'System offline' : 'Connecting…'}
    </div>
  )
}

function Footer() {
  const heading = 'mb-2 text-[0.8rem] font-semibold uppercase tracking-wider text-saffron'
  const link = 'text-white/80 hover:text-white hover:underline'
  return (
    <footer className="mt-4 bg-navy-950 text-[0.9rem] text-white/80">
      <div className="mx-auto grid max-w-[1680px] gap-8 px-6 py-8 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <div className="mb-2 text-lg font-bold text-white">MITRA <span className="font-hindi font-semibold" lang="hi">मित्र</span></div>
          <p className="text-white/70">
            Traceability and EPR-compliance data layer connecting India's informal waste collectors to
            CPCB-authorised recyclers. Every kg logged is a data point on recoverable metal.
          </p>
        </div>
        <div>
          <div className={heading}>Dashboards</div>
          <ul className="space-y-1">
            {VIEWS.map((v) => <li key={v.id}><a href={`#${v.id}`} className={link}>{v.label}</a></li>)}
          </ul>
        </div>
        <div>
          <div className={heading}>For collectors</div>
          <ul className="space-y-1 text-white/80">
            <li>Register on Telegram: send <code className="rounded bg-white/10 px-1">/start</code></li>
            <li>Hindi and English, no app to install</li>
            <li>Fair reference price per kg at every sale</li>
            <li>Right to erasure (DPDP Act, 2023): <code className="rounded bg-white/10 px-1">/forget</code></li>
          </ul>
        </div>
        <div>
          <div className={heading}>Reports</div>
          <ul className="space-y-1">
            <li><a href="/api/epr/report?format=pdf" className={link}>EPR report (PDF)</a></li>
            <li><a href="/api/epr/report?format=csv" className={link}>EPR report (CSV)</a></li>
            <li><a href="/api/epr/report?format=json" className={link}>EPR report (JSON)</a></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/10">
        <div className="mx-auto flex max-w-[1680px] flex-wrap justify-between gap-x-6 gap-y-1 px-6 py-3 text-[0.8rem] text-white/60">
          <span>Prototype for Smart India Hackathon problem SIH26229 (Ministry of Mines). Not an official Government of India website.</span>
          <span>Demo data is synthetic; aggregator and recycler names are marked "(synthetic)".</span>
        </div>
      </div>
    </footer>
  )
}
