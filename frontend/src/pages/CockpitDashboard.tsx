import React from 'react'
import {
  Grid,
  Paper,
  Typography,
  Box,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  Chip,
  IconButton,
} from '@mui/material'
import {
  Memory as MemoryIcon,
  Storage as StorageIcon,
  NetworkCheck as NetworkIcon,
  Schedule as ScheduleIcon,
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  Refresh as RefreshIcon,
  CheckCircle,
  Error,
  Warning,
} from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'

interface MetricCardProps {
  title: string
  value: string | number
  unit?: string
  icon: React.ReactNode
  progress?: number
  color?: string
}

const MetricCard: React.FC<MetricCardProps> = ({ title, value, unit, icon, progress, color = '#0066cc' }) => (
  <Paper sx={{ p: 2, height: '100%', border: '1px solid #333', borderRadius: 1 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
      <Box sx={{ color, mr: 1 }}>{icon}</Box>
      <Typography variant="caption" sx={{ color: '#888', textTransform: 'uppercase', fontSize: '0.7rem' }}>
        {title}
      </Typography>
    </Box>
    <Typography variant="h4" sx={{ color: '#f5f5f5', fontWeight: 300 }}>
      {value}
      {unit && <Typography component="span" variant="body2" sx={{ color: '#888', ml: 0.5 }}>{unit}</Typography>}
    </Typography>
    {progress !== undefined && (
      <LinearProgress
        variant="determinate"
        value={progress}
        sx={{
          mt: 1,
          height: 4,
          borderRadius: 2,
          bgcolor: '#333',
          '& .MuiLinearProgress-bar': {
            bgcolor: progress > 80 ? '#ff5252' : progress > 60 ? '#ffa726' : color,
          },
        }}
      />
    )}
  </Paper>
)

interface ServiceRowProps {
  name: string
  description: string
  status: 'active' | 'inactive' | 'failed' | 'unknown'
  onAction?: (action: 'start' | 'stop' | 'restart') => void
}

const ServiceRow: React.FC<ServiceRowProps> = ({ name, description, status, onAction }) => {
  const getStatusIcon = () => {
    switch (status) {
      case 'active':
        return <CheckCircle sx={{ color: '#00a86b', fontSize: 20 }} />
      case 'failed':
        return <Error sx={{ color: '#ff5252', fontSize: 20 }} />
      case 'inactive':
        return <Warning sx={{ color: '#888', fontSize: 20 }} />
      default:
        return <Warning sx={{ color: '#ffa726', fontSize: 20 }} />
    }
  }

  return (
    <ListItem
      sx={{
        borderBottom: '1px solid #333',
        '&:last-child': { borderBottom: 'none' },
        px: 2,
        py: 1.5,
      }}
      secondaryAction={
        onAction && (
          <Box>
            {status === 'active' ? (
              <IconButton size="small" onClick={() => onAction('stop')} sx={{ color: '#888' }}>
                <StopIcon fontSize="small" />
              </IconButton>
            ) : (
              <IconButton size="small" onClick={() => onAction('start')} sx={{ color: '#888' }}>
                <PlayIcon fontSize="small" />
              </IconButton>
            )}
            <IconButton size="small" onClick={() => onAction('restart')} sx={{ color: '#888', ml: 1 }}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Box>
        )
      }
    >
      <Box sx={{ display: 'flex', alignItems: 'center', mr: 2 }}>
        {getStatusIcon()}
      </Box>
      <ListItemText
        primary={
          <Typography variant="body2" sx={{ color: '#f5f5f5', fontWeight: 500 }}>
            {name}
          </Typography>
        }
        secondary={
          <Typography variant="caption" sx={{ color: '#888' }}>
            {description}
          </Typography>
        }
      />
    </ListItem>
  )
}

const CockpitDashboard: React.FC = () => {
  // Query deployment matrix for stats
  const { data: matrix } = useQuery({
    queryKey: ['deployment-matrix'],
    queryFn: () => apiClient.getDeploymentMatrix(),
    retry: false,
  })

  // Query systemd units status
  const { data: systemdData } = useQuery({
    queryKey: ['systemd-units'],
    queryFn: () => apiClient.getSystemdUnits([
      'otto-bgp.service',
      'otto-bgp-webui-adapter.service',
      'otto-bgp-rpki-update.service',
      'otto-bgp.timer',
      'otto-bgp-rpki-update.timer',
    ]),
    refetchInterval: 30000,
  })

  const stats = matrix?.statistics || {
    total_routers: 0,
    total_as_numbers: 0,
    total_bgp_groups: 0,
  }

  const getServiceStatus = (unitName: string): 'active' | 'inactive' | 'failed' | 'unknown' => {
    const unit = systemdData?.units.find(u => u.name === unitName)
    if (unit?.error) return 'failed'
    if (unit?.activestate === 'active') return 'active'
    if (unit?.activestate === 'inactive') return 'inactive'
    return 'unknown'
  }

  const handleServiceAction = (serviceName: string, action: string) => {
    console.log(`${action} service: ${serviceName}`)
    // TODO: Implement service control
  }

  return (
    <Grid container spacing={2}>
      {/* System Metrics Row */}
      <Grid item xs={12}>
        <Typography variant="h6" sx={{ color: '#f5f5f5', mb: 2, fontWeight: 600 }}>
          System Overview
        </Typography>
      </Grid>

      <Grid item xs={12} sm={6} md={3}>
        <MetricCard
          title="Routers"
          value={stats.total_routers}
          icon={<NetworkIcon />}
          color="#0066cc"
        />
      </Grid>

      <Grid item xs={12} sm={6} md={3}>
        <MetricCard
          title="AS Numbers"
          value={stats.total_as_numbers}
          icon={<StorageIcon />}
          color="#00a86b"
        />
      </Grid>

      <Grid item xs={12} sm={6} md={3}>
        <MetricCard
          title="BGP Groups"
          value={stats.total_bgp_groups}
          icon={<MemoryIcon />}
          color="#9c27b0"
        />
      </Grid>

      <Grid item xs={12} sm={6} md={3}>
        <MetricCard
          title="Policies"
          value={(stats as any).total_policies || 0}
          icon={<ScheduleIcon />}
          color="#ff9800"
        />
      </Grid>

      {/* Services Section */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ border: '1px solid #333', borderRadius: 1, overflow: 'hidden' }}>
          <Box sx={{ p: 2, borderBottom: '1px solid #333', bgcolor: '#1a1a1a' }}>
            <Typography variant="body1" sx={{ color: '#f5f5f5', fontWeight: 600 }}>
              System Services
            </Typography>
          </Box>
          <List disablePadding>
            <ServiceRow
              name="otto-bgp.service"
              description="Main BGP policy generation service"
              status={getServiceStatus('otto-bgp.service')}
              onAction={(action) => handleServiceAction('otto-bgp.service', action)}
            />
            <ServiceRow
              name="otto-bgp-webui-adapter.service"
              description="Web interface service"
              status={getServiceStatus('otto-bgp-webui-adapter.service')}
              onAction={(action) => handleServiceAction('otto-bgp-webui-adapter.service', action)}
            />
            <ServiceRow
              name="otto-bgp-rpki-update.service"
              description="RPKI cache update service"
              status={getServiceStatus('otto-bgp-rpki-update.service')}
              onAction={(action) => handleServiceAction('otto-bgp-rpki-update.service', action)}
            />
          </List>
        </Paper>
      </Grid>

      {/* Timers Section */}
      <Grid item xs={12} md={6}>
        <Paper sx={{ border: '1px solid #333', borderRadius: 1, overflow: 'hidden' }}>
          <Box sx={{ p: 2, borderBottom: '1px solid #333', bgcolor: '#1a1a1a' }}>
            <Typography variant="body1" sx={{ color: '#f5f5f5', fontWeight: 600 }}>
              Scheduled Tasks
            </Typography>
          </Box>
          <List disablePadding>
            <ServiceRow
              name="otto-bgp.timer"
              description="Daily BGP policy update"
              status={getServiceStatus('otto-bgp.timer')}
            />
            <ServiceRow
              name="otto-bgp-rpki-update.timer"
              description="Hourly RPKI cache refresh"
              status={getServiceStatus('otto-bgp-rpki-update.timer')}
            />
          </List>
        </Paper>
      </Grid>

      {/* Recent Activity */}
      <Grid item xs={12}>
        <Paper sx={{ border: '1px solid #333', borderRadius: 1, overflow: 'hidden' }}>
          <Box sx={{ p: 2, borderBottom: '1px solid #333', bgcolor: '#1a1a1a' }}>
            <Typography variant="body1" sx={{ color: '#f5f5f5', fontWeight: 600 }}>
              System Information
            </Typography>
          </Box>
          <Box sx={{ p: 2 }}>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <Typography variant="caption" sx={{ color: '#888', textTransform: 'uppercase', fontSize: '0.7rem' }}>
                  Last Policy Generation
                </Typography>
                <Typography variant="body2" sx={{ color: '#f5f5f5', mt: 0.5 }}>
                  {matrix?.generated_at ? new Date(matrix.generated_at).toLocaleString() : 'No data available'}
                </Typography>
              </Grid>
              <Grid item xs={12} md={4}>
                <Typography variant="caption" sx={{ color: '#888', textTransform: 'uppercase', fontSize: '0.7rem' }}>
                  Configuration Mode
                </Typography>
                <Typography variant="body2" sx={{ color: '#f5f5f5', mt: 0.5 }}>
                  System Mode
                </Typography>
              </Grid>
              <Grid item xs={12} md={4}>
                <Typography variant="caption" sx={{ color: '#888', textTransform: 'uppercase', fontSize: '0.7rem' }}>
                  RPKI Validation
                </Typography>
                <Typography variant="body2" sx={{ color: '#f5f5f5', mt: 0.5 }}>
                  <Chip label="Enabled" size="small" sx={{ bgcolor: '#00a86b', color: '#fff', height: 20 }} />
                </Typography>
              </Grid>
            </Grid>
          </Box>
        </Paper>
      </Grid>
    </Grid>
  )
}

export default CockpitDashboard