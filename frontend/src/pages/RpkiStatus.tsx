import React, { useState } from 'react'
import {
  Grid,
  Paper,
  Typography,
  Box,
  Chip,
  LinearProgress,
  Alert,
  Button,
  CircularProgress,
} from '@mui/material'
import {
  Security as SecurityIcon,
  Schedule,
  Refresh as RefreshIcon,
  Warning as WarningIcon,
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'

interface RpkiMetric {
  label: string
  value: number
  total?: number
  color: string
}

const RpkiMetricCard: React.FC<RpkiMetric> = ({ label, value, total, color }) => (
  <Paper sx={{ p: 2, border: '1px solid #333' }}>
    <Typography variant="caption" sx={{ color: '#888', textTransform: 'uppercase', fontSize: '0.7rem' }}>
      {label}
    </Typography>
    <Typography variant="h4" sx={{ color: '#f5f5f5', fontWeight: 300, mt: 1 }}>
      {value.toLocaleString()}
    </Typography>
    {total && (
      <>
        <Typography variant="caption" sx={{ color: '#888' }}>
          of {total.toLocaleString()} total
        </Typography>
        <LinearProgress
          variant="determinate"
          value={(value / total) * 100}
          sx={{
            mt: 1,
            height: 4,
            borderRadius: 2,
            bgcolor: '#333',
            '& .MuiLinearProgress-bar': { bgcolor: color },
          }}
        />
      </>
    )}
  </Paper>
)

const RpkiStatus: React.FC = () => {
  const queryClient = useQueryClient()
  const [refreshError, setRefreshError] = useState<string | null>(null)

  // Fetch real RPKI data
  const { data: rpkiData, isLoading } = useQuery({
    queryKey: ['rpki-status'],
    queryFn: () => apiClient.getRpkiStatus(),
    refetchInterval: 60000, // Refresh every minute
  })

  // Refresh cache mutation
  const refreshMutation = useMutation({
    mutationFn: () => apiClient.refreshRpkiCache(),
    onSuccess: (data) => {
      if (data.ok) {
        setRefreshError(null)
        // Refetch RPKI status after successful refresh
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: ['rpki-status'] })
        }, 3000) // Wait 3s for cache to update
      } else {
        setRefreshError('Refresh attempted but may have failed')
      }
    },
    onError: () => {
      setRefreshError('Failed to trigger cache refresh')
    },
  })

  const handleRefresh = () => {
    setRefreshError(null)
    refreshMutation.mutate()
  }

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <Typography sx={{ color: '#888' }}>Loading RPKI status...</Typography>
      </Box>
    )
  }

  const stats = rpkiData?.statistics || {
    validPrefixes: 0,
    invalidPrefixes: 0,
    notFoundPrefixes: 0,
    totalPrefixes: 0,
  }


  return (
    <Grid container spacing={2}>
      {/* Header */}
      <Grid item xs={12}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h6" sx={{ color: '#f5f5f5', fontWeight: 600 }}>
            RPKI Validation Status
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Button
              variant="outlined"
              size="small"
              startIcon={refreshMutation.isPending ? <CircularProgress size={16} /> : <RefreshIcon />}
              onClick={handleRefresh}
              disabled={refreshMutation.isPending}
              sx={{
                borderColor: '#333',
                color: '#f5f5f5',
                '&:hover': { borderColor: '#666', bgcolor: 'rgba(255,255,255,0.05)' },
              }}
            >
              {refreshMutation.isPending ? 'Refreshing...' : 'Refresh Now'}
            </Button>
            <Chip
              icon={<SecurityIcon sx={{ fontSize: 16 }} />}
              label={rpkiData?.status === 'active' ? 'Active' : 'Inactive'}
              size="small"
              sx={{
                bgcolor: rpkiData?.status === 'active' ? '#00a86b' : '#666',
                color: '#fff',
              }}
            />
          </Box>
        </Box>
      </Grid>

      {/* Staleness Warning */}
      {rpkiData?.stale && (
        <Grid item xs={12}>
          <Alert
            severity="warning"
            icon={<WarningIcon />}
            sx={{ bgcolor: '#3d2800', color: '#ffa726', border: '1px solid #ffa726' }}
          >
            VRP cache is stale (age: {rpkiData.ageSeconds ? `${Math.floor(rpkiData.ageSeconds / 3600)}h` : 'unknown'}).
            {rpkiData.failClosed && ' Fail-closed is enabled - operations may be blocked.'}
          </Alert>
        </Grid>
      )}

      {/* Refresh Error */}
      {refreshError && (
        <Grid item xs={12}>
          <Alert severity="error" sx={{ bgcolor: '#3d0000', color: '#ff5252', border: '1px solid #ff5252' }}>
            {refreshError}
          </Alert>
        </Grid>
      )}

      {/* Refresh Success */}
      {refreshMutation.isSuccess && !refreshError && (
        <Grid item xs={12}>
          <Alert severity="success" sx={{ bgcolor: '#003d00', color: '#00a86b', border: '1px solid #00a86b' }}>
            Cache refresh triggered successfully. Status will update in a few seconds.
          </Alert>
        </Grid>
      )}

      {/* Metrics */}
      <Grid item xs={12} sm={6} md={3}>
        <RpkiMetricCard
          label="Valid Prefixes"
          value={stats.validPrefixes}
          total={stats.totalPrefixes}
          color="#00a86b"
        />
      </Grid>
      <Grid item xs={12} sm={6} md={3}>
        <RpkiMetricCard
          label="Invalid Prefixes"
          value={stats.invalidPrefixes}
          total={stats.totalPrefixes}
          color="#ff5252"
        />
      </Grid>
      <Grid item xs={12} sm={6} md={3}>
        <RpkiMetricCard
          label="Not Found"
          value={stats.notFoundPrefixes}
          total={stats.totalPrefixes}
          color="#ffa726"
        />
      </Grid>
      <Grid item xs={12} sm={6} md={3}>
        <RpkiMetricCard
          label="Total Prefixes"
          value={stats.totalPrefixes}
          color="#0066cc"
        />
      </Grid>

      {/* Cache Status */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ p: 2, border: '1px solid #333' }}>
          <Typography variant="body1" sx={{ color: '#f5f5f5', fontWeight: 600, mb: 2 }}>
            Otto RPKI Cache Status
          </Typography>
          <Box sx={{ display: 'grid', gap: 1 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#888' }}>Last Update</Typography>
              <Typography variant="body2" sx={{ color: '#f5f5f5' }}>
                {rpkiData?.lastUpdate ? new Date(rpkiData.lastUpdate).toLocaleString() : 'Never'}
              </Typography>
            </Box>
            {rpkiData?.ageSeconds !== undefined && (
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" sx={{ color: '#888' }}>Cache Age</Typography>
                <Typography variant="body2" sx={{ color: rpkiData.stale ? '#ffa726' : '#f5f5f5' }}>
                  {Math.floor(rpkiData.ageSeconds / 3600)}h {Math.floor((rpkiData.ageSeconds % 3600) / 60)}m
                  {rpkiData.stale && ' (stale)'}
                </Typography>
              </Box>
            )}
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#888' }}>Fail-Closed Mode</Typography>
              <Chip
                label={rpkiData?.failClosed ? 'Enabled' : 'Disabled'}
                size="small"
                sx={{
                  bgcolor: rpkiData?.failClosed ? '#003d00' : '#666',
                  color: rpkiData?.failClosed ? '#00a86b' : '#f5f5f5',
                  height: 20,
                  fontSize: '0.7rem',
                }}
              />
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#888' }}>Update Frequency</Typography>
              <Typography variant="body2" sx={{ color: '#f5f5f5' }}>Hourly</Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#888' }}>Cache Source</Typography>
              <Typography variant="body2" sx={{ color: '#f5f5f5' }}>rpki-client</Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#888' }}>Next Update</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Schedule sx={{ fontSize: 14, color: '#888' }} />
                <Typography variant="body2" sx={{ color: '#f5f5f5' }}>
                  {(() => {
                    if (!rpkiData?.lastUpdate) return 'Unknown';
                    const lastUpdate = new Date(rpkiData.lastUpdate);
                    const nextUpdate = new Date(lastUpdate.getTime() + 60 * 60 * 1000); // Add 1 hour
                    const now = new Date();
                    const minutesUntilUpdate = Math.max(0, Math.round((nextUpdate.getTime() - now.getTime()) / 60000));
                    if (minutesUntilUpdate === 0) return 'Now';
                    if (minutesUntilUpdate < 60) return `in ${minutesUntilUpdate} minute${minutesUntilUpdate !== 1 ? 's' : ''}`;
                    const hoursUntilUpdate = Math.floor(minutesUntilUpdate / 60);
                    const remainingMinutes = minutesUntilUpdate % 60;
                    return `in ${hoursUntilUpdate} hour${hoursUntilUpdate !== 1 ? 's' : ''}${remainingMinutes > 0 ? ` ${remainingMinutes} min` : ''}`;
                  })()}
                </Typography>
              </Box>
            </Box>
          </Box>
        </Paper>
      </Grid>

      {/* System rpki-client Status */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ p: 2, border: '1px solid #333' }}>
          <Typography variant="body1" sx={{ color: '#f5f5f5', fontWeight: 600, mb: 2 }}>
            System RPKI Client Status
          </Typography>
          <Box sx={{ display: 'grid', gap: 1 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#888' }}>rpki-client.service</Typography>
              <Chip
                label={rpkiData?.systemRpkiClient?.serviceActive ? 'Active' : 'Inactive'}
                size="small"
                sx={{
                  bgcolor: rpkiData?.systemRpkiClient?.serviceActive ? '#00a86b' : '#666',
                  color: '#fff',
                  height: 20,
                }}
              />
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#888' }}>rpki-client.timer</Typography>
              <Chip
                label={rpkiData?.systemRpkiClient?.timerActive ? 'Active' : 'Inactive'}
                size="small"
                sx={{
                  bgcolor: rpkiData?.systemRpkiClient?.timerActive ? '#00a86b' : '#666',
                  color: '#fff',
                  height: 20,
                }}
              />
            </Box>
            {rpkiData?.systemRpkiClient?.lastRun && (
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" sx={{ color: '#888' }}>Last Run</Typography>
                <Typography variant="body2" sx={{ color: '#f5f5f5' }}>
                  {new Date(rpkiData.systemRpkiClient.lastRun).toLocaleString()}
                </Typography>
              </Box>
            )}
            {rpkiData?.systemRpkiClient?.nextRun && (
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" sx={{ color: '#888' }}>Next Run</Typography>
                <Typography variant="body2" sx={{ color: '#f5f5f5' }}>
                  {new Date(rpkiData.systemRpkiClient.nextRun).toLocaleString()}
                </Typography>
              </Box>
            )}
          </Box>
        </Paper>
      </Grid>

      {/* Otto RPKI Service Status */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ p: 2, border: '1px solid #333' }}>
          <Typography variant="body1" sx={{ color: '#f5f5f5', fontWeight: 600, mb: 2 }}>
            Otto RPKI Service Status
          </Typography>
          <Box sx={{ display: 'grid', gap: 1 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#888' }}>Update Timer</Typography>
              <Chip
                label={rpkiData?.timerActive ? 'Active' : 'Inactive'}
                size="small"
                sx={{
                  bgcolor: rpkiData?.timerActive ? '#00a86b' : '#666',
                  color: '#fff',
                  height: 20,
                }}
              />
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#888' }}>Cache Status</Typography>
              <Typography variant="body2" sx={{ color: '#f5f5f5' }}>
                {rpkiData?.status === 'active' ? 'Available' : 'Not Available'}
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#888' }}>Cache File</Typography>
              <Typography variant="body2" sx={{ color: '#f5f5f5', fontSize: '0.75rem', fontFamily: 'monospace' }}>
                /var/lib/otto-bgp/rpki/vrp_cache.json
              </Typography>
            </Box>
          </Box>
        </Paper>
      </Grid>

      {/* Info Alert */}
      <Grid item xs={12}>
        <Alert severity="info" sx={{ bgcolor: '#1a1a1a', color: '#f5f5f5' }}>
          RPKI validation is automatically performed on all BGP policies before application. 
          Invalid prefixes are rejected to maintain routing security.
        </Alert>
      </Grid>
    </Grid>
  )
}

export default RpkiStatus