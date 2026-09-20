/**
 * Design-system primitives.
 *
 * Deliberately plain: a civic tool should look like infrastructure, not like a
 * consumer app. Every interactive element meets a 44px touch target and carries
 * a visible focus ring, because this has to work on a cheap phone held at a bus
 * stop and on a keyboard at a ward office.
 */

import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'
import { classNames } from '../../lib/format'

// ---------------------------------------------------------------------------
//  Button
// ---------------------------------------------------------------------------
type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'accent'
type Size = 'sm' | 'md' | 'lg'

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800 disabled:bg-brand-300 shadow-sm',
  accent:
    'bg-accent-500 text-white hover:bg-accent-600 active:bg-accent-700 disabled:bg-accent-300 shadow-sm',
  secondary:
    'bg-white text-ink-800 border border-ink-200 hover:bg-ink-50 active:bg-ink-100 disabled:text-ink-400',
  ghost: 'bg-transparent text-ink-700 hover:bg-ink-100 active:bg-ink-200 disabled:text-ink-400',
  danger:
    'bg-danger-500 text-white hover:bg-danger-600 active:bg-danger-700 disabled:bg-danger-100 shadow-sm',
}

const SIZES: Record<Size, string> = {
  sm: 'text-sm px-3 py-1.5 rounded-lg gap-1.5',
  md: 'text-sm px-4 py-2.5 rounded-lg gap-2 min-h-[44px]',
  lg: 'text-base px-5 py-3 rounded-xl gap-2 min-h-[52px] font-semibold',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: ReactNode
  block?: boolean
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  block = false,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={classNames(
        'inline-flex items-center justify-center font-medium transition-colors',
        'disabled:cursor-not-allowed select-none',
        VARIANTS[variant],
        SIZES[size],
        block && 'w-full',
        className,
      )}
    >
      {loading ? <Spinner className="h-4 w-4" /> : icon}
      {children}
    </button>
  )
}

// ---------------------------------------------------------------------------
//  Form fields
// ---------------------------------------------------------------------------
interface FieldProps {
  label?: string
  hint?: string
  error?: string
  required?: boolean
  children: ReactNode
  htmlFor?: string
}

export function Field({ label, hint, error, required, children, htmlFor }: FieldProps) {
  return (
    <div>
      {label && (
        <label className="nn-label" htmlFor={htmlFor}>
          {label}
          {required && <span className="text-danger-500 ml-0.5">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p className="text-xs text-danger-600 mt-1.5 font-medium">{error}</p>
      ) : hint ? (
        <p className="nn-hint">{hint}</p>
      ) : null}
    </div>
  )
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={classNames('nn-input', className)} />
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={classNames('nn-input resize-y', className)} />
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={classNames('nn-input pr-9 appearance-none bg-no-repeat', className)}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%234F6E93' stroke-width='2.5' stroke-linecap='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")",
        backgroundPosition: 'right 0.75rem center',
      }}
    >
      {children}
    </select>
  )
}

// ---------------------------------------------------------------------------
//  Surfaces
// ---------------------------------------------------------------------------
export function Card({
  className,
  children,
  as: Tag = 'div',
}: {
  className?: string
  children: ReactNode
  as?: 'div' | 'section' | 'article' | 'li'
}) {
  return <Tag className={classNames('nn-card', className)}>{children}</Tag>
}

export function CardHeader({
  title,
  subtitle,
  action,
  className,
}: {
  title: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={classNames(
        'flex items-start justify-between gap-4 px-5 py-4 border-b border-ink-100',
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="font-semibold text-ink-900 leading-tight">{title}</h2>
        {subtitle && <p className="text-sm text-ink-500 mt-1 leading-relaxed">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

// ---------------------------------------------------------------------------
//  Badges and chips
// ---------------------------------------------------------------------------
export function Badge({
  children,
  className,
  tone = 'neutral',
}: {
  children: ReactNode
  className?: string
  tone?: 'neutral' | 'brand' | 'success' | 'warn' | 'danger' | 'accent'
}) {
  const tones = {
    neutral: 'bg-ink-100 text-ink-700 border-ink-200',
    brand: 'bg-brand-50 text-brand-700 border-brand-100',
    success: 'bg-success-50 text-success-700 border-success-100',
    warn: 'bg-warn-50 text-warn-600 border-warn-100',
    danger: 'bg-danger-50 text-danger-700 border-danger-100',
    accent: 'bg-accent-50 text-accent-700 border-accent-100',
  }
  return (
    <span
      className={classNames(
        'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

// ---------------------------------------------------------------------------
//  Feedback
// ---------------------------------------------------------------------------
export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={classNames('animate-spin', className ?? 'h-5 w-5')}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M12 2a10 10 0 0 1 10 10h-3a7 7 0 0 0-7-7V2z"
      />
    </svg>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={classNames('nn-skeleton rounded-md', className ?? 'h-4 w-full')} />
}

export function Alert({
  tone = 'info',
  title,
  children,
  action,
}: {
  tone?: 'info' | 'success' | 'warn' | 'danger'
  title?: ReactNode
  children?: ReactNode
  action?: ReactNode
}) {
  const tones = {
    info: 'bg-brand-50 border-brand-100 text-brand-900',
    success: 'bg-success-50 border-success-100 text-success-700',
    warn: 'bg-warn-50 border-warn-100 text-warn-600',
    danger: 'bg-danger-50 border-danger-100 text-danger-700',
  }
  return (
    <div className={classNames('rounded-xl border px-4 py-3 text-sm', tones[tone])} role="status">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {title && <p className="font-semibold mb-0.5">{title}</p>}
          {children && <div className="leading-relaxed">{children}</div>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
    </div>
  )
}

export function EmptyState({
  title,
  body,
  action,
  icon,
}: {
  title: string
  body?: string
  action?: ReactNode
  icon?: ReactNode
}) {
  return (
    <div className="text-center py-14 px-6">
      {icon && <div className="mx-auto mb-4 text-ink-300">{icon}</div>}
      <p className="font-semibold text-ink-800">{title}</p>
      {body && <p className="text-sm text-ink-500 mt-1.5 max-w-sm mx-auto leading-relaxed">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="text-center py-12 px-6">
      <div className="mx-auto mb-3 h-11 w-11 rounded-full bg-danger-50 flex items-center justify-center">
        <svg className="h-6 w-6 text-danger-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <p className="text-sm text-ink-700 max-w-md mx-auto leading-relaxed">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
//  Confidence meter - shown next to every AI output
// ---------------------------------------------------------------------------
export function ConfidenceMeter({
  value,
  label,
  className,
}: {
  value: number
  label?: string
  className?: string
}) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100)
  const tone = pct >= 75 ? 'bg-success-500' : pct >= 55 ? 'bg-warn-500' : 'bg-danger-500'
  return (
    <div className={className}>
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <span className="text-xs text-ink-500">{label ?? 'Confidence'}</span>
        <span className="text-xs font-semibold tabular-nums text-ink-800">{pct}%</span>
      </div>
      <div
        className="h-1.5 rounded-full bg-ink-100 overflow-hidden"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? 'Confidence'}
      >
        <div className={classNames('h-full rounded-full transition-all', tone)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
