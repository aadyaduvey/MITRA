import { useMemo, useState } from 'react'
import { ResponsiveContainer, Sankey, Tooltip } from 'recharts'
import { url, useApi, type Category, type Sankey as SankeyData } from '../api'
import {
  Async, Card, DataTable, Empty, FilterRow, Legend, MaterialOptions, PeriodOptions, Segmented, Select,
  StatTile, TableView, type Period,
} from '../components/ui'
import { isoDay, kg, n1, pct } from '../format'
import { CATEGORY_COLOR, CATEGORY_LABEL, CATEGORY_ORDER, DEEMPH, NAVY } from '../theme'

type Node = SankeyData['nodes'][number]
type Link = SankeyData['links'][number]

// Shapes Recharts passes to custom Sankey link/node renderers (not exported by recharts 3).
interface LinkProps {
  sourceX: number; targetX: number; sourceY: number; targetY: number
  sourceControlX: number; targetControlX: number; linkWidth: number
  payload: unknown
}
interface NodeProps { x: number; y: number; width: number; height: number; payload: unknown }

const LEFT = 150
const RIGHT = 300

export function MaterialFlow() {
  const [period, setPeriod] = useState<Period>('all')
  const [groupBy, setGroupBy] = useState<'area' | 'collector'>('area')
  const [focus, setFocus] = useState<Category | ''>('')
  const start = period === 'all' ? null : isoDay(Number(period) - 1)
  const state = useApi<SankeyData>(url('/api/flow/sankey', { group_by: groupBy, start }))

  return (
    <div>
      <FilterRow>
        <Segmented label="Period" value={period} options={PeriodOptions()} onChange={setPeriod} />
        <Segmented
          label="Collectors grouped by"
          value={groupBy}
          options={[{ value: 'area', label: 'Area' }, { value: 'collector', label: 'Individual' }]}
          onChange={setGroupBy}
        />
        <Select label="Highlight material" value={focus} onChange={(v) => setFocus(v as Category | '')}>
          <MaterialOptions allLabel="All materials (coloured)" />
        </Select>
      </FilterRow>
      <Async state={state} loadingLabel="Loading material flow…">
        {(d) => <FlowBody data={d} focus={focus} setFocus={setFocus} groupBy={groupBy} />}
      </Async>
    </div>
  )
}

function FlowBody({ data, focus, setFocus, groupBy }: {
  data: SankeyData; focus: Category | ''; setFocus: (c: Category | '') => void; groupBy: string
}) {
  const present = useMemo(
    () => CATEGORY_ORDER.filter((c) => data.links.some((l) => l.material === c)),
    [data.links],
  )
  const awaiting = data.kg_total - data.kg_traced
  const collectorNodes = data.nodes.filter((n) => n.stage === 'collector').length
  const height = Math.max(560, collectorNodes * 22)

  if (data.links.length === 0) {
    return <Empty title="No material flow in this period" hint="Choose a longer period, or log a lot with an aggregator." />
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile label="Material in the chain" value={kg(data.kg_total)} note="Sold on to an aggregator" />
        <StatTile label="Traced to an authorised recycler" value={pct(data.pct_traced)} note={`${kg(data.kg_traced)} with a recycler on the passport`} />
        <StatTile label="Awaiting dispatch" value={kg(awaiting)} note="Held by aggregators, no recycler yet" />
      </div>

      <Card
        title="Where material goes: collector → aggregator → recycler"
        subtitle="Band width = kg. Colour = material. Hover a band for the figure; click a legend item to highlight one material."
      >
        <div className="mb-3"><Legend items={present} active={focus} onPick={(c) => setFocus(focus === c ? '' : c)} /></div>
        <div className="mb-1 flex justify-between text-[0.8rem] font-semibold uppercase tracking-wide text-ink-2">
          <span style={{ width: LEFT }} className="text-right">{groupBy === 'area' ? 'Collectors, by area' : 'Collectors'}</span>
          <span>Aggregators</span>
          <span style={{ width: RIGHT }} className="pl-3">Recyclers (CPCB) / awaiting</span>
        </div>
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <Sankey
              data={data as unknown as { nodes: Node[]; links: Link[] }}
              nodeWidth={12}
              nodePadding={groupBy === 'area' ? 14 : 6}
              margin={{ top: 8, bottom: 8, left: LEFT, right: RIGHT }}
              link={(p: LinkProps) => <FlowLink {...p} focus={focus} />}
              node={(p: NodeProps) => <FlowNode {...p} />}
              iterations={64}
            >
              <Tooltip content={<FlowTooltip />} />
            </Sankey>
          </ResponsiveContainer>
        </div>
        <TableView label="View flows as table">
          <FlowTable data={data} />
        </TableView>
      </Card>
    </div>
  )
}

