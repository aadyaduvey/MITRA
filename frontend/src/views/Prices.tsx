import { useState } from 'react'
import {
  sendJson, useApi, type LiveRefresh, type PriceBoard, type PriceHistoryRow, type PriceRow,
} from '../api'
import { Async, Card, DataTable, Empty, ErrorBox } from '../components/ui'
import { dateTime, inr } from '../format'
import { CATEGORY_COLOR } from '../theme'

const inputCls = 'rounded-md border border-navy-700/40 bg-white px-2.5 py-1.5 text-[0.95rem]'
const btnCls = 'rounded-md px-3.5 py-1.5 text-[0.95rem] font-semibold disabled:opacity-50'

export function Prices() {
  const [version, setVersion] = useState(0)
  const board = useApi<PriceBoard>(`/api/prices?v=${version}`)
  const hist = useApi<PriceHistoryRow[]>(`/api/prices/history?limit=20&v=${version}`)
  const reload = () => setVersion((v) => v + 1)

  return (
    <div className="space-y-5">
      <Card>
        <p className="text-[0.95rem] text-ink-2">
          <strong className="text-ink">Reference price = market price minus a fair trader margin.</strong>{' '}
          Collectors see these prices in the Telegram bot (💰 Today's prices) and on every receipt.
          Changing a price applies to new lots immediately; past receipts keep the price they were given.
        </p>
      </Card>
      <Async state={board} loadingLabel="Loading prices…">
        {(b) => (
          <>
            <LiveCard board={b} onDone={reload} />
            <Card title="Current prices" subtitle="Type a new price and where it comes from, then Save. Every change is kept in the history below.">
              <div className="overflow-auto rounded-md border border-black/10">
                <table className="w-full border-collapse text-[0.92rem]">
                  <thead className="bg-navy-50">
                    <tr className="text-left text-navy-900">
                      <th className="border-b border-navy-700/30 px-3 py-2">Material</th>
                      <th className="border-b border-navy-700/30 px-3 py-2 text-right">₹/kg now</th>
                      <th className="border-b border-navy-700/30 px-3 py-2">Updated · source</th>
                      <th className="border-b border-navy-700/30 px-3 py-2">Set a new price</th>
                    </tr>
                  </thead>
                  <tbody>
                    {b.prices.map((p) => <PriceEditRow key={p.id} p={p} onSaved={reload} />)}
                  </tbody>
                </table>
              </div>
            </Card>
          </>
        )}
      </Async>
      <Card title="Price history" subtitle="Latest 20 changes, newest first.">
        <Async state={hist}>
          {(rows) => rows.length === 0 ? (
            <Empty title="No price changes yet" hint="Save a new price above, or fetch live prices." />
          ) : (
            <DataTable
              rows={rows}
              rowKey={(r) => r.id}
              maxHeight={420}
              columns={[
                { key: 't', header: 'When', render: (r) => dateTime(r.ts) },
                { key: 'm', header: 'Material', render: (r) => r.material },
                { key: 'o', header: 'Old ₹/kg', numeric: true, render: (r) => (r.previous_price === null ? '-' : r.previous_price.toLocaleString('en-IN')) },
                { key: 'n', header: 'New ₹/kg', numeric: true, render: (r) => r.price_per_kg.toLocaleString('en-IN') },
                { key: 's', header: 'Source', render: (r) => r.source },
              ]}
            />
          )}
        </Async>
      </Card>
    </div>
  )
}

function PriceEditRow({ p, onSaved }: { p: PriceRow; onSaved: () => void }) {
  const [price, setPrice] = useState('')
  const [source, setSource] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const value = Number(price)
  const valid = price !== '' && value > 0 && value <= 100000 && source.trim().length >= 2

  const save = async () => {
    setBusy(true)
    setError(undefined)
    try {
      await sendJson('PUT', `/api/prices/${p.id}`, { ref_price_per_kg: value, source: source.trim() })
      setPrice('')
      setSource('')
      onSaved()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr className="odd:bg-white even:bg-[#f7f8fa] align-top">
      <td className="border-b border-black/5 px-3 py-2.5">
        <span className="inline-flex items-center gap-2 font-medium">
          <span className="h-3 w-3 rounded-sm" style={{ background: CATEGORY_COLOR[p.category] }} />
          {p.name}
        </span>
        {p.live && <div className="mt-0.5 text-[0.8rem] text-navy-700">⟳ live feed: {p.live_rule}</div>}
      </td>
      <td className="tabular border-b border-black/5 px-3 py-2.5 text-right text-[1.05rem] font-semibold">
        {inr(p.ref_price_per_kg)}
      </td>
      <td className="border-b border-black/5 px-3 py-2.5 text-[0.85rem] text-ink-2">
        {p.price_updated_at ? dateTime(p.price_updated_at) : '-'}
        <div className="max-w-[26rem] text-ink">{p.price_source ?? '-'}</div>
      </td>
      <td className="border-b border-black/5 px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <input aria-label={`New price for ${p.name}, rupees per kg`} type="number" min="0" step="0.5"
            placeholder="₹/kg" value={price} onChange={(e) => setPrice(e.target.value)} className={`${inputCls} w-24`} />
          <input aria-label={`Source for ${p.name} price`} placeholder="Source, e.g. Jaipur kabadi market"
            value={source} onChange={(e) => setSource(e.target.value)} className={`${inputCls} w-64`} />
          <button onClick={save} disabled={!valid || busy} className={`${btnCls} bg-navy-800 text-white hover:bg-navy-900`}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
        {error && <div className="mt-2"><ErrorBox message={error} /></div>}
      </td>
    </tr>
  )
}

const STATUS = {
  updated: { icon: '✓', cls: 'text-[#006300]', label: 'Updated' },
  kept: { icon: '•', cls: 'text-ink-2', label: 'Kept last price' },
  rejected: { icon: '⚠', cls: 'text-[#8f1f1f]', label: 'Rejected' },
} as const

function LiveCard({ board, onDone }: { board: PriceBoard; onDone: () => void }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<LiveRefresh>()
  const [error, setError] = useState<string>()
  const liveNames = board.prices.filter((p) => p.live).map((p) => p.name).join(', ')

  const refresh = async () => {
    setBusy(true)
    setError(undefined)
    try {
      setResult(await sendJson<LiveRefresh>('POST', '/api/prices/live'))
      onDone()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card
      title="Live metal prices"
      subtitle={board.live_configured
        ? `${liveNames} updates from ${board.live_provider} automatically when the API starts (if older than 12 hours), or now with the button.`
        : `Not set up yet. Get a free key at metalpriceapi.com, add METAL_PRICE_API_KEY=your-key to backend/.env, and restart MITRA. Until then, set every price by hand below.`}
      actions={
        <button onClick={refresh} disabled={busy}
          className={`${btnCls} border border-navy-700/40 bg-white text-navy-800 hover:bg-navy-50`}>
          {busy ? 'Fetching…' : '⟳ Fetch live prices now'}
        </button>
      }
    >
      <p className="text-[0.85rem] text-ink-2">
        Steel scrap, paper, PET, glass and e-waste have no free live feed: set them by hand from your local rate card.
        A live price outside a believable range is rejected and the last price is kept.
      </p>
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
      {result && (
        <div className="mt-3 rounded-md border border-black/10 bg-[#fafaf8] p-3 text-[0.92rem]">
          {!result.configured && <div>{result.message}</div>}
          {result.results.map((r) => (
            <div key={r.material} className={STATUS[r.status].cls}>
              <strong>{STATUS[r.status].icon} {r.material}: {STATUS[r.status].label}</strong>{' '}
              {inr(r.old_price)} → {inr(r.new_price)}/kg · <span className="text-ink-2">{r.detail}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
