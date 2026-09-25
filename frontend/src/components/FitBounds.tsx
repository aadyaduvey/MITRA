import { useEffect, useRef } from 'react'
import { useMap } from 'react-leaflet'

/** Zoom the map to fit `points` once, on first data. Later refreshes leave the view alone. */
export function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap()
  const done = useRef(false)
  useEffect(() => {
    if (done.current || points.length === 0) return
    map.fitBounds(points, { padding: [28, 28], maxZoom: 14 })
    done.current = true
  }, [map, points])
  return null
}
