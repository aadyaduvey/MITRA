// Indian number formatting (lakh/crore grouping) for a Ministry audience.
const inr0 = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const num1 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1, minimumFractionDigits: 1 })
const num0 = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export const inr = (v: number) => inr0.format(v)
export const kg = (v: number) => `${num1.format(v)} kg`
export const n1 = (v: number) => num1.format(v)
export const n0 = (v: number) => num0.format(v)
export const pct = (v: number) => `${v.toFixed(1)}%`

/** Compact rupees for chart labels: 1.5 L, 2.3 Cr. */
export function inrCompact(v: number): string {
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`
  if (v >= 1e3) return `₹${(v / 1e3).toFixed(1)}k`
  return `₹${v.toFixed(0)}`
}

const dt = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' })
const d = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' })
export const dateTime = (iso: string) => dt.format(new Date(iso))
export const date = (iso: string) => d.format(new Date(iso))

/** yyyy-mm-dd for the local day `daysAgo` days before today. */
export function isoDay(daysAgo = 0): string {
  const t = new Date()
  t.setDate(t.getDate() - daysAgo)
  const m = String(t.getMonth() + 1).padStart(2, '0')
  const day = String(t.getDate()).padStart(2, '0')
  return `${t.getFullYear()}-${m}-${day}`
}

export function minutesAgo(iso: string): number {
  return (Date.now() - new Date(iso).getTime()) / 60000
}

export const STATUS_LABEL = { collected: 'Collected', in_transit: 'In transit', delivered: 'Delivered' } as const
