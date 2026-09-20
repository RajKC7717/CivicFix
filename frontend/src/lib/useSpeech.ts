/**
 * Web Speech API wrapper for voice complaint intake.
 *
 * Voice is a convenience, never a dependency. The hook reports `supported:
 * false` on browsers without the API (Firefox, most in-app webviews) and the
 * form simply shows the textarea, which does the same job. Nothing in the
 * pipeline treats a spoken complaint differently from a typed one.
 *
 * Locale matters: hi-IN and mr-IN give dramatically better results for Hindi
 * and Marathi than the browser default, and that is the whole point of
 * supporting voice for citizens who find typing Devanagari slow.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

interface SpeechRecognitionAlternative {
  transcript: string
  confidence: number
}
interface SpeechRecognitionResult {
  isFinal: boolean
  0: SpeechRecognitionAlternative
  length: number
}
interface SpeechRecognitionEventLike {
  resultIndex: number
  results: { length: number; [index: number]: SpeechRecognitionResult }
}
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
}

type RecognitionCtor = new () => SpeechRecognitionLike

function getRecognitionCtor(): RecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor
    webkitSpeechRecognition?: RecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export interface UseSpeechResult {
  supported: boolean
  listening: boolean
  interim: string
  error: string | null
  start: (locale: string) => void
  stop: () => void
}

export function useSpeech(onFinalText: (text: string) => void): UseSpeechResult {
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState<string | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const callbackRef = useRef(onFinalText)
  callbackRef.current = onFinalText

  const supported = getRecognitionCtor() !== null

  const stop = useCallback(() => {
    try {
      recognitionRef.current?.stop()
    } catch {
      /* already stopped */
    }
    setListening(false)
    setInterim('')
  }, [])

  const start = useCallback(
    (locale: string) => {
      const Ctor = getRecognitionCtor()
      if (!Ctor) {
        setError('unsupported')
        return
      }
      stop()
      setError(null)

      const recognition = new Ctor()
      recognition.lang = locale
      recognition.continuous = true
      recognition.interimResults = true
      recognition.maxAlternatives = 1

      recognition.onresult = (event) => {
        let finalText = ''
        let pending = ''
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const result = event.results[i]
          const transcript = result[0]?.transcript ?? ''
          if (result.isFinal) finalText += transcript
          else pending += transcript
        }
        setInterim(pending)
        if (finalText.trim()) {
          callbackRef.current(finalText.trim())
          setInterim('')
        }
      }
      recognition.onerror = (event) => {
        // "aborted" and "no-speech" are normal when the user stops talking.
        if (event.error !== 'aborted' && event.error !== 'no-speech') setError(event.error)
        setListening(false)
      }
      recognition.onend = () => {
        setListening(false)
        setInterim('')
      }

      recognitionRef.current = recognition
      try {
        recognition.start()
        setListening(true)
      } catch {
        setError('start-failed')
        setListening(false)
      }
    },
    [stop],
  )

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.abort()
      } catch {
        /* ignore */
      }
    }
  }, [])

  return { supported, listening, interim, error, start, stop }
}
