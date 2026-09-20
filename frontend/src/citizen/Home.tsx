/** Citizen landing page: the pitch, the live numbers, and two clear actions. */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { IssueMarkers, MapView, WardBoundaries, useWardGeometry } from '../components/MapView'
import { Button, Card, Skeleton } from '../components/ui/primitives'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { formatHours } from '../lib/format'
import type { MapItem, PublicStats } from '../lib/types'

function Stat({ value, label, loading }: { value: string; label: string; loading: boolean }) {
  return (
    <div className="text-center px-2">
      {loading ? (
        <Skeleton className="h-8 w-16 mx-auto" />
      ) : (
        <p className="text-2xl sm:text-3xl font-bold text-white tabular-nums leading-none">{value}</p>
      )}
      <p className="text-2xs sm:text-xs text-white/60 mt-1.5 leading-tight">{label}</p>
    </div>
  )
}

const STEP_ICONS = [
  <svg key="1" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>,
  <svg key="2" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" strokeLinecap="round" strokeLinejoin="round" />
  </svg>,
  <svg key="3" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M12 22s8-4.5 8-11a8 8 0 1 0-16 0c0 6.5 8 11 8 11z" strokeLinejoin="round" />
    <circle cx="12" cy="11" r="3" />
  </svg>,
]

export default function Home() {
  const { t } = useI18n()
  const [stats, setStats] = useState<PublicStats | null>(null)
  const [items, setItems] = useState<MapItem[]>([])
  const wards = useWardGeometry()

  useEffect(() => {
    api.stats().then(setStats).catch(() => setStats(null))
    api
      .publicMap({})
      .then((payload) => setItems(payload.items.slice(0, 160)))
      .catch(() => setItems([]))
  }, [])

  const loading = stats === null

  const steps = [
    { title: t('home_how_1_title'), body: t('home_how_1_body') },
    { title: t('home_how_2_title'), body: t('home_how_2_body') },
    { title: t('home_how_3_title'), body: t('home_how_3_body') },
  ]

  return (
    <div>
      {/* Hero */}
      <section className="bg-ink-900 text-white">
        <div className="mx-auto max-w-5xl px-4 pt-10 pb-8">
          <div className="max-w-2xl">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-500/15 text-accent-200 px-3 py-1 text-xs font-medium border border-accent-400/25">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-400" />
              {t('challenge')} · SDG 11 + 16
            </span>
            <h1 className="text-3xl sm:text-4xl font-bold mt-4 leading-tight tracking-tight">
              {t('home_title')}
            </h1>
            <p className="text-white/70 mt-3 leading-relaxed text-sm sm:text-base">
              {t('home_subtitle')}
            </p>
            <div className="flex flex-wrap gap-3 mt-6">
              <Link to="/report">
                <Button size="lg" variant="accent">
                  {t('home_cta')}
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </Button>
              </Link>
              <Link to="/track">
                <Button
                  size="lg"
                  variant="secondary"
                  className="bg-white/10 border-white/20 text-white hover:bg-white/20"
                >
                  {t('home_track_cta')}
                </Button>
              </Link>
            </div>
          </div>

          <div className="grid grid-cols-4 gap-2 mt-9 pt-6 border-t border-white/10">
            <Stat loading={loading} value={String(stats?.total_issues ?? 0)} label={t('home_stat_issues')} />
            <Stat loading={loading} value={String(stats?.resolved_issues ?? 0)} label={t('home_stat_resolved')} />
            <Stat loading={loading} value={String(stats?.distinct_citizens ?? 0)} label={t('home_stat_citizens')} />
            <Stat
              loading={loading}
              value={stats?.median_resolution_hours ? formatHours(stats.median_resolution_hours) : '-'}
              label={t('home_stat_median')}
            />
          </div>
        </div>
      </section>

      {/* One issue, many voices */}
      {stats && stats.reports_collapsed > 0 && (
        <section className="mx-auto max-w-5xl px-4 -mt-5">
          <div className="rounded-xl bg-white border border-success-100 shadow-card px-4 py-3.5 flex items-start gap-3">
            <span className="mt-0.5 h-8 w-8 rounded-lg bg-success-50 text-success-700 flex items-center justify-center shrink-0">
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <p className="text-sm text-ink-700 leading-relaxed">
              <strong className="text-ink-900">One issue, many voices.</strong>{' '}
              {stats.total_reports} citizen reports have been grouped into {stats.total_issues} real
              issues — <strong className="text-success-700">{stats.triage_work_saved_pct}% less</strong>{' '}
              manual triage, and no citizen was ever told their report was a duplicate.
            </p>
          </div>
        </section>
      )}

      {/* How it works */}
      <section className="mx-auto max-w-5xl px-4 py-10">
        <h2 className="text-lg font-semibold text-ink-900 mb-4">{t('home_how_title')}</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {steps.map((step, index) => (
            <Card key={step.title} className="p-4">
              <span className="h-9 w-9 rounded-lg bg-brand-50 text-brand-700 flex items-center justify-center mb-3">
                {STEP_ICONS[index]}
              </span>
              <p className="font-semibold text-ink-900 text-sm">{step.title}</p>
              <p className="text-sm text-ink-600 mt-1.5 leading-relaxed">{step.body}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* Live map */}
      <section className="mx-auto max-w-5xl px-4 pb-4">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-lg font-semibold text-ink-900">{t('home_recent')}</h2>
          <Link to="/map" className="text-sm text-brand-600 hover:text-brand-700 font-medium">
            {t('nav_map')} →
          </Link>
        </div>
        <Card className="overflow-hidden p-1">
          <MapView className="h-[340px] sm:h-[420px]" zoom={11} scrollWheelZoom={false}>
            {wards && <WardBoundaries data={wards} />}
            <IssueMarkers items={items} />
          </MapView>
        </Card>
        <p className="text-2xs text-ink-500 mt-2 leading-relaxed">
          Each circle is an issue, coloured by priority; a number means several people reported the
          same problem. Ward outlines are synthetic. Map data © OpenStreetMap contributors.
        </p>
      </section>
    </div>
  )
}
