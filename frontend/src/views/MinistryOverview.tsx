import { useState } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip as MapTip } from 'react-leaflet'
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { url, useApi, type Category, type MinistrySummary } from '../api'
import { FitBounds } from '../components/FitBounds'
import {
  Async, Card, DataTable, Empty, FilterRow, PeriodOptions, Segmented, StatTile, TableView, type Period,
} from '../components/ui'
import { inr, inrCompact, isoDay, kg, n0, n1, pct } from '../format'
import { ACCENT, CATEGORY_COLOR, CATEGORY_LABEL, CATEGORY_ORDER, DEEMPH, METAL_BEARING, seqColor } from '../theme'

export function MinistryOverview() {
  const [period, setPeriod] = useState<Period>('all')
  const start = period === 'all' ? null : isoDay(Number(period) - 1)
  const state = useApi<MinistrySummary>(url('/api/ministry/summary', { start, end: start ? isoDay(0) : null }))
  return (
    <div>
      <FilterRow>
        <Segmented label="Period" value={period} options={PeriodOptions()} onChange={setPeriod} />
      </FilterRow>
      <Async state={state} loadingLabel="Loading national summary…">
        {(s) => (s.totals.lots === 0
          ? <Empty title="No material logged in this period" hint="Choose a longer period." />
          : <Body s={s} />)}
      </Async>
    </div>
  )
}

function Body({ s }: { s: MinistrySummary }) {
  const m = s.metal_recovery
  const copper = m.materials.find((x) => x.material === 'Copper')
  return (
    <div className="space-y-5">
      <section className="grid gap-5 rounded-lg bg-navy-900 p-6 text-white lg:grid-cols-[1.2fr_1fr]">
        <div>
          <div className="text-[0.9rem] font-medium uppercase tracking-wide text-white/75">
            Urban mining · metal-bearing material recovered through the informal chain
          </div>
          <div className="mt-2 text-[3.4rem] leading-none font-semibold">{inr(m.value_at_ref_inr)}</div>
          <div className="mt-2 text-[1.05rem] text-white/85">
            {kg(m.kg)} of metal and e-waste · <strong className="text-white">{pct(m.pct_of_total_value)}</strong> of all recovered value,
            from {pct((100 * m.kg) / s.totals.kg)} of the weight
          </div>
        </div>
        <ul className="grid content-center gap-2 text-[1rem]">
          {m.materials.map((x) => (
            <li key={x.material} className="flex items-baseline justify-between gap-4 border-b border-white/15 pb-1.5">
              <span>{x.material}</span>
              <span className="tabular text-white/85">{kg(x.kg)} · <strong className="text-white">{inr(x.value_at_ref_inr)}</strong></span>
            </li>
          ))}
          {copper && (
            <li className="pt-1 text-[0.9rem] text-white/75">
              Copper: {pct((100 * copper.kg) / s.totals.kg)} of weight, {pct((100 * copper.value_at_ref_inr) / s.totals.value_at_ref_inr)} of value.
            </li>
          )}
        </ul>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Material collected" value={kg(s.totals.kg)} note={`${n0(s.totals.lots)} lots logged`} />
        <StatTile label="Value at reference price" value={inr(s.totals.value_at_ref_inr)} note={`Collectors were paid ${inr(s.totals.amount_paid_inr)}`} />
        <StatTile label="Active collectors" value={n0(s.totals.active_collectors)} note={`of ${n0(s.totals.registered_collectors)} registered, no app install`} />
        <StatTile label="Traced to authorised recycler" value={pct(s.totals.pct_traced)} note={`${kg(s.totals.kg_traced)} with a recycler on the passport`} />
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <ValueByMaterial s={s} />
        <KgByCategory s={s} />
      </div>
      <Geography s={s} />
    </div>
  )
}

const row = (p: ReadonlyArray<{ payload?: unknown }>) => p[0].payload as Record<string, unknown>

const tipBox = 'rounded-md border border-black/10 bg-white px-3 py-2 text-[0.9rem] shadow-lg'

interface BarTipProps {
  active?: boolean
  payload?: ReadonlyArray<{ payload?: unknown }>
}

