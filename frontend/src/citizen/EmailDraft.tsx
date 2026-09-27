/**
 * Email draft component shown after complaint submission.
 *
 * Generates a professional email draft addressed to the relevant PMC department,
 * allows the citizen to edit it, and sends it via the backend API.
 */

import { useCallback, useEffect, useState } from 'react'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { useToast } from '../components/ui/overlays'
import { Alert, Button, Card, CardHeader, Field, Input, Textarea } from '../components/ui/primitives'
import type { EmailDraftResponse } from '../lib/types'

export default function EmailDraft({ ticketCode }: { ticketCode: string }) {
  const { t } = useI18n()
  const toast = useToast()

  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [draft, setDraft] = useState<EmailDraftResponse | null>(null)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [citizenEmail, setCitizenEmail] = useState('')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)

  const loadDraft = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.emailDraft(ticketCode)
      setDraft(data)
      setSubject(data.subject)
      setBody(data.body)
    } catch {
      toast.push(t('error_generic'), 'error')
    } finally {
      setLoading(false)
    }
  }, [ticketCode, t, toast])

  useEffect(() => {
    if (open && !draft) void loadDraft()
  }, [open, draft, loadDraft])

  async function handleSend() {
    if (!draft || !subject.trim() || !body.trim()) return
    setSending(true)
    try {
      const result = await api.sendEmail(ticketCode, {
        to_email: draft.recipient.email,
        subject: subject.trim(),
        body: body.trim(),
        citizen_email: citizenEmail.trim(),
      })
      setSent(true)
      toast.push(
        result.status === 'demo' ? t('email_sent_demo') : t('email_sent_success'),
        'success',
      )
    } catch {
      toast.push(t('email_failed'), 'error')
    } finally {
      setSending(false)
    }
  }

  function handleCopy() {
    const full = `To: ${draft?.recipient.email}\nSubject: ${subject}\n\n${body}`
    navigator.clipboard?.writeText(full).then(
      () => toast.push(t('email_copied'), 'success'),
      () => toast.push(t('error_generic'), 'error'),
    )
  }

  if (sent) {
    return (
      <Alert tone="success" title={t('email_sent_success')}>
        <p className="text-xs">
          {t('email_recipient')}: {draft?.recipient.email}
        </p>
      </Alert>
    )
  }

  return (
    <Card className="border-brand-200">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full px-5 py-4 flex items-center justify-between gap-3 text-left hover:bg-ink-50 transition-colors rounded-xl"
      >
        <div className="flex items-center gap-3">
          <span className="h-9 w-9 rounded-lg bg-brand-100 text-brand-600 flex items-center justify-center shrink-0">
            <svg className="h-4.5 w-4.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" strokeLinecap="round" strokeLinejoin="round" />
              <path d="m22 6-10 7L2 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <div>
            <p className="font-semibold text-ink-900 text-sm">{t(open ? 'email_collapse' : 'email_expand')}</p>
            <p className="text-xs text-ink-500 mt-0.5">{t('email_subtitle')}</p>
          </div>
        </div>
        <svg
          className={`h-4 w-4 text-ink-400 transition-transform ${open ? 'rotate-180' : ''}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="px-5 pb-5 space-y-4 border-t border-ink-100 pt-4">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <div className="h-6 w-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}

          {draft && !loading && (
            <>
              {/* Recipient info */}
              <div className="rounded-lg bg-ink-50 border border-ink-100 p-4">
                <p className="text-xs font-medium text-ink-500 mb-2">{t('email_recipient')}</p>
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-ink-900">{draft.recipient.department}</p>
                  <p className="text-xs text-ink-700">{draft.recipient.designation}</p>
                  <p className="text-xs font-mono text-brand-700 bg-brand-50 rounded px-2 py-1 inline-block">
                    {draft.recipient.email}
                  </p>
                  <p className="text-xs text-ink-500">{draft.recipient.office}</p>
                  {draft.recipient.phone && (
                    <p className="text-xs text-ink-500">☎ {draft.recipient.phone}</p>
                  )}
                </div>
                <p className="text-2xs text-ink-400 mt-2 italic">{draft.note}</p>
              </div>

              {/* Citizen email */}
              <Field label={t('email_your_email')} hint={t('email_your_email_hint')}>
                <Input
                  type="email"
                  value={citizenEmail}
                  onChange={(e) => setCitizenEmail(e.target.value)}
                  placeholder="your.email@example.com"
                />
              </Field>

              {/* Subject */}
              <Field label={t('email_subject')}>
                <Input
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                />
              </Field>

              {/* Body */}
              <Field label={t('email_body')} hint={t('email_edit_hint')}>
                <Textarea
                  rows={16}
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  className="font-mono text-xs leading-relaxed"
                />
              </Field>

              {/* Actions */}
              <div className="flex flex-wrap gap-3 pt-1">
                <Button
                  onClick={handleSend}
                  disabled={!subject.trim() || !body.trim()}
                  loading={sending}
                  className="flex-1 min-w-[160px]"
                >
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="m22 2-7 20-4-9-9-4 20-7z" strokeLinejoin="round" />
                    <path d="m22 2-11 11" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {sending ? t('email_sending') : t('email_send')}
                </Button>
                <Button variant="secondary" onClick={handleCopy} className="flex-1 min-w-[160px]">
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {t('email_copy')}
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </Card>
  )
}
