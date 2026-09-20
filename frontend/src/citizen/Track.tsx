/**
 * Public tracking page.
 *
 * Shows the same explanation the citizen saw at submission time, plus the live
 * status timeline, and — once the issue is resolved — invites a rating. The
 * feedback loop is what turns a complaint portal into an accountability tool:
 * the department's rating is visible to the ward officer.
 */

import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { HazardList, PriorityBadge, ScoreBreakdown, SourceChip, StatusPill, Timeline } from '../components/shared'
import { MapView, PinMarker } from '../components/MapView'
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
  Skeleton,
  Textarea,
} from '../components/ui/primitives'
import { useToast } from '../components/ui/overlays'
import { useI18n } from '../i18n'
import { ApiError, api } from '../lib/api'
import { formatDateTime, slaLabel, timeAgo } from '../lib/format'
import type { TrackResponse } from '../lib/types'

function StarPicker({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return (
    <div className="flex gap-1.5" role="radiogroup" aria-label="Rating">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          role="radio"
          aria-checked={value === star}
          aria-label={`${star} star${star === 1 ? '' : 's'}`}
          onClick={() => onChange(star)}
          className="nn-tap flex items-center justify-center rounded-lg hover:bg-ink-100 transition-colors"
        >
          <svg
            className={star <= value ? 'h-8 w-8 text-accent-500' : 'h-8 w-8 text-ink-200'}
            viewBox="0 0 24 24"
            fill="currentColor"
          >
            <path d="m12 2 2.9 6.3 6.8.8-5 4.7 1.3 6.8L12 17.3 6 20.6l1.3-6.8-5-4.7 6.8-.8L12 2z" />
          </svg>
        </button>
      ))}
    </div>
  )
}

