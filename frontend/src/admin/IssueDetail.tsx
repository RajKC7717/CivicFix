/**
 * One issue, in full: every citizen voice attached to it, the arithmetic behind
 * its priority, the trace of what each AI stage produced, and every human
 * decision made about it.
 *
 * All four officer overrides live here - category, priority band, status and
 * routing - and the three that contradict the AI go through ReasonDialog, which
 * cannot be submitted without a written explanation.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { MapView, PinMarker, WardBoundaries, useWardGeometry } from '../components/MapView'
import {
  HazardList,
  PriorityBadge,
  ScoreBreakdown,
  SourceChip,
  StatusPill,
  Timeline,
} from '../components/shared'
import { ReasonDialog, useToast } from '../components/ui/overlays'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  ConfidenceMeter,
  ErrorState,
  Field,
  Input,
  Select,
  Skeleton,
} from '../components/ui/primitives'
import { api } from '../lib/api'
import { classNames, formatDateTime, slaLabel, timeAgo } from '../lib/format'
import type { IssueDetailResponse, Meta, StageLog } from '../lib/types'
import { useAdmin } from './AdminShell'

const STAGE_TONE: Record<StageLog['status'], string> = {
  ok: 'bg-success-50 text-success-700 border-success-100',
  fallback: 'bg-warn-50 text-warn-600 border-warn-100',
  error: 'bg-danger-50 text-danger-700 border-danger-100',
  skipped: 'bg-ink-100 text-ink-500 border-ink-200',
}

type DialogKind = 'category' | 'priority' | 'merge' | 'unmerge' | null

export default function IssueDetail() {
  const { code = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { refreshReviewCount } = useAdmin()
  const wards = useWardGeometry()

  const [data, setData] = useState<IssueDetailResponse | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [dialog, setDialog] = useState<DialogKind>(null)
  const [pendingCategory, setPendingCategory] = useState('')
  const [pendingBand, setPendingBand] = useState('')
  const [mergeTarget, setMergeTarget] = useState('')
  const [unmergeReportId, setUnmergeReportId] = useState<number | null>(null)
  const [showTrace, setShowTrace] = useState(false)

  const load = useCallback(() => {
    setError(null)
    api
      .issue(code)
      .then(setData)
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Could not load'))
  }, [code])

  useEffect(() => {
    setData(null)
    load()
    api.meta().then(setMeta).catch(() => undefined)
  }, [load])

  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true)
    try {
      await action()
      toast.push(message, 'success')
      setDialog(null)
      load()
      refreshReviewCount()
    } catch (caught) {
      toast.push(caught instanceof Error ? caught.message : 'Action failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  if (error) {
    return (
      <div className="p-6">
        <Card>
          <ErrorState message={error} onRetry={load} />
        </Card>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-24 rounded-xl" />
        <div className="grid lg:grid-cols-3 gap-4">
          <Skeleton className="h-72 rounded-xl lg:col-span-2" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
      </div>
    )
  }

  const { issue } = data
  const nextStatus = meta?.statuses.filter((status) => status.key !== issue.status) ?? []

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <button
        onClick={() => navigate('/admin')}
        className="text-sm text-ink-500 hover:text-ink-800 inline-flex items-center gap-1"
      >
        ← Back to queue
      </button>

      {/* Header */}
      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <code className="font-mono text-xs text-ink-500">{issue.issue_code}</code>
              <StatusPill status={issue.status} label={issue.status_label} />
              <PriorityBadge
                band={issue.priority.band}
                score={issue.priority.score}
                overridden={issue.priority.overridden}
              />
              {issue.report_count > 1 && (
                <Badge tone="success">{issue.report_count} citizen voices</Badge>
              )}
              {issue.priority.equity_boost_applied && (
                <Badge tone="accent">equity boost applied</Badge>
              )}
            </div>
            <h1 className="text-xl font-bold text-ink-900 mt-2 leading-snug">{issue.title}</h1>
            <p className="text-sm text-ink-500 mt-1">
              {issue.category.label}
              {issue.ward && ` · ${issue.ward.name} (${issue.ward.code})`}
              {issue.location_text && ` · ${issue.location_text}`}
            </p>
            <div className="flex flex-wrap gap-3 mt-3 text-xs">
              <span className="text-ink-500">Created {timeAgo(issue.created_at)}</span>
              <span className={issue.sla.breached ? 'text-danger-600 font-semibold' : 'text-ink-500'}>
                SLA {issue.sla.hours} h · {slaLabel(issue.sla.deadline, issue.sla.breached)}
              </span>
              <span className="text-ink-500 capitalize">Dept: {issue.department}</span>
              {issue.assigned_to && <span className="text-ink-500">Assigned: {issue.assigned_to}</span>}
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-2 w-full sm:w-auto">
            <div className="flex gap-2">
              <Select
                value=""
                onChange={(event) => {
                  const status = event.target.value
                  if (!status) return
                  void run(
                    () => api.changeStatus(issue.issue_code, { status, note: '' }),
                    `Status changed to ${status.replace('_', ' ')}`,
                  )
                }}
                className="text-sm py-1.5 w-auto"
                aria-label="Change status"
              >
                <option value="">Change status…</option>
                {nextStatus.map((status) => (
                  <option key={status.key} value={status.key}>
                    {status.label}
                  </option>
                ))}
              </Select>
              <Select
                value=""
                onChange={(event) => {
                  const department = event.target.value
                  if (!department) return
                  void run(
                    () =>
                      api.assign(issue.issue_code, {
                        department,
                        assigned_to: '',
                        note: `Routed to ${department}`,
                      }),
                    'Work order routed',
                  )
                }}
                className="text-sm py-1.5 w-auto"
                aria-label="Assign department"
              >
                <option value="">Route to…</option>
                {meta?.departments.map((department) => (
                  <option key={department.code} value={department.code}>
                    {department.short}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setPendingCategory(issue.category.key)
                  setDialog('category')
                }}
              >
                Override category
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setPendingBand(issue.priority.band)
                  setDialog('priority')
                }}
              >
                Pin priority
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setDialog('merge')}>
                Merge into…
              </Button>
            </div>
          </div>
        </div>

        {issue.priority.overridden && data.priority_override_reason && (
          <Alert tone="warn" title={`Priority pinned to ${issue.priority.band} by an officer`}>
            <p className="text-xs">{data.priority_override_reason}</p>
          </Alert>
        )}
        {data.merged_into && (
          <Alert tone="info" title="This issue was merged">
            It is now part of{' '}
            <Link className="underline font-medium" to={`/admin/issues/${data.merged_into}`}>
              {data.merged_into}
            </Link>
            .
          </Alert>
        )}
      </Card>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          {/* Citizen voices */}
          <Card>
            <CardHeader
              title={`Citizen reports (${data.reports.length})`}
              subtitle="Every report is kept and stays addressable by its own ticket. Merging only links them."
            />
            <div className="divide-y divide-ink-100">
              {data.reports.map((report) => (
                <div key={report.id} className="p-4">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2 flex-wrap">
                      <code className="font-mono text-xs text-ink-500">{report.ticket_code}</code>
                      <Badge tone="neutral">{report.language.label}</Badge>
                      <Badge tone="neutral">{report.channel}</Badge>
                      <SourceChip source={report.ai.source} model={report.ai.model} />
                      {report.needs_review && <Badge tone="warn">needs review</Badge>}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-2xs text-ink-400">{timeAgo(report.created_at)}</span>
                      {data.reports.length > 1 && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setUnmergeReportId(report.id)
                            setDialog('unmerge')
                          }}
                        >
                          Split out
                        </Button>
                      )}
                    </div>
                  </div>

                  <p className="text-sm text-ink-800 mt-2 leading-relaxed">{report.text}</p>
                  {report.summary_en && report.summary_en !== report.text && (
                    <p className="text-xs text-ink-500 mt-1 italic">
                      Normalised: {report.summary_en}
                    </p>
                  )}

                  <div className="flex flex-wrap items-center gap-2 mt-2.5">
                    <HazardList hazards={report.hazard_flags} />
                    {report.dedup.decision === 'merge' && (
                      <Badge tone="brand">
                        auto-merged · {((report.dedup.score ?? 0) * 100).toFixed(0)}% match
                      </Badge>
                    )}
                    {report.location.source && (
                      <Badge tone="neutral">located via {report.location.source}</Badge>
                    )}
                  </div>

                  {report.redaction?.notice && (
                    <p className="text-2xs text-success-700 mt-2">{report.redaction.notice}</p>
                  )}
                  <div className="mt-2.5 max-w-xs">
                    <ConfidenceMeter value={report.ai.confidence} />
                  </div>
                  <p className="text-2xs text-ink-500 mt-1.5 leading-relaxed">
                    {report.ai.explanation}
                  </p>
                  {report.image_url && (
                    <img
                      src={report.image_url}
                      alt=""
                      className="mt-3 h-32 rounded-lg object-cover border border-ink-200"
                    />
                  )}
                </div>
              ))}
            </div>
          </Card>

          {/* Pipeline trace */}
          <Card>
            <CardHeader
              title="How the AI got here"
              subtitle="Every stage logs its output, its confidence, which implementation answered, and how long it took."
              action={
                <Button size="sm" variant="ghost" onClick={() => setShowTrace((v) => !v)}>
                  {showTrace ? 'Hide detail' : 'Show detail'}
                </Button>
              }
            />
            <div className="p-4">
              <div className="flex flex-wrap gap-1.5">
                {data.stage_logs.map((log, index) => (
                  <span
                    key={`${log.stage}-${index}`}
                    className={classNames(
                      'text-2xs rounded-md border px-2 py-1 font-medium',
                      STAGE_TONE[log.status],
                    )}
                    title={log.message}
                  >
                    {log.stage} · {log.duration_ms}ms
                  </span>
                ))}
              </div>
              {showTrace && (
                <div className="mt-4 space-y-2 max-h-96 overflow-y-auto nn-scroll">
                  {data.stage_logs.map((log, index) => (
                    <div
                      key={`detail-${log.stage}-${index}`}
                      className="rounded-lg border border-ink-100 p-3"
                    >
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <span className="font-medium text-sm text-ink-900">{log.stage}</span>
                        <div className="flex items-center gap-2">
                          {log.source && <Badge tone="neutral">{log.source}</Badge>}
                          {log.confidence !== null && (
                            <Badge tone="brand">{(log.confidence * 100).toFixed(0)}%</Badge>
                          )}
                          <span className="text-2xs text-ink-400">{log.duration_ms} ms</span>
                        </div>
                      </div>
                      {log.message && (
                        <p className="text-xs text-ink-600 mt-1.5 leading-relaxed">{log.message}</p>
                      )}
                      <pre className="text-2xs text-ink-500 mt-2 bg-ink-50 rounded p-2 overflow-x-auto nn-scroll">
                        {JSON.stringify(log.output, null, 1)}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>

          {/* Audit */}
          <Card>
            <CardHeader
              title={`Audit trail (${data.audit.length})`}
              subtitle="Append-only. Every human override with its written reason."
            />
            {data.audit.length === 0 ? (
              <p className="px-4 py-6 text-sm text-ink-500 text-center">
                No human has overridden anything on this issue yet.
              </p>
            ) : (
              <ul className="divide-y divide-ink-100">
                {data.audit.map((entry) => (
                  <li key={entry.id} className="px-4 py-3">
                    <div className="flex items-baseline justify-between gap-2 flex-wrap">
                      <span className="text-sm font-medium text-ink-900">
                        {entry.actor}{' '}
                        <span className="font-normal text-ink-500">
                          {entry.action.replace(/_/g, ' ')}
                        </span>
                      </span>
                      <span className="text-2xs text-ink-400">
                        {formatDateTime(entry.created_at)}
                      </span>
                    </div>
                    <p className="text-xs text-ink-700 mt-1 leading-relaxed">“{entry.reason}”</p>
                    {entry.before && entry.after && (
                      <p className="text-2xs text-ink-500 mt-1 font-mono">
                        {JSON.stringify(entry.before)} → {JSON.stringify(entry.after)}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          <Card>
            <CardHeader title="Why this priority" />
            <div className="p-4">
              <ScoreBreakdown
                components={data.priority_breakdown}
                score={issue.priority.score}
                band={issue.priority.band}
              />
            </div>
          </Card>

          {issue.lat != null && issue.lon != null && (
            <Card className="overflow-hidden p-1">
              <MapView className="h-56" center={[issue.lat, issue.lon]} zoom={15} scrollWheelZoom={false}>
                {wards && <WardBoundaries data={wards} />}
                <PinMarker position={[issue.lat, issue.lon]} />
              </MapView>
            </Card>
          )}

          <Card>
            <CardHeader title="Status timeline" />
            <div className="p-4">
              <Timeline events={data.timeline} currentStatus={issue.status} />
            </div>
          </Card>

          {data.review_tasks.length > 0 && (
            <Card>
              <CardHeader title="Review items" />
              <ul className="divide-y divide-ink-100">
                {data.review_tasks.map((task) => (
                  <li key={task.id} className="px-4 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <Badge tone={task.status === 'open' ? 'warn' : 'success'}>
                        {task.kind.replace(/_/g, ' ')}
                      </Badge>
                      <span className="text-2xs text-ink-400">{task.status}</span>
                    </div>
                    <p className="text-xs text-ink-600 mt-1">{String(task.payload.summary ?? '')}</p>
                    {task.reason && (
                      <p className="text-2xs text-ink-500 mt-1 italic">
                        Resolved by {task.resolved_by}: “{task.reason}”
                      </p>
                    )}
                  </li>
                ))}
              </ul>
              <div className="px-4 py-3 border-t border-ink-100">
                <Link to="/admin/review">
                  <Button size="sm" variant="secondary" block>
                    Open review queue
                  </Button>
                </Link>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* ---- dialogs ---- */}
      <ReasonDialog
        open={dialog === 'category'}
        title="Override the AI classification"
        description="The SLA and the priority score are recomputed from the new category."
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={(reason) =>
          run(
            () => api.overrideCategory(issue.issue_code, { category: pendingCategory, reason }),
            'Category corrected and recorded',
          )
        }
      >
        <Field label="Correct category">
          <Select value={pendingCategory} onChange={(event) => setPendingCategory(event.target.value)}>
            {meta?.categories.map((category) => (
              <option key={category.key} value={category.key}>
                {category.label}
              </option>
            ))}
          </Select>
        </Field>
      </ReasonDialog>

      <ReasonDialog
        open={dialog === 'priority'}
        title="Pin the priority band"
        description="Pinning overrides the computed score until an officer releases it."
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={(reason) =>
          run(
            () =>
              api.overridePriority(issue.issue_code, {
                band: pendingBand === 'auto' ? null : pendingBand,
                reason,
              }),
            pendingBand === 'auto' ? 'Priority released back to the formula' : 'Priority pinned',
          )
        }
      >
        <Field label="Band" hint="Choose 'Computed' to release it back to the published formula.">
          <Select value={pendingBand} onChange={(event) => setPendingBand(event.target.value)}>
            <option value="auto">Computed (no override)</option>
            <option value="P1">P1 — Critical</option>
            <option value="P2">P2 — High</option>
            <option value="P3">P3 — Medium</option>
            <option value="P4">P4 — Low</option>
          </Select>
        </Field>
      </ReasonDialog>

      <ReasonDialog
        open={dialog === 'merge'}
        title="Merge this issue into another"
        description="Reports move across. Both issue records are kept - nothing is deleted."
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={(reason) =>
          run(
            () =>
              api
                .mergeIssue(issue.issue_code, {
                  target_issue_code: mergeTarget.trim().toUpperCase(),
                  reason,
                })
                .then(() => navigate(`/admin/issues/${mergeTarget.trim().toUpperCase()}`)),
            'Issues merged',
          )
        }
      >
        <Field label="Target issue code" hint="e.g. ISU-4T8W21">
          <Input
            value={mergeTarget}
            onChange={(event) => setMergeTarget(event.target.value)}
            placeholder="ISU-XXXXXX"
            className="font-mono uppercase"
          />
        </Field>
      </ReasonDialog>

      <ReasonDialog
        open={dialog === 'unmerge'}
        title="Split this report into its own issue"
        description="Use this when deduplication grouped two different problems."
        busy={busy}
        onCancel={() => setDialog(null)}
        onConfirm={(reason) =>
          run(
            () => api.unmergeReport(unmergeReportId as number, reason),
            'Report separated into a new issue',
          )
        }
      />
    </div>
  )
}
