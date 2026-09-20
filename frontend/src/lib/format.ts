/** Formatting helpers shared by the citizen app and the officer dashboard. */

import type { Band } from './types'

export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null
  // The API emits ISO-8601; naive values from SQLite are UTC by convention.
  const normalised = /[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`
  const date = new Date(normalised)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return '-'
  return date.toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDate(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return '-'
  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

/** "just now" / "4 h ago" / "3 days ago" - deliberately terse for dense tables. */
export function timeAgo(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return '-'
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ago`
  const months = Math.floor(days / 30)
  return `${months} month${months === 1 ? '' : 's'} ago`
}

export function formatHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return '-'
  if (Math.abs(hours) < 1) return `${Math.round(hours * 60)} min`
  if (Math.abs(hours) < 48) return `${hours.toFixed(hours < 10 ? 1 : 0)} h`
  return `${(hours / 24).toFixed(1)} days`
}

export function percent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return '-'
  return `${(value * 100).toFixed(digits)}%`
}

export function compactNumber(value: number): string {
  if (value < 1000) return String(value)
  if (value < 100000) return `${(value / 1000).toFixed(1)}k`
  return `${(value / 100000).toFixed(1)}L` // lakh - the unit an Indian officer reads
}

/** Tailwind classes per priority band. One place, so the colour never drifts. */
export const BAND_STYLES: Record<Band, { dot: string; chip: string; bar: string; label: string }> = {
  P1: { dot: 'bg-p1', chip: 'bg-danger-50 text-danger-700 border-danger-100', bar: 'bg-p1', label: 'Critical' },
  P2: { dot: 'bg-p2', chip: 'bg-accent-50 text-accent-700 border-accent-100', bar: 'bg-p2', label: 'High' },
  P3: { dot: 'bg-p3', chip: 'bg-warn-50 text-warn-600 border-warn-100', bar: 'bg-p3', label: 'Medium' },
  P4: { dot: 'bg-p4', chip: 'bg-brand-50 text-brand-700 border-brand-100', bar: 'bg-p4', label: 'Low' },
}

export const BAND_HEX: Record<Band, string> = {
  P1: '#D14343',
  P2: '#E07B39',
  P3: '#D9A520',
  P4: '#4F90D0',
}

export const STATUS_STYLES: Record<string, string> = {
  received: 'bg-ink-100 text-ink-700',
  verified: 'bg-brand-50 text-brand-700',
  assigned: 'bg-accent-50 text-accent-700',
  in_progress: 'bg-warn-50 text-warn-600',
  resolved: 'bg-success-50 text-success-700',
}

/** Where an AI output came from - shown next to every machine decision. */
export const SOURCE_LABELS: Record<string, string> = {
  llm: 'Claude',
  offline_classifier: 'Offline classifier',
  officer: 'Officer',
  unresolved: 'Not classified',
}

export const SOURCE_STYLES: Record<string, string> = {
  ai: 'bg-brand-50 text-brand-700 border-brand-100',
  citizens: 'bg-success-50 text-success-700 border-success-100',
  map: 'bg-ink-100 text-ink-700 border-ink-200',
  policy: 'bg-warn-50 text-warn-600 border-warn-100',
  equity: 'bg-accent-50 text-accent-700 border-accent-100',
}

export function classNames(...values: (string | false | null | undefined)[]): string {
  return values.filter(Boolean).join(' ')
}

/** Human label for the SLA position of an issue. */
export function slaLabel(deadline: string | null, breached: boolean): string {
  const date = parseDate(deadline)
  if (!date) return 'No deadline'
  const hours = (date.getTime() - Date.now()) / 3600000
  if (breached || hours < 0) return `Overdue by ${formatHours(Math.abs(hours))}`
  return `${formatHours(hours)} left`
}
