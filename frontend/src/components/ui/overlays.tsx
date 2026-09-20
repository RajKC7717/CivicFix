/** Modal dialog and toast notifications. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { classNames } from '../../lib/format'
import { Button } from './primitives'

// ---------------------------------------------------------------------------
//  Modal
// ---------------------------------------------------------------------------
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
}) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    // Move focus into the dialog so the keyboard path works.
    window.setTimeout(() => panelRef.current?.focus(), 0)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
    }
  }, [open, onClose])

  if (!open) return null

  const widths = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div
        className="absolute inset-0 bg-ink-950/40 backdrop-blur-[2px] animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        className={classNames(
          'relative w-full bg-white shadow-pop animate-slide-up outline-none',
          'rounded-t-2xl sm:rounded-2xl max-h-[92vh] flex flex-col',
          widths[size],
        )}
      >
        <div className="px-5 pt-5 pb-3 border-b border-ink-100">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-ink-900 leading-tight">{title}</h2>
              {description && (
                <p className="text-sm text-ink-500 mt-1 leading-relaxed">{description}</p>
              )}
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              className="shrink-0 -mr-1 -mt-1 h-9 w-9 rounded-lg text-ink-400 hover:bg-ink-100 hover:text-ink-700 flex items-center justify-center transition"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
        <div className="px-5 py-4 overflow-y-auto nn-scroll flex-1">{children}</div>
        {footer && (
          <div className="px-5 py-4 border-t border-ink-100 bg-ink-50/60 rounded-b-2xl flex flex-wrap justify-end gap-2">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}

// ---------------------------------------------------------------------------
//  Toast
// ---------------------------------------------------------------------------
type ToastTone = 'success' | 'error' | 'info'
interface Toast {
  id: number
  tone: ToastTone
  message: string
}

const ToastContext = createContext<{
  push: (message: string, tone?: ToastTone) => void
} | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const counter = useRef(0)

  const push = useCallback((message: string, tone: ToastTone = 'info') => {
    const id = ++counter.current
    setToasts((current) => [...current, { id, tone, message }])
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, tone === 'error' ? 7000 : 4200)
  }, [])

  const value = useMemo(() => ({ push }), [push])

  const tones: Record<ToastTone, string> = {
    success: 'bg-success-700 text-white',
    error: 'bg-danger-700 text-white',
    info: 'bg-ink-900 text-white',
  }

  return (
    <ToastContext.Provider value={value}>
      {children}
      {createPortal(
        <div
          className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[60] flex flex-col items-center gap-2 px-4 w-full max-w-md pointer-events-none"
          aria-live="polite"
          aria-atomic="true"
        >
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={classNames(
                'pointer-events-auto w-full rounded-xl px-4 py-3 text-sm shadow-pop animate-slide-up',
                tones[toast.tone],
              )}
            >
              {toast.message}
            </div>
          ))}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside <ToastProvider>')
  return context
}

// ---------------------------------------------------------------------------
//  Reason-required confirmation
// ---------------------------------------------------------------------------
/**
 * Every officer override in NagarNetra needs a written reason. This dialog is
 * the only way to submit one, so the rule cannot be bypassed by accident.
 */
export function ReasonDialog({
  open,
  title,
  description,
  confirmLabel = 'Save and record',
  minLength = 8,
  onCancel,
  onConfirm,
  children,
  busy = false,
}: {
  open: boolean
  title: ReactNode
  description?: ReactNode
  confirmLabel?: string
  minLength?: number
  onCancel: () => void
  onConfirm: (reason: string) => void
  children?: ReactNode
  busy?: boolean
}) {
  const [reason, setReason] = useState('')
  useEffect(() => {
    if (open) setReason('')
  }, [open])

  const tooShort = reason.trim().length < minLength

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => onConfirm(reason.trim())} disabled={tooShort} loading={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {children}
        <div>
          <label className="nn-label" htmlFor="override-reason">
            Reason for this change <span className="text-danger-500">*</span>
          </label>
          <textarea
            id="override-reason"
            className="nn-input resize-y"
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="e.g. Site visit showed this is a drainage chamber, not a road defect."
          />
          <p className="nn-hint">
            This is written to the audit log with your name and the time, and cannot be edited or
            deleted afterwards. {tooShort && `At least ${minLength} characters.`}
          </p>
        </div>
      </div>
    </Modal>
  )
}
