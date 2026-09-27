/** Shapes returned by the NagarNetra API. Mirrors backend/app/schemas.py. */

export type Band = 'P1' | 'P2' | 'P3' | 'P4'
export type IssueStatus = 'received' | 'verified' | 'assigned' | 'in_progress' | 'resolved'
export type AiSource = 'llm' | 'offline_classifier' | 'officer' | 'unresolved'
export type ReviewKind =
  | 'low_confidence_category'
  | 'duplicate_candidate'
  | 'missing_location'
  | 'unparsed'

export interface CategoryBlock {
  key: string
  label: string
  label_hi: string
  label_mr: string
  icon: string
  department: string
}

export interface HazardBlock {
  key: string
  label: string
  label_hi: string
  label_mr: string
}

export interface ScoreComponent {
  key: string
  label: string
  points: number
  detail: string
  source: 'ai' | 'citizens' | 'map' | 'policy' | 'equity'
}

export interface WardRef {
  code: string
  name: string
  zone: string
}

export interface SlaBlock {
  hours: number
  deadline: string | null
  breached: boolean
}

export interface IssueSummary {
  id: number
  issue_code: string
  title: string
  category: CategoryBlock
  sub_issue: string
  status: IssueStatus
  status_label: string
  lat: number | null
  lon: number | null
  location_text: string
  ward: WardRef | null
  report_count: number
  severity: number
  hazard_flags: HazardBlock[]
  languages: { code: string; label: string }[]
  priority: {
    score: number
    band: Band
    overridden: boolean
    equity_boost_applied: boolean
  }
  sla: SlaBlock
  department: string
  assigned_to: string | null
  created_at: string
  updated_at: string
  resolved_at: string | null
  open_reviews?: number
}

export interface ReportPublic {
  id: number
  ticket_code: string
  text: string
  summary_en: string
  language: { code: string; label: string; confidence: number }
  channel: string
  category: CategoryBlock
  severity: number | null
  hazard_flags: HazardBlock[]
  ai: {
    confidence: number
    source: AiSource
    model: string
    explanation: string
    matched_terms: string[]
  }
  location: {
    lat: number | null
    lon: number | null
    text: string
    source: string
    confidence: number
  }
  image_url: string | null
  image_analysed: boolean
  dedup: { decision: string; score: number | null; detail: Record<string, unknown> }
  redaction: { counts?: Record<string, number>; notice?: string }
  needs_review: boolean
  review_reason: string
  created_at: string
  pipeline_ms: number
}

export interface StatusEventItem {
  from_status: string | null
  to_status: IssueStatus
  to_label: string
  actor: string
  actor_role: string
  note: string
  created_at: string
}

export interface StageLog {
  stage: string
  status: 'ok' | 'fallback' | 'error' | 'skipped'
  source: string
  confidence: number | null
  output: Record<string, unknown>
  message: string
  duration_ms: number
  created_at: string
}

export interface AuditItem {
  id: number
  actor: string
  actor_role: string
  action: string
  entity_type: string
  entity_id: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  reason: string
  created_at: string
}

export interface ReviewItem {
  id: number
  kind: ReviewKind
  status: 'open' | 'resolved'
  payload: Record<string, string | number>
  report_id: number | null
  issue_id: number | null
  candidate_issue_id: number | null
  report: ReportPublic | null
  candidate_issue: IssueSummary | null
  resolved_by: string | null
  resolved_at: string | null
  reason: string
  resolution: Record<string, unknown>
  created_at: string
}

/** Response to a citizen submitting a complaint. */
export interface SubmitResponse {
  ticket_code: string
  issue_code?: string
  status?: IssueStatus
  status_label?: string
  citizen_message: string
  category?: CategoryBlock
  sub_issue?: string
  severity?: number
  hazard_flags?: HazardBlock[]
  summary_en?: string
  ai?: {
    confidence: number
    source: AiSource
    model: string
    explanation: string
    matched_terms: string[]
  }
  location?: {
    lat: number | null
    lon: number | null
    text: string
    source: string
    confidence: number
    ward: string | null
  }
  cluster?: { joined_existing: boolean; report_count: number; others: number }
  priority?: { score: number; band: Band; breakdown: ScoreComponent[] }
  sla?: SlaBlock
  department?: string
  redaction?: { counts?: Record<string, number>; notice?: string }
  review?: { needed: boolean; kinds: ReviewKind[] }
  image_url?: string | null
  pipeline_ms?: number
  needs_review?: boolean
  degraded?: boolean
}

export interface TrackResponse {
  report: ReportPublic
  issue: IssueSummary | null
  timeline: StatusEventItem[]
  priority_breakdown: ScoreComponent[]
  can_give_feedback: boolean
  feedback_given: boolean
  pipeline_status: string
  ack: AckBlock | null
}

export interface IssueDetailResponse {
  issue: IssueSummary
  priority_breakdown: ScoreComponent[]
  priority_override_reason: string | null
  reports: ReportPublic[]
  timeline: StatusEventItem[]
  stage_logs: StageLog[]
  review_tasks: ReviewItem[]
  audit: AuditItem[]
  merged_from: string[]
  merged_into: string | null
}

