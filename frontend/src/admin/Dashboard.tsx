/**
 * The officer's main screen: a filterable priority queue beside a cluster map.
 *
 * The queue is the product. Everything else on this screen exists to let an
 * officer decide what to do next: the band colour, the voice count, the SLA
 * clock and the review flag are all visible without opening anything.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { IssueMarkers, MapView, WardBoundaries, useWardGeometry } from '../components/MapView'
import { IssueRow, StatCard } from '../components/shared'
import { useToast } from '../components/ui/overlays'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Select,
  Skeleton,
} from '../components/ui/primitives'
import { api } from '../lib/api'
import { classNames } from '../lib/format'
import type { IssueSummary, MapItem, Meta, PublicStats, WardListItem } from '../lib/types'
import { useAdmin } from './AdminShell'

type SortKey = 'priority' | 'newest' | 'oldest' | 'reports' | 'sla'

const SORTS: { key: SortKey; label: string }[] = [
  { key: 'priority', label: 'Priority' },
  { key: 'sla', label: 'SLA deadline' },
  { key: 'reports', label: 'Most reported' },
  { key: 'newest', label: 'Newest' },
  { key: 'oldest', label: 'Oldest' },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const toast = useToast()
  const { demoMode, refreshReviewCount } = useAdmin()
  const wards = useWardGeometry()

  const [meta, setMeta] = useState<Meta | null>(null)
  const [wardList, setWardList] = useState<WardListItem[]>([])
  const [stats, setStats] = useState<PublicStats | null>(null)
  const [issues, setIssues] = useState<IssueSummary[] | null>(null)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)
  const [view, setView] = useState<'list' | 'map'>('list')

  const [filters, setFilters] = useState({
    category: '',
    ward: '',
    status: '',
    band: '',
    breached: '',
    needs_review: '',
    sort: 'priority' as SortKey,
  })

  useEffect(() => {
    api.meta().then(setMeta).catch(() => undefined)
    api.wards().then((payload) => setWardList(payload.items)).catch(() => undefined)
  }, [])

  const load = useCallback(() => {
    setError(null)
    api
      .stats()
      .then(setStats)
      .catch(() => undefined)
    api
      .issues({
        ...filters,
        breached: filters.breached === '' ? undefined : filters.breached === 'true',
        needs_review: filters.needs_review === 'true' ? true : undefined,
        limit: 120,
      })
      .then((payload) => {
        setIssues(payload.items)
        setTotal(payload.total)
      })
      .catch((caught) => {
        setIssues([])
        setError(caught instanceof Error ? caught.message : 'Could not load the queue')
      })
  }, [filters])

  useEffect(() => {
    setIssues(null)
    load()
  }, [load])

  const mapItems = useMemo<MapItem[]>(
    () =>
      (issues ?? [])
        .filter((issue) => issue.lat != null && issue.lon != null)
        .map((issue) => ({
          issue_code: issue.issue_code,
          title: issue.title,
          category: issue.category.key,
          status: issue.status,
          lat: issue.lat as number,
          lon: issue.lon as number,
          band: issue.priority.band,
          score: issue.priority.score,
          report_count: issue.report_count,
          sla_breached: issue.sla.breached,
        })),
    [issues],
  )

  async function resetDemo() {
    if (!window.confirm('Rebuild the demo dataset from scratch? This deletes all current complaints.')) {
      return
    }
    setResetting(true)
    try {
      const summary = await api.demoReset()
      toast.push(
        `Demo reset: ${summary.reports} reports collapsed into ${summary.issues} issues.`,
        'success',
      )
      load()
      refreshReviewCount()
    } catch (caught) {
      toast.push(caught instanceof Error ? caught.message : 'Reset failed', 'error')
    } finally {
      setResetting(false)
    }
  }

  const activeFilters = Object.entries(filters).filter(
    ([key, value]) => key !== 'sort' && value !== '',
  ).length

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink-900">Priority queue</h1>
          <p className="text-sm text-ink-500 mt-0.5">
            {issues === null ? 'Loading…' : `${total} open issues, ranked by a published formula`}
          </p>
        </div>
        <div className="flex gap-2">
          {demoMode && (
            <Button size="sm" variant="secondary" onClick={resetDemo} loading={resetting}>
              Reset demo data
            </Button>
          )}
          <Button size="sm" variant="secondary" onClick={load}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Counters */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Open issues"
          value={stats ? stats.open_issues : '—'}
          sub={stats ? `${stats.resolved_issues} resolved` : undefined}
        />
        <StatCard
          label="Critical (P1)"
          value={stats?.by_band?.P1 ?? 0}
          tone="danger"
          sub="Act today"
        />
        <StatCard
          label="Reports collapsed"
          value={stats ? stats.reports_collapsed : '—'}
          tone="success"
          sub={stats ? `${stats.triage_work_saved_pct}% less triage work` : undefined}
        />
        <StatCard
          label="Citizens reporting"
          value={stats ? stats.distinct_citizens : '—'}
          sub={stats ? `${stats.total_reports} reports` : undefined}
        />
      </div>

      {/* Filters */}
      <Card className="p-3">
        <div className="flex flex-wrap gap-2 items-center">
          <Select
            value={filters.category}
            onChange={(event) => setFilters((f) => ({ ...f, category: event.target.value }))}
            className="w-auto text-sm py-1.5"
            aria-label="Category"
          >
            <option value="">All categories</option>
            {meta?.categories.map((category) => (
              <option key={category.key} value={category.key}>
                {category.label}
              </option>
            ))}
          </Select>
          <Select
            value={filters.ward}
            onChange={(event) => setFilters((f) => ({ ...f, ward: event.target.value }))}
            className="w-auto text-sm py-1.5"
            aria-label="Ward"
          >
            <option value="">All wards</option>
            {wardList.map((ward) => (
              <option key={ward.code} value={ward.code}>
                {ward.name} ({ward.open_issues})
              </option>
            ))}
          </Select>
          <Select
            value={filters.status}
            onChange={(event) => setFilters((f) => ({ ...f, status: event.target.value }))}
            className="w-auto text-sm py-1.5"
            aria-label="Status"
          >
            <option value="">Open only</option>
            {meta?.statuses.map((status) => (
              <option key={status.key} value={status.key}>
                {status.label}
              </option>
            ))}
          </Select>
          <Select
            value={filters.band}
            onChange={(event) => setFilters((f) => ({ ...f, band: event.target.value }))}
            className="w-auto text-sm py-1.5"
            aria-label="Priority band"
          >
            <option value="">All bands</option>
            <option value="P1">P1 Critical</option>
            <option value="P2">P2 High</option>
            <option value="P3">P3 Medium</option>
            <option value="P4">P4 Low</option>
          </Select>
          <Select
            value={filters.breached}
            onChange={(event) => setFilters((f) => ({ ...f, breached: event.target.value }))}
            className="w-auto text-sm py-1.5"
            aria-label="SLA"
          >
            <option value="">Any SLA state</option>
            <option value="true">Breached only</option>
            <option value="false">Within SLA</option>
          </Select>
          <Select
            value={filters.needs_review}
            onChange={(event) => setFilters((f) => ({ ...f, needs_review: event.target.value }))}
            className="w-auto text-sm py-1.5"
            aria-label="Review"
          >
            <option value="">Any review state</option>
            <option value="true">Needs human review</option>
          </Select>

          <div className="flex items-center gap-2">
            {activeFilters > 0 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  setFilters({
                    category: '',
                    ward: '',
                    status: '',
                    band: '',
                    breached: '',
                    needs_review: '',
                    sort: filters.sort,
                  })
                }
              >
                Clear {activeFilters}
              </Button>
            )}
            <Select
              value={filters.sort}
              onChange={(event) =>
                setFilters((f) => ({ ...f, sort: event.target.value as SortKey }))
              }
              className="w-auto text-sm py-1.5"
              aria-label="Sort"
            >
              {SORTS.map((sort) => (
                <option key={sort.key} value={sort.key}>
                  Sort: {sort.label}
                </option>
              ))}
            </Select>
          </div>
        </div>
      </Card>

      {/* Mobile view switch */}
      <div className="flex gap-1 xl:hidden">
        {(['list', 'map'] as const).map((option) => (
          <button
            key={option}
            onClick={() => setView(option)}
            className={classNames(
              'px-3 py-1.5 rounded-lg text-sm font-medium capitalize transition-colors',
              view === option ? 'bg-ink-900 text-white' : 'bg-white text-ink-600 border border-ink-200',
            )}
          >
            {option}
          </button>
        ))}
      </div>

      <div className="grid xl:grid-cols-2 gap-4">
        {/* Queue */}
        <Card className={classNames('overflow-hidden', view === 'map' && 'hidden xl:block')}>
          <div className="px-4 py-2.5 border-b border-ink-100 flex items-center justify-between">
            <span className="text-sm font-semibold text-ink-800">
              {issues === null ? '—' : `${issues.length} of ${total} shown`}
            </span>
            <div className="flex gap-1">
              {(['P1', 'P2', 'P3', 'P4'] as const).map((band) => {
                const count = (issues ?? []).filter((i) => i.priority.band === band).length
                return count ? (
                  <Badge key={band} tone="neutral" className="tabular-nums">
                    {band} {count}
                  </Badge>
                ) : null
              })}
            </div>
          </div>
          <div className="divide-y divide-ink-100 max-h-[640px] overflow-y-auto nn-scroll">
            {issues === null && (
              <div className="p-4 space-y-3">
                {Array.from({ length: 7 }).map((_, index) => (
                  <Skeleton key={index} className="h-14" />
                ))}
              </div>
            )}
            {error && <ErrorState message={error} onRetry={load} />}
            {issues?.length === 0 && !error && (
              <EmptyState
                title="Nothing matches those filters"
                body="Try clearing a filter, or switch the status to see resolved issues."
              />
            )}
            {issues?.map((issue) => (
              <IssueRow key={issue.id} issue={issue} to={`/admin/issues/${issue.issue_code}`} />
            ))}
          </div>
        </Card>

        {/* Map */}
        <Card className={classNames('p-1 overflow-hidden', view === 'list' && 'hidden xl:block')}>
          <MapView className="h-[400px] xl:h-[688px]" zoom={11}>
            {wards && <WardBoundaries data={wards} />}
            <IssueMarkers
              items={mapItems}
              onSelect={(code) => navigate(`/admin/issues/${code}`)}
            />
          </MapView>
        </Card>
      </div>
    </div>
  )
}
