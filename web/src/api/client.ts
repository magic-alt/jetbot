import axios, { AxiosError, type AxiosInstance } from 'axios'

const baseURL = (import.meta as any).env?.VITE_API_BASE || ''

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
  const body = r.data
  if (body && typeof body === 'object' && 'ok' in body) {
    if (!body.ok) throw new Error(body.error?.message || 'unknown error')
    return body.data as T
  }
  return body as T
}
