import { useApi, type Passport } from '../api'
import { dateTime, inr, kg } from '../format'
import { CATEGORY_COLOR } from '../theme'
import { Async, StatusBadge } from './ui'

const STAGE_LABEL = { collector: 'Collected by', aggregator: 'Aggregator', recycler: 'Recycler (CPCB-authorised)' }

/** Chain of custody for one lot, as a vertical timeline. */
export function PassportPanel({ transactionId, onClose }: { transactionId: number; onClose: () => void }) {
  const state = useApi<Passport>(`/api/passport/${transactionId}`)
  return (
    <div className="rounded-lg border border-navy-700/25 bg-navy-50/60 p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <div className="text-[0.8rem] font-medium uppercase tracking-wide text-ink-2">Material passport</div>
          <div className="font-semibold text-navy-900">{`MITRA-P-${String(transactionId).padStart(6, '0')}`}</div>
        </div>
        <button onClick={onClose} className="rounded px-2 text-xl leading-none text-ink-2 hover:bg-black/5" aria-label="Close passport">×</button>
      </div>
      <Async state={state}>
        {(p) => (
          <div className="space-y-3 text-[0.92rem]">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-sm" style={{ background: CATEGORY_COLOR[p.material.category] }} />
                <strong>{p.material.name}</strong>
              </span>
              <span>· {kg(p.weight_kg)} · paid {inr(p.amount_paid)}</span>
              <StatusBadge status={p.status} />
            </div>
            <ol className="relative ml-2 border-l-2 border-navy-700/30 pl-4">
              {p.chain.map((h, i) => (
                <li key={i} className="mb-3 last:mb-0">
                  <span className={`absolute -left-[7px] mt-1.5 h-3 w-3 rounded-full border-2 border-white ${h.ts ? 'bg-navy-700' : 'bg-[#c9c7bf]'}`} />
                  <div className="text-[0.8rem] text-ink-2">{STAGE_LABEL[h.stage]}</div>
                  <div className="font-medium">{h.name}</div>
                  <div className="text-[0.82rem] text-ink-2">
                    {h.cpcb_reg_no ?? h.reg_no ?? h.area}
                    {' · '}
                    {h.ts ? dateTime(h.ts) : h.stage === 'recycler' ? 'dispatched, receipt pending' : 'handover not yet recorded'}
                  </div>
                </li>
              ))}
              {p.chain.length < 3 && (
                <li className="text-[0.82rem] text-ink-2">
                  <span className="absolute -left-[7px] mt-1 h-3 w-3 rounded-full border-2 border-white bg-[#c9c7bf]" />
                  Awaiting dispatch to a recycler
                </li>
              )}
            </ol>
            <div className="text-[0.8rem] text-ink-2">
              GPS {p.gps ? `${p.gps.lat.toFixed(4)}, ${p.gps.lon.toFixed(4)}` : 'not recorded'} ·
              material confirmed by {p.classification.confirmed_by}
              {p.classification.cv_suggested && ` (camera suggested ${p.classification.cv_suggested})`}
            </div>
          </div>
        )}
      </Async>
    </div>
  )
}
