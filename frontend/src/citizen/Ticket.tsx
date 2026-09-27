/**
 * Confirmation page shown immediately after a complaint is filed.
 *
 * This screen carries most of the Responsible-AI weight of the citizen app. It
 * tells the person, in their own language and before they ask:
 *  - what the system decided,
 *  - how confident it was and *which* system decided it,
 *  - which words led to that decision,
 *  - how their report interacted with everyone else's,
 *  - and what the deadline is.
 *
 * When the complaint duplicates an existing one, the message is "N others
 * reported this and your report raised its priority" - never "rejected".
 */

import { useState } from 'react'
import { Link, Navigate, useLocation, useParams } from 'react-router-dom'
import { HazardList, PriorityBadge, ScoreBreakdown, SourceChip } from '../components/shared'
import { Alert, Badge, Button, Card, CardHeader, ConfidenceMeter } from '../components/ui/primitives'
import { MapView, PinMarker } from '../components/MapView'
import { useI18n } from '../i18n'
import { formatDateTime } from '../lib/format'
import type { SubmitResponse } from '../lib/types'
import EmailDraft from './EmailDraft'

function CopyableCode({ code, copyLabel, copiedLabel }: { code: string; copyLabel: string; copiedLabel: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <code className="font-mono text-xl sm:text-2xl font-bold tracking-wide text-ink-900 bg-ink-100 rounded-lg px-3 py-1.5">
        {code}
      </code>
      <Button
        size="sm"
        variant="secondary"
        onClick={() => {
          navigator.clipboard?.writeText(code).then(
            () => {
              setCopied(true)
              window.setTimeout(() => setCopied(false), 2000)
            },
            () => setCopied(false),
          )
        }}
      >
        {copied ? copiedLabel : copyLabel}
      </Button>
    </div>
  )
}

