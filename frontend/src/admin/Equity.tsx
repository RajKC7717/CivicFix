/**
 * The equity audit - the SDG-16 half of NagarNetra.
 *
 * A faster grievance system can still be an unfair one. This screen asks a
 * different question from the SLA page: not "are we slow?" but "are we slower
 * for some people than for others?" - by ward, and by the language the citizen
 * wrote in.
 *
 * The priority boost for flagged wards is switchable from here, and flipping it
 * is itself an audited act.
 */

import { useCallback, useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { MapView, WardBoundaries, useWardGeometry } from '../components/MapView'
import { StatCard } from '../components/shared'
import { ReasonDialog, useToast } from '../components/ui/overlays'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorState,
  Skeleton,
} from '../components/ui/primitives'
import { api } from '../lib/api'
import { classNames, formatHours, percent } from '../lib/format'
import type { EquityReport, GroupEquity } from '../lib/types'

const AXIS = { fontSize: 11, fill: '#4F6E93' }

function ParityTable({
  rows,
  cityMedian,
  caption,
}: {
  rows: GroupEquity[]
  cityMedian: number | null
  caption: string
}) {
  return (
    <div className="overflow-x-auto nn-scroll">
      <table className="w-full text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="text-left text-2xs uppercase tracking-wide text-ink-500 border-b border-ink-100">
            <th className="px-4 py-2 font-semibold">Group</th>
            <th className="px-3 py-2 font-semibold text-right">Issues</th>
            <th className="px-3 py-2 font-semibold text-right">Median fix</th>
            <th className="px-3 py-2 font-semibold text-right">vs city</th>
            <th className="px-4 py-2 font-semibold text-right">Breach rate</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-100">
          {rows.map((row) => (
            <tr key={row.key} className={classNames(row.flagged && 'bg-accent-50/50')}>
              <td className="px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-ink-900">{row.label}</span>
                  {row.flagged && <Badge tone="accent">under-served</Badge>}
                </div>
                {row.reasons.map((reason) => (
                  <p key={reason} className="text-2xs text-accent-700 mt-1 leading-relaxed">
                    {reason}
                  </p>
                ))}
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums text-ink-700">
                {row.total_issues}
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums text-ink-700">
                {formatHours(row.median_resolution_hours)}
              </td>
              <td className="px-3 py-2.5 text-right tabular-nums">
                {row.ratio_to_city ? (
                  <span
                    className={classNames(
                      'font-semibold',
                      row.ratio_to_city >= 1.5
                        ? 'text-danger-600'
                        : row.ratio_to_city >= 1.2
                          ? 'text-warn-600'
                          : 'text-success-700',
                    )}
                  >
                    {row.ratio_to_city.toFixed(2)}×
                  </span>
                ) : (
                  <span className="text-ink-400">—</span>
                )}
              </td>
              <td className="px-4 py-2.5 text-right tabular-nums text-ink-700">
                {percent(row.breach_rate)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {cityMedian !== null && (
        <p className="px-4 py-2.5 text-2xs text-ink-500 border-t border-ink-100">
          City median fix time: {formatHours(cityMedian)}. A group is flagged only once it has enough
          resolved issues to be evidence rather than noise.
        </p>
      )}
    </div>
  )
}

export default function Equity() {
  const toast = useToast()
  const wards = useWardGeometry()
  const [data, setData] = useState<EquityReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [boostOn, setBoostOn] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    setError(null)
    api
      .equity()
      .then(setData)
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Could not load'))
    api
      .settings()
      .then((settings) => setBoostOn(settings.equity_boost_enabled))
      .catch(() => undefined)
  }, [])

  useEffect(load, [load])

  async function toggleBoost(reason: string) {
    setBusy(true)
    try {
      const result = await api.updateSettings({ equity_boost_enabled: !boostOn, reason })
      setBoostOn(result.equity_boost_enabled)
      toast.push(
        `Equity boost ${result.equity_boost_enabled ? 'enabled' : 'disabled'}. ${result.issues_rescored} open issues rescored.`,
        'success',
      )
      setDialogOpen(false)
      load()
    } catch (caught) {
      toast.push(caught instanceof Error ? caught.message : 'Could not update', 'error')
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
        <Skeleton className="h-20 rounded-xl" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    )
  }

  const chartData = data.wards
    .filter((ward) => ward.median_resolution_hours !== null)
    .map((ward) => ({
      name: ward.label,
      hours: ward.median_resolution_hours ?? 0,
      flagged: ward.flagged,
    }))
    .sort((a, b) => b.hours - a.hours)

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-xl font-bold text-ink-900">Equity audit</h1>
          <p className="text-sm text-ink-500 mt-0.5 leading-relaxed">
            A grievance system that only gets faster can still be unfair. This page asks whether the
            city serves every ward, and every language, equally — and makes the answer public.
          </p>
        </div>
        <Button
          variant={boostOn ? 'primary' : 'secondary'}
          size="sm"
          onClick={() => setDialogOpen(true)}
        >
          Equity boost: {boostOn ? 'ON' : 'OFF'}
        </Button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="City median fix time"
          value={formatHours(data.city_median_resolution_hours)}
        />
        <StatCard label="City breach rate" value={percent(data.city_breach_rate)} tone="warn" />
        <StatCard
          label="Wards flagged"
          value={data.flagged_ward_codes.length}
          tone={data.flagged_ward_codes.length ? 'danger' : 'success'}
          sub={data.flagged_ward_codes.join(', ') || 'none'}
        />
        <StatCard
          label="Equity adjustment"
          value={boostOn ? `+${data.thresholds.equity_points ?? 0}` : 'off'}
          tone="brand"
          sub="points for flagged wards"
        />
      </div>

      <Alert tone="info" title="How a group gets flagged">
        <p className="text-xs leading-relaxed">{data.explanation}</p>
        <p className="text-xs leading-relaxed mt-1.5">{data.equity_boost_note}</p>
      </Alert>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader
            title="Median fix time by ward"
            subtitle="Orange bars are wards the audit has flagged as under-served."
          />
          <div className="p-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 4, right: 8, left: -14, bottom: 34 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E8EDF3" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ ...AXIS, fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  angle={-38}
                  textAnchor="end"
                  height={54}
                  interval={0}
                />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} unit="h" />
                <Tooltip
                  contentStyle={{ borderRadius: 10, border: '1px solid #E8EDF3', fontSize: 12 }}
                  cursor={{ fill: '#F5F7FA' }}
                  formatter={(value: number) => [`${value.toFixed(1)} h`, 'Median fix time']}
                />
                {data.city_median_resolution_hours && (
                  <ReferenceLine
                    y={data.city_median_resolution_hours}
                    stroke="#4F6E93"
                    strokeDasharray="4 4"
                    label={{ value: 'city median', fontSize: 10, fill: '#4F6E93', position: 'right' }}
                  />
                )}
                <Bar dataKey="hours" radius={[5, 5, 0, 0]}>
                  {chartData.map((entry) => (
                    <Cell key={entry.name} fill={entry.flagged ? '#DD7120' : '#4F90D0'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-1 overflow-hidden">
          <div className="px-4 pt-3 pb-2">
            <p className="font-semibold text-ink-900">Where the gap is</p>
            <p className="text-sm text-ink-500 mt-0.5">
              Flagged wards are outlined in orange.
            </p>
          </div>
          <MapView className="h-64" zoom={10.5}>
            {wards && <WardBoundaries data={wards} highlight={data.flagged_ward_codes} showLabels />}
          </MapView>
        </Card>
      </div>

      <Card className="overflow-hidden">
        <CardHeader
          title="Ward parity"
          subtitle="Median time-to-resolve and SLA breach rate against the city as a whole."
        />
        <ParityTable
          rows={data.wards}
          cityMedian={data.city_median_resolution_hours}
          caption="Resolution parity by ward"
        />
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="overflow-hidden">
          <CardHeader
            title="Language parity"
            subtitle="Does it matter which language you complain in?"
          />
          <ParityTable
            rows={data.languages}
            cityMedian={data.city_median_resolution_hours}
            caption="Resolution parity by language"
          />
        </Card>

        <Card className="overflow-hidden">
          <CardHeader
            title="AI accuracy by language"
            subtitle="How often an officer had to correct the classifier, per language. A gap here is a fairness defect, not a curiosity."
          />
          <div className="divide-y divide-ink-100">
            {data.language_accuracy.map((row) => (
              <div key={row.language} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium text-ink-900">{row.label}</span>
                  <span className="text-sm font-semibold tabular-nums text-ink-800">
                    {row.agreement_rate === null ? '—' : percent(row.agreement_rate, 1)}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-1.5">
                  <div className="h-1.5 flex-1 rounded-full bg-ink-100 overflow-hidden">
                    <div
                      className={classNames(
                        'h-full rounded-full',
                        (row.agreement_rate ?? 1) >= 0.95 ? 'bg-success-500' : 'bg-warn-500',
                      )}
                      style={{ width: `${(row.agreement_rate ?? 0) * 100}%` }}
                    />
                  </div>
                  <span className="text-2xs text-ink-500 tabular-nums w-28 text-right">
                    {row.officer_corrections} of {row.reports} corrected
                  </span>
                </div>
              </div>
            ))}
          </div>
          <p className="px-4 py-3 text-2xs text-ink-500 border-t border-ink-100 leading-relaxed">
            This is the live operational figure. The controlled held-out benchmark, broken down the
            same way, is on the AI Health page.
          </p>
        </Card>
      </div>

      <ReasonDialog
        open={dialogOpen}
        title={boostOn ? 'Turn the equity boost off' : 'Turn the equity boost on'}
        description={
          boostOn
            ? 'Flagged wards will stop receiving the priority adjustment. Every open issue is rescored immediately.'
            : `Flagged wards will receive +${data.thresholds.equity_points ?? 0} priority points. The adjustment is shown in every score breakdown.`
        }
        confirmLabel={boostOn ? 'Turn it off' : 'Turn it on'}
        busy={busy}
        onCancel={() => setDialogOpen(false)}
        onConfirm={toggleBoost}
      />
    </div>
  )
}
