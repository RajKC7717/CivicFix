/** Public city map: every open issue, filterable, with no personal data on it. */

import { useEffect, useMemo, useState } from 'react'
import { IssueMarkers, MapView, WardBoundaries, useWardGeometry } from '../components/MapView'
import { Badge, Card, Select, Skeleton } from '../components/ui/primitives'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { BAND_HEX } from '../lib/format'
import type { Band, MapItem, Meta } from '../lib/types'

export default function PublicMap() {
  const { t, pick } = useI18n()
  const [meta, setMeta] = useState<Meta | null>(null)
  const [items, setItems] = useState<MapItem[] | null>(null)
  const [category, setCategory] = useState('')
  const [showExpired, setShowExpired] = useState(false)
  const wards = useWardGeometry()

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setMeta(null))
  }, [])

  useEffect(() => {
    setItems(null)
    api
      .publicMap(category ? { category } : {})
      .then((payload) => setItems(payload.items))
      .catch(() => setItems([]))
  }, [category])

  const counts = useMemo(() => {
    const tally: Record<string, number> = { P1: 0, P2: 0, P3: 0, P4: 0 }
    for (const item of items ?? []) tally[item.band] = (tally[item.band] ?? 0) + 1
    return tally
  }, [items])

  const visibleItems = useMemo(() => {
    if (!items) return []
    if (showExpired) return items
    return items.filter(i => !i.ack_expired)
  }, [items, showExpired])

  return (
    <div className="mx-auto max-w-5xl px-4 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-ink-900">{t('nav_map')}</h1>
          <p className="text-sm text-ink-600 mt-1">
            {items === null ? t('loading') : `${items.length} open issues across the city`}
          </p>
        </div>
        <Select
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          className="w-auto min-w-[220px]"
          aria-label="Filter by category"
        >
          <option value="">All categories</option>
          {meta?.categories.map((option) => (
            <option key={option.key} value={option.key}>
              {pick(option)}
            </option>
          ))}
        </Select>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 mt-4">
        <div className="flex flex-wrap gap-2">
          {(['P1', 'P2', 'P3', 'P4'] as Band[]).map((band) => (
            <Badge key={band} tone="neutral" className="gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ background: BAND_HEX[band] }} />
              {band} · {counts[band] ?? 0}
            </Badge>
          ))}
        </div>
        
        <label className="flex items-center gap-2 text-sm text-ink-700 cursor-pointer">
          <input
            type="checkbox"
            checked={showExpired}
            onChange={(e) => setShowExpired(e.target.checked)}
            className="rounded border-ink-300 text-accent-500 focus:ring-accent-500"
          />
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-ink-300" />
            Show expired ({items?.filter(i => i.ack_expired).length ?? 0})
          </span>
        </label>
      </div>

      <Card className="mt-4 p-1 overflow-hidden">
        {items === null ? (
          <Skeleton className="h-[520px] rounded-xl" />
        ) : (
          <MapView className="h-[520px]" zoom={11}>
            {wards && <WardBoundaries data={wards} showLabels />}
            <IssueMarkers items={visibleItems} />
          </MapView>
        )}
      </Card>

      <p className="text-2xs text-ink-500 mt-3 leading-relaxed">
        Issues only — no reporter information is published. Ward outlines are synthetic and are not
        PMC electoral wards. Map data © OpenStreetMap contributors.
      </p>
    </div>
  )
}
