import React, { useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import {
  Box, Paper, TextField, Button, Typography, Alert,
  Container, InputAdornment, IconButton
} from '@mui/material'
import { Visibility, VisibilityOff, Security } from '@mui/icons-material'
import { useAuth } from '../hooks/useAuth'

const Login: React.FC = () => {
  const [credentials, setCredentials] = useState({ username: '', password: '' })
  const [showPassword, setShowPassword] = useState(false)
  const { login, isAuthenticated, isLoading, error } = useAuth()
  const location = useLocation()

  // Redirect if already authenticated
  if (isAuthenticated) {
    const from = (location.state as any)?.from?.pathname || '/dashboard'
    return <Navigate to={from} replace />
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (credentials.username && credentials.password) {
      await login(credentials)
    }
  }

  const handleInputChange = (field: 'username' | 'password') => (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    setCredentials(prev => ({ ...prev, [field]: e.target.value }))
  }

  return (
    <Container maxWidth="sm">
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Paper
          elevation={4}
          sx={{
            p: 4,
            width: '100%',
            maxWidth: 400,
            background: 'linear-gradient(145deg, #1a1a1a 0%, #2d2d2d 100%)',
          }}
        >
          <Box textAlign="center" mb={3}>
            <Security sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
            <Typography variant="h4" component="h1" gutterBottom>
              Otto BGP WebUI
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Authenticate to access the management interface
            </Typography>
          </Box>

          {error && (
            <Alert severity="error" sx={{ mb: 3 }}>
              {error}
            </Alert>
          )}

          <Box component="form" onSubmit={handleSubmit}>
            <TextField
              fullWidth
              label="Username"
              name="username"
              value={credentials.username}
              onChange={handleInputChange('username')}
              margin="normal"
              required
              autoComplete="username"
              autoFocus
              disabled={isLoading}
            />
            
            <TextField
              fullWidth
              label="Password"
              name="password"
              type={showPassword ? 'text' : 'password'}
              value={credentials.password}
              onChange={handleInputChange('password')}
              margin="normal"
              required
              autoComplete="current-password"
              disabled={isLoading}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={() => setShowPassword(!showPassword)}
                      edge="end"
                      disabled={isLoading}
                    >
                      {showPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />

            <Button
              type="submit"
              fullWidth
              variant="contained"
              size="large"
              sx={{ mt: 3, mb: 2 }}
              disabled={isLoading || !credentials.username || !credentials.password}
            >
              {isLoading ? 'Signing in...' : 'Sign In'}
            </Button>
          </Box>

          <Typography variant="caption" display="block" textAlign="center" mt={2} color="text.secondary">
            Otto BGP v0.3.2 - Unified Pipeline Architecture
          </Typography>
        </Paper>
      </Box>
    </Container>
  )
}

export default Login