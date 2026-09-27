/** Domain components shared by the citizen app and the officer dashboard. */

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  BAND_STYLES,
  SOURCE_LABELS,
  SOURCE_STYLES,
  STATUS_STYLES,
  classNames,
  formatDateTime,
  slaLabel,
  timeAgo,
} from '../lib/format'
import type {
  Band,
  HazardBlock,
  IssueSummary,
  ScoreComponent,
  StatusEventItem,
} from '../lib/types'
import { Badge } from './ui/primitives'

// ---------------------------------------------------------------------------
//  Priority
// ---------------------------------------------------------------------------
export function PriorityBadge({
  band,
  score,
  overridden,
  size = 'md',
}: {
  band: Band
  score?: number
  overridden?: boolean
  size?: 'sm' | 'md'
}) {
  const style = BAND_STYLES[band]
  return (
    <span
      className={classNames(
        'inline-flex items-center gap-1.5 rounded-md border font-semibold whitespace-nowrap',
        style.chip,
        size === 'sm' ? 'px-1.5 py-0.5 text-2xs' : 'px-2 py-1 text-xs',
      )}
      title={overridden ? 'Priority band pinned by an officer' : undefined}
    >
      <span className={classNames('h-1.5 w-1.5 rounded-full', style.dot)} />
      {band}
      {score !== undefined && <span className="tabular-nums opacity-70">{Math.round(score)}</span>}
      {overridden && (
        <svg className="h-3 w-3 opacity-80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M12 3v18M5 10l7-7 7 7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </span>
  )
}

export function StatusPill({ status, label }: { status: string; label: string }) {
  return (
    <span
      className={classNames(
        'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        STATUS_STYLES[status] ?? 'bg-ink-100 text-ink-700',
      )}
    >
      {label}
    </span>
  )
}

/** Who produced an AI output. Shown next to every machine decision. */
export function SourceChip({ source, model }: { source: string; model?: string }) {
  const label = SOURCE_LABELS[source] ?? source
  const tone = source === 'llm' ? 'brand' : source === 'officer' ? 'success' : 'neutral'
  return (
    <Badge tone={tone as 'brand' | 'success' | 'neutral'} className="font-medium">
      {source === 'officer' ? (
        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M20 21a8 8 0 1 0-16 0M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z" strokeLinecap="round" />
        </svg>
      ) : (
        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2a3 3 0 0 1 3 3v1h1a3 3 0 0 1 0 6h-1v1a3 3 0 1 1-6 0v-1H8a3 3 0 0 1 0-6h1V5a3 3 0 0 1 3-3z" strokeLinejoin="round" />
        </svg>
      )}
      {label}
      {model && <span className="opacity-60 font-normal">· {model}</span>}
    </Badge>
  )
}

export function HazardList({ hazards, pick }: { hazards: HazardBlock[]; pick?: (h: HazardBlock) => string }) {
  if (!hazards?.length) return null
  return (
    <div className="flex flex-wrap gap-1.5">
      {hazards.map((hazard) => (
        <Badge key={hazard.key} tone="danger">
          <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {pick ? pick(hazard) : hazard.label}
        </Badge>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
//  Score breakdown - the explainability centrepiece
// ---------------------------------------------------------------------------
const SOURCE_TITLES: Record<string, string> = {
  ai: 'Extracted by the AI from the complaint',
  citizens: 'Comes from how many people reported it',
  map: 'Verified against map data, not the text',
  policy: 'From the published SLA policy',
  equity: 'Equity correction - visible and switchable',
}

export function ScoreBreakdown({
  components,
  score,
  band,
  compact = false,
}: {
  components: ScoreComponent[]
  score: number
  band: Band
  compact?: boolean
}) {
  const max = Math.max(1, ...components.map((c) => c.points))
  return (
    <div>
      <div className="flex items-end justify-between gap-3 mb-3">
        <div>
          <p className="text-2xs uppercase tracking-wide text-ink-500 font-semibold">
            Priority score
          </p>
          <p className="text-3xl font-bold text-ink-900 tabular-nums leading-none mt-1">
            {Math.round(score)}
            <span className="text-base font-medium text-ink-400">/100</span>
          </p>
        </div>
        <PriorityBadge band={band} />
      </div>

      <ul className="space-y-2">
        {components.map((component) => (
          <li key={component.key}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-sm text-ink-800 min-w-0 truncate" title={component.label}>
                {component.label}
              </span>
              <span className="text-sm font-semibold tabular-nums text-ink-900 shrink-0">
                +{component.points.toFixed(component.points % 1 ? 1 : 0)}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <div className="h-1.5 flex-1 rounded-full bg-ink-100 overflow-hidden">
                <div
                  className={classNames('h-full rounded-full', BAND_STYLES[band].bar, 'opacity-70')}
                  style={{ width: `${Math.max(3, (component.points / max) * 100)}%` }}
                />
              </div>
              <span
                className={classNames(
                  'text-2xs px-1.5 py-0.5 rounded border font-medium shrink-0',
                  SOURCE_STYLES[component.source] ?? 'bg-ink-100 text-ink-600 border-ink-200',
                )}
                title={SOURCE_TITLES[component.source]}
              >
                {component.source}
              </span>
            </div>
            {!compact && component.detail && (
              <p className="text-2xs text-ink-500 mt-1 leading-relaxed">{component.detail}</p>
            )}
          </li>
        ))}
      </ul>

      {!compact && (
        <p className="text-2xs text-ink-500 mt-4 pt-3 border-t border-ink-100 leading-relaxed">
          The AI only extracts the features above. The score itself is a published weighted sum in{' '}
          <code className="font-mono text-ink-700">priority_config.yaml</code> - you can reproduce
          this number by hand.
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
//  Timeline
// ---------------------------------------------------------------------------
const LIFECYCLE: { key: string; label: string }[] = [
  { key: 'received', label: 'Received' },
  { key: 'verified', label: 'Verified' },
  { key: 'assigned', label: 'Assigned' },
  { key: 'in_progress', label: 'In progress' },
  { key: 'resolved', label: 'Resolved' },
]

export function Timeline({
  events,
  currentStatus,
  labels,
  ackHours,
}: {
  events: StatusEventItem[]
  currentStatus: string
  labels?: Record<string, string>
  ackHours?: number | null
}) {
  const reachedIndex = LIFECYCLE.findIndex((stage) => stage.key === currentStatus)
  const eventByStatus = new Map(events.map((event) => [event.to_status, event]))

  return (
    <ol className="relative">
      {LIFECYCLE.map((stage, index) => {
        const done = index <= reachedIndex
        const current = index === reachedIndex
        const event = eventByStatus.get(stage.key as StatusEventItem['to_status'])
        const isLast = index === LIFECYCLE.length - 1
        return (
          <li key={stage.key} className="flex gap-3 pb-5 last:pb-0">
            <div className="flex flex-col items-center shrink-0">
              <span
                className={classNames(
                  'h-7 w-7 rounded-full flex items-center justify-center border-2 transition-colors',
                  done
                    ? current
                      ? 'bg-brand-600 border-brand-600 text-white'
                      : 'bg-success-500 border-success-500 text-white'
                    : 'bg-white border-ink-200 text-ink-300',
                )}
              >
                {done ? (
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <path d="m5 13 4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                )}
              </span>
              {!isLast && (
                <span
                  className={classNames(
                    'w-0.5 flex-1 mt-1 min-h-[16px]',
                    index < reachedIndex ? 'bg-success-500' : 'bg-ink-150 bg-ink-100',
                  )}
                />
              )}
              {!isLast && stage.key === 'received' && ackHours && !eventByStatus.has('verified') && (
                <span className="text-2xs text-ink-400 mt-1 whitespace-nowrap">~{ackHours}h est.</span>
              )}
            </div>
            <div className="min-w-0 pt-0.5">
              <p className={classNames('text-sm font-medium', done ? 'text-ink-900' : 'text-ink-400')}>
                {labels?.[stage.key] ?? stage.label}
              </p>
              {event && (
                <p className="text-xs text-ink-500 mt-0.5">
                  {formatDateTime(event.created_at)}
                  {event.actor && event.actor !== 'system' && ` · ${event.actor}`}
                </p>
              )}
              {event?.note && (
                <p className="text-xs text-ink-600 mt-1 leading-relaxed bg-ink-50 rounded-md px-2 py-1.5">
                  {event.note}
                </p>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

// ---------------------------------------------------------------------------
//  Stats
// ---------------------------------------------------------------------------
export function StatCard({
  label,
  value,
  sub,
  tone = 'neutral',
  icon,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: 'neutral' | 'brand' | 'success' | 'warn' | 'danger'
  icon?: ReactNode
}) {
  const tones = {
    neutral: 'text-ink-900',
    brand: 'text-brand-700',
    success: 'text-success-700',
    warn: 'text-warn-600',
    danger: 'text-danger-600',
  }
  return (
    <div className="nn-card px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-ink-500 leading-tight">{label}</p>
        {icon && <span className="text-ink-300 shrink-0">{icon}</span>}
      </div>
      <p className={classNames('text-2xl font-bold tabular-nums mt-1.5 leading-none', tones[tone])}>
        {value}
      </p>
      {sub && <p className="text-xs text-ink-500 mt-1.5 leading-relaxed">{sub}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
//  Issue row (officer queue)
// ---------------------------------------------------------------------------
export function IssueRow({ issue, to }: { issue: IssueSummary; to: string }) {
  return (
    <Link
      to={to}
      className="block px-4 py-3 hover:bg-ink-50 transition-colors focus-visible:bg-ink-50"
    >
      <div className="flex items-start gap-3">
        <PriorityBadge band={issue.priority.band} score={issue.priority.score} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 flex-wrap">
            <p className="font-medium text-ink-900 truncate">{issue.title || issue.issue_code}</p>
            {issue.report_count > 1 && (
              <Badge tone="success">
                <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {issue.report_count} voices
              </Badge>
            )}
            {issue.priority.equity_boost_applied && (
              <Badge tone="accent" className="font-medium">
                equity +
              </Badge>
            )}
          </div>
          <p className="text-xs text-ink-500 mt-1 truncate">
            {issue.category.label}
            {issue.ward && ` · ${issue.ward.name}`}
            {issue.location_text && ` · ${issue.location_text}`}
          </p>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <StatusPill status={issue.status} label={issue.status_label} />
            <span
              className={classNames(
                'text-2xs font-medium',
                issue.sla.breached ? 'text-danger-600' : 'text-ink-500',
              )}
            >
              {slaLabel(issue.sla.deadline, issue.sla.breached)}
            </span>
            <span className="text-2xs text-ink-400">· {timeAgo(issue.created_at)}</span>
            {!!issue.open_reviews && (
              <Badge tone="warn">{issue.open_reviews} to review</Badge>
            )}
          </div>
        </div>
      </div>
    </Link>
  )
}
