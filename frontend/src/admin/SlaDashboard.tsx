/** SLA performance: is the city keeping the promises it published? */

import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { StatCard } from '../components/shared'
import { Card, CardHeader, ErrorState, Skeleton } from '../components/ui/primitives'
import { api } from '../lib/api'
import { classNames, formatHours, percent } from '../lib/format'
import type { SlaGroup, SlaReport } from '../lib/types'

const AXIS = { fontSize: 11, fill: '#4F6E93' }

function BreachTable({ title, subtitle, rows }: { title: string; subtitle: string; rows: SlaGroup[] }) {
  return (
    <Card className="overflow-hidden">
      <CardHeader title={title} subtitle={subtitle} />
      <div className="overflow-x-auto nn-scroll">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-2xs uppercase tracking-wide text-ink-500 border-b border-ink-100">
              <th className="px-4 py-2 font-semibold">Name</th>
              <th className="px-3 py-2 font-semibold text-right">Open</th>
              <th className="px-3 py-2 font-semibold text-right">Resolved</th>
              <th className="px-3 py-2 font-semibold text-right">Median fix</th>
              <th className="px-4 py-2 font-semibold text-right">Breach rate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {rows.map((row) => (
              <tr key={row.key} className="hover:bg-ink-50">
                <td className="px-4 py-2.5 font-medium text-ink-900">{row.label}</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-ink-700">{row.open}</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-ink-700">{row.resolved}</td>
                <td className="px-3 py-2.5 text-right tabular-nums text-ink-700">
                  {formatHours(row.median_hours)}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <div className="h-1.5 w-16 rounded-full bg-ink-100 overflow-hidden">
                      <div
                        className={classNames(
                          'h-full rounded-full',
                          row.breach_rate > 0.6
                            ? 'bg-p1'
                            : row.breach_rate > 0.35
                              ? 'bg-p2'
                              : 'bg-success-500',
                        )}
                        style={{ width: `${Math.min(100, row.breach_rate * 100)}%` }}
                      />
                    </div>
                    <span
                      className={classNames(
                        'tabular-nums font-semibold w-11 text-right',
                        row.breach_rate > 0.6 ? 'text-danger-600' : 'text-ink-700',
                      )}
                    >
                      {percent(row.breach_rate)}
                    </span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export default function SlaDashboard() {
  const [data, setData] = useState<SlaReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .sla()
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

  const { summary } = data

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <div>
        <h1 className="text-xl font-bold text-ink-900">SLA performance</h1>
        <p className="text-sm text-ink-500 mt-0.5 max-w-3xl leading-relaxed">
          Every category carries a published turnaround target. The clock starts when the citizen
          submits, not when an officer opens the ticket.
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <StatCard label="Open" value={summary.open} sub={`${summary.total_issues} total`} />
        <StatCard label="Resolved" value={summary.resolved} tone="success" />
        <StatCard
          label="Breached & open"
          value={summary.breached_open}
          tone="danger"
          sub={`${percent(summary.breach_rate)} of all issues`}
        />
        <StatCard
          label="Median fix time"
          value={formatHours(summary.median_resolution_hours)}
          sub={`p90 ${formatHours(summary.p90_resolution_hours)}`}
        />
        <StatCard
          label="Resolved on time"
          value={percent(summary.on_time_rate)}
          tone={summary.on_time_rate && summary.on_time_rate > 0.6 ? 'success' : 'warn'}
        />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader
            title="Backlog ageing"
            subtitle="How long open issues have been waiting. A fat right tail means the queue is not draining."
          />
          <div className="p-4 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.backlog_ageing} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E8EDF3" vertical={false} />
                <XAxis dataKey="bucket" tick={AXIS} axisLine={false} tickLine={false} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ borderRadius: 10, border: '1px solid #E8EDF3', fontSize: 12 }}
                  cursor={{ fill: '#F5F7FA' }}
                />
                <Bar dataKey="count" radius={[5, 5, 0, 0]}>
                  {data.backlog_ageing.map((entry, index) => (
                    <Cell
                      key={entry.bucket}
                      fill={['#4F90D0', '#4F90D0', '#D9A520', '#E07B39', '#D14343', '#8F2A2A'][index] ?? '#4F90D0'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Created vs resolved"
            subtitle="Last 30 days. When the orange line stays under the blue one, the backlog is growing."
          />
          <div className="p-4 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.trend} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E8EDF3" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={AXIS}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(value: string) => value.slice(5)}
                  interval={5}
                />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #E8EDF3', fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey="created"
                  name="Reported"
                  stroke="#2F72B8"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="resolved"
                  name="Resolved"
                  stroke="#DD7120"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <BreachTable
        title="By department"
        subtitle="Which department is missing its targets, and by how much."
        rows={data.by_department}
      />
      <BreachTable
        title="By ward"
        subtitle="Geography of neglect. The equity audit turns this into a flag."
        rows={data.by_ward}
      />
      <BreachTable
        title="By category"
        subtitle="Some problems are structurally harder to close than others."
        rows={data.by_category}
      />
    </div>
  )
}