function FlowLink(p: LinkProps & { focus: Category | '' }) {
  const material = (p.payload as unknown as Link).material
  const on = !p.focus || p.focus === material
  const d = `M${p.sourceX},${p.sourceY} C${p.sourceControlX},${p.sourceY} ${p.targetControlX},${p.targetY} ${p.targetX},${p.targetY}`
  return (
    <path
      d={d}
      fill="none"
      stroke={on ? CATEGORY_COLOR[material] : DEEMPH}
      strokeWidth={Math.max(1, p.linkWidth)}
      strokeOpacity={on ? (p.focus ? 0.75 : 0.5) : 0.18}
      className="transition-[stroke-opacity] hover:[stroke-opacity:0.9]"
    />
  )
}

function FlowNode({ x, y, width, height, payload }: NodeProps) {
  const node = payload as unknown as Node & { value: number }
  const pending = node.stage === 'pending'
  const leftCol = node.stage === 'collector'
  const rightCol = node.stage === 'recycler' || pending
  const tx = leftCol ? x - 6 : x + width + 6
  const anchor = leftCol ? 'end' : 'start'
  const name = node.name.replace(' (synthetic)', '')
  const halo = { paintOrder: 'stroke' as const, stroke: '#fff', strokeWidth: 4, strokeLinejoin: 'round' as const }
  return (
    <g>
      <rect x={x} y={y} width={width} height={Math.max(height, 1)} rx={2}
        fill={pending ? '#ffffff' : NAVY} stroke={pending ? NAVY : 'none'} strokeWidth={pending ? 1.5 : 0} />
      {height >= 2 && (
        <text x={tx} y={y + height / 2} dy="0.35em" textAnchor={anchor} fontSize={rightCol || node.stage === 'aggregator' ? 14 : height < 9 ? 12 : 13}
          fill="#0b0b0b" style={halo}>
          <tspan fontWeight={600}>{name}</tspan>
          {(rightCol || node.stage === 'aggregator') && <tspan fill="#52514e"> {n1(node.value)} kg</tspan>}
        </text>
      )}
    </g>
  )
}

interface TipProps {
  active?: boolean
  payload?: ReadonlyArray<{ payload?: unknown }>
}

function FlowTooltip({ active, payload }: TipProps) {
  if (!active || !payload?.length) return null
  const raw = payload[0].payload as Record<string, unknown> | undefined
  const item = ((raw?.payload as Record<string, unknown> | undefined) ?? raw) as Record<string, unknown> | undefined
  if (!item) return null
  const box = 'rounded-md border border-black/10 bg-white px-3 py-2 text-[0.9rem] shadow-lg'
  if (item.source && item.target) {
    const s = item.source as Node, t = item.target as Node
    const m = item.material as Category
    return (
      <div className={box}>
        <div className="flex items-center gap-2 font-semibold">
          <span className="h-3 w-3 rounded-sm" style={{ background: CATEGORY_COLOR[m] }} />
          {CATEGORY_LABEL[m]}
        </div>
        <div className="text-ink-2">{s.name.replace(' (synthetic)', '')} → {t.name.replace(' (synthetic)', '')}</div>
        <div className="tabular font-semibold">{kg(item.value as number)}</div>
      </div>
    )
  }
  return (
    <div className={box}>
      <div className="font-semibold">{String(item.name).replace(' (synthetic)', '')}</div>
      <div className="tabular">{kg(item.value as number)}</div>
    </div>
  )
}

function FlowTable({ data }: { data: SankeyData }) {
  const rows = data.links.map((l, i) => ({ ...l, i }))
  return (
    <DataTable
      rows={rows}
      rowKey={(r) => r.i}
      maxHeight={360}
      columns={[
        { key: 'from', header: 'From', render: (r) => data.nodes[r.source].name },
        { key: 'to', header: 'To', render: (r) => data.nodes[r.target].name },
        { key: 'm', header: 'Material', render: (r) => CATEGORY_LABEL[r.material] },
        { key: 'kg', header: 'kg', numeric: true, render: (r) => n1(r.value) },
      ]}
    />
  )
}
