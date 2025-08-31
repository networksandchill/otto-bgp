import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import { useQuery } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './hooks/useAuth'
import CockpitLayout from './components/CockpitLayout'
import RequireRole from './components/RequireRole'
import Login from './pages/Login'
import CockpitDashboard from './pages/CockpitDashboard'
import Reports from './pages/Reports'
import Configuration from './pages/Configuration'
import SetupWizard from './pages/setup/SetupWizard'
import apiClient from './api/client'

// Cockpit-inspired theme
const cockpitTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#0066cc',
      light: '#4d94ff',
      dark: '#004499',
    },
    secondary: {
      main: '#00a86b',
    },
    background: {
      default: '#151515',
      paper: '#1f1f1f',
    },
    text: {
      primary: '#f5f5f5',
      secondary: '#b3b3b3',
    },
    divider: '#333',
  },
  typography: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    h6: {
      fontSize: '1rem',
      fontWeight: 600,
    },
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
      },
    },
  },
})

const AppContent: React.FC = () => {
  const { isAuthenticated } = useAuth()

  // Check setup state
  const { data: setupState } = useQuery({
    queryKey: ['setup-state'],
    queryFn: () => apiClient.getSetupState(),
    retry: false,
  })

  // Show setup wizard if setup is needed
  if (setupState?.needs_setup) {
    return <SetupWizard />
  }

  if (!isAuthenticated) {
    return <Login />
  }

  return (
    <Routes>
      <Route path="/" element={<CockpitLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={
          <RequireRole role="read_only">
            <CockpitDashboard />
          </RequireRole>
        } />
        <Route path="reports" element={
          <RequireRole role="read_only">
            <Reports />
          </RequireRole>
        } />
        <Route path="config" element={
          <RequireRole role="admin">
            <Configuration />
          </RequireRole>
        } />
      </Route>
      <Route path="/login" element={<Login />} />
    </Routes>
  )
}

const App: React.FC = () => {
  return (
    <ThemeProvider theme={cockpitTheme}>
      <CssBaseline />
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ThemeProvider>
  )
}

export default App