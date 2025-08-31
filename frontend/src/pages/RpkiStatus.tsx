import React from 'react'
import {
  Grid,
  Paper,
  Typography,
  Box,
  Chip,
  LinearProgress,
  Alert,
} from '@mui/material'
import {
  Security as SecurityIcon,
  Schedule,
} from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
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
  // Fetch real RPKI data
  const { data: rpkiData, isLoading } = useQuery({
    queryKey: ['rpki-status'],
    queryFn: () => apiClient.getRpkiStatus(),
    refetchInterval: 60000, // Refresh every minute
  })

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
      </Grid>

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
            RPKI Cache Status
          </Typography>
          <Box sx={{ display: 'grid', gap: 1 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#888' }}>Last Update</Typography>
              <Typography variant="body2" sx={{ color: '#f5f5f5' }}>
                {rpkiData?.lastUpdate ? new Date(rpkiData.lastUpdate).toLocaleString() : 'Never'}
              </Typography>
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
                  in 42 minutes
                </Typography>
              </Box>
            </Box>
          </Box>
        </Paper>
      </Grid>

      {/* Timer Status */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ p: 2, border: '1px solid #333' }}>
          <Typography variant="body1" sx={{ color: '#f5f5f5', fontWeight: 600, mb: 2 }}>
            RPKI Service Status
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