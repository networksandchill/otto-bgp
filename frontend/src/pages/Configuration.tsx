import React, { useState, useEffect } from 'react'
import { 
  Container, Typography, Paper, Box, TextField, Button,
  Grid, Alert, Snackbar, FormControlLabel, Switch,
  Divider, Chip, Tabs, Tab, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, IconButton, Dialog,
  DialogTitle, DialogContent, DialogActions
} from '@mui/material'
import { 
  Save as SaveIcon, Science as TestIcon, Add as AddIcon,
  Edit as EditIcon, Delete as DeleteIcon, Router as RouterIcon,
  Email as EmailIcon, Security as SecurityIcon
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import type { AppConfig, SMTPConfig } from '../types'

interface TabPanelProps {
  children?: React.ReactNode
  index: number
  value: number
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      {...other}
    >
      {value === index && (
        <Box sx={{ pt: 3 }}>
          {children}
        </Box>
      )}
    </div>
  )
}

interface Device {
  address: string
  hostname: string
  role: string
  region: string
}

const Configuration: React.FC = () => {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [showSuccess, setShowSuccess] = useState(false)
  const [tabValue, setTabValue] = useState(0)
  const [devices, setDevices] = useState<Device[]>([])
  const [deviceDialog, setDeviceDialog] = useState<{
    open: boolean
    mode: 'add' | 'edit'
    device?: Device
  }>({ open: false, mode: 'add' })
  const [deviceForm, setDeviceForm] = useState<Device>({
    address: '',
    hostname: '',
    role: '',
    region: ''
  })
  const queryClient = useQueryClient()

  // Query current config
  const { data: configData, isLoading: configLoading } = useQuery({
    queryKey: ['config'],
    queryFn: () => apiClient.getConfig(),
  })

  // Query devices
  const { data: devicesData, isLoading: devicesLoading, refetch: refetchDevices } = useQuery({
    queryKey: ['devices'],
    queryFn: () => apiClient.getDevices(),
  })

  // Set config when data loads
  useEffect(() => {
    if (configData && !config) {
      setConfig(configData)
    }
  }, [configData, config])

  // Set devices when data loads
  useEffect(() => {
    if (devicesData?.devices) {
      setDevices(devicesData.devices)
    }
  }, [devicesData])

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

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue)
  }

  const handleOpenDeviceDialog = (mode: 'add' | 'edit', device?: Device) => {
    setDeviceDialog({ open: true, mode, device })
    setDeviceForm(device || {
      address: '',
      hostname: '',
      role: '',
      region: ''
    })
  }

  const handleCloseDeviceDialog = () => {
    setDeviceDialog({ open: false, mode: 'add' })
    setDeviceForm({
      address: '',
      hostname: '',
      role: '',
      region: ''
    })
  }

  const handleSaveDevice = async () => {
    try {
      if (deviceDialog.mode === 'add') {
        await apiClient.addDevice(deviceForm)
      } else if (deviceDialog.device) {
        await apiClient.updateDevice(deviceDialog.device.address, deviceForm)
      }
      await refetchDevices()
      handleCloseDeviceDialog()
      setShowSuccess(true)
    } catch (error: any) {
      console.error('Failed to save device:', error)
    }
  }

  const handleDeleteDevice = async (address: string) => {
    if (confirm('Are you sure you want to delete this device?')) {
      try {
        await apiClient.deleteDevice(address)
        await refetchDevices()
        setShowSuccess(true)
      } catch (error: any) {
        console.error('Failed to delete device:', error)
      }
    }
  }

  const isLoading = configLoading || devicesLoading

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
        Manage routers, SSH credentials, SMTP settings, and system parameters
      </Typography>

      <Paper sx={{ mt: 3 }}>
        <Tabs value={tabValue} onChange={handleTabChange} sx={{ borderBottom: 1, borderColor: 'divider', px: 2 }}>
          <Tab icon={<RouterIcon />} label="Devices" />
          <Tab icon={<SecurityIcon />} label="Global SSH Credentials" />
          <Tab icon={<EmailIcon />} label="SMTP Settings" />
        </Tabs>

        <Box sx={{ p: 3 }}>
          <TabPanel value={tabValue} index={0}>
            {/* Devices Management */}
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h5">
                Router Devices
              </Typography>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={() => handleOpenDeviceDialog('add')}
              >
                Add Device
              </Button>
            </Box>

            <TableContainer component={Paper} variant="outlined">
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Address</TableCell>
                    <TableCell>Hostname</TableCell>
                    <TableCell>Role</TableCell>
                    <TableCell>Region</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {devices.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} align="center">
                        <Typography color="text.secondary" sx={{ py: 2 }}>
                          No devices configured. Add your first router device.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    devices.map((device) => (
                      <TableRow key={device.address}>
                        <TableCell>{device.address}</TableCell>
                        <TableCell>{device.hostname}</TableCell>
                        <TableCell>
                          <Chip label={device.role} size="small" />
                        </TableCell>
                        <TableCell>{device.region}</TableCell>
                        <TableCell align="right">
                          <IconButton
                            size="small"
                            onClick={() => handleOpenDeviceDialog('edit', device)}
                          >
                            <EditIcon fontSize="small" />
                          </IconButton>
                          <IconButton
                            size="small"
                            onClick={() => handleDeleteDevice(device.address)}
                            color="error"
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </TabPanel>

          <TabPanel value={tabValue} index={1}>
            {/* Global SSH Credentials */}
            <Typography variant="h5" gutterBottom>
              Global SSH Credentials
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              These credentials are used to connect to all network devices
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Username"
                  value={config.ssh?.username || ''}
                  onChange={(e) => handleConfigChange('ssh', 'username', e.target.value)}
                  margin="normal"
                  helperText="Service account used for all routers"
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
          </TabPanel>

          <TabPanel value={tabValue} index={2}>
            {/* SMTP Configuration */}
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
          </TabPanel>
        </Box>
      </Paper>

      {/* Save Button - Always visible */}
      <Box display="flex" justifyContent="flex-end" gap={2} sx={{ mt: 3 }}>
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

      {/* Device Add/Edit Dialog */}
      <Dialog open={deviceDialog.open} onClose={handleCloseDeviceDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {deviceDialog.mode === 'add' ? 'Add New Device' : 'Edit Device'}
        </DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label="IP Address"
            value={deviceForm.address}
            onChange={(e) => setDeviceForm({ ...deviceForm, address: e.target.value })}
            margin="normal"
            disabled={deviceDialog.mode === 'edit'}
            helperText={deviceDialog.mode === 'edit' ? 'IP address cannot be changed' : ''}
          />
          <TextField
            fullWidth
            label="Hostname"
            value={deviceForm.hostname}
            onChange={(e) => setDeviceForm({ ...deviceForm, hostname: e.target.value })}
            margin="normal"
          />
          <TextField
            fullWidth
            label="Role"
            value={deviceForm.role}
            onChange={(e) => setDeviceForm({ ...deviceForm, role: e.target.value })}
            margin="normal"
            helperText="e.g., edge, core, transit, lab"
          />
          <TextField
            fullWidth
            label="Region"
            value={deviceForm.region}
            onChange={(e) => setDeviceForm({ ...deviceForm, region: e.target.value })}
            margin="normal"
            helperText="e.g., us-east, us-west, eu-central"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDeviceDialog}>Cancel</Button>
          <Button onClick={handleSaveDevice} variant="contained">
            {deviceDialog.mode === 'add' ? 'Add' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  )
}

export default Configuration