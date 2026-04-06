import axios from 'axios'

const USER_ID_KEY = 'memrag_user_id'
const DEFAULT_USER_ID = 'default_user'

export const getUserId = (): string => {
  return localStorage.getItem(USER_ID_KEY) ?? DEFAULT_USER_ID
}

export const setUserIdInStorage = (userId: string): void => {
  localStorage.setItem(USER_ID_KEY, userId)
}

// "" = relative URL → CloudFront proxy /api/* → EC2 (production & default)
// Set VITE_API_BASE_URL=http://localhost:8000 trong .env.local khi dev local
const baseURL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''

export const apiClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Inject X-User-ID header on every request
apiClient.interceptors.request.use((config) => {
  config.headers['X-User-ID'] = getUserId()
  return config
})

export const getApiBaseUrl = (): string => baseURL
