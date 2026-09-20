/**
 * Officer dashboard shell: sidebar navigation, auth guard, live review badge.
 *
 * Desktop-first, unlike the citizen app: this is a workstation tool for someone
 * triaging a queue all day. It still collapses to a usable single column on a
 * tablet.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Badge, Button, Spinner } from '../components/ui/primitives'
import { ApiError, api, getToken, setToken } from '../lib/api'
import { classNames } from '../lib/format'
import type { Officer } from '../lib/types'

interface AdminContextValue {
  officer: Officer
  reviewCount: number
  refreshReviewCount: () => void
  demoMode: boolean
  llmActive: boolean
}

const AdminContext = createContext<AdminContextValue | null>(null)

export function useAdmin(): AdminContextValue {
  const context = useContext(AdminContext)
  if (!context) throw new Error('useAdmin must be used inside the officer dashboard')
  return context
}

const NAV = [
  {
    to: '/admin',
    end: true,
    label: 'Priority queue',
    icon: (
      <path d="M4 6h16M4 12h10M4 18h7" strokeLinecap="round" />
    ),
  },
  {
    to: '/admin/review',
    label: 'Human review',
    badge: true,
    icon: (
      <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM12 8v5M12 16h.01" strokeLinecap="round" />
    ),
  },
  {
    to: '/admin/sla',
    label: 'SLA performance',
    icon: <path d="M3 20h18M6 20V10M11 20V4M16 20v-7M21 20v-4" strokeLinecap="round" />,
  },
  {
    to: '/admin/equity',
    label: 'Equity audit',
    icon: (
      <path d="M12 3v18M5 7h14M7 7l-3 7h6l-3-7zM17 7l-3 7h6l-3-7z" strokeLinecap="round" strokeLinejoin="round" />
    ),
  },
  {
    to: '/admin/ai-health',
    label: 'AI health',
    icon: (
      <path d="M12 2a3 3 0 0 1 3 3v1h1a3 3 0 0 1 0 6h-1v1a3 3 0 1 1-6 0v-1H8a3 3 0 0 1 0-6h1V5a3 3 0 0 1 3-3z" strokeLinejoin="round" />
    ),
  },
  {
    to: '/admin/audit',
    label: 'Audit log',
    icon: (
      <path d="M9 12h6M9 16h6M9 8h2M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" strokeLinecap="round" strokeLinejoin="round" />
    ),
  },
]

export default function AdminShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const [officer, setOfficer] = useState<Officer | null>(null)
  const [checking, setChecking] = useState(true)
  const [reviewCount, setReviewCount] = useState(0)
  const [flags, setFlags] = useState({ demoMode: false, llmActive: false })
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  const refreshReviewCount = useCallback(() => {
    api
      .reviewQueue({ status: 'open', limit: 1 })
      .then((payload) => setReviewCount(payload.open_total))
      .catch(() => setReviewCount(0))
  }, [])

  useEffect(() => {
    if (!getToken()) {
      navigate('/admin/login', { replace: true, state: { from: location.pathname } })
      return
    }
    api
      .me()
      .then((me) => {
        setOfficer(me)
        refreshReviewCount()
        api
          .settings()
          .then((s) => setFlags({ demoMode: s.demo_mode, llmActive: s.llm_active }))
          .catch(() => undefined)
      })
      .catch((caught) => {
        if (caught instanceof ApiError && caught.status === 401) {
          navigate('/admin/login', { replace: true })
        }
      })
      .finally(() => setChecking(false))
    // Re-checking on every navigation would be wasteful; the token is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    setMobileNavOpen(false)
  }, [location.pathname])

  const value = useMemo<AdminContextValue | null>(
    () =>
      officer
        ? {
            officer,
            reviewCount,
            refreshReviewCount,
            demoMode: flags.demoMode,
            llmActive: flags.llmActive,
          }
        : null,
    [officer, reviewCount, refreshReviewCount, flags],
  )

  if (checking || !value) {
    return (
      <div className="min-h-screen flex items-center justify-center text-brand-600">
        <Spinner className="h-7 w-7" />
      </div>
    )
  }

  const nav = (
    <nav className="space-y-0.5">
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            classNames(
              'flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
              isActive
                ? 'bg-white/10 text-white'
                : 'text-white/60 hover:text-white hover:bg-white/5',
            )
          }
        >
          <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            {item.icon}
          </svg>
          <span className="flex-1">{item.label}</span>
          {item.badge && reviewCount > 0 && (
            <span className="rounded-full bg-accent-500 text-white text-2xs font-bold px-1.5 py-0.5 min-w-[20px] text-center">
              {reviewCount}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  )

  return (
    <AdminContext.Provider value={value}>
      <div className="min-h-screen bg-ink-50 flex">
        {/* Sidebar */}
        <aside
          className={classNames(
            'bg-ink-900 text-white w-60 shrink-0 flex-col fixed inset-y-0 left-0 z-40 transition-transform lg:static lg:translate-x-0 lg:flex',
            mobileNavOpen ? 'flex translate-x-0' : 'flex -translate-x-full lg:translate-x-0',
          )}
        >
          <div className="px-4 py-4 border-b border-white/10">
            <p className="font-semibold leading-tight">NagarNetra</p>
            <p className="text-2xs text-white/50 mt-0.5">Officer dashboard · PS-18</p>
          </div>

          <div className="flex-1 overflow-y-auto nn-scroll px-2 py-3">{nav}</div>

          <div className="px-3 py-3 border-t border-white/10 space-y-2">
            <div className="flex items-center gap-2">
              <span className="h-8 w-8 rounded-full bg-brand-600 text-white flex items-center justify-center text-xs font-semibold shrink-0">
                {value.officer.display_name.slice(0, 1)}
              </span>
              <div className="min-w-0">
                <p className="text-xs font-medium truncate">{value.officer.display_name}</p>
                <p className="text-2xs text-white/50 capitalize">{value.officer.role}</p>
              </div>
            </div>
            <div className="flex flex-wrap gap-1">
              <span className="text-2xs rounded bg-white/10 px-1.5 py-0.5 text-white/70">
                {value.llmActive ? 'LLM on' : 'Offline AI'}
              </span>
              {value.demoMode && (
                <span className="text-2xs rounded bg-accent-500/20 px-1.5 py-0.5 text-accent-200">
                  demo mode
                </span>
              )}
            </div>
            <Button
              size="sm"
              variant="ghost"
              block
              className="text-white/60 hover:text-white hover:bg-white/10 justify-start"
              onClick={() => {
                setToken(null)
                navigate('/admin/login', { replace: true })
              }}
            >
              Sign out
            </Button>
          </div>
        </aside>

        {mobileNavOpen && (
          <div
            className="fixed inset-0 bg-ink-950/40 z-30 lg:hidden"
            onClick={() => setMobileNavOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Content */}
        <div className="flex-1 min-w-0 flex flex-col">
          <div className="lg:hidden sticky top-0 z-20 bg-white border-b border-ink-100 px-3 py-2 flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation">
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
              </svg>
            </Button>
            <span className="font-semibold text-ink-900">NagarNetra</span>
            {reviewCount > 0 && <Badge tone="accent">{reviewCount} to review</Badge>}
          </div>

          <div className="flex-1 min-w-0">
            <Outlet />
          </div>

          <footer className="px-6 py-4 text-2xs text-ink-400 border-t border-ink-100 bg-white leading-relaxed">
            Decision-support tool for municipal staff. Not an autonomous enforcement system. Final
            decisions rest with officers. · PS-18 CivicFix · Demo authentication — not a production
            identity system.
          </footer>
        </div>
      </div>
    </AdminContext.Provider>
  )
}
