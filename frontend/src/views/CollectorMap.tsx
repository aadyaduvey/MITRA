import { useMemo, useState } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip } from 'react-leaflet'
import { url, useApi, type Category, type CollectorDetail, type Transaction } from '../api'
import { FitBounds } from '../components/FitBounds'
import { PassportPanel } from '../components/PassportPanel'
import {
  Async, Card, Empty, FilterRow, MaterialOptions, PeriodOptions, Segmented, Select,
  StatusBadge, type Period,
} from '../components/ui'
import { dateTime, inr, isoDay, kg, minutesAgo, n0 } from '../format'
import { ACCENT, CATEGORY_COLOR, CATEGORY_SHORT, DEEMPH } from '../theme'

const JAIPUR: [number, number] = [26.89, 75.8]
const LIVE_POLL_MS = 5000
const NEW_MINUTES = 15

function radius(weightKg: number) {
  return 4 + Math.sqrt(weightKg) * 1.3
}

export function CollectorMap() {
  const [period, setPeriod] = useState<Period>('14')
  const [material, setMaterial] = useState<Category | ''>('')
  const [collectorId, setCollectorId] = useState<number | null>(null)
  const [passportTx, setPassportTx] = useState<number | null>(null)

  const start = period === 'all' ? null : isoDay(Number(period) - 1)
  const txState = useApi<Transaction[]>(url('/api/transactions', { start, limit: 5000 }), LIVE_POLL_MS)

  const shown = useMemo(
    () => (txState.data ?? []).filter((t) => t.gps_lat !== null && (!material || t.category === material)),
    [txState.data, material],
  )
  // Draw the selected collector's pins last so they sit on top of the greyed-out rest.
  const drawn = useMemo(
    () => (collectorId === null ? shown : [...shown.filter((t) => t.collector_id !== collectorId),
      ...shown.filter((t) => t.collector_id === collectorId)]),
    [shown, collectorId],
  )
  const noGps = (txState.data ?? []).filter((t) => t.gps_lat === null).length

  const select = (id: number | null) => { setCollectorId(id); setPassportTx(null) }

  return (
    <div>
      <FilterRow>
        <Segmented label="Period" value={period} options={PeriodOptions()} onChange={setPeriod} />
        <Select label="Material" value={material} onChange={(v) => setMaterial(v as Category | '')}>
          <MaterialOptions />
        </Select>
        <div className="ml-auto flex items-center gap-2 text-[0.9rem] text-ink-2" aria-live="polite">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#0ca30c] opacity-60" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[#0ca30c]" />
          </span>
          Live · refreshes every {LIVE_POLL_MS / 1000}s
        </div>
      </FilterRow>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_420px]">
        <Card
          title="Collector map"
          subtitle={
            txState.data
              ? `${n0(shown.length)} lots with GPS · ${kg(shown.reduce((s, t) => s + t.weight_kg, 0))}${noGps ? ` · ${noGps} without GPS not shown` : ''}. Circle size = weight. Click a pin to open that collector.`
              : 'Every pin is one logged lot at the GPS point where it was collected.'
          }
        >
          <Async state={txState} loadingLabel="Loading transactions…">
            {() => (
              <div className="relative h-[560px] overflow-hidden rounded-md border border-black/10 lg:h-[640px]">
                <MapContainer center={JAIPUR} zoom={12} zoomSnap={0.25} zoomDelta={0.5} scrollWheelZoom className="h-full w-full">
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                  <FitBounds points={shown.map((t) => [t.gps_lat!, t.gps_lon!] as [number, number])} />
                  {drawn.map((t) => {
                    const mine = collectorId === t.collector_id
                    const dim = collectorId !== null && !mine
                    const fresh = minutesAgo(t.ts) < NEW_MINUTES
                    return (
                      <CircleMarker
                        key={`${t.id}-${dim ? 'd' : mine ? 'm' : 'n'}`}
                        center={[t.gps_lat!, t.gps_lon!]}
                        radius={radius(t.weight_kg)}
                        pathOptions={{
                          color: fresh ? '#eb6834' : '#ffffff',
                          weight: fresh ? 3 : 1.5,
                          fillColor: dim ? DEEMPH : ACCENT,
                          fillOpacity: dim ? 0.35 : 0.75,
                        }}
                        eventHandlers={{ click: () => select(t.collector_id) }}
                      >
                        <Tooltip>
                          <strong>{t.collector_name}</strong> · {t.material}
                          <br />
                          {kg(t.weight_kg)} · {dateTime(t.ts)}
                        </Tooltip>
                      </CircleMarker>
                    )
                  })}
                </MapContainer>
                {shown.length === 0 && (
                  <div className="pointer-events-none absolute inset-0 z-[500] flex items-center justify-center">
                    <div className="rounded-md bg-white/95 px-4 py-3 shadow">No lots with GPS for this filter.</div>
                  </div>
                )}
              </div>
            )}
          </Async>
        </Card>

        <div className="space-y-5">
          {collectorId !== null
            ? <CollectorPanel id={collectorId} onClose={() => select(null)} onPassport={setPassportTx} />
            : <LiveFeed txs={txState.data} onPick={select} />}
          {passportTx !== null && <PassportPanel transactionId={passportTx} onClose={() => setPassportTx(null)} />}
        </div>
      </div>
    </div>
  )
}

