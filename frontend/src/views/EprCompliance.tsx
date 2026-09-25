import { useState } from 'react'
import { url, useApi, type EprReport } from '../api'
import {
  Async, Card, DataTable, Empty, Field, FilterRow, StatTile, StatusBadge,
} from '../components/ui'
import { date, isoDay, kg, n0, n1 } from '../format'
import { CATEGORY_COLOR } from '../theme'

const PRESETS = [
  { label: 'Last 7 days', days: 7 },
  { label: 'Last 30 days', days: 30 },
  { label: 'Last 90 days', days: 90 },
]
const LOT_PAGE = 25

export function EprCompliance() {
  const [start, setStart] = useState(isoDay(29))
  const [end, setEnd] = useState(isoDay(0))
  const invalid = start > end
  const params = { start, end }
  const state = useApi<EprReport>(invalid ? null : url('/api/epr/report', params))

  const preset = (days: number) => { setStart(isoDay(days - 1)); setEnd(isoDay(0)) }
  const btn = 'inline-flex items-center gap-2 rounded-md px-4 py-2 text-[0.95rem] font-semibold'

  return (
    <div>
      <FilterRow>
        <Field label="From">
          <input type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)}
            className="rounded-md border border-navy-700/40 bg-white px-3 py-1.5" />
        </Field>
        <Field label="To">
          <input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)}
            className="rounded-md border border-navy-700/40 bg-white px-3 py-1.5" />
        </Field>
        <div className="flex gap-2">
          {PRESETS.map((p) => (
            <button key={p.days} onClick={() => preset(p.days)}
              className="rounded-md border border-navy-700/40 bg-white px-3 py-1.5 text-[0.9rem] font-medium text-navy-800 hover:bg-navy-50">
              {p.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <a href={invalid ? undefined : url('/api/epr/report', { ...params, format: 'pdf' })}
            aria-disabled={invalid} className={`${btn} bg-navy-800 text-white hover:bg-navy-900 ${invalid ? 'pointer-events-none opacity-50' : ''}`}>
            ⬇ Download PDF
          </a>
          <a href={invalid ? undefined : url('/api/epr/report', { ...params, format: 'csv' })}
            className={`${btn} border border-navy-700/40 bg-white text-navy-800 hover:bg-navy-50 ${invalid ? 'pointer-events-none opacity-50' : ''}`}>
            CSV
          </a>
          <a href={invalid ? undefined : url('/api/epr/report', params)} target="_blank" rel="noreferrer"
            className={`${btn} border border-navy-700/40 bg-white text-navy-800 hover:bg-navy-50 ${invalid ? 'pointer-events-none opacity-50' : ''}`}>
            JSON
          </a>
        </div>
      </FilterRow>

      {invalid ? (
        <Empty title="The start date is after the end date" hint="Pick a start date on or before the end date." />
      ) : (
        <Async state={state} loadingLabel="Building report…">
          {(r) => <Report r={r} />}
        </Async>
      )}
    </div>
  )
}

function Report({ r }: { r: EprReport }) {
  const [showAll, setShowAll] = useState(false)
  if (r.totals.lots === 0) {
    return <Empty title="No lots logged in this period" hint={`Nothing was collected between ${date(r.period.start)} and ${date(r.period.end)}. The PDF will still download, with empty tables.`} />
  }
  const lots = showAll ? r.lots : r.lots.slice(0, LOT_PAGE)
  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-navy-900 px-6 py-4 text-white">
        <div className="text-xl font-semibold">EPR Compliance Report: First-Mile Material Recovery</div>
        <div className="mt-1 text-[0.95rem] text-white/80">
          Period {date(r.period.start)} to {date(r.period.end)} · Source: MITRA collector transactions and material passports ·
          PDF format is what a producer files with CPCB
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatTile label="Lots logged" value={n0(r.totals.lots)} />
        <StatTile label="Collectors" value={n0(r.totals.collectors)} />
        <StatTile label="Collected" value={kg(r.totals.kg_collected)} />
        <StatTile label="Delivered to recyclers" value={kg(r.totals.kg_delivered)} note="Receipt recorded on passport" />
        <StatTile label="In transit" value={kg(r.totals.kg_in_transit)} note="Dispatched, receipt pending" />
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card title="1. Material collected and recovered">
          <DataTable
            rows={r.by_material}
            rowKey={(m) => m.material}
            columns={[
              { key: 'm', header: 'Material', render: (m) => (
                <span className="inline-flex items-center gap-2">
                  <span className="h-3 w-3 rounded-sm" style={{ background: CATEGORY_COLOR[m.category] }} />{m.material}
                </span>) },
              { key: 'l', header: 'Lots', numeric: true, render: (m) => n0(m.lots) },
              { key: 'c', header: 'kg collected', numeric: true, render: (m) => n1(m.kg_collected) },
              { key: 't', header: 'kg in transit', numeric: true, render: (m) => n1(m.kg_in_transit) },
              { key: 'd', header: 'kg delivered', numeric: true, render: (m) => n1(m.kg_delivered) },
            ]}
          />
        </Card>
        <Card title="2. Destination recyclers (CPCB-authorised)">
          {r.recyclers.length === 0 ? (
            <Empty title="No material reached a recycler in this period" />
          ) : (
            <DataTable
              rows={r.recyclers}
              rowKey={(x) => x.cpcb_reg_no ?? x.name}
              columns={[
                { key: 'n', header: 'Recycler', render: (x) => x.name },
                { key: 'r', header: 'CPCB reg. no.', render: (x) => <code className="text-[0.85rem]">{x.cpcb_reg_no ?? '-'}</code> },
                { key: 'd', header: 'kg delivered', numeric: true, render: (x) => n1(x.kg_delivered) },
                { key: 't', header: 'kg in transit', numeric: true, render: (x) => n1(x.kg_in_transit) },
              ]}
            />
          )}
        </Card>
      </div>

      <Card
        title="Annex A. Lot-level chain of custody"
        subtitle={`${n0(r.lots.length)} lots with a verified recycler. Lots without a passport count as collected only.`}
      >
        <DataTable
          rows={lots}
          rowKey={(l) => l.passport_id}
          columns={[
            { key: 'p', header: 'Passport', render: (l) => <code className="text-[0.85rem]">{l.passport_id}</code> },
            { key: 'c', header: 'Collector', render: (l) => `C-${String(l.collector_id).padStart(6, '0')}` },
            { key: 'd', header: 'Collected', render: (l) => date(l.collected_at) },
            { key: 'm', header: 'Material', render: (l) => l.material },
            { key: 'k', header: 'kg', numeric: true, render: (l) => n1(l.kg) },
            { key: 'r', header: 'Recycler CPCB reg. no.', render: (l) => <code className="text-[0.85rem]">{l.recycler_cpcb_reg_no}</code> },
            { key: 's', header: 'Status', render: (l) => <StatusBadge status={l.status} /> },
          ]}
        />
        {r.lots.length > LOT_PAGE && (
          <button onClick={() => setShowAll(!showAll)} className="mt-3 text-[0.95rem] font-medium text-navy-700 hover:underline">
            {showAll ? 'Show first 25' : `Show all ${n0(r.lots.length)} lots`}
          </button>
        )}
      </Card>
    </div>
  )
}
