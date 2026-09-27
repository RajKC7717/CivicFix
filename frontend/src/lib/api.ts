/**
 * API client.
 *
 * Two things every call gets for free:
 *  - a typed, readable error rather than an unhandled rejection, so the UI can
 *    always show the citizen or the officer something honest;
 *  - the officer bearer token, when one is stored.
 *
 * Requests go to a relative path. In development Vite proxies /api to the
 * FastAPI server, so there is one origin and no CORS in the demo path.
 */

import type {
  AiHealth,
  AuditItem,
  EquityReport,
  IssueDetailResponse,
  IssueSummary,
  MapItem,
  Meta,
  Officer,
  PublicStats,
  ReviewItem,
  SlaReport,
  SubmitResponse,
  TrackResponse,
  WardListItem,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''
const TOKEN_KEY = 'nagarnetra.officer.token'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private browsing - the session simply will not persist */
  }
}

/** A stable per-browser id so we can count distinct citizens without identifying one. */
export function deviceRef(): string {
  const key = 'nagarnetra.device'
  try {
    let value = localStorage.getItem(key)
    if (!value) {
      value = `d-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`
      localStorage.setItem(key, value)
    }
    return value
  } catch {
    return 'anonymous'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(
      'Could not reach the NagarNetra server. Check that the backend is running.',
      0,
    )
  }

  if (response.status === 204) return undefined as T

  const raw = await response.text()
  let payload: unknown = null
  if (raw) {
    try {
      payload = JSON.parse(raw)
    } catch {
      payload = raw
    }
  }

  if (!response.ok) {
    if (response.status === 401) setToken(null)
    throw new ApiError(extractMessage(payload, response.status), response.status)
  }
  return payload as T
}

/** FastAPI returns `detail` as a string or as a list of validation errors. */
function extractMessage(payload: unknown, status: number): string {
  if (typeof payload === 'string' && payload) return payload
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string } | undefined
      if (first?.msg) return first.msg.replace(/^Value error,\s*/, '')
    }
  }
  return `Request failed (${status})`
}

// ---------------------------------------------------------------------------
//  Public
// ---------------------------------------------------------------------------
export const api = {
  meta: () => request<Meta>('/api/meta'),
  health: () => request<Record<string, unknown>>('/api/health'),
  policyDocument: () => request<{ filename: string; content: string }>('/api/meta/policy'),
  stats: () => request<PublicStats>('/api/public/stats'),
  wards: () => request<{ items: WardListItem[]; boundary_note: string }>('/api/public/wards'),
  publicMap: (params: { status?: string; category?: string } = {}) =>
    request<{ count: number; items: MapItem[] }>(`/api/public/map${qs(params)}`),

  submitComplaint: (form: FormData) =>
    request<SubmitResponse>('/api/complaints', { method: 'POST', body: form }),
  track: (ticket: string) => request<TrackResponse>(`/api/complaints/${encodeURIComponent(ticket)}`),
  feedback: (ticket: string, body: { rating: number; comment: string }) =>
    request<{ ok: boolean; message: string }>(
      `/api/complaints/${encodeURIComponent(ticket)}/feedback`,
      { method: 'POST', body: JSON.stringify(body) },
    ),

  emailDraft: (ticket: string) =>
    request<EmailDraftResponse>(`/api/complaints/${encodeURIComponent(ticket)}/email-draft`),
  sendEmail: (ticket: string, body: { to_email: string; subject: string; body: string; citizen_email: string }) => {
    const form = new FormData()
    form.append('to_email', body.to_email)
    form.append('subject', body.subject)
    form.append('body', body.body)
    form.append('citizen_email', body.citizen_email)
    return request<{ ok: boolean; status: string; message: string }>(
      `/api/complaints/${encodeURIComponent(ticket)}/send-email`,
      { method: 'POST', body: form },
    )
  },
  notifications: (ticket: string) =>
    request<{ items: NotificationItem[] }>(`/api/complaints/${encodeURIComponent(ticket)}/notifications`),

  // -------------------------------------------------------------------------
  //  Auth
  // -------------------------------------------------------------------------
  login: (username: string, password: string) =>
    request<{ token: string; officer: Officer; notice: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<Officer>('/api/auth/me'),

  // -------------------------------------------------------------------------
  //  Officer
  // -------------------------------------------------------------------------
  issues: (params: Record<string, string | number | boolean | undefined>) =>
    request<{ total: number; limit: number; offset: number; items: IssueSummary[] }>(
      `/api/admin/issues${qs(params)}`,
    ),
  issue: (code: string) => request<IssueDetailResponse>(`/api/admin/issues/${code}`),
  changeStatus: (code: string, body: { status: string; note: string }) =>
    request<{ ok: boolean; issue: IssueSummary }>(`/api/admin/issues/${code}/status`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  assign: (code: string, body: { department: string; assigned_to: string; note: string }) =>
    request<{ ok: boolean; issue: IssueSummary }>(`/api/admin/issues/${code}/assign`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  overrideCategory: (code: string, body: { category: string; reason: string }) =>
    request<{ ok: boolean; issue: IssueSummary }>(
      `/api/admin/issues/${code}/override-category`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  overridePriority: (code: string, body: { band: string | null; reason: string }) =>
    request<{ ok: boolean; issue: IssueSummary }>(
      `/api/admin/issues/${code}/override-priority`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  mergeIssue: (code: string, body: { target_issue_code: string; reason: string }) =>
    request<{ ok: boolean; merged_reports: number; target: IssueSummary }>(
      `/api/admin/issues/${code}/merge`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  unmergeReport: (reportId: number, reason: string) =>
    request<{ ok: boolean; new_issue: IssueSummary }>(
      `/api/admin/reports/${reportId}/unmerge`,
      { method: 'POST', body: JSON.stringify({ reason, target_issue_code: '' }) },
    ),

  reviewQueue: (params: { kind?: string; status?: string; limit?: number } = {}) =>
    request<{
      items: ReviewItem[]
      open_counts: Record<string, number>
      open_total: number
    }>(`/api/admin/review${qs(params)}`),
  resolveReview: (
    id: number,
    body: {
      action: string
      reason: string
      category?: string
      lat?: number
      lon?: number
      location_text?: string
    },
  ) =>
    request<{ ok: boolean; resolution: Record<string, unknown> }>(
      `/api/admin/review/${id}/resolve`,
      { method: 'POST', body: JSON.stringify(body) },
    ),

  audit: (params: { limit?: number; offset?: number; action?: string } = {}) =>
    request<{ total: number; items: AuditItem[]; actions: string[] }>(
      `/api/admin/audit${qs(params)}`,
    ),

  settings: () =>
    request<{
      equity_boost_enabled: boolean
      demo_mode: boolean
      llm_provider: string
      llm_active: boolean
    }>('/api/admin/settings'),
  updateSettings: (body: { equity_boost_enabled: boolean; reason: string }) =>
    request<{ ok: boolean; equity_boost_enabled: boolean; issues_rescored: number }>(
      '/api/admin/settings',
      { method: 'PATCH', body: JSON.stringify(body) },
    ),
  demoReset: () =>
    request<Record<string, number | boolean>>('/api/admin/demo/reset', { method: 'POST' }),

  // -------------------------------------------------------------------------
  //  Analytics
  // -------------------------------------------------------------------------
  sla: () => request<SlaReport>('/api/analytics/sla'),
  equity: () => request<EquityReport>('/api/analytics/equity'),
  aiHealth: () => request<AiHealth>('/api/analytics/ai-health'),
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '' && value !== null) search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}
