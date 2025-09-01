import React, { useState } from 'react'
import {
  Container, Paper, Box, Stepper, Step, StepLabel, Typography,
  TextField, Button, Alert, InputAdornment, IconButton
} from '@mui/material'
import { Visibility, VisibilityOff, CheckCircle } from '@mui/icons-material'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../../api/client'
import type { SetupAdminRequest, AppConfig } from '../../types'

const steps = ['Setup Token', 'Create Admin', 'SSH Credentials', 'Complete']

const SetupWizard: React.FC = () => {
  const [activeStep, setActiveStep] = useState(0)
  const [setupToken, setSetupToken] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [adminData, setAdminData] = useState<SetupAdminRequest>({
    username: '',
    email: '',
    password: ''
  })
  const [config, setConfig] = useState<AppConfig>({
    ssh: {
      hostname: '',
      username: 'admin',
      password: '',
      port: 22
    },
    smtp: {
      enabled: false
    }
  })

  const queryClient = useQueryClient()

  // Setup mutations
  const setupAdminMutation = useMutation({
    mutationFn: () => apiClient.setupAdmin(adminData, setupToken),
    onSuccess: () => setActiveStep(2),
  })

  const setupConfigMutation = useMutation({
    mutationFn: () => apiClient.setupConfig(config, setupToken),
    onSuccess: () => setActiveStep(3),
  })

  const completeSetupMutation = useMutation({
    mutationFn: () => apiClient.completeSetup(setupToken),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['setup-state'] })
      // Redirect will happen automatically when setup state changes
    },
  })

  const handleNext = async () => {
    if (activeStep === 0) {
      setActiveStep(1)
    } else if (activeStep === 1) {
      await setupAdminMutation.mutateAsync()
    } else if (activeStep === 2) {
      await setupConfigMutation.mutateAsync()
    } else if (activeStep === 3) {
      await completeSetupMutation.mutateAsync()
    }
  }

  const isStepValid = () => {
    switch (activeStep) {
      case 0:
        return setupToken.length > 10
      case 1:
        return adminData.username && adminData.email && adminData.password.length >= 8
      case 2:
        return config.ssh.username && (config.ssh.password || config.ssh.key_path)
      default:
        return true
    }
  }

  const getStepContent = () => {
    switch (activeStep) {
      case 0:
        return (
          <Box>
            <Typography variant="h5" gutterBottom>
              Enter Setup Token
            </Typography>
            <Typography variant="body1" color="text.secondary" gutterBottom>
              Enter the setup token generated during installation. This token was saved to:
            </Typography>
            <Typography variant="body2" fontFamily="monospace" sx={{ bgcolor: 'grey.900', p: 1, my: 2 }}>
              /etc/otto-bgp/.setup_token
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Retrieve it with: <code>sudo cat /etc/otto-bgp/.setup_token</code>
            </Typography>
            
            <TextField
              fullWidth
              label="Setup Token"
              value={setupToken}
              onChange={(e) => setSetupToken(e.target.value.trim())}
              margin="normal"
              placeholder="Enter the setup token from the server"
              sx={{ mt: 3 }}
            />
          </Box>
        )

      case 1:
        return (
          <Box>
            <Typography variant="h5" gutterBottom>
              Create Administrator Account
            </Typography>
            <Typography variant="body1" color="text.secondary" gutterBottom>
              Create the first admin user for Otto BGP WebUI.
            </Typography>
            
            <TextField
              fullWidth
              label="Username"
              value={adminData.username}
              onChange={(e) => setAdminData(prev => ({ ...prev, username: e.target.value }))}
              margin="normal"
              required
            />
            
            <TextField
              fullWidth
              label="Email"
              type="email"
              value={adminData.email}
              onChange={(e) => setAdminData(prev => ({ ...prev, email: e.target.value }))}
              margin="normal"
              required
            />
            
            <TextField
              fullWidth
              label="Password"
              type={showPassword ? 'text' : 'password'}
              value={adminData.password}
              onChange={(e) => setAdminData(prev => ({ ...prev, password: e.target.value }))}
              margin="normal"
              required
              helperText="Minimum 8 characters"
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowPassword(!showPassword)}>
                      {showPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
          </Box>
        )

      case 2:
        return (
          <Box>
            <Typography variant="h5" gutterBottom>
              Global SSH Credentials
            </Typography>
            <Typography variant="body1" color="text.secondary" gutterBottom>
              Configure SSH credentials that will be used to connect to all network devices.
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              These credentials will be applied globally. You can manage individual devices after setup.
            </Typography>
            
            <TextField
              fullWidth
              label="SSH Username"
              value={config.ssh.username}
              onChange={(e) => setConfig(prev => ({
                ...prev,
                ssh: { ...prev.ssh, username: e.target.value }
              }))}
              margin="normal"
              required
              helperText="Common service account used for all routers"
            />
            
            <TextField
              fullWidth
              label="SSH Password"
              type="password"
              value={config.ssh.password}
              onChange={(e) => setConfig(prev => ({
                ...prev,
                ssh: { ...prev.ssh, password: e.target.value }
              }))}
              margin="normal"
              helperText="You can configure SSH keys later in Settings"
            />
          </Box>
        )

      case 3:
        return (
          <Box textAlign="center">
            <CheckCircle sx={{ fontSize: 80, color: 'success.main', mb: 2 }} />
            <Typography variant="h5" gutterBottom>
              Setup Complete!
            </Typography>
            <Typography variant="body1" color="text.secondary" gutterBottom>
              Otto BGP WebUI has been configured successfully. The setup token has been removed
              for security.
            </Typography>
            <Typography variant="body2" sx={{ mt: 2 }}>
              You will be redirected to the login page shortly.
            </Typography>
          </Box>
        )

      default:
        return null
    }
  }

  const getError = () => {
    if (setupAdminMutation.error) return setupAdminMutation.error
    if (setupConfigMutation.error) return setupConfigMutation.error
    if (completeSetupMutation.error) return completeSetupMutation.error
    return null
  }

  const isLoading = setupAdminMutation.isPending || setupConfigMutation.isPending || completeSetupMutation.isPending

  return (
    <Container maxWidth="md">
      <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', py: 4 }}>
        <Paper sx={{ width: '100%', p: 4 }}>
          <Typography variant="h3" component="h1" textAlign="center" gutterBottom>
            Otto BGP Setup Wizard
          </Typography>
          <Typography variant="body1" textAlign="center" color="text.secondary" gutterBottom>
            Complete the initial configuration to start using Otto BGP WebUI
          </Typography>

          <Stepper activeStep={activeStep} sx={{ my: 4 }}>
            {steps.map((label) => (
              <Step key={label}>
                <StepLabel>{label}</StepLabel>
              </Step>
            ))}
          </Stepper>

          <Box sx={{ mt: 4, mb: 2 }}>
            {getStepContent()}
          </Box>

          {getError() && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {(getError() as any)?.response?.data?.error || 'Setup failed'}
            </Alert>
          )}

          <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 4 }}>
            <Button
              variant="contained"
              onClick={handleNext}
              disabled={!isStepValid() || isLoading}
              size="large"
            >
              {isLoading ? 'Processing...' : activeStep === 3 ? 'Complete Setup' : 'Next'}
            </Button>
          </Box>
        </Paper>
      </Box>
    </Container>
  )
}

export default SetupWizard