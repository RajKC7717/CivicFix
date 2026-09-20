/**
 * The audit log.
 *
 * Append-only, unfiltered by default, and readable by anyone with a dashboard
 * account. Every entry names a person, a time, a before, an after and a reason.
 * Nothing in the product can edit or delete a row here, which is the entire
 * point: an override an officer can hide is not accountability.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Select, Skeleton } from '../components/ui/primitives'
import { api } from '../lib/api'
import { formatDateTime, timeAgo } from '../lib/format'
import type { AuditItem } from '../lib/types'

const ACTION_TONE: Record<string, 'brand' | 'warn' | 'danger' | 'success' | 'neutral' | 'accent'> = {
  override_category: 'warn',
  override_priority: 'warn',
  merge_issues: 'brand',
  unmerge_report: 'brand',
  change_status: 'success',
  assign: 'neutral',
  set_location: 'brand',
  toggle_equity_boost: 'accent',
  review_confirm: 'success',
  review_keep_separate: 'neutral',
}

function Diff({ entry }: { entry: AuditItem }) {
  if (!entry.before && !entry.after) return null
  const keys = Array.from(
    new Set([...Object.keys(entry.before ?? {}), ...Object.keys(entry.after ?? {})]),
  )
  return (
    <div className="mt-2 rounded-lg bg-ink-50 border border-ink-100 px-3 py-2 text-2xs font-mono">
      {keys.map((key) => {
        const before = JSON.stringify((entry.before ?? {})[key])
        const after = JSON.stringify((entry.after ?? {})[key])
        if (before === after) return null
        return (
          <div key={key} className="flex flex-wrap gap-1.5 py-0.5">
            <span className="text-ink-500">{key}:</span>
            <span className="text-danger-600 line-through">{before}</span>
            <span className="text-ink-400">→</span>
            <span className="text-success-700 font-semibold">{after}</span>
          </div>
        )
      })}
    </div>
  )
}

export default function AuditLog() {
  const [items, setItems] = useState<AuditItem[] | null>(null)
  const [actions, setActions] = useState<string[]>([])
  const [total, setTotal] = useState(0)
  const [action, setAction] = useState('')
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const limit = 50

  const load = useCallback(() => {
    setError(null)
    api
      .audit({ limit, offset, action: action || undefined })
      .then((payload) => {
        setItems(payload.items)
        setActions(payload.actions)
        setTotal(payload.total)
      })
      .catch((caught) => {
        setItems([])
        setError(caught instanceof Error ? caught.message : 'Could not load the audit log')
      })
  }, [action, offset])

  useEffect(() => {
    setItems(null)
    load()
  }, [load])

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="max-w-3xl">
          <h1 className="text-xl font-bold text-ink-900">Audit log</h1>
          <p className="text-sm text-ink-500 mt-0.5 leading-relaxed">
            Every human decision that changed what the AI proposed — who, what, before, after, and
            why. Append-only: no part of NagarNetra can edit or delete an entry.
          </p>
        </div>
        <Select
          value={action}
          onChange={(event) => {
            setOffset(0)
            setAction(event.target.value)
          }}
          className="w-auto text-sm py-1.5"
          aria-label="Filter by action"
        >
          <option value="">All actions ({total})</option>
          {actions.map((name) => (
            <option key={name} value={name}>
              {name.replace(/_/g, ' ')}
            </option>
          ))}
        </Select>
      </div>

      <Card className="overflow-hidden">
        <CardHeader title={`${total} recorded decisions`} />
        {items === null && (
          <div className="p-4 space-y-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-16" />
            ))}
          </div>
        )}
        {error && <ErrorState message={error} onRetry={load} />}
        {items?.length === 0 && !error && (
          <EmptyState
            title="No overrides recorded yet"
            body="When an officer corrects a category, merges issues, pins a priority or flips a policy switch, it appears here."
          />
        )}
        <ul className="divide-y divide-ink-100">
          {items?.map((entry) => (
            <li key={entry.id} className="px-4 py-3.5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge tone={ACTION_TONE[entry.action] ?? 'neutral'}>
                    {entry.action.replace(/_/g, ' ')}
                  </Badge>
                  <span className="text-sm font-medium text-ink-900">{entry.actor}</span>
                  <span className="text-2xs text-ink-400 capitalize">({entry.actor_role})</span>
                  {entry.entity_type === 'issue' && (
                    <Link
                      to={`/admin/issues/${entry.entity_id}`}
                      className="text-xs text-brand-600 hover:underline font-mono"
                    >
                      issue #{entry.entity_id}
                    </Link>
                  )}
                  {entry.entity_type !== 'issue' && (
                    <span className="text-xs text-ink-500 font-mono">
                      {entry.entity_type} #{entry.entity_id}
                    </span>
                  )}
                </div>
                <span className="text-2xs text-ink-400" title={formatDateTime(entry.created_at)}>
                  {timeAgo(entry.created_at)}
                </span>
              </div>
              {entry.reason && (
                <p className="text-sm text-ink-700 mt-1.5 leading-relaxed">“{entry.reason}”</p>
              )}
              <Diff entry={entry} />
            </li>
          ))}
        </ul>

        {total > limit && (
          <div className="px-4 py-3 border-t border-ink-100 flex items-center justify-between">
            <span className="text-xs text-ink-500 tabular-nums">
              {offset + 1}–{Math.min(offset + limit, total)} of {total}
            </span>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={offset + limit >= total}
                onClick={() => setOffset(offset + limit)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
