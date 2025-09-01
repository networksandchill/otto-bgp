import React, { useState } from 'react'
import {
  Container, Paper, Typography, TextField, Button, Box,
  Alert, Snackbar, Divider, InputAdornment, IconButton
} from '@mui/material'
import { Visibility, VisibilityOff, Save as SaveIcon } from '@mui/icons-material'
import { useQuery, useMutation } from '@tanstack/react-query'
import apiClient from '../api/client'

const Profile: React.FC = () => {
  const [showPassword, setShowPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [formData, setFormData] = useState({
    email: '',
    currentPassword: '',
    newPassword: '',
    confirmPassword: ''
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [successMessage, setSuccessMessage] = useState('')

  // Get current user info
  const { data: session } = useQuery({
    queryKey: ['session'],
    queryFn: () => apiClient.getSession(),
  })

  // Get user details
  const { data: userDetails } = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiClient.getUserProfile(),
  })

  // Update form when user details load
  React.useEffect(() => {
    if (userDetails?.email) {
      setFormData(prev => ({
        ...prev,
        email: userDetails.email || ''
      }))
    }
  }, [userDetails])

  // Update profile mutation
  const updateProfileMutation = useMutation({
    mutationFn: (data: { email?: string; current_password?: string; new_password?: string }) => 
      apiClient.updateProfile(data),
    onSuccess: () => {
      setSuccessMessage('Profile updated successfully')
      setFormData(prev => ({
        ...prev,
        currentPassword: '',
        newPassword: '',
        confirmPassword: ''
      }))
      setErrors({})
    },
    onError: (error: any) => {
      const message = error.response?.data?.error || 'Failed to update profile'
      setErrors({ submit: message })
    }
  })

  const validateForm = () => {
    const newErrors: Record<string, string> = {}

    // Email validation
    if (formData.email && !formData.email.match(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)) {
      newErrors.email = 'Invalid email address'
    }

    // Password validation (only if changing password)
    if (formData.newPassword || formData.confirmPassword || formData.currentPassword) {
      if (!formData.currentPassword) {
        newErrors.currentPassword = 'Current password is required to change password'
      }
      if (!formData.newPassword) {
        newErrors.newPassword = 'New password is required'
      } else if (formData.newPassword.length < 8) {
        newErrors.newPassword = 'Password must be at least 8 characters'
      }
      if (formData.newPassword !== formData.confirmPassword) {
        newErrors.confirmPassword = 'Passwords do not match'
      }
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!validateForm()) {
      return
    }

    const updateData: any = {}
    
    // Only include email if it changed
    if (formData.email !== userDetails?.email) {
      updateData.email = formData.email
    }

    // Only include password fields if changing password
    if (formData.currentPassword && formData.newPassword) {
      updateData.current_password = formData.currentPassword
      updateData.new_password = formData.newPassword
    }

    // Only submit if there are changes
    if (Object.keys(updateData).length > 0) {
      updateProfileMutation.mutate(updateData)
    } else {
      setErrors({ submit: 'No changes to save' })
    }
  }

  const handleChange = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData(prev => ({
      ...prev,
      [field]: e.target.value
    }))
    // Clear error for this field
    setErrors(prev => ({
      ...prev,
      [field]: ''
    }))
  }

  return (
    <Container maxWidth="md">
      <Typography variant="h4" component="h1" gutterBottom sx={{ mt: 4 }}>
        Profile Settings
      </Typography>

      <Paper sx={{ p: 4, mt: 3 }}>
        <Box component="form" onSubmit={handleSubmit}>
          <Typography variant="h6" gutterBottom>
            Account Information
          </Typography>
          
          <TextField
            fullWidth
            label="Username"
            value={session?.user || ''}
            disabled
            margin="normal"
            helperText="Username cannot be changed"
          />

          <TextField
            fullWidth
            label="Email"
            type="email"
            value={formData.email}
            onChange={handleChange('email')}
            error={!!errors.email}
            helperText={errors.email}
            margin="normal"
          />

          <Divider sx={{ my: 4 }} />

          <Typography variant="h6" gutterBottom>
            Change Password
          </Typography>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            Leave blank to keep current password
          </Typography>

          <TextField
            fullWidth
            label="Current Password"
            type={showPassword ? 'text' : 'password'}
            value={formData.currentPassword}
            onChange={handleChange('currentPassword')}
            error={!!errors.currentPassword}
            helperText={errors.currentPassword}
            margin="normal"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={() => setShowPassword(!showPassword)}
                    edge="end"
                  >
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />

          <TextField
            fullWidth
            label="New Password"
            type={showNewPassword ? 'text' : 'password'}
            value={formData.newPassword}
            onChange={handleChange('newPassword')}
            error={!!errors.newPassword}
            helperText={errors.newPassword || 'Minimum 8 characters'}
            margin="normal"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    edge="end"
                  >
                    {showNewPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />

          <TextField
            fullWidth
            label="Confirm New Password"
            type={showConfirmPassword ? 'text' : 'password'}
            value={formData.confirmPassword}
            onChange={handleChange('confirmPassword')}
            error={!!errors.confirmPassword}
            helperText={errors.confirmPassword}
            margin="normal"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    edge="end"
                  >
                    {showConfirmPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />

          {errors.submit && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {errors.submit}
            </Alert>
          )}

          <Box sx={{ mt: 4, display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              type="submit"
              variant="contained"
              startIcon={<SaveIcon />}
              disabled={updateProfileMutation.isPending}
            >
              {updateProfileMutation.isPending ? 'Saving...' : 'Save Changes'}
            </Button>
          </Box>
        </Box>
      </Paper>

      <Snackbar
        open={!!successMessage}
        autoHideDuration={6000}
        onClose={() => setSuccessMessage('')}
      >
        <Alert severity="success" onClose={() => setSuccessMessage('')}>
          {successMessage}
        </Alert>
      </Snackbar>
    </Container>
  )
}

export default Profile