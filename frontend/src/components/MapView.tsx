/**
 * Leaflet map with graceful offline degradation.
 *
 * The one thing a venue demo cannot rely on is the internet, and OpenStreetMap
 * tiles come from the internet. So the map watches for tile errors and, after a
 * few, switches off the tile layer and renders the ward polygons on a plain
 * canvas instead. The markers, the clusters and the pin picker all keep working -
 * an officer still sees where every issue is, just without street imagery.
 *
 * Markers are Leaflet `divIcon`s rather than image pins: no bundler asset paths
 * to break, and the colour can encode the priority band directly.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { GeoJSON, MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import { BAND_HEX, classNames } from '../lib/format'
import type { Band, MapItem } from '../lib/types'

/** Pune. Used when we have nothing better to centre on. */
export const CITY_CENTER: [number, number] = [18.5204, 73.8567]
const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
const TILE_ERROR_LIMIT = 6

// ---------------------------------------------------------------------------
//  Icons
// ---------------------------------------------------------------------------
function bandIcon(band: Band, count: number, breached: boolean, ack_expired?: boolean): L.DivIcon {
  const colour = ack_expired ? '#94A3B8' : (BAND_HEX[band] ?? BAND_HEX.P4)
  const size = count > 1 ? 34 : 26
  const ring = breached ? `box-shadow:0 0 0 3px rgba(209,67,67,.35);` : ''
  const innerHtml = ack_expired ? '⚠' : (count > 1 ? count : '')
  return L.divIcon({
    className: 'nn-marker',
    html: `<div style="width:${size}px;height:${size}px;border-radius:9999px;background:${colour};
      border:2.5px solid #fff;${ring}display:flex;align-items:center;justify-content:center;
      color:#fff;font-size:${count > 1 || ack_expired ? 12 : 0}px;font-weight:700;font-family:Inter,sans-serif;
      box-sizing:border-box;">${innerHtml}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

const PIN_ICON = L.divIcon({
  className: 'nn-pin',
  html: `<div style="width:30px;height:38px;position:relative;">
    <svg viewBox="0 0 24 32" width="30" height="38" fill="none">
      <path d="M12 0C5.4 0 0 5.4 0 12c0 8.4 12 20 12 20s12-11.6 12-20C24 5.4 18.6 0 12 0z" fill="#DD7120"/>
      <circle cx="12" cy="12" r="4.5" fill="#fff"/>
    </svg></div>`,
  iconSize: [30, 38],
  iconAnchor: [15, 38],
})

// ---------------------------------------------------------------------------
//  Tile layer that gives up gracefully
// ---------------------------------------------------------------------------
function ResilientTiles({ onOffline }: { onOffline: () => void }) {
  const [errors, setErrors] = useState(0)

  useEffect(() => {
    if (errors >= TILE_ERROR_LIMIT) onOffline()
  }, [errors, onOffline])

  return (
    <TileLayer
      url={TILE_URL}
      attribution={TILE_ATTRIBUTION}
      maxZoom={19}
      eventHandlers={{ tileerror: () => setErrors((n) => n + 1) }}
    />
  )
}

/** Keeps the map view in sync when the caller changes centre or zoom. */
function ViewSync({ center, zoom }: { center: [number, number] | null; zoom?: number }) {
  const map = useMap()
  useEffect(() => {
    if (center) map.setView(center, zoom ?? map.getZoom(), { animate: true })
  }, [center, zoom, map])
  return null
}

/** Invalidate size after mount - Leaflet renders grey tiles inside flex layouts otherwise. */
function SizeFix() {
  const map = useMap()
  useEffect(() => {
    const timer = window.setTimeout(() => map.invalidateSize(), 120)
    const onResize = () => map.invalidateSize()
    window.addEventListener('resize', onResize)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('resize', onResize)
    }
  }, [map])
  return null
}

function ClickToPin({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({
    click: (event) => onPick(event.latlng.lat, event.latlng.lng),
  })
  return null
}

// ---------------------------------------------------------------------------
//  Ward boundaries
// ---------------------------------------------------------------------------
export function WardBoundaries({
  data,
  highlight,
  showLabels = false,
}: {
  data: FeatureCollection
  highlight?: string[]
  showLabels?: boolean
}) {
  const flagged = useMemo(() => new Set(highlight ?? []), [highlight])

  return (
    <GeoJSON
      key={`wards-${flagged.size}-${showLabels}`}
      data={data}
      style={(feature) => {
        const code = String((feature as Feature<Geometry>)?.properties?.code ?? '')
        const isFlagged = flagged.has(code)
        return {
          color: isFlagged ? '#DD7120' : '#4F6E93',
          weight: isFlagged ? 2.5 : 1,
          opacity: isFlagged ? 0.9 : 0.45,
          fillColor: isFlagged ? '#F2A868' : '#7590B0',
          fillOpacity: isFlagged ? 0.18 : 0.06,
        }
      }}
      onEachFeature={(feature, layer) => {
        const props = feature.properties ?? {}
        const name = String(props.name ?? 'Ward')
        if (showLabels) {
          layer.bindTooltip(name, { permanent: false, direction: 'center', className: 'nn-ward-label' })
        }
        layer.bindPopup(
          `<div style="padding:10px 12px;font-family:Inter,sans-serif;">
             <div style="font-weight:600;color:#0B2239;">${name}</div>
             <div style="font-size:12px;color:#4F6E93;margin-top:2px;">
               Ward ${props.code ?? '?'} · ${props.zone ?? ''}<br/>
               ${Number(props.population ?? 0).toLocaleString('en-IN')} residents · ${props.area_sq_km ?? '?'} km&sup2;
             </div>
             <div style="font-size:10px;color:#7590B0;margin-top:6px;">Synthetic boundary</div>
           </div>`,
        )
      }}
    />
  )
}

// ---------------------------------------------------------------------------
//  Map shell
// ---------------------------------------------------------------------------
export function MapView({
  center = CITY_CENTER,
  zoom = 12,
  className,
  children,
  onPick,
  recenter,
  scrollWheelZoom = true,
}: {
  center?: [number, number]
  zoom?: number
  className?: string
  children?: ReactNode
  onPick?: (lat: number, lon: number) => void
  recenter?: [number, number] | null
  scrollWheelZoom?: boolean
}) {
  const [offline, setOffline] = useState(false)
  const handleOffline = useCallback(() => setOffline(true), [])

  return (
    <div className={classNames('relative', className)}>
      <MapContainer
        center={center}
        zoom={zoom}
        scrollWheelZoom={scrollWheelZoom}
        className="h-full w-full rounded-xl"
        zoomControl
      >
        {!offline && <ResilientTiles onOffline={handleOffline} />}
        <SizeFix />
        <ViewSync center={recenter ?? null} />
        {onPick && <ClickToPin onPick={onPick} />}
        {children}
      </MapContainer>
      {offline && (
        <div className="absolute top-2 left-2 z-[400] rounded-lg bg-white/95 border border-ink-200 px-2.5 py-1.5 text-2xs text-ink-600 shadow-card max-w-[240px] leading-relaxed">
          <span className="font-semibold text-ink-800">Offline map.</span> Street tiles are
          unreachable, so ward outlines are shown instead. Everything else still works.
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
//  Issue markers
// ---------------------------------------------------------------------------
export function IssueMarkers({
  items,
  onSelect,
}: {
  items: MapItem[]
  onSelect?: (code: string) => void
}) {
  return (
    <>
      {items.map((item) => (
        <Marker
          key={item.issue_code}
          position={[item.lat, item.lon]}
          icon={bandIcon(item.band, item.report_count, item.sla_breached, item.ack_expired)}
          eventHandlers={onSelect ? { click: () => onSelect(item.issue_code) } : undefined}
        >
          <Popup>
            <div className="px-3 py-2.5 font-sans max-w-[240px]">
              <div className="flex items-center gap-1.5 mb-1">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ background: BAND_HEX[item.band] }}
                />
                <span className="text-2xs font-semibold text-ink-600">
                  {item.band} · {Math.round(item.score)}
                </span>
                {item.sla_breached && (
                  <span className="text-2xs font-semibold text-danger-600">SLA breached</span>
                )}
              </div>
              <p className="text-sm font-medium text-ink-900 leading-snug">{item.title}</p>
              <p className="text-2xs text-ink-500 mt-1">
                {item.issue_code} · {item.report_count} report{item.report_count === 1 ? '' : 's'}
              </p>
            </div>
          </Popup>
        </Marker>
      ))}
    </>
  )
}

export function PinMarker({ position }: { position: [number, number] }) {
  return <Marker position={position} icon={PIN_ICON} />
}

/** Fetch ward geometry once and cache it for the session. */
let wardCache: FeatureCollection | null = null
export function useWardGeometry(): FeatureCollection | null {
  const [data, setData] = useState<FeatureCollection | null>(wardCache)
  useEffect(() => {
    if (wardCache) return
    let cancelled = false
    fetch('/api/public/wards.geojson')
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (!cancelled && payload?.features?.length) {
          wardCache = payload as FeatureCollection
          setData(wardCache)
        }
      })
      .catch(() => {
        /* the map simply renders without ward outlines */
      })
    return () => {
      cancelled = true
    }
  }, [])
  return data
}