function ValueByMaterial({ s }: { s: MinistrySummary }) {
  const rows = [...s.by_material].sort((a, b) => b.value_at_ref_inr - a.value_at_ref_inr)
  const metal = (c: Category) => METAL_BEARING.includes(c)
  return (
    <Card title="Value recovered, by material" subtitle="At reference price per kg. Metal-bearing streams highlighted.">
      <ul className="mb-2 flex gap-5 text-[0.9rem] text-ink-2">
        <li className="inline-flex items-center gap-2"><span className="h-3 w-3 rounded-sm" style={{ background: ACCENT }} />Metal-bearing (metal, copper, e-waste)</li>
        <li className="inline-flex items-center gap-2"><span className="h-3 w-3 rounded-sm" style={{ background: DEEMPH }} />Other materials</li>
      </ul>
      <div style={{ height: rows.length * 40 + 16 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 80, bottom: 4, left: 8 }} barCategoryGap={8}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="material" width={210} tickLine={false} axisLine={{ stroke: '#c3c2b7' }}
              tick={{ fontSize: 14, fill: '#0b0b0b' }} />
            <Tooltip cursor={{ fill: '#eef3f8' }} content={({ active, payload }: BarTipProps) =>
              active && payload?.length ? (
                <div className={tipBox}>
                  <div className="font-semibold">{String(row(payload).material)}</div>
                  <div className="tabular">{inr(row(payload).value_at_ref_inr as number)} · {kg(row(payload).kg as number)}</div>
                </div>) : null} />
            <Bar dataKey="value_at_ref_inr" radius={[0, 4, 4, 0]} maxBarSize={24} isAnimationActive={false}>
              {rows.map((r) => <Cell key={r.material} fill={metal(r.category) ? ACCENT : DEEMPH} />)}
              <LabelList dataKey="value_at_ref_inr" position="right" formatter={(v: unknown) => inrCompact(Number(v))}
                style={{ fontSize: 13, fill: '#52514e' }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <TableView>
        <DataTable rows={rows} rowKey={(r) => r.material} columns={[
          { key: 'm', header: 'Material', render: (r) => r.material },
          { key: 'k', header: 'kg', numeric: true, render: (r) => n1(r.kg) },
          { key: 'v', header: 'Value at reference', numeric: true, render: (r) => inr(r.value_at_ref_inr) },
        ]} />
      </TableView>
    </Card>
  )
}

function KgByCategory({ s }: { s: MinistrySummary }) {
  const rows = CATEGORY_ORDER
    .filter((c) => s.by_category[c] !== undefined)
    .map((c) => ({ category: c, label: CATEGORY_LABEL[c], kg: s.by_category[c]! }))
    .sort((a, b) => b.kg - a.kg)
  return (
    <Card title="Material mix, by weight" subtitle="kg collected in each of the six material classes.">
      <div className="mb-2 h-[21px]" />
      <div style={{ height: rows.length * 40 + 16 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 80, bottom: 4, left: 8 }} barCategoryGap={8}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="label" width={210} tickLine={false} axisLine={{ stroke: '#c3c2b7' }}
              tick={{ fontSize: 14, fill: '#0b0b0b' }} />
            <Tooltip cursor={{ fill: '#eef3f8' }} content={({ active, payload }: BarTipProps) =>
              active && payload?.length ? (
                <div className={tipBox}>
                  <div className="font-semibold">{String(row(payload).label)}</div>
                  <div className="tabular">{kg(row(payload).kg as number)} · {pct((100 * (row(payload).kg as number)) / s.totals.kg)}</div>
                </div>) : null} />
            <Bar dataKey="kg" fill={ACCENT} radius={[0, 4, 4, 0]} maxBarSize={24} isAnimationActive={false}>
              <LabelList dataKey="kg" position="right" formatter={(v: unknown) => `${n0(Number(v))} kg`}
                style={{ fontSize: 13, fill: '#52514e' }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <TableView>
        <DataTable rows={rows} rowKey={(r) => r.category} columns={[
          { key: 'c', header: 'Material class', render: (r) => (
            <span className="inline-flex items-center gap-2"><span className="h-3 w-3 rounded-sm" style={{ background: CATEGORY_COLOR[r.category] }} />{r.label}</span>) },
          { key: 'k', header: 'kg', numeric: true, render: (r) => n1(r.kg) },
          { key: 'p', header: 'Share', numeric: true, render: (r) => pct((100 * r.kg) / s.totals.kg) },
        ]} />
      </TableView>
    </Card>
  )
}

function Geography({ s }: { s: MinistrySummary }) {
  const located = s.by_area.filter((a) => a.lat !== null && a.lon !== null)
  const max = Math.max(...s.by_area.map((a) => a.kg), 1)
  return (
    <Card title="Where material is collected" subtitle="Circle size and shade = kg collected in each locality (darker = more).">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="h-[440px] overflow-hidden rounded-md border border-black/10">
          <MapContainer center={[26.885, 75.8]} zoom={12} zoomSnap={0.25} scrollWheelZoom={false} className="h-full w-full">
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <FitBounds points={located.map((a) => [a.lat!, a.lon!] as [number, number])} />
            {located.map((a) => (
              <CircleMarker key={a.area} center={[a.lat!, a.lon!]} radius={8 + 22 * Math.sqrt(a.kg / max)}
                pathOptions={{ color: '#ffffff', weight: 2, fillColor: seqColor(a.kg / max), fillOpacity: 0.8 }}>
                <MapTip>
                  <strong>{a.area}</strong><br />{kg(a.kg)} · {a.lots} lots · {a.collectors} collectors
                </MapTip>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>
        <DataTable rows={s.by_area} rowKey={(a) => a.area} maxHeight={440} columns={[
          { key: 'a', header: 'Area', render: (a) => a.area },
          { key: 'k', header: 'kg', numeric: true, render: (a) => n1(a.kg) },
          { key: 'l', header: 'Lots', numeric: true, render: (a) => n0(a.lots) },
          { key: 'c', header: 'Collectors', numeric: true, render: (a) => n0(a.collectors) },
        ]} />
      </div>
    </Card>
  )
}
