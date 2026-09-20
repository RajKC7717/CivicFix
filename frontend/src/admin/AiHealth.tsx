/**
 * AI health: what the machine is doing, how well, and where it fails.
 *
 * Two kinds of number are kept strictly apart on this page:
 *  - **Live** figures, computed from this database right now.
 *  - **Held-out** figures from scripts/evaluate.py on a labelled split the model
 *    never trained on.
 * Mixing them would flatter the system, so they get separate sections and the
 * page says which is which.
 *
 * The held-out dedup metric ships with its own caveat text from the evaluator,
 * and it is rendered here rather than hidden in a file.
 */

import { useEffect, useState } from 'react'
import { StatCard } from '../components/shared'
import { Alert, Badge, Card, CardHeader, ErrorState, Skeleton } from '../components/ui/primitives'
import { api } from '../lib/api'
import { classNames, formatDateTime, percent } from '../lib/format'
import type { AiHealth as AiHealthReport } from '../lib/types'

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English',
  hi: 'हिन्दी Hindi',
  mr: 'मराठी Marathi',
  hinglish: 'Hinglish (romanised)',
  unknown: 'Unknown',
}

function Bar({ value, tone = 'brand' }: { value: number; tone?: 'brand' | 'success' | 'warn' }) {
  const tones = { brand: 'bg-brand-500', success: 'bg-success-500', warn: 'bg-warn-500' }
  return (
    <div className="h-1.5 rounded-full bg-ink-100 overflow-hidden">
      <div
        className={classNames('h-full rounded-full', tones[tone])}
        style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }}
      />
    </div>
  )
}

