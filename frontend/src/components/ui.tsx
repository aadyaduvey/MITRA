import type { ReactNode } from 'react'
import type { Category, PassportStatus } from '../api'
import { STATUS_LABEL } from '../format'
import { CATEGORY_COLOR, CATEGORY_LABEL, CATEGORY_ORDER } from '../theme'

export function Card({ title, subtitle, children, actions, className = '' }: {
  title?: ReactNode; subtitle?: ReactNode; children: ReactNode; actions?: ReactNode; className?: string
}) {
  return (
    <section className={`rounded-lg border border-black/10 bg-white p-5 shadow-sm ${className}`}>
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title && <h2 className="border-l-4 border-saffron pl-2.5 text-lg font-semibold text-navy-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-[0.9rem] text-ink-2">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function StatTile({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="rounded-lg border border-black/10 border-t-4 border-t-navy-800 bg-white px-5 py-4 shadow-sm">
      <div className="text-[0.85rem] font-medium uppercase tracking-wide text-ink-2">{label}</div>
      <div className="mt-1 text-[1.9rem] leading-tight font-semibold text-navy-900">{value}</div>
      {note && <div className="mt-1 text-[0.85rem] text-muted">{note}</div>}
    </div>
  )
}

/** One filter row, above everything it scopes. */
export function FilterRow({ children }: { children: ReactNode }) {
  return <div className="mb-5 flex flex-wrap items-end gap-x-6 gap-y-3">{children}</div>
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-[0.85rem] font-medium text-ink-2">
      {label}
      {children}
    </label>
  )
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string
}) {
  return (
    <Field label={label}>
      <div role="radiogroup" aria-label={label} className="inline-flex overflow-hidden rounded-md border border-navy-700/40 bg-white">
        {options.map((o) => (
          <button
            key={o.value}
            role="radio"
            aria-checked={o.value === value}
            onClick={() => onChange(o.value)}
            className={`px-3.5 py-1.5 text-[0.95rem] font-medium transition-colors ${
              o.value === value ? 'bg-navy-800 text-white' : 'text-navy-800 hover:bg-navy-50'
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </Field>
  )
}

export function Select({ value, onChange, children, label }: {
  value: string; onChange: (v: string) => void; children: ReactNode; label: string
}) {
  return (
    <Field label={label}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-navy-700/40 bg-white px-3 py-1.5 text-[0.95rem] text-ink"
      >
        {children}
      </select>
    </Field>
  )
}

export function MaterialOptions({ allLabel = 'All materials' }: { allLabel?: string }) {
  return (
    <>
      <option value="">{allLabel}</option>
      {CATEGORY_ORDER.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}
    </>
  )
}

export function Legend({ items, onPick, active }: {
  items: Category[]; onPick?: (c: Category) => void; active?: Category | ''
}) {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1.5 text-[0.9rem] text-ink-2">
      {items.map((c) => {
        const dim = active && active !== c
        return (
          <li key={c}>
            <button
              type="button"
              disabled={!onPick}
              onClick={() => onPick?.(c)}
              className={`inline-flex items-center gap-2 ${onPick ? 'cursor-pointer hover:text-ink' : 'cursor-default'} ${dim ? 'opacity-45' : ''}`}
            >
              <span className="inline-block h-3 w-3 rounded-sm" style={{ background: CATEGORY_COLOR[c] }} />
              {CATEGORY_LABEL[c]}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

const STATUS_STYLE: Record<PassportStatus, { icon: string; cls: string }> = {
  delivered: { icon: '✓', cls: 'bg-[#e7f6e7] text-[#006300] border-[#0ca30c]/40' },
  in_transit: { icon: '→', cls: 'bg-navy-50 text-navy-800 border-navy-700/30' },
  collected: { icon: '•', cls: 'bg-[#f3f2ee] text-ink-2 border-black/15' },
}

/** Status never relies on colour alone: icon + label. */
export function StatusBadge({ status }: { status: PassportStatus }) {
  const s = STATUS_STYLE[status]
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[0.8rem] font-medium ${s.cls}`}>
      <span aria-hidden>{s.icon}</span>
      {STATUS_LABEL[status]}
    </span>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center gap-3 text-ink-2" role="status">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-navy-700/25 border-t-navy-700" />
      {label}
    </div>
  )
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[#d03b3b]/40 bg-[#fdf0f0] px-4 py-3 text-[#8f1f1f]">
      <span><strong className="mr-1">⚠ Error:</strong>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="rounded-md border border-[#8f1f1f]/40 bg-white px-3 py-1 text-[0.9rem] font-medium hover:bg-[#fff6f6]">
          Retry
        </button>
      )}
    </div>
  )
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center gap-1 rounded-md border border-dashed border-black/20 bg-[#fafaf8] p-6 text-center">
      <div className="font-medium text-ink">{title}</div>
      {hint && <div className="text-[0.9rem] text-ink-2">{hint}</div>}
    </div>
  )
}

/** Loading / error / content wrapper. Keeps stale data visible (dimmed) while refreshing. */
export function Async<T>({ state, children, loadingLabel }: {
  state: { data: T | undefined; error?: string; loading: boolean; refreshing: boolean; retry: () => void }
  children: (data: T) => ReactNode
  loadingLabel?: string
}) {
  if (state.data === undefined) {
    if (state.error) return <ErrorBox message={state.error} onRetry={state.retry} />
    return <Loading label={loadingLabel} />
  }
  return (
    <div className={`transition-opacity ${state.refreshing ? 'opacity-60' : ''}`}>
      {state.error && <div className="mb-3"><ErrorBox message={`${state.error} (showing last loaded data)`} onRetry={state.retry} /></div>}
      {children(state.data)}
    </div>
  )
}

export interface Column<R> {
  key: string
  header: string
  render: (r: R) => ReactNode
  numeric?: boolean
}

export function DataTable<R>({ rows, columns, rowKey, maxHeight }: {
  rows: R[]; columns: Column<R>[]; rowKey: (r: R, i: number) => string | number; maxHeight?: number
}) {
  return (
    <div className="overflow-auto rounded-md border border-black/10" style={maxHeight ? { maxHeight } : undefined}>
      <table className="w-full border-collapse text-[0.9rem]">
        <thead className="sticky top-0 bg-navy-50">
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={`border-b border-navy-700/30 px-3 py-2 font-semibold text-navy-900 ${c.numeric ? 'text-right' : 'text-left'}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={rowKey(r, i)} className="odd:bg-white even:bg-[#f7f8fa]">
              {columns.map((c) => (
                <td key={c.key} className={`border-b border-black/5 px-3 py-1.5 ${c.numeric ? 'tabular text-right' : ''}`}>
                  {c.render(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** The accessible twin of a chart: same numbers, as a table, behind a toggle. */
export function TableView({ children, label = 'View as table' }: { children: ReactNode; label?: string }) {
  return (
    <details className="mt-3 group">
      <summary className="cursor-pointer select-none text-[0.9rem] font-medium text-navy-700 hover:underline">
        {label}
      </summary>
      <div className="mt-2">{children}</div>
    </details>
  )
}

export function PeriodOptions() {
  return [
    { value: 'all', label: 'All' },
    { value: '7', label: '7 days' },
    { value: '14', label: '14 days' },
    { value: '30', label: '30 days' },
  ] as { value: Period; label: string }[]
}

export type Period = 'all' | '7' | '14' | '30'