export interface Meta {
  app_name: string
  challenge_id: string
  city: string
  demo_mode: boolean
  categories: (CategoryBlock & { examples: string[] })[]
  hazards: HazardBlock[]
  departments: { code: string; name: string; short: string }[]
  statuses: { key: IssueStatus; label: string }[]
  languages: Record<string, string>
  speech_locales: Record<string, string>
  review_kinds: Record<string, string>
  bands: Record<Band, number>
  city_bbox: [number, number, number, number]
  policy: {
    dedup_radius_m: number
    dedup_window_days: number
    auto_merge_threshold: number
    review_threshold: number
    equity_points: number
  }
  scope_statement: string
}

export interface PublicStats {
  total_reports: number
  total_issues: number
  resolved_issues: number
  open_issues: number
  resolved_last_30_days: number
  distinct_citizens: number
  median_resolution_hours: number | null
  reports_collapsed: number
  triage_work_saved_pct: number
  by_category: { category: string; count: number }[]
  by_band: Partial<Record<Band, number>>
}

export interface MapItem {
  issue_code: string
  title: string
  category: string
  status: IssueStatus
  lat: number
  lon: number
  band: Band
  score: number
  report_count: number
  sla_breached: boolean
  ack_expired: boolean
}

export interface GroupEquity {
  key: string
  label: string
  total_issues: number
  resolved_count: number
  open_count: number
  median_resolution_hours: number | null
  breach_rate: number
  flagged: boolean
  reasons: string[]
  ratio_to_city: number | null
}

export interface EquityReport {
  city_median_resolution_hours: number | null
  city_breach_rate: number
  wards: GroupEquity[]
  languages: GroupEquity[]
  language_accuracy: {
    language: string
    label: string
    reports: number
    officer_corrections: number
    agreement_rate: number | null
  }[]
  thresholds: Record<string, number>
  flagged_ward_codes: string[]
  explanation: string
  equity_boost_note: string
}

export interface SlaGroup {
  key: string
  label: string
  open: number
  resolved: number
  breached: number
  total: number
  breach_rate: number
  median_hours: number | null
}

export interface SlaReport {
  summary: {
    total_issues: number
    open: number
    resolved: number
    breached_open: number
    breach_rate: number
    median_resolution_hours: number | null
    p90_resolution_hours: number | null
    on_time_rate: number | null
  }
  by_department: SlaGroup[]
  by_ward: SlaGroup[]
  by_category: SlaGroup[]
  backlog_ageing: { bucket: string; count: number }[]
  trend: { date: string; created: number; resolved: number }[]
}

export interface AiHealth {
  components: {
    llm_provider: string
    llm_active: boolean
    llm_model: string
    offline_classifier_trained: boolean
    embedder: string
    cached_llm_responses: number
  }
  live: {
    total_reports: number
    total_issues: number
    reports_collapsed: number
    triage_work_saved_pct: number
    by_source: Record<string, number>
    mean_confidence: number | null
    low_confidence_share: number | null
    dedup_decisions: Record<string, number>
    geocode: { resolved_rate: number | null; by_source: Record<string, number> }
    review: {
      open_by_kind: Record<string, number>
      open_total: number
      resolved_total: number
    }
    latency: {
      pipeline_p50_ms: number | null
      pipeline_p95_ms: number | null
      by_stage: {
        stage: string
        runs: number
        p50_ms: number | null
        p95_ms: number | null
        fallback_or_error: number
      }[]
    }
  }
  holdout: HoldoutReport | null
  holdout_run_at: string | null
  note: string
}

export interface HoldoutReport {
  generated_at: string
  test_set: {
    reports: number
    clusters: number
    languages: Record<string, number>
    categories: Record<string, number>
  }
  classification: {
    offline_classifier: {
      n: number
      accuracy: number
      macro_f1: number
      by_language: Record<string, { n: number; accuracy: number; macro_f1: number }>
      routed_to_human_pct: number
      median_latency_ms: number | null
      model_trained: boolean
      top_confusions: { true: string; predicted: string; count: number }[]
    }
    llm: { evaluated?: boolean; reason?: string; accuracy?: number; macro_f1?: number }
  }
  dedup: {
    reports: number
    issues_created: number
    ideal_issues: number
    auto_merge: { precision: number; recall: number; f1: number }
    with_human_review: { precision: number; recall: number; f1: number }
    triage_work_saved_pct: number
    triage_work_saved_with_review_pct: number
    best_possible_work_saved_pct: number
    decisions: Record<string, number>
    caveat: string
  }
  geocoding: { resolved_pct: number; by_source: Record<string, number> }
  geocoding_text_only: { mode: string; resolved_pct: number; by_source: Record<string, number> }
  human_review: {
    tasks_raised: number
    by_kind: Record<string, number>
    share_of_reports_pct: number
  }
  latency: {
    pipeline_p50_ms: number | null
    pipeline_p95_ms: number | null
    by_stage: Record<string, { p50_ms: number | null; p95_ms: number | null }>
  }
}

export interface Officer {
  username: string
  display_name: string
  role: string
  department: string
}

export interface WardListItem {
  code: string
  name: string
  zone: string
  population: number
  area_sq_km: number
  centroid: { lat: number; lon: number }
  open_issues: number
}