export default function Track() {
  const { t, pick } = useI18n()
  const { code } = useParams()
  const navigate = useNavigate()
  const toast = useToast()

  const [query, setQuery] = useState(code ?? '')
  const [data, setData] = useState<TrackResponse | null>(null)
  const [loading, setLoading] = useState(Boolean(code))
  const [error, setError] = useState<string | null>(null)
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')
  const [sending, setSending] = useState(false)

  const load = useCallback(
    async (ticket: string) => {
      setLoading(true)
      setError(null)
      try {
        setData(await api.track(ticket.trim().toUpperCase()))
      } catch (caught) {
        setData(null)
        setError(
          caught instanceof ApiError && caught.status === 404
            ? t('track_not_found')
            : caught instanceof Error
              ? caught.message
              : t('error_generic'),
        )
      } finally {
        setLoading(false)
      }
    },
    [t],
  )

  useEffect(() => {
    if (code) {
      setQuery(code)
      void load(code)
    }
  }, [code, load])

  async function submitRating() {
    if (!data || rating === 0) return
    setSending(true)
    try {
      const response = await api.feedback(data.report.ticket_code, { rating, comment })
      toast.push(response.message ?? t('track_rate_thanks'), 'success')
      await load(data.report.ticket_code)
    } catch (caught) {
      toast.push(caught instanceof Error ? caught.message : t('error_generic'), 'error')
    } finally {
      setSending(false)
    }
  }

  const statusLabels = {
    received: t('status_received'),
    verified: t('status_verified'),
    assigned: t('status_assigned'),
    in_progress: t('status_in_progress'),
    resolved: t('status_resolved'),
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <h1 className="text-2xl font-bold text-ink-900">{t('track_title')}</h1>

      <form
        className="flex gap-2 mt-4"
        onSubmit={(event) => {
          event.preventDefault()
          if (query.trim()) navigate(`/track/${query.trim().toUpperCase()}`)
        }}
      >
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('track_placeholder')}
          className="font-mono uppercase"
          aria-label={t('track_placeholder')}
        />
        <Button type="submit" disabled={!query.trim()}>
          {t('track_button')}
        </Button>
      </form>

      {loading && (
        <div className="space-y-3 mt-6">
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-56 rounded-xl" />
        </div>
      )}

      {!loading && error && (
        <Card className="mt-6">
          <ErrorState message={error} onRetry={code ? () => void load(code) : undefined} />
        </Card>
      )}

      {!loading && data && (
        <div className="space-y-4 mt-6">
          {/* Summary */}
          <Card className="p-5">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <p className="font-mono text-sm text-ink-500">{data.report.ticket_code}</p>
                <h2 className="text-lg font-semibold text-ink-900 mt-0.5 leading-snug">
                  {data.issue?.title || data.report.summary_en || pick(data.report.category)}
                </h2>
                <p className="text-xs text-ink-500 mt-1">
                  {t('track_reported')} {timeAgo(data.report.created_at)}
                  {data.report.location.text && ` · ${data.report.location.text}`}
                </p>
              </div>
              {data.issue && (
                <div className="flex flex-col items-end gap-1.5">
                  <StatusPill status={data.issue.status} label={statusLabels[data.issue.status]} />
                  <PriorityBadge band={data.issue.priority.band} score={data.issue.priority.score} />
                </div>
              )}
            </div>

            {data.issue && data.issue.report_count > 1 && (
              <div className="mt-4 rounded-lg bg-brand-50 border border-brand-100 px-3 py-2.5 text-sm text-ink-700">
                <strong className="text-brand-700">{data.issue.report_count}</strong>{' '}
                {t('track_others')}.
              </div>
            )}

            {data.issue && (
              <div className="grid grid-cols-2 gap-3 mt-4 pt-4 border-t border-ink-100 text-sm">
                <div>
                  <p className="text-xs text-ink-500">{t('ticket_department')}</p>
                  <p className="font-medium text-ink-800 capitalize mt-0.5">
                    {data.issue.department}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-ink-500">{t('ticket_deadline')}</p>
                  <p
                    className={`font-medium mt-0.5 ${
                      data.issue.sla.breached ? 'text-danger-600' : 'text-ink-800'
                    }`}
                  >
                    {slaLabel(data.issue.sla.deadline, data.issue.sla.breached)}
                  </p>
                </div>
              </div>
            )}
          </Card>

          {/* Timeline */}
          <Card>
            <CardHeader title={t('track_timeline')} />
            <div className="p-5">
              <Timeline
                events={data.timeline}
                currentStatus={data.issue?.status ?? 'received'}
                labels={statusLabels}
              />
            </div>
          </Card>

          {/* Rating */}
          {data.can_give_feedback && (
            <Card className="border-accent-200">
              <CardHeader title={t('track_rate_title')} subtitle={t('track_rate_hint')} />
              <div className="p-5 space-y-4">
                <StarPicker value={rating} onChange={setRating} />
                <Field label={t('track_rate_comment')}>
                  <Textarea
                    rows={3}
                    value={comment}
                    onChange={(event) => setComment(event.target.value)}
                    maxLength={600}
                  />
                </Field>
                <Button onClick={submitRating} disabled={rating === 0} loading={sending}>
                  {t('track_rate_submit')}
                </Button>
              </div>
            </Card>
          )}
          {data.feedback_given && (
            <Alert tone="success" title={t('track_rated')}>
              {t('track_rate_thanks')}
            </Alert>
          )}

          {/* What the AI understood */}
          <Card>
            <CardHeader
              title={t('ticket_understood')}
              action={<SourceChip source={data.report.ai.source} model={data.report.ai.model} />}
            />
            <div className="p-5 space-y-4">
              <p className="text-sm text-ink-700 bg-ink-50 rounded-lg px-3 py-2.5 leading-relaxed">
                {data.report.text}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="brand">{pick(data.report.category)}</Badge>
                <Badge tone="neutral">{data.report.language.label}</Badge>
                {data.report.severity && <Badge tone="warn">Severity {data.report.severity}/5</Badge>}
              </div>
              <HazardList hazards={data.report.hazard_flags} pick={pick} />
              <ConfidenceMeter value={data.report.ai.confidence} label={t('ticket_confidence')} />
              <p className="text-xs text-ink-600 leading-relaxed">
                <span className="font-medium text-ink-800">{t('ticket_why')}: </span>
                {data.report.ai.explanation}
              </p>
              {data.report.redaction?.notice && (
                <p className="text-xs text-success-700">{data.report.redaction.notice}</p>
              )}
            </div>
          </Card>

          {/* Priority */}
          {data.issue && data.priority_breakdown.length > 0 && (
            <Card>
              <CardHeader title={t('ticket_priority_why')} />
              <div className="p-5">
                <ScoreBreakdown
                  components={data.priority_breakdown}
                  score={data.issue.priority.score}
                  band={data.issue.priority.band}
                />
              </div>
            </Card>
          )}

          {/* Map */}
          {data.report.location.lat != null && data.report.location.lon != null && (
            <Card className="overflow-hidden">
              <CardHeader
                title="Location"
                subtitle={data.issue?.ward?.name ? `Ward: ${data.issue.ward.name}` : undefined}
              />
              <MapView
                className="h-[220px]"
                center={[data.report.location.lat, data.report.location.lon]}
                zoom={16}
                scrollWheelZoom={false}
              >
                <PinMarker position={[data.report.location.lat, data.report.location.lon]} />
              </MapView>
            </Card>
          )}

          {data.report.image_url && (
            <Card className="overflow-hidden">
              <CardHeader title="Photo" />
              <img src={data.report.image_url} alt="" className="w-full max-h-80 object-cover" />
            </Card>
          )}

          {data.issue?.resolved_at && (
            <p className="text-xs text-ink-500 text-center">
              Resolved {formatDateTime(data.issue.resolved_at)}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