export default function Ticket() {
  const { t, pick } = useI18n()
  const { code = '' } = useParams()
  const location = useLocation()
  const result = (location.state as { result?: SubmitResponse } | null)?.result

  // Arrived by a shared link or a refresh: there is no submission payload in
  // history, so fall through to the durable tracking view.
  if (!result) return <Navigate to={`/track/${code}`} replace />

  const joined = result.cluster?.joined_existing
  const others = result.cluster?.others ?? 0
  const needsReview = result.review?.needed

  return (
    <div className="mx-auto max-w-2xl px-4 py-6 space-y-4">
      {/* Success banner */}
      <div className="rounded-2xl bg-success-50 border border-success-100 px-5 py-5">
        <div className="flex items-start gap-3">
          <span className="h-10 w-10 rounded-full bg-success-500 text-white flex items-center justify-center shrink-0">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
              <path d="m5 13 4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <div className="min-w-0">
            <h1 className="text-xl font-bold text-ink-900">{t('ticket_title')}</h1>
            <p className="text-sm text-ink-700 mt-1 leading-relaxed">{result.citizen_message}</p>
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-success-100">
          <p className="text-xs font-medium text-ink-600 mb-2">{t('ticket_number')}</p>
          <CopyableCode code={result.ticket_code} copyLabel={t('ticket_copy')} copiedLabel={t('ticket_copied')} />
        </div>
      </div>

      {result.degraded && (
        <Alert tone="warn" title="Automatic triage did not run">
          Your complaint is safely recorded and a municipal officer will handle it personally.
        </Alert>
      )}

      {/* "One issue, many voices" */}
      {joined && others > 0 && (
        <Card className="border-brand-200 bg-brand-50/50 p-4">
          <div className="flex items-start gap-3">
            <span className="h-9 w-9 rounded-lg bg-brand-600 text-white flex items-center justify-center shrink-0">
              <svg className="h-4.5 w-4.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <div>
              <p className="font-semibold text-ink-900 text-sm">{t('ticket_joined_title')}</p>
              <p className="text-sm text-ink-700 mt-1 leading-relaxed">
                <strong className="text-brand-700">{result.cluster?.report_count} people</strong> have
                reported this same problem. Your report has been added to issue{' '}
                <code className="font-mono text-xs">{result.issue_code}</code> and raised its
                priority — it was not filed as a duplicate.
              </p>
            </div>
          </div>
        </Card>
      )}

      {needsReview && (
        <Alert tone="info" title={t('ticket_review_note')}>
          <ul className="mt-1 space-y-0.5 text-xs">
            {result.review?.kinds.map((kind) => (
              <li key={kind}>
                ·{' '}
                {kind === 'missing_location'
                  ? 'An officer will confirm the exact location on the map.'
                  : kind === 'low_confidence_category'
                    ? 'An officer will confirm the category before it is assigned.'
                    : kind === 'duplicate_candidate'
                      ? 'An officer will check whether this is the same as a nearby report.'
                      : 'An officer will read this complaint personally.'}
              </li>
            ))}
          </ul>
        </Alert>
      )}

      {/* What we understood */}
      <Card>
        <CardHeader
          title={t('ticket_understood')}
          action={result.ai && <SourceChip source={result.ai.source} />}
        />
        <div className="p-5 space-y-4">
          <dl className="grid grid-cols-2 gap-4">
            <div>
              <dt className="text-xs text-ink-500">{t('ticket_category')}</dt>
              <dd className="font-semibold text-ink-900 mt-0.5">{pick(result.category)}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-500">{t('ticket_severity')}</dt>
              <dd className="font-semibold text-ink-900 mt-0.5 flex items-center gap-1.5">
                {result.severity}/5
                <span className="flex gap-0.5">
                  {[1, 2, 3, 4, 5].map((level) => (
                    <span
                      key={level}
                      className={`h-1.5 w-3 rounded-sm ${
                        level <= (result.severity ?? 0) ? 'bg-accent-500' : 'bg-ink-200'
                      }`}
                    />
                  ))}
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-500">{t('ticket_department')}</dt>
              <dd className="font-medium text-ink-800 mt-0.5 capitalize">{result.department}</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-500">{t('ticket_deadline')}</dt>
              <dd className="font-medium text-ink-800 mt-0.5">
                {result.sla?.deadline ? formatDateTime(result.sla.deadline) : '-'}
                <span className="block text-2xs text-ink-500">
                  {result.sla?.hours} hour target
                </span>
              </dd>
            </div>
          </dl>

          {!!result.hazard_flags?.length && (
            <div>
              <p className="text-xs text-ink-500 mb-1.5">Hazards detected</p>
              <HazardList hazards={result.hazard_flags} pick={pick} />
            </div>
          )}

          {result.ai && (
            <div className="rounded-lg bg-ink-50 border border-ink-100 p-3">
              <ConfidenceMeter value={result.ai.confidence} label={t('ticket_confidence')} />
              <p className="text-xs text-ink-600 mt-2.5 leading-relaxed">
                <span className="font-medium text-ink-800">{t('ticket_why')}: </span>
                {result.ai.explanation}
              </p>
              {!!result.ai.matched_terms?.length && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {result.ai.matched_terms.map((term) => (
                    <Badge key={term} tone="neutral" className="font-mono text-2xs">
                      {term.replace(/_/g, ' ')}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          {result.redaction?.notice && (
            <Alert tone="success" title={t('ticket_redacted')}>
              <p className="text-xs">{result.redaction.notice}</p>
            </Alert>
          )}
        </div>
      </Card>

      {/* Priority explanation */}
      {result.priority && (
        <Card>
          <CardHeader
            title={t('ticket_priority_why')}
            action={<PriorityBadge band={result.priority.band} score={result.priority.score} />}
          />
          <div className="p-5">
            <ScoreBreakdown
              components={result.priority.breakdown}
              score={result.priority.score}
              band={result.priority.band}
            />
          </div>
        </Card>
      )}

      {/* Email draft */}
      {result.ticket_code && (
        <EmailDraft ticketCode={result.ticket_code} />
      )}

      {/* Location */}
      {result.location?.lat != null && result.location?.lon != null && (
        <Card className="overflow-hidden">
          <CardHeader
            title="Where we placed it"
            subtitle={
              [result.location.ward, result.location.text].filter(Boolean).join(' · ') ||
              undefined
            }
          />
          <MapView
            className="h-[220px]"
            center={[result.location.lat, result.location.lon]}
            zoom={16}
            scrollWheelZoom={false}
          >
            <PinMarker position={[result.location.lat, result.location.lon]} />
          </MapView>
          <p className="px-5 py-3 text-2xs text-ink-500 leading-relaxed">
            Placed from <strong>{result.location.source}</strong>
            {result.location.confidence < 1 &&
              ` (approximate — an officer will confirm the exact spot)`}
            .
          </p>
        </Card>
      )}

      {result.image_url && (
        <Card className="overflow-hidden">
          <CardHeader title="Your photo" subtitle="Metadata removed before storage" />
          <img src={result.image_url} alt="Submitted evidence" className="w-full max-h-80 object-cover" />
        </Card>
      )}

      <div className="flex flex-wrap gap-3 pt-2">
        <Link to={`/track/${result.ticket_code}`} className="flex-1 min-w-[180px]">
          <Button block variant="primary">
            {t('ticket_track_cta')}
          </Button>
        </Link>
        <Link to="/report" className="flex-1 min-w-[180px]">
          <Button block variant="secondary">
            {t('ticket_new_cta')}
          </Button>
        </Link>
      </div>
    </div>
  )
}
