import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Box, Typography, Paper } from '@mui/material'
import { useAuth } from '../hooks/useAuth'

interface RequireRoleProps {
  role: 'admin' | 'read_only'
  children: React.ReactNode
}

const RequireRole: React.FC<RequireRoleProps> = ({ role, children }) => {
  const { user, isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="200px">
        <Typography>Loading...</Typography>
      </Box>
    )
  }

  if (!isAuthenticated) {
    // Redirect to login with return URL
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // Check role requirements
  if (role === 'admin' && user?.role !== 'admin') {
    return (
      <Paper sx={{ p: 3, m: 2 }}>
        <Typography variant="h5" color="error" gutterBottom>
          Access Denied
        </Typography>
        <Typography>
          This page requires administrator privileges. Your current role is: {user?.role}
        </Typography>
      </Paper>
    )
  }

  // read_only role allows both admin and read_only users
  if (role === 'read_only' && !['admin', 'read_only'].includes(user?.role || '')) {
    return (
      <Paper sx={{ p: 3, m: 2 }}>
        <Typography variant="h5" color="error" gutterBottom>
          Access Denied
        </Typography>
        <Typography>
          You do not have permission to access this page.
        </Typography>
      </Paper>
    )
  }

  return <>{children}</>
}

export default RequireRole