/** Officer sign-in. Demo credentials, and the page says so plainly. */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Alert, Button, Card, Field, Input } from '../components/ui/primitives'
import { api, setToken } from '../lib/api'

const DEMO_ACCOUNTS = [
  { username: 'officer', password: 'officer', role: 'Ward officer' },
  { username: 'roads', password: 'roads', role: 'Roads department' },
  { username: 'commissioner', password: 'commissioner', role: 'Commissioner (admin)' },
]

export default function Login() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('officer')
  const [password, setPassword] = useState('officer')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const result = await api.login(username, password)
      setToken(result.token)
      navigate('/admin', { replace: true })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-ink-900 flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-2.5 text-white">
            <svg viewBox="0 0 32 32" className="h-10 w-10" aria-hidden="true">
              <rect width="32" height="32" rx="8" fill="#123252" />
              <path d="M6 23h4v-6h3v6h3v-9h3v9h3v-5h4v5" stroke="#4F90D0" strokeWidth="1.6" fill="none" strokeLinejoin="round" />
              <ellipse cx="16" cy="11.5" rx="7.5" ry="4.5" stroke="#DD7120" strokeWidth="1.8" fill="none" />
              <circle cx="16" cy="11.5" r="2" fill="#DD7120" />
            </svg>
            <div className="text-left">
              <p className="font-semibold leading-tight">NagarNetra</p>
              <p className="text-2xs text-white/50">Officer dashboard</p>
            </div>
          </div>
        </div>

        <Card className="p-6">
          <h1 className="text-lg font-semibold text-ink-900">Sign in</h1>
          <p className="text-sm text-ink-500 mt-1">Municipal grievance triage console</p>

          <form onSubmit={submit} className="space-y-4 mt-5">
            <Field label="Username" htmlFor="username">
              <Input
                id="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                autoFocus
              />
            </Field>
            <Field label="Password" htmlFor="password">
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
              />
            </Field>
            {error && <Alert tone="danger">{error}</Alert>}
            <Button type="submit" block loading={busy}>
              Sign in
            </Button>
          </form>

          <div className="mt-5 pt-4 border-t border-ink-100">
            <p className="text-xs font-medium text-ink-700 mb-2">Demo accounts</p>
            <div className="space-y-1">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  key={account.username}
                  type="button"
                  onClick={() => {
                    setUsername(account.username)
                    setPassword(account.password)
                  }}
                  className="w-full text-left rounded-lg px-2.5 py-1.5 hover:bg-ink-50 transition-colors"
                >
                  <span className="font-mono text-xs text-ink-800">
                    {account.username} / {account.password}
                  </span>
                  <span className="block text-2xs text-ink-500">{account.role}</span>
                </button>
              ))}
            </div>
          </div>
        </Card>

        <Alert tone="warn" title="Demo authentication">
          <p className="text-xs leading-relaxed">
            Credentials are hardcoded and shown above on purpose. A real deployment would federate
            to the corporation&apos;s identity provider. Every action you take here is still
            attributed to the account you sign in as, and written to the audit log.
          </p>
        </Alert>

        <p className="text-center mt-5">
          <Link to="/" className="text-sm text-white/60 hover:text-white">
            ← Back to the citizen app
          </Link>
        </p>
      </div>
    </div>
  )
}