function LiveFeed({ txs, onPick }: { txs: Transaction[] | undefined; onPick: (id: number) => void }) {
  const latest = (txs ?? []).slice(0, 8)
  return (
    <Card title="Latest lots" subtitle="Newest first. Lots logged in the last 15 minutes are outlined orange on the map.">
      {!txs ? null : latest.length === 0 ? (
        <Empty title="No lots in this period" hint="Try a longer period." />
      ) : (
        <ul className="divide-y divide-black/5">
          {latest.map((t) => (
            <li key={t.id}>
              <button onClick={() => onPick(t.collector_id)} className="flex w-full items-center justify-between gap-3 py-2 text-left hover:bg-navy-50/60">
                <span>
                  <span className="font-medium">{t.collector_name}</span>
                  {minutesAgo(t.ts) < NEW_MINUTES && (
                    <span className="ml-2 rounded bg-[#eb6834] px-1.5 py-0.5 text-[0.7rem] font-bold text-white">NEW</span>
                  )}
                  <span className="block text-[0.85rem] text-ink-2">
                    <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: CATEGORY_COLOR[t.category] }} />
                    {t.material} · {kg(t.weight_kg)}
                  </span>
                </span>
                <span className="shrink-0 text-right text-[0.82rem] text-ink-2">{dateTime(t.ts)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function CollectorPanel({ id, onClose, onPassport }: { id: number; onClose: () => void; onPassport: (tx: number) => void }) {
  const state = useApi<CollectorDetail>(`/api/collectors/${id}`, LIVE_POLL_MS)
  return (
    <Card
      title={state.data ? state.data.name : 'Collector'}
      subtitle={state.data && `${state.data.code} · ${state.data.area}`}
      actions={<button onClick={onClose} className="rounded px-2 text-2xl leading-none text-ink-2 hover:bg-black/5" aria-label="Close collector">×</button>}
    >
      <Async state={state}>
        {(c) => (
          <div className="space-y-3">
            <dl className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-md bg-navy-50 p-2"><dt className="text-[0.75rem] text-ink-2">Lots</dt><dd className="text-xl font-semibold">{n0(c.lots)}</dd></div>
              <div className="rounded-md bg-navy-50 p-2"><dt className="text-[0.75rem] text-ink-2">Total</dt><dd className="text-xl font-semibold">{kg(c.kg)}</dd></div>
              <div className="rounded-md bg-navy-50 p-2"><dt className="text-[0.75rem] text-ink-2">Registered</dt><dd className="text-[0.95rem] font-semibold">{dateTime(c.registered_ts).split(',')[0]}</dd></div>
            </dl>
            {c.recent_transactions.length === 0 ? (
              <Empty title="No lots logged yet" hint="This collector is registered but has not logged material." />
            ) : (
              <>
                <div className="text-[0.85rem] font-medium text-ink-2">Recent lots (click for passport)</div>
                <ul className="divide-y divide-black/5 rounded-md border border-black/10">
                  {c.recent_transactions.map((t) => (
                    <li key={t.id}>
                      <button onClick={() => onPassport(t.id)} className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-navy-50/60">
                        <span>
                          <span className="inline-flex items-center gap-1.5 font-medium">
                            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: CATEGORY_COLOR[t.category] }} />
                            {t.material === 'Copper' ? 'Copper' : CATEGORY_SHORT[t.category]} · {kg(t.weight_kg)} · {inr(t.amount_paid)}
                          </span>
                          <span className="block text-[0.82rem] text-ink-2">{dateTime(t.ts)} · {t.passport_id}</span>
                        </span>
                        <StatusBadge status={t.passport_status} />
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
      </Async>
    </Card>
  )
}
