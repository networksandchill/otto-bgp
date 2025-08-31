import React, { useState, useEffect, createContext, useContext, ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import type { User, LoginRequest } from '../types'

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  isAdmin: boolean
  isReadOnly: boolean
  login: (credentials: LoginRequest) => Promise<void>
  logout: () => Promise<void>
  error: string | null
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

interface AuthProviderProps {
  children: ReactNode
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [initialCheckDone, setInitialCheckDone] = useState(false)
  const queryClient = useQueryClient()

  // Check if we have a stored token on mount
  const hasStoredToken = !!sessionStorage.getItem('access_token')

  // Query to get current session
  const { data: sessionData, isLoading, error: sessionError } = useQuery({
    queryKey: ['session'],
    queryFn: () => apiClient.getSession(),
    retry: (failureCount, error: any) => {
      // Retry once for 401 errors (token might need refresh)
      if (error?.response?.status === 401 && failureCount < 1) {
        return true
      }
      return false
    },
    enabled: hasStoredToken && !initialCheckDone,
  })

  // Update user from session data
  useEffect(() => {
    if (sessionData) {
      setUser({
        username: sessionData.user,
        role: sessionData.role,
      })
      setError(null)
      setInitialCheckDone(true)
    } else if (sessionError) {
      // Clear everything on error
      setUser(null)
      apiClient.clearTokens()
      setInitialCheckDone(true)
    } else if (!hasStoredToken && !isLoading) {
      // No token and not loading means not authenticated
      setInitialCheckDone(true)
    }
  }, [sessionData, sessionError, hasStoredToken, isLoading])

  // Login mutation
  const loginMutation = useMutation({
    mutationFn: (credentials: LoginRequest) => apiClient.login(credentials),
    onSuccess: (loginResponse) => {
      setUser({
        username: loginResponse.user,
        role: loginResponse.role,
      })
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['session'] })
    },
    onError: (error: any) => {
      setError(error.response?.data?.error || 'Login failed')
      apiClient.clearTokens()
    },
  })

  // Logout mutation
  const logoutMutation = useMutation({
    mutationFn: () => apiClient.logout(),
    onSettled: () => {
      setUser(null)
      setError(null)
      apiClient.clearTokens()
      queryClient.clear()
    },
  })

  const login = async (credentials: LoginRequest) => {
    setError(null)
    await loginMutation.mutateAsync(credentials)
  }

  const logout = async () => {
    await logoutMutation.mutateAsync()
  }

  const contextValue: AuthContextType = {
    user,
    isAuthenticated: !!user,
    isLoading: !initialCheckDone || isLoading || loginMutation.isPending,
    isAdmin: user?.role === 'admin',
    isReadOnly: user?.role === 'read_only',
    login,
    logout,
    error: error || (loginMutation.error as any)?.response?.data?.error,
  }

  return React.createElement(AuthContext.Provider, { value: contextValue }, children)
}