/** Layout for the citizen-facing app: mobile-first, high contrast, three languages. */

import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { LANGUAGE_OPTIONS, useI18n } from '../i18n'
import { classNames } from '../lib/format'

function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      {/* An eye over a city skyline - "the city's eye". */}
      <rect width="32" height="32" rx="8" fill="#0B2239" />
      <path d="M6 23h4v-6h3v6h3v-9h3v9h3v-5h4v5" stroke="#4F90D0" strokeWidth="1.6" fill="none" strokeLinejoin="round" />
      <ellipse cx="16" cy="11.5" rx="7.5" ry="4.5" stroke="#DD7120" strokeWidth="1.8" fill="none" />
      <circle cx="16" cy="11.5" r="2" fill="#DD7120" />
    </svg>
  )
}

export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const { lang, setLang, t } = useI18n()
  return (
    <div
      className={classNames(
        'inline-flex rounded-lg bg-white/10 p-0.5',
        compact ? 'text-xs' : 'text-sm',
      )}
      role="group"
      aria-label={t('language')}
    >
      {LANGUAGE_OPTIONS.map((option) => (
        <button
          key={option.code}
          onClick={() => setLang(option.code)}
          aria-pressed={lang === option.code}
          className={classNames(
            'px-2.5 py-1 rounded-md font-medium transition-colors',
            lang === option.code
              ? 'bg-white text-ink-900 shadow-sm'
              : 'text-white/80 hover:text-white hover:bg-white/10',
          )}
        >
          {option.native}
        </button>
      ))}
    </div>
  )
}

export default function CitizenShell() {
  const { t } = useI18n()
  const location = useLocation()

  const links = [
    { to: '/report', label: t('nav_report') },
    { to: '/track', label: t('nav_track') },
    { to: '/map', label: t('nav_map') },
  ]

  return (
    <div className="min-h-screen flex flex-col bg-ink-50">
      <header className="bg-ink-900 text-white sticky top-0 z-30">
        <div className="mx-auto max-w-5xl px-4">
          <div className="flex items-center justify-between h-14 gap-3">
            <Link to="/" className="flex items-center gap-2.5 min-w-0">
              <Logo className="h-8 w-8 shrink-0" />
              <span className="min-w-0">
                <span className="block font-semibold leading-tight truncate">{t('appName')}</span>
                <span className="block text-2xs text-white/60 leading-tight truncate">
                  {t('tagline')}
                </span>
              </span>
            </Link>
            <div className="flex items-center gap-2">
              <LanguageSwitcher compact />
              <Link
                to="/admin"
                className="hidden sm:inline-flex items-center gap-1.5 text-xs text-white/70 hover:text-white px-2.5 py-1.5 rounded-lg hover:bg-white/10 transition-colors"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
                {t('nav_officer')}
              </Link>
            </div>
          </div>
          <nav className="flex gap-1 -mb-px overflow-x-auto nn-scroll">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  classNames(
                    'px-3 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
                    isActive || (link.to === '/report' && location.pathname.startsWith('/ticket'))
                      ? 'border-accent-400 text-white'
                      : 'border-transparent text-white/60 hover:text-white',
                  )
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="bg-ink-900 text-white/70 mt-12">
        <div className="mx-auto max-w-5xl px-4 py-8">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div className="max-w-md">
              <div className="flex items-center gap-2 mb-2">
                <Logo className="h-6 w-6" />
                <span className="font-semibold text-white">{t('appName')}</span>
              </div>
              <p className="text-xs leading-relaxed">{t('scope_notice')}</p>
            </div>
            <div className="text-xs space-y-1">
              <p className="font-semibold text-white/90">Challenge {t('challenge')}</p>
              <p>Global SDG + AI Hackathon 2026</p>
              <p>SDG 11 · Sustainable Cities</p>
              <p>SDG 16 · Accountable Institutions</p>
            </div>
          </div>
          <p className="text-2xs text-white/40 mt-6 pt-5 border-t border-white/10 leading-relaxed">
            Prototype built for demonstration. Complaint data shown is synthetic. Ward boundaries are
            synthetic and are not Pune Municipal Corporation electoral wards.
          </p>
        </div>
      </footer>
    </div>
  )
}
