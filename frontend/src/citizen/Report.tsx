/**
 * The complaint form.
 *
 * Design rules, in priority order:
 *  1. The textarea always works. Voice and photo are additions that can fail
 *     without blocking anyone.
 *  2. Location has three independent routes - GPS, a map pin, or a landmark in
 *     words - because a citizen may have denied location permission, be indoors,
 *     or simply be reporting a place they are not standing in.
 *  3. Nothing is required except *some* description. An incomplete complaint is
 *     accepted and routed to a human, never refused.
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapView, PinMarker, WardBoundaries, useWardGeometry, CITY_CENTER } from '../components/MapView'
import { Alert, Button, Card, Field, Input, Textarea } from '../components/ui/primitives'
import { useToast } from '../components/ui/overlays'
import { useI18n } from '../i18n'
import { api, deviceRef } from '../lib/api'
import { classNames } from '../lib/format'
import { useSpeech } from '../lib/useSpeech'
import type { Meta } from '../lib/types'

type LocationMode = 'gps' | 'pin' | 'text'

export default function Report() {
  const { t, lang } = useI18n()
  const navigate = useNavigate()
  const toast = useToast()

  const [meta, setMeta] = useState<Meta | null>(null)
  const [text, setText] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)
  const [consentExif, setConsentExif] = useState(false)
  const [mode, setMode] = useState<LocationMode>('gps')
  const [coords, setCoords] = useState<[number, number] | null>(null)
  const [gpsState, setGpsState] = useState<'idle' | 'working' | 'done' | 'denied'>('idle')
  const [landmark, setLandmark] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [usedVoice, setUsedVoice] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const wards = useWardGeometry()

  const speech = useSpeech((finalText) => {
    setUsedVoice(true)
    setText((current) => (current ? `${current} ${finalText}` : finalText))
  })

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setMeta(null))
  }, [])

  useEffect(() => {
    return () => {
      if (photoPreview) URL.revokeObjectURL(photoPreview)
    }
  }, [photoPreview])

  // ---- location ----
  function requestGps() {
    if (!navigator.geolocation) {
      setGpsState('denied')
      setMode('text')
      return
    }
    setGpsState('working')
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCoords([position.coords.latitude, position.coords.longitude])
        setGpsState('done')
        setMode('gps')
      },
      () => {
        setGpsState('denied')
        setMode('pin')
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    )
  }

  function onPhotoChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    if (photoPreview) URL.revokeObjectURL(photoPreview)
    if (!file) {
      setPhoto(null)
      setPhotoPreview(null)
      return
    }
    if (file.size > 8 * 1024 * 1024) {
      toast.push('That photo is larger than 8 MB. Please choose a smaller one.', 'error')
      return
    }
    setPhoto(file)
    setPhotoPreview(URL.createObjectURL(file))
  }

  function clearPhoto() {
    if (photoPreview) URL.revokeObjectURL(photoPreview)
    setPhoto(null)
    setPhotoPreview(null)
    setConsentExif(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function submit() {
    setError(null)
    if (!text.trim() && !photo) {
      setError(t('report_need_text'))
      return
    }
    if (speech.listening) speech.stop()

    const form = new FormData()
    form.set('text', text.trim())
    form.set('ui_language', lang)
    form.set('channel', usedVoice ? 'voice' : photo && !text.trim() ? 'photo' : 'text')
    form.set('device_ref', deviceRef())
    form.set('consent_exif_gps', String(consentExif))
    if (coords && mode !== 'text') {
      form.set('lat', String(coords[0]))
      form.set('lon', String(coords[1]))
      form.set('location_source', mode === 'gps' ? 'gps' : 'pin')
    }
    if (landmark.trim()) form.set('location_text', landmark.trim())
    if (photo) form.set('photo', photo)

    setSubmitting(true)
    try {
      const result = await api.submitComplaint(form)
      // Hand the full result to the ticket page so it renders instantly,
      // with the ticket code in the URL as the durable fallback.
      navigate(`/ticket/${result.ticket_code}`, { state: { result } })
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : t('error_generic')
      setError(message)
      toast.push(message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const speechLocale = meta?.speech_locales?.[lang] ?? 'en-IN'
  const canSubmit = Boolean(text.trim() || photo)

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <h1 className="text-2xl font-bold text-ink-900">{t('report_title')}</h1>
      <p className="text-sm text-ink-600 mt-1.5 leading-relaxed">{t('report_what_hint')}</p>

      <div className="space-y-4 mt-6">
        {/* ---------------- describe ---------------- */}
        <Card className="p-4">
          <Field label={t('report_what')} hint={t('report_privacy_note')} htmlFor="complaint-text">
            <Textarea
              id="complaint-text"
              rows={5}
              value={text + (speech.interim ? ` ${speech.interim}` : '')}
              onChange={(event) => setText(event.target.value)}
              placeholder={t('report_what_placeholder')}
              className="text-base"
              maxLength={4000}
            />
          </Field>

          <div className="flex flex-wrap items-center gap-2 mt-3">
            {speech.supported ? (
              <Button
                type="button"
                variant={speech.listening ? 'danger' : 'secondary'}
                size="sm"
                onClick={() => (speech.listening ? speech.stop() : speech.start(speechLocale))}
                icon={
                  speech.listening ? (
                    <span className="h-2.5 w-2.5 rounded-sm bg-current animate-pulse" />
                  ) : (
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v4" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )
                }
              >
                {speech.listening ? t('report_voice_stop') : t('report_voice_start')}
              </Button>
            ) : (
              <span className="text-xs text-ink-500 leading-relaxed">
                {t('report_voice_unsupported')}
              </span>
            )}
            {speech.listening && (
              <span className="text-xs text-danger-600 font-medium">
                {t('report_voice_listening')} ({speechLocale})
              </span>
            )}
            <span className="text-2xs text-ink-400 ml-auto tabular-nums">{text.length}/4000</span>
          </div>
          {speech.error && speech.error !== 'unsupported' && (
            <p className="text-xs text-warn-600 mt-2">{t('report_voice_error')}</p>
          )}
        </Card>

        {/* ---------------- photo ---------------- */}
        <Card className="p-4">
          <p className="nn-label">
            {t('report_photo')}
          </p>
          {photoPreview ? (
            <div className="flex items-start gap-3">
              <img
                src={photoPreview}
                alt=""
                className="h-24 w-24 rounded-lg object-cover border border-ink-200"
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm text-ink-700 truncate">{photo?.name}</p>
                <p className="text-xs text-ink-500 mt-0.5">
                  {photo ? `${(photo.size / 1024 / 1024).toFixed(1)} MB` : ''}
                </p>
                <div className="flex gap-2 mt-2">
                  <Button size="sm" variant="secondary" onClick={() => fileInputRef.current?.click()}>
                    {t('report_photo_change')}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={clearPhoto}>
                    {t('report_photo_remove')}
                  </Button>
                </div>
                <label className="flex items-start gap-2 mt-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consentExif}
                    onChange={(event) => setConsentExif(event.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-ink-300 text-brand-600 focus:ring-brand-500"
                  />
                  <span className="text-xs text-ink-600 leading-relaxed">
                    {t('report_exif_consent')}
                  </span>
                </label>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="w-full border-2 border-dashed border-ink-200 rounded-xl py-7 text-center hover:border-brand-400 hover:bg-brand-50/40 transition-colors"
            >
              <svg className="h-7 w-7 mx-auto text-ink-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="5" width="18" height="15" rx="2" />
                <circle cx="9" cy="10.5" r="1.8" />
                <path d="m3 17 5-4 4 3 3-2 6 5" strokeLinejoin="round" />
              </svg>
              <span className="block text-sm text-ink-600 mt-2 font-medium">{t('report_photo')}</span>
            </button>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={onPhotoChange}
            className="hidden"
          />
          <p className="nn-hint">{t('report_photo_hint')}</p>
        </Card>

        {/* ---------------- location ---------------- */}
        <Card className="p-4">
          <p className="nn-label">{t('report_where')}</p>

          <div className="flex gap-2 mb-3">
            <Button
              type="button"
              variant={mode === 'gps' && gpsState === 'done' ? 'primary' : 'secondary'}
              size="sm"
              onClick={requestGps}
              loading={gpsState === 'working'}
              icon={
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M12 2v3M12 19v3M2 12h3M19 12h3" strokeLinecap="round" />
                  <circle cx="12" cy="12" r="8" />
                </svg>
              }
            >
              {gpsState === 'working'
                ? t('report_gps_working')
                : gpsState === 'done'
                  ? t('report_gps_done')
                  : t('report_gps')}
            </Button>
            <Button
              type="button"
              variant={mode === 'pin' ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setMode('pin')}
            >
              {t('report_pin_hint')}
            </Button>
          </div>

          {gpsState === 'denied' && (
            <Alert tone="warn">{t('report_gps_denied')}</Alert>
          )}

          {(mode === 'pin' || coords) && (
            <div className="mt-3">
              <MapView
                className="h-[240px]"
                center={coords ?? CITY_CENTER}
                zoom={coords ? 16 : 12}
                recenter={coords}
                onPick={(lat, lon) => {
                  setCoords([lat, lon])
                  setMode('pin')
                }}
              >
                {wards && <WardBoundaries data={wards} />}
                {coords && <PinMarker position={coords} />}
              </MapView>
              <p className="nn-hint">
                {coords
                  ? `${coords[0].toFixed(5)}, ${coords[1].toFixed(5)} — ${t('report_pin_hint')}`
                  : t('report_pin_hint')}
              </p>
            </div>
          )}

          <div className="mt-4">
            <Field label={t('report_landmark')} hint={t('report_landmark_hint')} htmlFor="landmark">
              <Input
                id="landmark"
                value={landmark}
                onChange={(event) => setLandmark(event.target.value)}
                placeholder={t('report_landmark_placeholder')}
                maxLength={300}
              />
            </Field>
          </div>
        </Card>

        {error && <Alert tone="danger">{error}</Alert>}

        <div className="sticky bottom-0 -mx-4 px-4 py-3 bg-ink-50/95 backdrop-blur border-t border-ink-100">
          <Button
            size="lg"
            variant="accent"
            block
            onClick={submit}
            loading={submitting}
            disabled={!canSubmit}
          >
            {submitting ? t('report_sending') : t('report_submit')}
          </Button>
          <p className={classNames('text-2xs text-center mt-2 leading-relaxed', 'text-ink-500')}>
            {t('report_privacy_note')}
          </p>
        </div>
      </div>
    </div>
  )
}
