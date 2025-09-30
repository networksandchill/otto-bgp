import React, { useState } from 'react'
import {
  Grid,
  Paper,
  Typography,
  Box,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Alert,
  IconButton,
  Tooltip,
  Tab,
  Tabs,
} from '@mui/material'
import {
  Block as BlockIcon,
  CheckCircle as CheckCircleIcon,
  Add as AddIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'

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
      id={`tabpanel-${index}`}
      aria-labelledby={`tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  )
}

const RpkiOverrides: React.FC = () => {
  const queryClient = useQueryClient()
  const [tabValue, setTabValue] = useState(0)
  const [openDialog, setOpenDialog] = useState(false)
  const [dialogType, setDialogType] = useState<'enable' | 'disable'>('disable')
  const [selectedAs, setSelectedAs] = useState<number | null>(null)
  const [asInput, setAsInput] = useState('')
  const [reasonInput, setReasonInput] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Fetch overrides
  const { data: overridesData, isLoading } = useQuery({
    queryKey: ['rpki-overrides'],
    queryFn: () => apiClient.listRpkiOverrides(),
    refetchInterval: 30000,
  })

  // Fetch history
  const { data: historyData } = useQuery({
    queryKey: ['rpki-override-history'],
    queryFn: () => apiClient.getRpkiOverrideHistory(),
    refetchInterval: 60000,
  })

  // Mutations
  const disableMutation = useMutation({
    mutationFn: ({ asNumber, reason }: { asNumber: number; reason: string }) =>
      apiClient.disableRpkiForAs(asNumber, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rpki-overrides'] })
      queryClient.invalidateQueries({ queryKey: ['rpki-override-history'] })
      handleCloseDialog()
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to disable RPKI')
    },
  })

  const enableMutation = useMutation({
    mutationFn: ({ asNumber, reason }: { asNumber: number; reason: string }) =>
      apiClient.enableRpkiForAs(asNumber, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rpki-overrides'] })
      queryClient.invalidateQueries({ queryKey: ['rpki-override-history'] })
      handleCloseDialog()
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to enable RPKI')
    },
  })

  const handleOpenDialog = (type: 'enable' | 'disable', asNumber?: number) => {
    setDialogType(type)
    setSelectedAs(asNumber || null)
    setAsInput(asNumber?.toString() || '')
    setReasonInput('')
    setError(null)
    setOpenDialog(true)
  }

  const handleCloseDialog = () => {
    setOpenDialog(false)
    setSelectedAs(null)
    setAsInput('')
    setReasonInput('')
    setError(null)
  }

  const handleSubmit = () => {
    const asNumber = selectedAs || parseInt(asInput)
    if (!asNumber || isNaN(asNumber)) {
      setError('Please enter a valid AS number')
      return
    }
    if (!reasonInput.trim()) {
      setError('Please provide a reason')
      return
    }

    if (dialogType === 'disable') {
      disableMutation.mutate({ asNumber, reason: reasonInput })
    } else {
      enableMutation.mutate({ asNumber, reason: reasonInput })
    }
  }

  const overrides = overridesData?.overrides || []
  const history = historyData?.history || []

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <Typography sx={{ color: '#888' }}>Loading RPKI overrides...</Typography>
      </Box>
    )
  }

  return (
    <Grid container spacing={2}>
      {/* Header */}
      <Grid item xs={12}>
        <Paper sx={{ p: 2, border: '1px solid #333', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <BlockIcon sx={{ color: '#888' }} />
            <Typography variant="h6" sx={{ color: '#f5f5f5' }}>
              RPKI Override Management
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => handleOpenDialog('disable')}
              sx={{ textTransform: 'none' }}
            >
              Add Override
            </Button>
            <Tooltip title="Refresh">
              <IconButton
                onClick={() => {
                  queryClient.invalidateQueries({ queryKey: ['rpki-overrides'] })
                  queryClient.invalidateQueries({ queryKey: ['rpki-override-history'] })
                }}
                sx={{ color: '#888' }}
              >
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>
        </Paper>
      </Grid>

      {/* Tabs */}
      <Grid item xs={12}>
        <Paper sx={{ border: '1px solid #333' }}>
          <Tabs
            value={tabValue}
            onChange={(_, newValue) => setTabValue(newValue)}
            sx={{
              borderBottom: '1px solid #333',
              '& .MuiTab-root': { textTransform: 'none' },
            }}
          >
            <Tab label={`Overrides (${overrides.length})`} />
            <Tab label="History" />
          </Tabs>

          <TabPanel value={tabValue} index={0}>
            {/* Overrides Table */}
            {overrides.length === 0 ? (
              <Box sx={{ p: 4, textAlign: 'center' }}>
                <Typography sx={{ color: '#888' }}>
                  No RPKI overrides configured
                </Typography>
              </Box>
            ) : (
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow sx={{ '& th': { borderBottom: '1px solid #333' } }}>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>AS Number</TableCell>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>Status</TableCell>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>Reason</TableCell>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>Modified</TableCell>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>Modified By</TableCell>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {overrides.map((override) => (
                      <TableRow key={override.as_number} sx={{ '& td': { borderBottom: '1px solid #333' } }}>
                        <TableCell sx={{ color: '#f5f5f5' }}>AS{override.as_number}</TableCell>
                        <TableCell>
                          <Chip
                            label={override.rpki_enabled ? 'Enabled' : 'Disabled'}
                            color={override.rpki_enabled ? 'success' : 'error'}
                            size="small"
                            icon={override.rpki_enabled ? <CheckCircleIcon /> : <BlockIcon />}
                          />
                        </TableCell>
                        <TableCell sx={{ color: '#b3b3b3', maxWidth: 300 }}>
                          {override.reason || '-'}
                        </TableCell>
                        <TableCell sx={{ color: '#888', fontSize: '0.875rem' }}>
                          {new Date(override.modified_date).toLocaleString()}
                        </TableCell>
                        <TableCell sx={{ color: '#888' }}>
                          {override.modified_by || '-'}
                        </TableCell>
                        <TableCell>
                          {override.rpki_enabled ? (
                            <Button
                              size="small"
                              startIcon={<BlockIcon />}
                              onClick={() => handleOpenDialog('disable', override.as_number)}
                              sx={{ textTransform: 'none' }}
                            >
                              Disable
                            </Button>
                          ) : (
                            <Button
                              size="small"
                              startIcon={<CheckCircleIcon />}
                              onClick={() => handleOpenDialog('enable', override.as_number)}
                              sx={{ textTransform: 'none' }}
                            >
                              Enable
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </TabPanel>

          <TabPanel value={tabValue} index={1}>
            {/* History Table */}
            {history.length === 0 ? (
              <Box sx={{ p: 4, textAlign: 'center' }}>
                <Typography sx={{ color: '#888' }}>
                  No override history available
                </Typography>
              </Box>
            ) : (
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow sx={{ '& th': { borderBottom: '1px solid #333' } }}>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>Timestamp</TableCell>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>AS Number</TableCell>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>Action</TableCell>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>Reason</TableCell>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>User</TableCell>
                      <TableCell sx={{ color: '#888', fontWeight: 600 }}>IP Address</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {history.map((entry) => (
                      <TableRow key={entry.id} sx={{ '& td': { borderBottom: '1px solid #333' } }}>
                        <TableCell sx={{ color: '#888', fontSize: '0.875rem' }}>
                          {new Date(entry.timestamp).toLocaleString()}
                        </TableCell>
                        <TableCell sx={{ color: '#f5f5f5' }}>AS{entry.as_number}</TableCell>
                        <TableCell>
                          <Chip
                            label={entry.action}
                            color={entry.action === 'enable' ? 'success' : 'error'}
                            size="small"
                          />
                        </TableCell>
                        <TableCell sx={{ color: '#b3b3b3', maxWidth: 300 }}>
                          {entry.reason || '-'}
                        </TableCell>
                        <TableCell sx={{ color: '#888' }}>{entry.user || '-'}</TableCell>
                        <TableCell sx={{ color: '#888' }}>{entry.ip_address || '-'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </TabPanel>
        </Paper>
      </Grid>

      {/* Dialog */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {dialogType === 'disable' ? 'Disable RPKI Validation' : 'Enable RPKI Validation'}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {error && (
              <Alert severity="error" onClose={() => setError(null)}>
                {error}
              </Alert>
            )}
            {!selectedAs && (
              <TextField
                label="AS Number"
                type="number"
                value={asInput}
                onChange={(e) => setAsInput(e.target.value)}
                fullWidth
                placeholder="e.g., 13335"
                helperText="Enter the AS number to manage"
              />
            )}
            {selectedAs && (
              <Alert severity="info">
                AS Number: <strong>AS{selectedAs}</strong>
              </Alert>
            )}
            <TextField
              label="Reason"
              value={reasonInput}
              onChange={(e) => setReasonInput(e.target.value)}
              fullWidth
              multiline
              rows={3}
              placeholder="Enter a reason for this change"
              helperText="This will be logged in the audit trail"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={disableMutation.isPending || enableMutation.isPending}
          >
            {dialogType === 'disable' ? 'Disable RPKI' : 'Enable RPKI'}
          </Button>
        </DialogActions>
      </Dialog>
    </Grid>
  )
}

export default RpkiOverrides