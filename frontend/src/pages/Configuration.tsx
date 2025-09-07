import React, { useState, useEffect } from 'react'
import { 
  Container, Typography, Paper, Box, TextField, Button,
  Grid, Alert, Snackbar, FormControlLabel, Switch,
  Divider, Chip, Tabs, Tab, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, IconButton, Dialog,
  DialogTitle, DialogContent, DialogActions, Accordion,
  AccordionSummary, AccordionDetails
} from '@mui/material'
import { 
  Save as SaveIcon, Science as TestIcon, Add as AddIcon,
  Edit as EditIcon, Delete as DeleteIcon, Router as RouterIcon,
  Email as EmailIcon, Security as SecurityIcon, Shield as ShieldIcon,
  VerifiedUser as VerifiedIcon, Build as BuildIcon, 
  NetworkCheck as NetworkIcon, ExpandMore as ExpandMoreIcon,
  CheckCircle as CheckCircleIcon, PlayCircleOutline as AutoIcon
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
  
  // SSH Key Management state
  const [sshKeyInfo, setSshKeyInfo] = useState<{
    public_key?: string
    fingerprints?: { sha256: string; md5: string }
    path?: string
  } | null>(null)
  const [knownHosts, setKnownHosts] = useState<Array<{
    line: number
    host: string
    key_type: string
    fingerprint: string
    raw: string
  }>>([])
  const [sshKeyLoading, setSshKeyLoading] = useState(false)
  const [knownHostsLoading, setKnownHostsLoading] = useState(false)
  const [fetchHostDialog, setFetchHostDialog] = useState<{
    open: boolean
    host: string
    port: number
  }>({ open: false, host: '', port: 22 })
  const [addHostDialog, setAddHostDialog] = useState<{
    open: boolean
    entry: string
  }>({ open: false, entry: '' })
  const [backupDialog, setBackupDialog] = useState<{
    open: boolean
  }>({ open: false })
  const [backups, setBackups] = useState<Array<{
    id: string
    timestamp: string
    files: Array<{ name: string; size: number }>
  }>>([])
  const [backupsLoading, setBackupsLoading] = useState(false)
  
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

  // Load SSH key info when Global SSH tab is selected
  useEffect(() => {
    if (tabValue === 1) {
      loadSSHKeyInfo()
      loadKnownHosts()
    }
  }, [tabValue])

  useEffect(() => {
    if (backupDialog.open) {
      loadBackups()
    }
  }, [backupDialog.open])

  const loadSSHKeyInfo = async () => {
    try {
      setSshKeyLoading(true)
      const data = await apiClient.getSSHPublicKey()
      setSshKeyInfo(data)
    } catch (error) {
      // Key might not exist yet, which is ok
      setSshKeyInfo(null)
    } finally {
      setSshKeyLoading(false)
    }
  }

  const loadKnownHosts = async () => {
    try {
      setKnownHostsLoading(true)
      const data = await apiClient.getKnownHosts()
      setKnownHosts(data.entries || [])
    } catch (error) {
      setKnownHosts([])
    } finally {
      setKnownHostsLoading(false)
    }
  }

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

  const handleSendTestEmail = async () => {
    if (config?.smtp) {
      setTestResult(null)
      try {
        const result = await apiClient.sendTestEmail(config.smtp)
        setTestResult(result.success ? 'Test email sent successfully!' : `Failed: ${result.message}`)
      } catch (error: any) {
        setTestResult(`Failed: ${error.response?.data?.detail || error.message}`)
      }
    }
  }

  const handleValidateRpkiCache = async () => {
    try {
      const result = await apiClient.validateRpkiCache()
      if (result.ok) {
        setTestResult('RPKI cache is valid')
      } else {
        setTestResult(`RPKI cache issues: ${result.issues?.join(', ')}`)
      }
    } catch (error: any) {
      setTestResult(`Failed to validate RPKI cache: ${error.response?.data?.detail || error.message}`)
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

  // SSH Key Management Handlers
  const handleGenerateKey = async () => {
    try {
      setSshKeyLoading(true)
      const result = await apiClient.generateSSHKey({ key_type: 'ed25519' })
      setSshKeyInfo(result)
      setShowSuccess(true)
    } catch (error: any) {
      console.error('Failed to generate SSH key:', error)
    } finally {
      setSshKeyLoading(false)
    }
  }

  const handleUploadKey = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    
    try {
      setSshKeyLoading(true)
      const result = await apiClient.uploadSSHKey(file)
      setSshKeyInfo(result)
      setShowSuccess(true)
    } catch (error: any) {
      console.error('Failed to upload SSH key:', error)
    } finally {
      setSshKeyLoading(false)
    }
  }


  const handleFetchHost = async () => {
    if (!fetchHostDialog.host) return
    
    try {
      setKnownHostsLoading(true)
      const result = await apiClient.fetchHostKey(
        fetchHostDialog.host,
        fetchHostDialog.port
      )
      
      // Ask user to confirm adding the key
      if (confirm(`Add this host key?\n\nHost: ${fetchHostDialog.host}\nFingerprint: ${result.fingerprint}`)) {
        await apiClient.addKnownHost(result.key_entry)
        await loadKnownHosts()
        setShowSuccess(true)
      }
      
      setFetchHostDialog({ open: false, host: '', port: 22 })
    } catch (error: any) {
      console.error('Failed to fetch host key:', error)
      alert(`Failed to fetch host key: ${error.message || error}`)
    } finally {
      setKnownHostsLoading(false)
    }
  }

  const handleAddHost = async () => {
    if (!addHostDialog.entry) return
    
    try {
      await apiClient.addKnownHost(addHostDialog.entry)
      await loadKnownHosts()
      setAddHostDialog({ open: false, entry: '' })
      setShowSuccess(true)
    } catch (error: any) {
      console.error('Failed to add known host:', error)
      alert(`Failed to add host: ${error.message || error}`)
    }
  }

  const handleRemoveHost = async (lineNumber: number) => {
    if (confirm('Remove this host from known_hosts?')) {
      try {
        await apiClient.removeKnownHost(lineNumber)
        await loadKnownHosts()
        setShowSuccess(true)
      } catch (error: any) {
        console.error('Failed to remove host:', error)
      }
    }
  }

  // Export/Import handlers
  const handleExportConfig = async () => {
    try {
      const blob = await apiClient.exportConfig()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `otto_bgp_config_${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      setShowSuccess(true)
    } catch (error: any) {
      console.error('Failed to export config:', error)
      alert('Failed to export configuration')
    }
  }

  const handleImportConfig = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    
    if (!confirm('Import configuration? This will backup and replace the current configuration.')) {
      return
    }
    
    try {
      const result = await apiClient.importConfig(file)
      await queryClient.refetchQueries()
      setShowSuccess(true)
      alert(`Configuration imported successfully. Backup ID: ${result.backup_id}`)
      window.location.reload() // Reload to get new config
    } catch (error: any) {
      console.error('Failed to import config:', error)
      alert(`Failed to import configuration: ${error.message || error}`)
    }
  }

  const loadBackups = async () => {
    try {
      setBackupsLoading(true)
      const data = await apiClient.listBackups()
      setBackups(data.backups || [])
    } catch (error) {
      console.error('Failed to load backups:', error)
      setBackups([])
    } finally {
      setBackupsLoading(false)
    }
  }

  const handleRestoreBackup = async (backupId: string) => {
    if (!confirm(`Restore configuration from backup ${backupId}? Current configuration will be backed up first.`)) {
      return
    }
    
    try {
      const result = await apiClient.restoreBackup(backupId)
      await queryClient.refetchQueries()
      setBackupDialog({ open: false })
      setShowSuccess(true)
      alert(`Configuration restored successfully. Previous backup ID: ${result.previous_backup_id}`)
      window.location.reload() // Reload to get restored config
    } catch (error: any) {
      console.error('Failed to restore backup:', error)
      alert(`Failed to restore backup: ${error.message || error}`)
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
        <Tabs value={tabValue} onChange={handleTabChange} sx={{ borderBottom: 1, borderColor: 'divider', px: 2 }} variant="scrollable" scrollButtons="auto">
          <Tab icon={<RouterIcon />} label="Devices" />
          <Tab icon={<SecurityIcon />} label="Global SSH" />
          <Tab icon={<EmailIcon />} label="Notifications" />
          <Tab icon={<VerifiedIcon />} label="RPKI Validation" />
          <Tab icon={<BuildIcon />} label="BGPq4" />
          <Tab icon={<ShieldIcon />} label="Guardrails" />
          <Tab icon={<NetworkIcon />} label="Network Security" />
          <Tab icon={<AutoIcon />} label="Autonomous Mode" />
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
            
            {/* SSH Key Management Section */}
            <Box sx={{ mt: 4 }}>
              <Divider sx={{ mb: 3 }}>
                <Chip label="SSH Key Management" />
              </Divider>
              
              {/* SSH Key Actions */}
              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <Typography variant="h6" gutterBottom>
                    SSH Keypair
                  </Typography>
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <Button
                    variant="contained"
                    onClick={handleGenerateKey}
                    disabled={sshKeyLoading}
                    startIcon={<BuildIcon />}
                  >
                    Generate New Keypair
                  </Button>
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <Button
                    variant="outlined"
                    component="label"
                    disabled={sshKeyLoading}
                  >
                    Upload Private Key
                    <input
                      type="file"
                      hidden
                      accept=".pem,.key,*"
                      onChange={handleUploadKey}
                    />
                  </Button>
                </Grid>
                
                {/* Display SSH Key Info */}
                {sshKeyInfo?.public_key && (
                  <Grid item xs={12}>
                    <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>
                        Public Key
                      </Typography>
                      <TextField
                        fullWidth
                        multiline
                        rows={2}
                        value={sshKeyInfo?.public_key || ''}
                        InputProps={{ readOnly: true }}
                        variant="filled"
                        sx={{ mb: 2 }}
                      />
                      
                      {sshKeyInfo?.fingerprints && (
                        <>
                          <Typography variant="subtitle2" gutterBottom>
                            Fingerprints
                          </Typography>
                          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                            SHA256: {sshKeyInfo?.fingerprints?.sha256}
                          </Typography>
                          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                            MD5: {sshKeyInfo?.fingerprints?.md5}
                          </Typography>
                        </>
                      )}
                    </Paper>
                  </Grid>
                )}
              </Grid>
              
              {/* Known Hosts Management */}
              <Box sx={{ mt: 4 }}>
                <Typography variant="h6" gutterBottom>
                  Known Hosts
                </Typography>
                
                <Box display="flex" gap={2} mb={2}>
                  <Button
                    variant="outlined"
                    onClick={() => setAddHostDialog({ open: true, entry: '' })}
                    startIcon={<AddIcon />}
                  >
                    Add Entry
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={() => setFetchHostDialog({ open: true, host: '', port: 22 })}
                    startIcon={<NetworkIcon />}
                  >
                    Fetch Host Key
                  </Button>
                </Box>
                
                {knownHostsLoading ? (
                  <Typography>Loading known hosts...</Typography>
                ) : knownHosts.length > 0 ? (
                  <TableContainer component={Paper} variant="outlined">
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Host</TableCell>
                          <TableCell>Key Type</TableCell>
                          <TableCell>Fingerprint</TableCell>
                          <TableCell align="right">Actions</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {knownHosts.map((entry) => (
                          <TableRow key={entry.line}>
                            <TableCell>{entry.host}</TableCell>
                            <TableCell>{entry.key_type}</TableCell>
                            <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.875rem' }}>
                              {entry.fingerprint}
                            </TableCell>
                            <TableCell align="right">
                              <IconButton
                                size="small"
                                onClick={() => handleRemoveHost(entry.line)}
                                color="error"
                              >
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Typography color="text.secondary">
                    No known hosts configured
                  </Typography>
                )}
              </Box>
            </Box>
            
            {/* NETCONF Configuration Section */}
            <Box sx={{ mt: 4 }}>
              <Divider sx={{ mb: 3 }}>
                <Chip label="NETCONF Configuration" />
              </Divider>
              
              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <Typography variant="h6" gutterBottom>
                    NETCONF Defaults
                  </Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Configure default settings for NETCONF policy application
                  </Typography>
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="NETCONF Username"
                    value={config.netconf?.username || ''}
                    onChange={(e) => handleConfigChange('netconf', 'username', e.target.value)}
                    margin="normal"
                    helperText="Override SSH username for NETCONF"
                  />
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="NETCONF Password"
                    type="password"
                    value={config.netconf?.password || ''}
                    onChange={(e) => handleConfigChange('netconf', 'password', e.target.value)}
                    margin="normal"
                    helperText="Override SSH password for NETCONF"
                  />
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="SSH Key Path"
                    value={config.netconf?.ssh_key || ''}
                    onChange={(e) => handleConfigChange('netconf', 'ssh_key', e.target.value)}
                    margin="normal"
                    helperText="Path to SSH key for NETCONF authentication"
                  />
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="NETCONF Port"
                    type="number"
                    value={config.netconf?.port || 830}
                    onChange={(e) => handleConfigChange('netconf', 'port', parseInt(e.target.value))}
                    margin="normal"
                    helperText="Default: 830"
                  />
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="Operation Timeout (seconds)"
                    type="number"
                    value={config.netconf?.timeout || 60}
                    onChange={(e) => handleConfigChange('netconf', 'timeout', parseInt(e.target.value))}
                    margin="normal"
                    helperText="Timeout for NETCONF operations"
                  />
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="Default Confirmed Commit (minutes)"
                    type="number"
                    value={config.netconf?.default_confirmed_commit || 5}
                    onChange={(e) => handleConfigChange('netconf', 'default_confirmed_commit', parseInt(e.target.value))}
                    margin="normal"
                    helperText="Automatic rollback time if not confirmed"
                  />
                </Grid>
                
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="Commit Comment Prefix"
                    value={config.netconf?.commit_comment_prefix || '[Otto BGP]'}
                    onChange={(e) => handleConfigChange('netconf', 'commit_comment_prefix', e.target.value)}
                    margin="normal"
                    helperText="Prefix added to all commit messages"
                  />
                </Grid>
              </Grid>
            </Box>
          </TabPanel>

          <TabPanel value={tabValue} index={2}>
            {/* Notifications Configuration */}
            <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
              <Typography variant="h5">
                Email Notifications
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
                  
                  {/* Phase 1: Notification Preferences */}
                  <Grid item xs={12}>
                    <Divider sx={{ my: 2 }}>
                      <Chip label="Notification Preferences" />
                    </Divider>
                  </Grid>
                  
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Subject Prefix"
                      value={config.smtp?.subject_prefix || '[Otto BGP Autonomous]'}
                      onChange={(e) => handleConfigChange('smtp', 'subject_prefix', e.target.value)}
                      margin="normal"
                      helperText="Prefix added to all email subjects"
                    />
                  </Grid>
                  
                  <Grid item xs={12} md={6}>
                    <Box sx={{ mt: 2 }}>
                      <FormControlLabel
                        control={
                          <Switch
                            checked={config.smtp?.send_on_success || false}
                            onChange={(e) => handleConfigChange('smtp', 'send_on_success', e.target.checked)}
                          />
                        }
                        label="Send on Success"
                      />
                    </Box>
                  </Grid>
                  
                  <Grid item xs={12} md={6}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={config.smtp?.send_on_failure !== false}
                          onChange={(e) => handleConfigChange('smtp', 'send_on_failure', e.target.checked)}
                        />
                      }
                      label="Send on Failure"
                    />
                  </Grid>
                  
                  <Grid item xs={12} md={6}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={config.smtp?.alert_on_manual || false}
                          onChange={(e) => handleConfigChange('smtp', 'alert_on_manual', e.target.checked)}
                        />
                      }
                      label="Alert on Manual Actions"
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
                    {testSmtpMutation.isPending ? 'Testing...' : 'Validate Config'}
                  </Button>
                  
                  <Button
                    variant="contained"
                    startIcon={<EmailIcon />}
                    onClick={handleSendTestEmail}
                  >
                    Send Test Email
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

          {/* RPKI Validation Configuration */}
          <TabPanel value={tabValue} index={3}>
            <Typography variant="h5" gutterBottom>
              RPKI Validation Configuration
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Configure Route Origin Authorization (ROA) validation settings
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={config.rpki?.enabled || false}
                      onChange={(e) => handleConfigChange('rpki', 'enabled', e.target.checked)}
                    />
                  }
                  label="Enable RPKI Validation"
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Cache Directory"
                  value={config.rpki?.cache_dir || '/var/lib/otto-bgp/rpki'}
                  onChange={(e) => handleConfigChange('rpki', 'cache_dir', e.target.value)}
                  margin="normal"
                  helperText="Directory for RPKI cache files"
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Validator URL"
                  value={config.rpki?.validator_url || ''}
                  onChange={(e) => handleConfigChange('rpki', 'validator_url', e.target.value)}
                  margin="normal"
                  helperText="RPKI validator service URL"
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Refresh Interval (hours)"
                  type="number"
                  value={config.rpki?.refresh_interval || 24}
                  onChange={(e) => handleConfigChange('rpki', 'refresh_interval', parseInt(e.target.value))}
                  margin="normal"
                />
              </Grid>
              
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={config.rpki?.strict_validation || false}
                      onChange={(e) => handleConfigChange('rpki', 'strict_validation', e.target.checked)}
                    />
                  }
                  label="Strict Validation (reject invalid ROAs)"
                />
              </Grid>
              
              {/* Phase 2: Advanced RPKI Options */}
              <Grid item xs={12}>
                <Accordion sx={{ mt: 2 }}>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography>Advanced RPKI Settings</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Grid container spacing={2}>
                      <Grid item xs={12} md={6}>
                        <FormControlLabel
                          control={
                            <Switch
                              checked={config.rpki?.fail_closed !== false}
                              onChange={(e) => handleConfigChange('rpki', 'fail_closed', e.target.checked)}
                            />
                          }
                          label="Fail Closed (block on validation failure)"
                        />
                      </Grid>
                      
                      <Grid item xs={12} md={6}>
                        <TextField
                          fullWidth
                          type="number"
                          label="Max VRP Age (hours)"
                          value={config.rpki?.max_vrp_age_hours ?? 24}
                          onChange={(e) => handleConfigChange('rpki', 'max_vrp_age_hours', parseInt(e.target.value))}
                          margin="normal"
                          helperText="Maximum age for VRP cache data"
                        />
                      </Grid>
                      
                      <Grid item xs={12} md={6}>
                        <TextField
                          fullWidth
                          label="VRP Cache Path"
                          value={config.rpki?.vrp_cache_path || ''}
                          onChange={(e) => handleConfigChange('rpki', 'vrp_cache_path', e.target.value)}
                          margin="normal"
                          helperText="Path to VRP cache file"
                        />
                      </Grid>
                      
                      <Grid item xs={12} md={6}>
                        <TextField
                          fullWidth
                          label="Allowlist Path"
                          value={config.rpki?.allowlist_path || ''}
                          onChange={(e) => handleConfigChange('rpki', 'allowlist_path', e.target.value)}
                          margin="normal"
                          helperText="Path to RPKI allowlist file"
                        />
                      </Grid>
                      
                      <Grid item xs={12} md={6}>
                        <TextField
                          fullWidth
                          type="number"
                          label="Max Invalid Percent"
                          value={config.rpki?.max_invalid_percent ?? 10}
                          onChange={(e) => handleConfigChange('rpki', 'max_invalid_percent', parseInt(e.target.value))}
                          margin="normal"
                          helperText="Maximum percentage of invalid prefixes allowed"
                        />
                      </Grid>
                      
                      <Grid item xs={12} md={6}>
                        <TextField
                          fullWidth
                          type="number"
                          label="Max Not Found Percent"
                          value={config.rpki?.max_notfound_percent ?? 50}
                          onChange={(e) => handleConfigChange('rpki', 'max_notfound_percent', parseInt(e.target.value))}
                          margin="normal"
                          helperText="Maximum percentage of not-found prefixes allowed"
                        />
                      </Grid>
                      
                      <Grid item xs={12}>
                        <FormControlLabel
                          control={
                            <Switch
                              checked={config.rpki?.require_vrp_data || false}
                              onChange={(e) => handleConfigChange('rpki', 'require_vrp_data', e.target.checked)}
                            />
                          }
                          label="Require VRP Data (fail if no data available)"
                        />
                      </Grid>
                      
                      <Grid item xs={12}>
                        <Divider sx={{ my: 2 }} />
                        <Button
                          variant="outlined"
                          startIcon={<CheckCircleIcon />}
                          onClick={handleValidateRpkiCache}
                        >
                          Validate RPKI Cache
                        </Button>
                      </Grid>
                    </Grid>
                  </AccordionDetails>
                </Accordion>
              </Grid>
            </Grid>
          </TabPanel>

          {/* BGPq4 Configuration */}
          <TabPanel value={tabValue} index={4}>
            <Typography variant="h5" gutterBottom>
              BGPq4 Configuration
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Configure BGP policy generation settings
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Execution Mode"
                  value={config.bgpq4?.mode || 'auto'}
                  onChange={(e) => handleConfigChange('bgpq4', 'mode', e.target.value)}
                  margin="normal"
                  select
                  SelectProps={{ native: true }}
                  helperText="How to run bgpq4"
                >
                  <option value="auto">Auto-detect</option>
                  <option value="native">Native binary</option>
                  <option value="docker">Docker container</option>
                  <option value="podman">Podman container</option>
                </TextField>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Timeout (seconds)"
                  type="number"
                  value={config.bgpq4?.timeout || 45}
                  onChange={(e) => handleConfigChange('bgpq4', 'timeout', parseInt(e.target.value))}
                  margin="normal"
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="IRR Source"
                  value={config.bgpq4?.irr_source || 'RADB,RIPE,APNIC'}
                  onChange={(e) => handleConfigChange('bgpq4', 'irr_source', e.target.value)}
                  margin="normal"
                  helperText="Comma-separated list of IRR databases"
                />
              </Grid>
              
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={config.bgpq4?.aggregate_prefixes !== false}
                      onChange={(e) => handleConfigChange('bgpq4', 'aggregate_prefixes', e.target.checked)}
                    />
                  }
                  label="Aggregate Prefixes"
                />
              </Grid>
              
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={config.bgpq4?.ipv4_enabled !== false}
                      onChange={(e) => handleConfigChange('bgpq4', 'ipv4_enabled', e.target.checked)}
                    />
                  }
                  label="IPv4 Support"
                />
              </Grid>
              
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={config.bgpq4?.ipv6_enabled || false}
                      onChange={(e) => handleConfigChange('bgpq4', 'ipv6_enabled', e.target.checked)}
                    />
                  }
                  label="IPv6 Support"
                />
              </Grid>

              {/* IRR Proxy Configuration Subsection */}
              <Grid item xs={12}>
                <Divider sx={{ my: 3 }} />
                <Typography variant="h6" gutterBottom>
                  IRR Proxy Configuration
                </Typography>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Configure SSH tunnel for accessing IRR servers through a jump host
                </Typography>
              </Grid>

              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={config.irr_proxy?.enabled || false}
                      onChange={(e) => handleConfigChange('irr_proxy', 'enabled', e.target.checked)}
                    />
                  }
                  label="Enable IRR Proxy"
                />
              </Grid>

              {config.irr_proxy?.enabled && (
                <>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Proxy Method"
                      value={config.irr_proxy?.method || 'ssh_tunnel'}
                      onChange={(e) => handleConfigChange('irr_proxy', 'method', e.target.value)}
                      margin="normal"
                      select
                      SelectProps={{ native: true }}
                      helperText="Method for proxying IRR connections"
                    >
                      <option value="ssh_tunnel">SSH Tunnel</option>
                    </TextField>
                  </Grid>

                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Jump Host"
                      value={config.irr_proxy?.jump_host || ''}
                      onChange={(e) => handleConfigChange('irr_proxy', 'jump_host', e.target.value)}
                      margin="normal"
                      helperText="SSH jump host for tunnel (e.g., jump.example.com)"
                    />
                  </Grid>

                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Jump User"
                      value={config.irr_proxy?.jump_user || ''}
                      onChange={(e) => handleConfigChange('irr_proxy', 'jump_user', e.target.value)}
                      margin="normal"
                      helperText="Username for SSH jump host"
                    />
                  </Grid>

                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="SSH Key File"
                      value={config.irr_proxy?.ssh_key_file || ''}
                      onChange={(e) => handleConfigChange('irr_proxy', 'ssh_key_file', e.target.value)}
                      margin="normal"
                      helperText="Path to SSH private key (optional)"
                    />
                  </Grid>

                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Known Hosts File"
                      value={config.irr_proxy?.known_hosts_file || ''}
                      onChange={(e) => handleConfigChange('irr_proxy', 'known_hosts_file', e.target.value)}
                      margin="normal"
                      helperText="Path to SSH known_hosts file (optional)"
                    />
                  </Grid>

                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Connection Timeout (seconds)"
                      type="number"
                      value={config.irr_proxy?.connection_timeout || 30}
                      onChange={(e) => handleConfigChange('irr_proxy', 'connection_timeout', parseInt(e.target.value))}
                      margin="normal"
                      helperText="Timeout for establishing SSH tunnel"
                    />
                  </Grid>

                  <Grid item xs={12}>
                    <Button
                      variant="outlined"
                      startIcon={<TestIcon />}
                      onClick={async () => {
                        try {
                          const result = await apiClient.testIrrProxy()
                          alert(result.success 
                              ? 'IRR Proxy test successful' 
                              : `IRR Proxy test failed: ${result.message}`)
                        } catch (error: any) {
                          alert(`Failed to test IRR proxy: ${error.response?.data?.detail || error.message}`)
                        }
                      }}
                      disabled={!config.irr_proxy?.jump_host}
                    >
                      Test IRR Proxy
                    </Button>
                  </Grid>
                </>
              )}
            </Grid>
          </TabPanel>

          {/* Guardrail Configuration */}
          <TabPanel value={tabValue} index={5}>
            <Typography variant="h5" gutterBottom>
              Guardrail Configuration
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Configure safety mechanisms to prevent dangerous policy changes
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={config.guardrails?.enabled !== false}
                      onChange={(e) => handleConfigChange('guardrails', 'enabled', e.target.checked)}
                    />
                  }
                  label="Enable Guardrails"
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Max Prefix Change Threshold"
                  type="number"
                  value={config.guardrails?.max_prefix_threshold || 100}
                  onChange={(e) => handleConfigChange('guardrails', 'max_prefix_threshold', parseInt(e.target.value))}
                  margin="normal"
                  helperText="Maximum number of prefix changes allowed"
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Max Session Loss (%)"
                  type="number"
                  value={config.guardrails?.max_session_loss_percent || 5.0}
                  onChange={(e) => handleConfigChange('guardrails', 'max_session_loss_percent', parseFloat(e.target.value))}
                  margin="normal"
                  helperText="Maximum acceptable BGP session loss percentage"
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Max Route Loss (%)"
                  type="number"
                  value={config.guardrails?.max_route_loss_percent || 10.0}
                  onChange={(e) => handleConfigChange('guardrails', 'max_route_loss_percent', parseFloat(e.target.value))}
                  margin="normal"
                  helperText="Maximum acceptable route loss percentage"
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Monitoring Duration (seconds)"
                  type="number"
                  value={config.guardrails?.monitoring_duration || 300}
                  onChange={(e) => handleConfigChange('guardrails', 'monitoring_duration', parseInt(e.target.value))}
                  margin="normal"
                  helperText="Duration to monitor after policy application"
                />
              </Grid>
              
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={config.guardrails?.bogon_check_enabled !== false}
                      onChange={(e) => handleConfigChange('guardrails', 'bogon_check_enabled', e.target.checked)}
                    />
                  }
                  label="Enable Bogon Prefix Detection"
                />
              </Grid>
              
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={config.guardrails?.require_confirmation || false}
                      onChange={(e) => handleConfigChange('guardrails', 'require_confirmation', e.target.checked)}
                    />
                  }
                  label="Require Manual Confirmation"
                />
              </Grid>
            </Grid>
          </TabPanel>

          {/* Network Security Configuration */}
          <TabPanel value={tabValue} index={6}>
            <Typography variant="h5" gutterBottom>
              Network Security Configuration
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Configure network access and security settings
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="SSH Known Hosts File"
                  value={config.network_security?.ssh_known_hosts || '/var/lib/otto-bgp/ssh-keys/known_hosts'}
                  onChange={(e) => handleConfigChange('network_security', 'ssh_known_hosts', e.target.value)}
                  margin="normal"
                  helperText="Path to SSH known_hosts file"
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="SSH Connection Timeout (seconds)"
                  type="number"
                  value={config.network_security?.ssh_connection_timeout || 30}
                  onChange={(e) => handleConfigChange('network_security', 'ssh_connection_timeout', parseInt(e.target.value))}
                  margin="normal"
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Max Parallel SSH Workers"
                  type="number"
                  value={config.network_security?.ssh_max_workers || 5}
                  onChange={(e) => handleConfigChange('network_security', 'ssh_max_workers', parseInt(e.target.value))}
                  margin="normal"
                  helperText="Maximum concurrent SSH connections"
                />
              </Grid>
              
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={config.network_security?.strict_host_verification !== false}
                      onChange={(e) => handleConfigChange('network_security', 'strict_host_verification', e.target.checked)}
                    />
                  }
                  label="Strict SSH Host Key Verification"
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Allowed Networks"
                  value={config.network_security?.allowed_networks?.join(', ') || ''}
                  onChange={(e) => handleConfigChange('network_security', 'allowed_networks', 
                    e.target.value.split(',').map(s => s.trim()).filter(s => s)
                  )}
                  margin="normal"
                  helperText="Comma-separated list of allowed network CIDRs"
                  multiline
                  rows={2}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Blocked Networks"
                  value={config.network_security?.blocked_networks?.join(', ') || ''}
                  onChange={(e) => handleConfigChange('network_security', 'blocked_networks',
                    e.target.value.split(',').map(s => s.trim()).filter(s => s)
                  )}
                  margin="normal"
                  helperText="Comma-separated list of blocked network CIDRs"
                  multiline
                  rows={2}
                />
              </Grid>
            </Grid>
          </TabPanel>

          {/* Autonomous Mode Configuration */}
          <TabPanel value={tabValue} index={7}>
            <Typography variant="h5" gutterBottom>
              Autonomous Mode Configuration
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Configure unattended operation and automatic policy application
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={config.autonomous_mode?.enabled || false}
                      onChange={(e) => handleConfigChange('autonomous_mode', 'enabled', e.target.checked)}
                    />
                  }
                  label="Enable Autonomous Mode"
                />
                <Typography variant="body2" color="text.secondary" sx={{ ml: 4 }}>
                  When enabled, Otto BGP will operate unattended with enhanced safety guardrails
                </Typography>
              </Grid>
              
              {config.autonomous_mode?.enabled && (
                <>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Auto-Apply Threshold"
                      type="number"
                      value={config.autonomous_mode?.auto_apply_threshold ?? 100}
                      onChange={(e) => handleConfigChange('autonomous_mode', 'auto_apply_threshold', parseInt(e.target.value))}
                      margin="normal"
                      helperText="Maximum number of prefix changes to apply automatically"
                    />
                  </Grid>
                  
                  <Grid item xs={12}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={config.autonomous_mode?.require_confirmation !== false}
                          onChange={(e) => handleConfigChange('autonomous_mode', 'require_confirmation', e.target.checked)}
                        />
                      }
                      label="Require Confirmation for Major Changes"
                    />
                    <Typography variant="body2" color="text.secondary" sx={{ ml: 4 }}>
                      Prompt for confirmation when changes exceed safety thresholds
                    </Typography>
                  </Grid>
                  
                  <Grid item xs={12}>
                    <Divider sx={{ my: 2 }} />
                    <Typography variant="h6" gutterBottom>
                      Safety Overrides
                    </Typography>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Advanced settings for experienced operators (use with caution)
                    </Typography>
                  </Grid>
                  
                  <Grid item xs={12} md={4}>
                    <TextField
                      fullWidth
                      label="Max Session Loss %"
                      type="number"
                      value={config.autonomous_mode?.safety_overrides?.max_session_loss_percent ?? 10}
                      onChange={(e) => {
                        const newValue = parseInt(e.target.value)
                        setConfig(prev => ({
                          ...prev!,
                          autonomous_mode: {
                            ...prev!.autonomous_mode!,
                            safety_overrides: {
                              ...prev!.autonomous_mode?.safety_overrides,
                              max_session_loss_percent: newValue
                            }
                          }
                        }))
                      }}
                      margin="normal"
                      helperText="Maximum acceptable BGP session loss percentage"
                      inputProps={{ min: 0, max: 100 }}
                    />
                  </Grid>
                  
                  <Grid item xs={12} md={4}>
                    <TextField
                      fullWidth
                      label="Max Route Loss %"
                      type="number"
                      value={config.autonomous_mode?.safety_overrides?.max_route_loss_percent ?? 20}
                      onChange={(e) => {
                        const newValue = parseInt(e.target.value)
                        setConfig(prev => ({
                          ...prev!,
                          autonomous_mode: {
                            ...prev!.autonomous_mode!,
                            safety_overrides: {
                              ...prev!.autonomous_mode?.safety_overrides,
                              max_route_loss_percent: newValue
                            }
                          }
                        }))
                      }}
                      margin="normal"
                      helperText="Maximum acceptable route loss percentage"
                      inputProps={{ min: 0, max: 100 }}
                    />
                  </Grid>
                  
                  <Grid item xs={12} md={4}>
                    <TextField
                      fullWidth
                      label="Monitoring Duration (seconds)"
                      type="number"
                      value={config.autonomous_mode?.safety_overrides?.monitoring_duration_seconds ?? 300}
                      onChange={(e) => {
                        const newValue = parseInt(e.target.value)
                        setConfig(prev => ({
                          ...prev!,
                          autonomous_mode: {
                            ...prev!.autonomous_mode!,
                            safety_overrides: {
                              ...prev!.autonomous_mode?.safety_overrides,
                              monitoring_duration_seconds: newValue
                            }
                          }
                        }))
                      }}
                      margin="normal"
                      helperText="Duration to monitor for impact after policy application"
                      inputProps={{ min: 60, max: 3600 }}
                    />
                  </Grid>
                </>
              )}
            </Grid>
          </TabPanel>
        </Box>
      </Paper>

      {/* Configuration Actions - Always visible */}
      <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mt: 3 }}>
        {/* Export/Import Actions */}
        <Box display="flex" gap={2}>
          <Button
            variant="outlined"
            onClick={handleExportConfig}
            startIcon={<SaveIcon />}
          >
            Export Config
          </Button>
          <Button
            variant="outlined"
            component="label"
            startIcon={<SaveIcon />}
          >
            Import Config
            <input
              type="file"
              hidden
              accept=".json"
              onChange={handleImportConfig}
            />
          </Button>
          <Button
            variant="outlined"
            onClick={() => setBackupDialog({ open: true })}
          >
            Manage Backups
          </Button>
        </Box>
        
        {/* Save Button */}
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

      {/* Fetch Host Key Dialog */}
      <Dialog open={fetchHostDialog.open} onClose={() => setFetchHostDialog({ open: false, host: '', port: 22 })} maxWidth="sm" fullWidth>
        <DialogTitle>Fetch Host Key</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label="Host"
            value={fetchHostDialog.host}
            onChange={(e) => setFetchHostDialog({ ...fetchHostDialog, host: e.target.value })}
            margin="normal"
            helperText="Hostname or IP address"
            autoFocus
          />
          <TextField
            fullWidth
            label="Port"
            type="number"
            value={fetchHostDialog.port}
            onChange={(e) => setFetchHostDialog({ ...fetchHostDialog, port: parseInt(e.target.value) || 22 })}
            margin="normal"
            helperText="SSH port (default: 22)"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFetchHostDialog({ open: false, host: '', port: 22 })}>
            Cancel
          </Button>
          <Button 
            onClick={handleFetchHost} 
            variant="contained"
            disabled={!fetchHostDialog.host || knownHostsLoading}
          >
            Fetch
          </Button>
        </DialogActions>
      </Dialog>

      {/* Add Known Host Dialog */}
      <Dialog open={addHostDialog.open} onClose={() => setAddHostDialog({ open: false, entry: '' })} maxWidth="md" fullWidth>
        <DialogTitle>Add Known Host Entry</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label="Host Key Entry"
            value={addHostDialog.entry}
            onChange={(e) => setAddHostDialog({ ...addHostDialog, entry: e.target.value })}
            margin="normal"
            multiline
            rows={3}
            helperText="Paste the complete known_hosts entry (e.g., hostname ssh-rsa AAAAB3...)"
            autoFocus
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddHostDialog({ open: false, entry: '' })}>
            Cancel
          </Button>
          <Button 
            onClick={handleAddHost} 
            variant="contained"
            disabled={!addHostDialog.entry}
          >
            Add
          </Button>
        </DialogActions>
      </Dialog>

      {/* Backup Management Dialog */}
      <Dialog open={backupDialog.open} onClose={() => setBackupDialog({ open: false })} maxWidth="md" fullWidth>
        <DialogTitle>Manage Configuration Backups</DialogTitle>
        <DialogContent>
          {backupsLoading ? (
            <Typography>Loading backups...</Typography>
          ) : backups.length === 0 ? (
            <Typography color="text.secondary">No backups available</Typography>
          ) : (
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Backup ID</TableCell>
                    <TableCell>Files</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {backups.map((backup) => (
                    <TableRow key={backup.id}>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                          {backup.timestamp}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        {backup.files.map(f => f.name).join(', ')}
                      </TableCell>
                      <TableCell align="right">
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => handleRestoreBackup(backup.id)}
                        >
                          Restore
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBackupDialog({ open: false })}>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  )
}

export default Configuration