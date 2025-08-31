import React from 'react'
import {
  Grid,
  Paper,
  Typography,
  Box,
  Chip,
  List,
  ListItem,
  ListItemText,
  LinearProgress,
  Alert,
} from '@mui/material'
import {
  Security as SecurityIcon,
  CheckCircle,
  Warning,
  Error as ErrorIcon,
  Schedule,
} from '@mui/icons-material'

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
  // Mock data for now - replace with actual API calls
  const rpkiData = {
    status: 'active',
    lastUpdate: new Date().toISOString(),
    statistics: {
      validPrefixes: 342567,
      invalidPrefixes: 1234,
      notFoundPrefixes: 45678,
      totalPrefixes: 389479,
    },
    recentValidations: [
      { asn: 'AS13335', prefix: '104.16.0.0/14', status: 'valid', time: '2 min ago' },
      { asn: 'AS15169', prefix: '8.8.8.0/24', status: 'valid', time: '5 min ago' },
      { asn: 'AS16509', prefix: '52.0.0.0/8', status: 'invalid', time: '7 min ago' },
      { asn: 'AS32934', prefix: '157.240.0.0/16', status: 'not-found', time: '12 min ago' },
    ],
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'valid':
        return 'success'
      case 'invalid':
        return 'error'
      case 'not-found':
        return 'warning'
      default:
        return 'default'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'valid':
        return <CheckCircle sx={{ color: '#00a86b', fontSize: 18 }} />
      case 'invalid':
        return <ErrorIcon sx={{ color: '#ff5252', fontSize: 18 }} />
      case 'not-found':
        return <Warning sx={{ color: '#ffa726', fontSize: 18 }} />
      default:
        return null
    }
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
            label={rpkiData.status === 'active' ? 'Active' : 'Inactive'}
            size="small"
            sx={{
              bgcolor: rpkiData.status === 'active' ? '#00a86b' : '#666',
              color: '#fff',
            }}
          />
        </Box>
      </Grid>

      {/* Metrics */}
      <Grid item xs={12} sm={6} md={3}>
        <RpkiMetricCard
          label="Valid Prefixes"
          value={rpkiData.statistics.validPrefixes}
          total={rpkiData.statistics.totalPrefixes}
          color="#00a86b"
        />
      </Grid>
      <Grid item xs={12} sm={6} md={3}>
        <RpkiMetricCard
          label="Invalid Prefixes"
          value={rpkiData.statistics.invalidPrefixes}
          total={rpkiData.statistics.totalPrefixes}
          color="#ff5252"
        />
      </Grid>
      <Grid item xs={12} sm={6} md={3}>
        <RpkiMetricCard
          label="Not Found"
          value={rpkiData.statistics.notFoundPrefixes}
          total={rpkiData.statistics.totalPrefixes}
          color="#ffa726"
        />
      </Grid>
      <Grid item xs={12} sm={6} md={3}>
        <RpkiMetricCard
          label="Total Prefixes"
          value={rpkiData.statistics.totalPrefixes}
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
                {new Date(rpkiData.lastUpdate).toLocaleString()}
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

      {/* Recent Validations */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ border: '1px solid #333', overflow: 'hidden' }}>
          <Box sx={{ p: 2, borderBottom: '1px solid #333', bgcolor: '#1a1a1a' }}>
            <Typography variant="body1" sx={{ color: '#f5f5f5', fontWeight: 600 }}>
              Recent Validations
            </Typography>
          </Box>
          <List disablePadding>
            {rpkiData.recentValidations.map((validation, index) => (
              <ListItem
                key={index}
                sx={{
                  borderBottom: index < rpkiData.recentValidations.length - 1 ? '1px solid #333' : 'none',
                  py: 1,
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', mr: 2 }}>
                  {getStatusIcon(validation.status)}
                </Box>
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="body2" sx={{ color: '#f5f5f5', fontFamily: 'monospace' }}>
                        {validation.asn}
                      </Typography>
                      <Typography variant="body2" sx={{ color: '#888' }}>→</Typography>
                      <Typography variant="body2" sx={{ color: '#f5f5f5', fontFamily: 'monospace' }}>
                        {validation.prefix}
                      </Typography>
                    </Box>
                  }
                  secondary={
                    <Typography variant="caption" sx={{ color: '#888' }}>
                      {validation.time}
                    </Typography>
                  }
                />
                <Chip
                  label={validation.status}
                  size="small"
                  color={getStatusColor(validation.status) as any}
                  sx={{ height: 20, fontSize: '0.7rem' }}
                />
              </ListItem>
            ))}
          </List>
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