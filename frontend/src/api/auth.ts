import type { AuthResponse, AuthUser, GoogleAuthUrlResponse } from '@/types'
import { apiClient } from './client'

export interface RegisterParams {
  email: string
  password: string
  display_name?: string
}

export interface LoginParams {
  email: string
  password: string
}

export const authApi = {
  register: async (params: RegisterParams): Promise<AuthResponse> => {
    const { data } = await apiClient.post<AuthResponse>('/api/v1/auth/register', params)
    return data
  },

  login: async (params: LoginParams): Promise<AuthResponse> => {
    const { data } = await apiClient.post<AuthResponse>('/api/v1/auth/login', params)
    return data
  },

  logout: async (): Promise<void> => {
    await apiClient.post('/api/v1/auth/logout')
  },

  refresh: async (): Promise<AuthResponse> => {
    const { data } = await apiClient.post<AuthResponse>('/api/v1/auth/refresh')
    return data
  },

  getMe: async (): Promise<AuthUser> => {
    const { data } = await apiClient.get<AuthUser>('/api/v1/auth/me')
    return data
  },

  getGoogleAuthUrl: async (): Promise<string> => {
    const { data } = await apiClient.get<GoogleAuthUrlResponse>('/api/v1/auth/google')
    return data.url
  },

  googleCallback: async (code: string): Promise<AuthResponse> => {
    const { data } = await apiClient.post<AuthResponse>('/api/v1/auth/google/callback', { code })
    return data
  },
}