export default function AiHealth() {
  const [data, setData] = useState<AiHealthReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .aiHealth()
      .then(setData)
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Could not load'))
  }, [])

  if (error) {
    return (
      <div className="p-6">
        <Card>
          <ErrorState message={error} />
        </Card>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-20 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    )
  }

  const { live, components, holdout } = data
  const offline = holdout?.classification.offline_classifier

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div>
        <h1 className="text-xl font-bold text-ink-900">AI health</h1>
        <p className="text-sm text-ink-500 mt-0.5 max-w-3xl leading-relaxed">{data.note}</p>
      </div>

      {/* Which components are live */}
      <Card>
        <CardHeader title="What is running right now" />
        <div className="p-4 flex flex-wrap gap-2">
          <Badge tone={components.llm_active ? 'brand' : 'neutral'}>
            LLM: {components.llm_active ? components.llm_model : `${components.llm_provider} (inactive)`}
          </Badge>
          <Badge tone={components.offline_classifier_trained ? 'success' : 'warn'}>
            Offline classifier: {components.offline_classifier_trained ? 'trained' : 'lexicon rules only'}
          </Badge>
          <Badge tone="neutral">Embedder: {components.embedder}</Badge>
          <Badge tone="neutral">{components.cached_llm_responses} cached LLM responses</Badge>
        </div>
        {!components.llm_active && (
          <p className="px-4 pb-4 text-xs text-ink-600 leading-relaxed">
            No LLM is configured, so every complaint on this screen was classified by the offline
            path — no network, no API key, no GPU. That is the supported default, not a degraded
            mode.
          </p>
        )}
      </Card>

      {/* Live */}
      <div>
        <h2 className="text-sm font-semibold text-ink-700 uppercase tracking-wide mb-2">
          Live — this database
        </h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            label="Reports → issues"
            value={`${live.total_reports} → ${live.total_issues}`}
            tone="success"
            sub={`${live.reports_collapsed} folded in = ${live.triage_work_saved_pct}% less triage`}
          />
          <StatCard
            label="Mean confidence"
            value={live.mean_confidence !== null ? percent(live.mean_confidence, 1) : '—'}
            sub={
              live.low_confidence_share !== null
                ? `${percent(live.low_confidence_share)} sent to a human`
                : undefined
            }
          />
          <StatCard
            label="Located on the map"
            value={live.geocode.resolved_rate !== null ? percent(live.geocode.resolved_rate, 1) : '—'}
            sub={Object.entries(live.geocode.by_source)
              .map(([source, count]) => `${source} ${count}`)
              .join(' · ')}
          />
          <StatCard
            label="Pipeline latency"
            value={`${live.latency.pipeline_p50_ms ?? '—'} ms`}
            sub={`p95 ${live.latency.pipeline_p95_ms ?? '—'} ms`}
          />
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card>
          <CardHeader title="Deduplication decisions" />
          <div className="p-4 space-y-3">
            {Object.entries(live.dedup_decisions).map(([decision, count]) => (
              <div key={decision}>
                <div className="flex justify-between text-sm">
                  <span className="text-ink-700 capitalize">{decision.replace(/_/g, ' ')}</span>
                  <span className="font-semibold tabular-nums text-ink-900">{count}</span>
                </div>
                <Bar
                  value={count / Math.max(1, live.total_reports)}
                  tone={decision === 'merge' ? 'success' : decision === 'review' ? 'warn' : 'brand'}
                />
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader title="Human review load" />
          <div className="p-4">
            <p className="text-3xl font-bold text-ink-900 tabular-nums">
              {live.review.open_total}
            </p>
            <p className="text-xs text-ink-500 mb-3">open · {live.review.resolved_total} resolved</p>
            <div className="space-y-1.5">
              {Object.entries(live.review.open_by_kind).map(([kind, count]) => (
                <div key={kind} className="flex justify-between text-xs">
                  <span className="text-ink-600 capitalize">{kind.replace(/_/g, ' ')}</span>
                  <span className="font-semibold tabular-nums text-ink-800">{count}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Who classified" />
          <div className="p-4 space-y-3">
            {Object.entries(live.by_source).map(([source, count]) => (
              <div key={source}>
                <div className="flex justify-between text-sm">
                  <span className="text-ink-700 capitalize">{source.replace(/_/g, ' ')}</span>
                  <span className="font-semibold tabular-nums text-ink-900">{count}</span>
                </div>
                <Bar value={count / Math.max(1, live.total_reports)} />
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Per-stage latency */}
      <Card className="overflow-hidden">
        <CardHeader
          title="Per-stage latency and fallbacks"
          subtitle="Each pipeline stage times itself and records whether it used its primary path or its fallback."
        />
        <div className="overflow-x-auto nn-scroll">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-2xs uppercase tracking-wide text-ink-500 border-b border-ink-100">
                <th className="px-4 py-2 font-semibold">Stage</th>
                <th className="px-3 py-2 font-semibold text-right">Runs</th>
                <th className="px-3 py-2 font-semibold text-right">p50</th>
                <th className="px-3 py-2 font-semibold text-right">p95</th>
                <th className="px-4 py-2 font-semibold text-right">Fallback / error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {live.latency.by_stage.map((stage) => (
                <tr key={stage.stage} className="hover:bg-ink-50">
                  <td className="px-4 py-2.5 font-medium text-ink-900">{stage.stage}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-700">{stage.runs}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-700">
                    {stage.p50_ms} ms
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-ink-700">
                    {stage.p95_ms} ms
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums">
                    {stage.fallback_or_error > 0 ? (
                      <span className="text-warn-600 font-medium">{stage.fallback_or_error}</span>
                    ) : (
                      <span className="text-ink-400">0</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Held-out */}
      <div>
        <h2 className="text-sm font-semibold text-ink-700 uppercase tracking-wide mb-2">
          Held-out benchmark
          {data.holdout_run_at && (
            <span className="font-normal normal-case text-ink-400 ml-2">
              run {formatDateTime(data.holdout_run_at)}
            </span>
          )}
        </h2>

        {!holdout || !offline ? (
          <Card>
            <div className="p-6 text-sm text-ink-600 leading-relaxed">
              No evaluation has been run against this database yet. Run{' '}
              <code className="font-mono text-xs bg-ink-100 px-1.5 py-0.5 rounded">
                python scripts/evaluate.py
              </code>{' '}
              to populate this section.
            </div>
          </Card>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <StatCard
                label="Classification accuracy"
                value={percent(offline.accuracy, 1)}
                tone="success"
                sub={`macro-F1 ${offline.macro_f1.toFixed(3)} on ${offline.n} unseen complaints`}
              />
              <StatCard
                label="Dedup F1 (automatic)"
                value={holdout.dedup.auto_merge.f1.toFixed(3)}
                sub={`precision ${holdout.dedup.auto_merge.precision.toFixed(2)} · recall ${holdout.dedup.auto_merge.recall.toFixed(2)}`}
              />
              <StatCard
                label="Dedup F1 (+ officer)"
                value={holdout.dedup.with_human_review.f1.toFixed(3)}
                tone="brand"
                sub={`recall ${holdout.dedup.with_human_review.recall.toFixed(2)} once review items are confirmed`}
              />
              <StatCard
                label="Routed to a human"
                value={`${offline.routed_to_human_pct}%`}
                tone="warn"
                sub="low confidence, by design"
              />
            </div>

            <div className="grid lg:grid-cols-2 gap-4">
              <Card className="overflow-hidden">
                <CardHeader
                  title="Accuracy by language"
                  subtitle="The fairness question the equity panel exists to keep asking."
                />
                <div className="divide-y divide-ink-100">
                  {Object.entries(offline.by_language).map(([language, stats]) => (
                    <div key={language} className="px-4 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium text-ink-900">
                          {LANGUAGE_NAMES[language] ?? language}
                        </span>
                        <span className="text-sm font-semibold tabular-nums text-ink-800">
                          {percent(stats.accuracy, 1)}
                        </span>
                      </div>
                      <div className="mt-1.5">
                        <Bar value={stats.accuracy} tone={stats.accuracy >= 0.97 ? 'success' : 'warn'} />
                      </div>
                      <p className="text-2xs text-ink-500 mt-1 tabular-nums">
                        n={stats.n} · macro-F1 {stats.macro_f1.toFixed(3)}
                      </p>
                    </div>
                  ))}
                </div>
              </Card>

              <Card>
                <CardHeader
                  title="Deduplication"
                  subtitle={`${holdout.dedup.reports} reports, ${holdout.dedup.ideal_issues} true issues`}
                />
                <div className="p-4 space-y-3">
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div className="rounded-lg bg-ink-50 py-2.5">
                      <p className="text-xl font-bold text-ink-900 tabular-nums">
                        {holdout.dedup.issues_created}
                      </p>
                      <p className="text-2xs text-ink-500">issues created</p>
                    </div>
                    <div className="rounded-lg bg-success-50 py-2.5">
                      <p className="text-xl font-bold text-success-700 tabular-nums">
                        {holdout.dedup.triage_work_saved_pct}%
                      </p>
                      <p className="text-2xs text-ink-500">work removed</p>
                    </div>
                    <div className="rounded-lg bg-brand-50 py-2.5">
                      <p className="text-xl font-bold text-brand-700 tabular-nums">
                        {holdout.dedup.best_possible_work_saved_pct}%
                      </p>
                      <p className="text-2xs text-ink-500">theoretical best</p>
                    </div>
                  </div>
                  <p className="text-xs text-ink-600 leading-relaxed">
                    With officer confirmation of the flagged candidates, work removed rises to{' '}
                    <strong className="text-ink-900">
                      {holdout.dedup.triage_work_saved_with_review_pct}%
                    </strong>
                    .
                  </p>
                  <Alert tone="warn" title="Read this metric carefully">
                    <p className="text-xs leading-relaxed">{holdout.dedup.caveat}</p>
                  </Alert>
                </div>
              </Card>
            </div>

            {offline.top_confusions.length > 0 && (
              <Card>
                <CardHeader
                  title="Where it gets confused"
                  subtitle="The mistakes it actually made on unseen data."
                />
                <ul className="divide-y divide-ink-100">
                  {offline.top_confusions.map((confusion) => (
                    <li
                      key={`${confusion.true}-${confusion.predicted}`}
                      className="px-4 py-2.5 flex items-center justify-between text-sm"
                    >
                      <span className="text-ink-700">
                        <span className="font-medium text-ink-900">{confusion.true}</span>
                        <span className="text-ink-400"> classified as </span>
                        <span className="font-medium text-danger-600">{confusion.predicted}</span>
                      </span>
                      <span className="tabular-nums text-ink-500">×{confusion.count}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            <Card>
              <CardHeader title="Geocoding and review load" />
              <div className="p-4 grid sm:grid-cols-3 gap-4 text-sm">
                <div>
                  <p className="text-xs text-ink-500">With GPS present</p>
                  <p className="text-xl font-bold text-ink-900 tabular-nums mt-0.5">
                    {holdout.geocoding.resolved_pct}%
                  </p>
                </div>
                <div>
                  <p className="text-xs text-ink-500">
                    Text only ({holdout.geocoding_text_only.mode})
                  </p>
                  <p className="text-xl font-bold text-ink-900 tabular-nums mt-0.5">
                    {holdout.geocoding_text_only.resolved_pct}%
                  </p>
                </div>
                <div>
                  <p className="text-xs text-ink-500">Review raised on</p>
                  <p className="text-xl font-bold text-ink-900 tabular-nums mt-0.5">
                    {holdout.human_review.share_of_reports_pct}%
                  </p>
                  <p className="text-2xs text-ink-500">
                    {Object.entries(holdout.human_review.by_kind)
                      .map(([kind, count]) => `${kind.replace(/_/g, ' ')} ${count}`)
                      .join(' · ')}
                  </p>
                </div>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}
