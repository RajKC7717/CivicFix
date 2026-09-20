/**
 * The human review queue.
 *
 * This screen is the answer to "what does the system do when it is not sure?"
 * It does not guess and it does not discard. It puts the complaint here, with
 * the evidence, and waits for a person.
 *
 * Four kinds of item, each with its own resolution:
 *  - low_confidence_category : confirm the AI's guess, or correct it
 *  - duplicate_candidate     : the two reports side by side; merge or keep apart
 *  - missing_location        : drop a pin on the map
 *  - unparsed                : the AI understood nothing; classify it by hand
 *
 * Every resolution requires a written reason and is recorded in the audit log.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { MapView, PinMarker, WardBoundaries, useWardGeometry, CITY_CENTER } from '../components/MapView'
import { HazardList, PriorityBadge, SourceChip } from '../components/shared'
import { ReasonDialog, useToast } from '../components/ui/overlays'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ConfidenceMeter,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Select,
  Skeleton,
} from '../components/ui/primitives'
import { api } from '../lib/api'
import { classNames, timeAgo } from '../lib/format'
import type { Meta, ReviewItem } from '../lib/types'
import { useAdmin } from './AdminShell'

const KIND_LABELS: Record<string, string> = {
  low_confidence_category: 'Low-confidence classification',
  duplicate_candidate: 'Possible duplicate',
  missing_location: 'Location not resolved',
  unparsed: 'AI could not parse',
}

const KIND_HELP: Record<string, string> = {
  low_confidence_category:
    'The classifier and the keyword rules did not agree, or the evidence was thin. Confirm or correct.',
  duplicate_candidate:
    'Similar enough to be worth a look, not similar enough to merge automatically. Compare and decide.',
  missing_location:
    'No GPS, no usable landmark. Read the complaint and drop a pin so it can be routed and mapped.',
  unparsed: 'No civic keyword matched at all. Read it and classify it by hand.',
}

type Pending =
  | { kind: 'confirm' | 'keep_separate' | 'merge'; task: ReviewItem }
  | { kind: 'recategorise'; task: ReviewItem; category: string }
  | { kind: 'set_location'; task: ReviewItem; lat: number; lon: number; text: string }
  | null

export default function Review() {
  const toast = useToast()
  const { refreshReviewCount } = useAdmin()
  const wards = useWardGeometry()

  const [items, setItems] = useState<ReviewItem[] | null>(null)
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [filter, setFilter] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<Pending>(null)
  const [pins, setPins] = useState<Record<number, [number, number]>>({})
  const [locationText, setLocationText] = useState<Record<number, string>>({})
  const [categoryChoice, setCategoryChoice] = useState<Record<number, string>>({})

  const load = useCallback(() => {
    setError(null)
    api
      .reviewQueue({ status: 'open', kind: filter || undefined, limit: 60 })
      .then((payload) => {
        setItems(payload.items)
        setCounts(payload.open_counts)
      })
      .catch((caught) => {
        setItems([])
        setError(caught instanceof Error ? caught.message : 'Could not load the review queue')
      })
  }, [filter])

  useEffect(() => {
    setItems(null)
    load()
    api.meta().then(setMeta).catch(() => undefined)
  }, [load])

  async function resolve(reason: string) {
    if (!pending) return
    const { task } = pending
    setBusy(true)
    try {
      const body: Parameters<typeof api.resolveReview>[1] = { action: pending.kind, reason }
      if (pending.kind === 'recategorise') body.category = pending.category
      if (pending.kind === 'set_location') {
        body.lat = pending.lat
        body.lon = pending.lon
        body.location_text = pending.text || undefined
      }
      await api.resolveReview(task.id, body)
      toast.push('Recorded. The decision is in the audit log.', 'success')
      setPending(null)
      load()
      refreshReviewCount()
    } catch (caught) {
      toast.push(caught instanceof Error ? caught.message : 'Could not save', 'error')
    } finally {
      setBusy(false)
    }
  }

  const totalOpen = Object.values(counts).reduce((sum, value) => sum + value, 0)

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div>
        <h1 className="text-xl font-bold text-ink-900">Human review</h1>
        <p className="text-sm text-ink-500 mt-0.5 max-w-3xl leading-relaxed">
          Nothing here was rejected by the AI. These are the complaints it deliberately refused to
          decide alone — because it was unsure, because two reports might be the same, or because it
          could not find the place. Your decision is final and is recorded with your reason.
        </p>
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setFilter('')}
          className={classNames(
            'px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors',
            filter === ''
              ? 'bg-ink-900 text-white border-ink-900'
              : 'bg-white text-ink-700 border-ink-200 hover:bg-ink-50',
          )}
        >
          All open ({totalOpen})
        </button>
        {Object.entries(KIND_LABELS).map(([kind, label]) => (
          <button
            key={kind}
            onClick={() => setFilter(kind)}
            className={classNames(
              'px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors',
              filter === kind
                ? 'bg-ink-900 text-white border-ink-900'
                : 'bg-white text-ink-700 border-ink-200 hover:bg-ink-50',
            )}
          >
            {label} ({counts[kind] ?? 0})
          </button>
        ))}
      </div>

      {items === null && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-40 rounded-xl" />
          ))}
        </div>
      )}

      {error && (
        <Card>
          <ErrorState message={error} onRetry={load} />
        </Card>
      )}

      {items?.length === 0 && !error && (
        <Card>
          <EmptyState
            title="Nothing waiting for a human"
            body="Every complaint the AI was unsure about has been reviewed. New ones will appear here automatically."
          />
        </Card>
      )}

      <div className="space-y-4">
        {items?.map((task) => {
          const report = task.report
          const pin = pins[task.id] ?? (report?.location.lat != null ? ([report.location.lat, report.location.lon] as [number, number]) : null)

          return (
            <Card key={task.id}>
              <CardHeader
                title={
                  <span className="flex items-center gap-2 flex-wrap">
                    <Badge tone="warn">{KIND_LABELS[task.kind] ?? task.kind}</Badge>
                    {report && (
                      <code className="font-mono text-xs text-ink-500">{report.ticket_code}</code>
                    )}
                    <span className="text-2xs text-ink-400 font-normal">
                      {timeAgo(task.created_at)}
                    </span>
                  </span>
                }
                subtitle={KIND_HELP[task.kind]}
              />

              <div className="p-4 space-y-4">
                {/* The complaint itself */}
                {report && (
                  <div className="rounded-lg bg-ink-50 border border-ink-100 p-3">
                    <div className="flex items-center gap-2 flex-wrap mb-2">
                      <Badge tone="neutral">{report.language.label}</Badge>
                      <Badge tone="brand">{report.category.label}</Badge>
                      <SourceChip source={report.ai.source} model={report.ai.model} />
                    </div>
                    <p className="text-sm text-ink-900 leading-relaxed">{report.text}</p>
                    {report.summary_en && (
                      <p className="text-xs text-ink-500 mt-1.5 italic">→ {report.summary_en}</p>
                    )}
                    <div className="mt-2.5 flex flex-wrap items-center gap-3">
                      <div className="w-40">
                        <ConfidenceMeter value={report.ai.confidence} />
                      </div>
                      <HazardList hazards={report.hazard_flags} />
                    </div>
                    <p className="text-2xs text-ink-500 mt-2 leading-relaxed">
                      {report.ai.explanation}
                    </p>
                  </div>
                )}

                {/* ---- duplicate candidate ---- */}
                {task.kind === 'duplicate_candidate' && task.candidate_issue && (
                  <div className="grid sm:grid-cols-2 gap-3">
                    <div className="rounded-lg border border-ink-200 p-3">
                      <p className="text-2xs uppercase tracking-wide text-ink-500 font-semibold mb-1.5">
                        This new report
                      </p>
                      <p className="text-sm text-ink-900">{report?.summary_en || report?.text}</p>
                    </div>
                    <div className="rounded-lg border border-brand-200 bg-brand-50/40 p-3">
                      <p className="text-2xs uppercase tracking-wide text-brand-700 font-semibold mb-1.5">
                        Existing issue {task.candidate_issue.issue_code}
                      </p>
                      <p className="text-sm text-ink-900">{task.candidate_issue.title}</p>
                      <div className="flex items-center gap-2 mt-2 flex-wrap">
                        <PriorityBadge
                          band={task.candidate_issue.priority.band}
                          score={task.candidate_issue.priority.score}
                          size="sm"
                        />
                        <Badge tone="neutral">
                          {task.candidate_issue.report_count} reports
                        </Badge>
                        <Link
                          to={`/admin/issues/${task.candidate_issue.issue_code}`}
                          className="text-xs text-brand-600 hover:underline"
                        >
                          open →
                        </Link>
                      </div>
                    </div>
                    <p className="sm:col-span-2 text-xs text-ink-600">
                      {String(task.payload.explanation ?? '')}
                    </p>
                  </div>
                )}

                {/* ---- missing location ---- */}
                {task.kind === 'missing_location' && (
                  <div>
                    <p className="text-xs text-ink-600 mb-2">
                      Tap the map to place this complaint.{' '}
                      {pin && (
                        <span className="font-mono text-ink-800">
                          {pin[0].toFixed(5)}, {pin[1].toFixed(5)}
                        </span>
                      )}
                    </p>
                    <MapView
                      className="h-64"
                      center={pin ?? CITY_CENTER}
                      zoom={pin ? 15 : 11}
                      onPick={(lat, lon) => setPins((current) => ({ ...current, [task.id]: [lat, lon] }))}
                    >
                      {wards && <WardBoundaries data={wards} showLabels />}
                      {pin && <PinMarker position={pin} />}
                    </MapView>
                    <div className="mt-3">
                      <Field label="Location description (optional)">
                        <Input
                          value={locationText[task.id] ?? ''}
                          onChange={(event) =>
                            setLocationText((current) => ({
                              ...current,
                              [task.id]: event.target.value,
                            }))
                          }
                          placeholder="e.g. Lane 3, opposite Katraj dairy"
                        />
                      </Field>
                    </div>
                  </div>
                )}

                {/* ---- category choice ---- */}
                {(task.kind === 'low_confidence_category' || task.kind === 'unparsed') && (
                  <Field
                    label="Correct category"
                    hint="Leave as-is and press Confirm if the AI was right."
                  >
                    <Select
                      value={categoryChoice[task.id] ?? report?.category.key ?? ''}
                      onChange={(event) =>
                        setCategoryChoice((current) => ({
                          ...current,
                          [task.id]: event.target.value,
                        }))
                      }
                    >
                      {meta?.categories.map((category) => (
                        <option key={category.key} value={category.key}>
                          {category.label}
                        </option>
                      ))}
                    </Select>
                  </Field>
                )}

                {/* ---- actions ---- */}
                <div className="flex flex-wrap gap-2 pt-1">
                  {task.kind === 'duplicate_candidate' ? (
                    <>
                      <Button size="sm" onClick={() => setPending({ kind: 'merge', task })}>
                        Yes — same issue, merge
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setPending({ kind: 'keep_separate', task })}
                      >
                        No — keep separate
                      </Button>
                    </>
                  ) : task.kind === 'missing_location' ? (
                    <Button
                      size="sm"
                      disabled={!pin}
                      onClick={() =>
                        pin &&
                        setPending({
                          kind: 'set_location',
                          task,
                          lat: pin[0],
                          lon: pin[1],
                          text: locationText[task.id] ?? '',
                        })
                      }
                    >
                      Save this pin
                    </Button>
                  ) : (
                    <>
                      <Button size="sm" onClick={() => setPending({ kind: 'confirm', task })}>
                        Confirm the AI
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          setPending({
                            kind: 'recategorise',
                            task,
                            category: categoryChoice[task.id] ?? report?.category.key ?? 'other',
                          })
                        }
                      >
                        Correct the category
                      </Button>
                    </>
                  )}
                  {task.issue_id && (
                    <Link to={`/admin/issues/${task.issue_id}`} className="ml-auto">
                      <Button size="sm" variant="ghost">
                        Open issue →
                      </Button>
                    </Link>
                  )}
                </div>
              </div>
            </Card>
          )
        })}
      </div>

      <ReasonDialog
        open={pending !== null}
        title={
          pending?.kind === 'merge'
            ? 'Merge these reports'
            : pending?.kind === 'keep_separate'
              ? 'Keep these separate'
              : pending?.kind === 'set_location'
                ? 'Set the location'
                : pending?.kind === 'recategorise'
                  ? 'Correct the category'
                  : 'Confirm the classification'
        }
        description="Your name, the time and this reason are written to the audit log."
        confirmLabel="Save and record"
        busy={busy}
        onCancel={() => setPending(null)}
        onConfirm={resolve}
      />
    </div>
  )
}
