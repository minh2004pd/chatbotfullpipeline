import axios from 'axios'

// "" = relative URL → CloudFront proxy /api/* → EC2 (production & default)
// Set VITE_API_BASE_URL=http://localhost:8000 trong .env.local khi dev local
const baseURL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''

export const apiClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',  // CSRF protection
  },
  withCredentials: true, // send/receive HTTP-only cookies
  // FastAPI expects repeated params for arrays: ?a=1&a=2, not ?a[]=1&a[]=2
  paramsSerializer: { indexes: null },
})

// ── 401 interceptor: try refresh → retry, else logout ──────────────────
let isRefreshing = false
let failedQueue: Array<{ resolve: (value?: undefined) => void; reject: (err: unknown) => void }> = []

function processQueue(error: unknown) {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error)
    else resolve(undefined)
  })
  failedQueue = []
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // Skip auth endpoints — don't try to refresh on login/register failures
    if (originalRequest.url?.includes('/auth/')) {
      return Promise.reject(error)
    }

    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error)
    }

    if (isRefreshing) {
      // Queue other requests while refreshing
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject })
      }).then(() => apiClient(originalRequest))
    }

    originalRequest._retry = true
    isRefreshing = true

    try {
      await apiClient.post('/api/v1/auth/refresh')
      processQueue(null)
      return apiClient(originalRequest)
    } catch (refreshError) {
      processQueue(refreshError)
      // Refresh failed — dispatch logout event
      window.dispatchEvent(new CustomEvent('auth:logout'))
      return Promise.reject(refreshError)
    } finally {
      isRefreshing = false
    }
  },
)

export const getApiBaseUrl = (): string => baseURL
