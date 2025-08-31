import React, { useState } from 'react'
import { 
  Container, Typography, Paper, Box, TextField, Button,
  Grid, Alert, Snackbar, FormControlLabel, Switch,
  Divider, Chip
} from '@mui/material'
import { Save as SaveIcon, Science as TestIcon } from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import type { AppConfig, SMTPConfig } from '../types'

const Configuration: React.FC = () => {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [showSuccess, setShowSuccess] = useState(false)
  const queryClient = useQueryClient()

  // Query current config
  const { data: configData, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: () => apiClient.getConfig(),
  })

  // Set config when data loads
  React.useEffect(() => {
    if (configData && !config) {
      setConfig(configData)
    }
  }, [configData, config])

  // Save config mutation
  const saveConfigMutation = useMutation({
    mutationFn: (config: AppConfig) => apiClient.updateConfig(config),
    onSuccess: () => {
      setShowSuccess(true)
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })

  // Test SMTP mutation
  const testSmtpMutation = useMutation({
    mutationFn: (smtpConfig: SMTPConfig) => apiClient.testSmtp(smtpConfig),
    onSuccess: (result) => {
      setTestResult(result.success ? 'SMTP test successful!' : `SMTP test failed: ${result.message}`)
    },
    onError: (error: any) => {
      setTestResult(`SMTP test failed: ${error.response?.data?.error || error.message}`)
    },
  })

  const handleConfigChange = (section: string, field: string, value: any) => {
    if (!config) return

    setConfig(prev => ({
      ...prev!,
      [section]: {
        ...prev![section],
        [field]: value
      }
    }))
  }

  const handleSave = async () => {
    if (config) {
      await saveConfigMutation.mutateAsync(config)
    }
  }

  const handleTestSmtp = async () => {
    if (config?.smtp) {
      setTestResult(null)
      await testSmtpMutation.mutateAsync(config.smtp)
    }
  }

  if (isLoading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4 }}>
        <Typography>Loading configuration...</Typography>
      </Container>
    )
  }

  if (!config) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4 }}>
        <Alert severity="error">Failed to load configuration</Alert>
      </Container>
    )
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h3" component="h1" gutterBottom>
        System Configuration
      </Typography>
      <Typography variant="subtitle1" color="text.secondary" gutterBottom>
        Manage SSH credentials, SMTP settings, and system parameters
      </Typography>

      <Grid container spacing={3} sx={{ mt: 2 }}>
        {/* SSH Configuration */}
        <Grid item xs={12}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h5" gutterBottom>
              SSH Configuration
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Hostname/IP"
                  value={config.ssh?.hostname || ''}
                  onChange={(e) => handleConfigChange('ssh', 'hostname', e.target.value)}
                  margin="normal"
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Username"
                  value={config.ssh?.username || ''}
                  onChange={(e) => handleConfigChange('ssh', 'username', e.target.value)}
                  margin="normal"
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Password"
                  type="password"
                  value={config.ssh?.password || ''}
                  onChange={(e) => handleConfigChange('ssh', 'password', e.target.value)}
                  margin="normal"
                  helperText="Leave as ***** to keep current password"
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Private Key Path"
                  value={config.ssh?.key_path || ''}
                  onChange={(e) => handleConfigChange('ssh', 'key_path', e.target.value)}
                  margin="normal"
                  helperText="Alternative to password authentication"
                />
              </Grid>
            </Grid>
          </Paper>
        </Grid>

        {/* SMTP Configuration */}
        <Grid item xs={12}>
          <Paper sx={{ p: 3 }}>
            <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
              <Typography variant="h5">
                SMTP Configuration
              </Typography>
              <FormControlLabel
                control={
                  <Switch
                    checked={config.smtp?.enabled || false}
                    onChange={(e) => handleConfigChange('smtp', 'enabled', e.target.checked)}
                  />
                }
                label="Enable SMTP"
              />
            </Box>
            
            {config.smtp?.enabled && (
              <>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="SMTP Host"
                      value={config.smtp?.host || ''}
                      onChange={(e) => handleConfigChange('smtp', 'host', e.target.value)}
                      margin="normal"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Port"
                      type="number"
                      value={config.smtp?.port || 587}
                      onChange={(e) => handleConfigChange('smtp', 'port', parseInt(e.target.value))}
                      margin="normal"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Username"
                      value={config.smtp?.username || ''}
                      onChange={(e) => handleConfigChange('smtp', 'username', e.target.value)}
                      margin="normal"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Password"
                      type="password"
                      value={config.smtp?.password || ''}
                      onChange={(e) => handleConfigChange('smtp', 'password', e.target.value)}
                      margin="normal"
                      helperText="Leave as ***** to keep current password"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="From Address"
                      value={config.smtp?.from_address || ''}
                      onChange={(e) => handleConfigChange('smtp', 'from_address', e.target.value)}
                      margin="normal"
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={config.smtp?.use_tls || false}
                          onChange={(e) => handleConfigChange('smtp', 'use_tls', e.target.checked)}
                        />
                      }
                      label="Use TLS"
                      sx={{ mt: 2 }}
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <TextField
                      fullWidth
                      label="To Addresses (comma-separated)"
                      value={config.smtp?.to_addresses?.join(', ') || ''}
                      onChange={(e) => {
                        const addresses = e.target.value.split(',').map(addr => addr.trim()).filter(addr => addr)
                        handleConfigChange('smtp', 'to_addresses', addresses)
                      }}
                      margin="normal"
                      helperText="Enter email addresses separated by commas"
                    />
                  </Grid>
                </Grid>

                <Divider sx={{ my: 2 }} />
                
                <Box display="flex" alignItems="center" gap={2}>
                  <Button
                    variant="outlined"
                    startIcon={<TestIcon />}
                    onClick={handleTestSmtp}
                    disabled={testSmtpMutation.isPending}
                  >
                    {testSmtpMutation.isPending ? 'Testing...' : 'Test SMTP'}
                  </Button>
                  
                  {testResult && (
                    <Chip 
                      label={testResult} 
                      color={testResult.includes('successful') ? 'success' : 'error'}
                    />
                  )}
                </Box>
              </>
            )}
          </Paper>
        </Grid>

        {/* Save Button */}
        <Grid item xs={12}>
          <Box display="flex" justifyContent="flex-end" gap={2}>
            <Button
              variant="contained"
              size="large"
              startIcon={<SaveIcon />}
              onClick={handleSave}
              disabled={saveConfigMutation.isPending}
            >
              {saveConfigMutation.isPending ? 'Saving...' : 'Save Configuration'}
            </Button>
          </Box>
        </Grid>
      </Grid>

      {/* Error Display */}
      {saveConfigMutation.error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          Save failed: {(saveConfigMutation.error as any)?.response?.data?.error || 'Unknown error'}
        </Alert>
      )}

      {/* Success Snackbar */}
      <Snackbar
        open={showSuccess}
        autoHideDuration={6000}
        onClose={() => setShowSuccess(false)}
        message="Configuration saved successfully"
      />
    </Container>
  )
}

export default Configuration