import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Box, AppBar, Toolbar, Typography, IconButton, Menu, MenuItem } from '@mui/material'
import { AccountCircle, ExitToApp } from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './hooks/useAuth'
import RequireRole from './components/RequireRole'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Reports from './pages/Reports'
import Configuration from './pages/Configuration'
import SetupWizard from './pages/setup/SetupWizard'
import apiClient from './api/client'

const AppContent: React.FC = () => {
  const { user, isAuthenticated, logout } = useAuth()
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null)

  // Check setup state
  const { data: setupState } = useQuery({
    queryKey: ['setup-state'],
    queryFn: () => apiClient.getSetupState(),
    retry: false,
  })

  const handleMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleClose = () => {
    setAnchorEl(null)
  }

  const handleLogout = async () => {
    handleClose()
    await logout()
  }

  // Show setup wizard if setup is needed
  if (setupState?.needs_setup) {
    return <SetupWizard />
  }

  return (
    <Box sx={{ flexGrow: 1 }}>
      {isAuthenticated && (
        <AppBar position="static" sx={{ background: 'linear-gradient(45deg, #1976d2 30%, #21CBF3 90%)' }}>
          <Toolbar>
            <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
              Otto BGP WebUI
            </Typography>
            {user && (
              <Box display="flex" alignItems="center">
                <Typography variant="body2" sx={{ mr: 1 }}>
                  {user.username} ({user.role})
                </Typography>
                <IconButton
                  size="large"
                  onClick={handleMenu}
                  color="inherit"
                >
                  <AccountCircle />
                </IconButton>
                <Menu
                  anchorEl={anchorEl}
                  open={Boolean(anchorEl)}
                  onClose={handleClose}
                >
                  <MenuItem onClick={handleLogout}>
                    <ExitToApp sx={{ mr: 1 }} />
                    Logout
                  </MenuItem>
                </Menu>
              </Box>
            )}
          </Toolbar>
        </AppBar>
      )}

      <Routes>
        <Route path="/login" element={<Login />} />
        
        <Route path="/dashboard" element={
          <RequireRole role="read_only">
            <Dashboard />
          </RequireRole>
        } />
        
        <Route path="/reports" element={
          <RequireRole role="read_only">
            <Reports />
          </RequireRole>
        } />
        
        <Route path="/config" element={
          <RequireRole role="admin">
            <Configuration />
          </RequireRole>
        } />
        
        <Route path="/" element={
          isAuthenticated ? <Navigate to="/dashboard" replace /> : <Navigate to="/login" replace />
        } />
      </Routes>
    </Box>
  )
}

const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}

export default App