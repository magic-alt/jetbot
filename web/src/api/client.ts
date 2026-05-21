import axios, { AxiosError, type AxiosInstance } from 'axios'

interface ApiEnvelope<T> {
  ok: boolean
  data: T
  error?: { message?: string } | null
}

function resolveApiBaseUrl(): string {
  const configuredBase = ((import.meta as any).env?.VITE_API_BASE || '').trim()
  if (configuredBase) {
    return configuredBase.replace(/\/$/, '')
  }

  // Default to same-origin requests so the Docker-served SPA at /ui and the
  // Vite dev proxy can both reach /v1 without hard-coding a host port.
  return ''
}

const baseURL = resolveApiBaseUrl()

export function buildApiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) {
    return path
  }
  return baseURL ? `${baseURL}${path}` : path
}

function maybeParseJson(value: unknown): unknown {
  if (typeof value !== 'string') {
    return value
  }

  const trimmed = value.trim()
  if (!(trimmed.startsWith('{') || trimmed.startsWith('['))) {
    return value
  }

  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function isApiEnvelope<T>(value: unknown): value is ApiEnvelope<T> {
  return value !== null && typeof value === 'object' && 'ok' in value && 'data' in value
}

export const http: AxiosInstance = axios.create({
  baseURL,
  timeout: 60000,
})

http.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('jetbot.apiKey')
  if (apiKey) config.headers.set('X-API-Key', apiKey)
  return config
})

http.interceptors.response.use(
  (r) => r,
  (err: AxiosError<any>) => {
    if (err.response?.data?.error?.message) {
      err.message = err.response.data.error.message
    }
    return Promise.reject(err)
  },
)

/** Unwrap the `{ok, data, error}` envelope returned by FastAPI handlers. */
export async function unwrap<T>(p: Promise<{ data: any }>): Promise<T> {
  const r = await p
  const body = maybeParseJson(r.data)
  if (typeof body === 'string' && /^\s*<!doctype html|^\s*<html/i.test(body)) {
    throw new Error('API returned HTML instead of JSON. Check the frontend API base URL or dev proxy configuration.')
  }
  if (isApiEnvelope<T>(body)) {
    if (!body.ok) throw new Error(body.error?.message || 'unknown error')
    return body.data as T
  }
  return body as T
}
