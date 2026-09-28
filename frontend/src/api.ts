// Typed client for the MITRA FastAPI backend. Types mirror backend/app/schemas.py.
import { useCallback, useEffect, useState } from 'react'

export type Category = 'metal' | 'ewaste' | 'paper' | 'pet' | 'hdpe' | 'glass'
export type PassportStatus = 'collected' | 'in_transit' | 'delivered'

export interface Material {
  id: number
  name: string
  category: Category
  ref_price_per_kg: number
}

export interface Transaction {
  id: number
  collector_id: number
  collector_name: string
  material_id: number
  material: string
  category: Category
  weight_kg: number
  amount_paid: number
  ref_price_per_kg: number
  ref_amount: number
  gps_lat: number | null
  gps_lon: number | null
  photo_url: string | null
  cv_suggested: string | null
  cv_confidence: number | null
  ts: string
  aggregator_id: number | null
  passport_id: string
  passport_status: PassportStatus
}

export interface CollectorDetail {
  id: number
  code: string
  name: string
  area: string
  phone: string | null
  registered_ts: string
  lots: number
  kg: number
  last_ts: string | null
  last_lat: number | null
  last_lon: number | null
  recent_transactions: Transaction[]
}

export interface ChainHop {
  stage: 'collector' | 'aggregator' | 'recycler'
  id: number
  name: string
  area?: string | null
  reg_no?: string | null
  cpcb_reg_no?: string | null
  ts: string | null
}

export interface Passport {
  passport_id: string
  transaction_id: number
  status: PassportStatus
  custody_complete: boolean
  collected_at: string
  collector: { id: number; name: string; area: string }
  material: { name: string; category: Category; ref_price_per_kg: number }
  weight_kg: number
  amount_paid: number
  gps: { lat: number; lon: number } | null
  classification: { confirmed_by: string; cv_suggested: string | null; cv_confidence: number | null }
  chain: ChainHop[]
  destination: { recycler_id: number; name: string; cpcb_reg_no: string } | null
}

export interface EprReport {
  period: { start: string; end: string }
  generated_at: string
  totals: { lots: number; collectors: number; kg_collected: number; kg_in_transit: number; kg_delivered: number }
  by_material: {
    material: string; category: Category; lots: number
    kg_collected: number; kg_in_transit: number; kg_delivered: number
  }[]
  recyclers: {
    name: string; cpcb_reg_no: string | null; lots: number
    kg_in_transit: number; kg_delivered: number; kg_by_material: Record<string, number>
  }[]
  collector_ids: number[]
  lots: {
    passport_id: string; transaction_id: number; collector_id: number; collected_at: string
    material: string; category: Category; kg: number; aggregator: string | null
    recycler: string | null; recycler_cpcb_reg_no: string | null
    status: PassportStatus; delivered_at: string | null
  }[]
}

export interface MinistrySummary {
  period: { start: string; end: string } | null
  totals: {
    kg: number; lots: number; value_at_ref_inr: number; amount_paid_inr: number
    active_collectors: number; registered_collectors: number; kg_traced: number; pct_traced: number
  }
  by_material: { material: string; category: Category; kg: number; lots: number; value_at_ref_inr: number }[]
  by_category: Partial<Record<Category, number>>
  by_area: { area: string; kg: number; lots: number; collectors: number; lat: number | null; lon: number | null }[]
  metal_recovery: {
    kg: number; value_at_ref_inr: number; pct_of_total_value: number
    materials: { material: string; kg: number; value_at_ref_inr: number }[]
  }
}

export interface Sankey {
  nodes: { name: string; stage: 'collector' | 'aggregator' | 'recycler' | 'pending' }[]
  links: { source: number; target: number; material: Category; value: number }[]
  kg_total: number
  kg_traced: number
  pct_traced: number
}

export interface PriceRow extends Material {
  price_updated_at: string | null
  price_source: string | null
  live: boolean
  live_rule: string | null
}

export interface PriceBoard {
  live_configured: boolean
  live_provider: string
  prices: PriceRow[]
}

export interface PriceHistoryRow {
  id: number
  material_id: number
  material: string
  price_per_kg: number
  previous_price: number | null
  source: string
  ts: string
}

export interface LiveRefresh {
  configured: boolean
  message: string
  results: { material: string; status: 'updated' | 'kept' | 'rejected'; old_price: number; new_price: number; detail: string }[]
}

/** Build a URL with only the params that are set. */
export function url(path: string, params: Record<string, string | number | null | undefined> = {}) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') q.set(k, String(v))
  const s = q.toString()
  return s ? `${path}?${s}` : path
}

const UNREACHABLE = 'Cannot reach the MITRA API. Is the backend running? (start everything with start.cmd)'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return requestJson<T>(path, { signal })
}

/** POST/PUT a JSON body; throws with the API's own error message. */
export async function sendJson<T>(method: 'POST' | 'PUT', path: string, body?: unknown): Promise<T> {
  return requestJson<T>(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new Error(UNREACHABLE)
  }
  if (!res.ok) {
    let body: { detail?: unknown } | undefined
    try { body = await res.json() } catch { /* non-JSON: the dev proxy could not reach FastAPI */ }
    if (body === undefined && res.status >= 500) throw new Error(UNREACHABLE)
    const detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? res.statusText)
    throw new Error(`API ${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export interface ApiState<T> {
  data: T | undefined
  error: string | undefined
  loading: boolean // true only while there is no data for the current request yet
  refreshing: boolean // true while re-fetching with previous data still on screen
  retry: () => void
}

/**
 * Fetch JSON from `path`; keeps the previous data on screen while a new request
 * is in flight (no skeleton flash). Optional polling for live views.
 */
export function useApi<T>(path: string | null, pollMs?: number): ApiState<T> {
  const [data, setData] = useState<T>()
  const [error, setError] = useState<string>()
  const [pending, setPending] = useState(false)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    if (!path) return
    const ctrl = new AbortController()
    const load = (background: boolean) => {
      if (!background) setPending(true)
      getJson<T>(path, ctrl.signal)
        .then((d) => { setData(d); setError(undefined) })
        .catch((e: Error) => { if (e.name !== 'AbortError') setError(e.message) })
        .finally(() => { if (!ctrl.signal.aborted && !background) setPending(false) })
    }
    load(false)
    const timer = pollMs ? window.setInterval(() => load(true), pollMs) : undefined
    return () => { ctrl.abort(); window.clearInterval(timer) }
  }, [path, pollMs, nonce])

  const retry = useCallback(() => setNonce((n) => n + 1), [])
  const hasData = data !== undefined
  return { data, error, loading: pending && !hasData, refreshing: pending && hasData, retry }
}
