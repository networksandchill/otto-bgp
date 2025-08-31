import React from 'react'
import { 
  Container, Typography, Grid, Paper, Box, Card, CardContent,
  List, ListItem, ListItemText, Chip
} from '@mui/material'
import { 
  Router as RouterIcon, 
  Assessment as AssessmentIcon,
  Security as SecurityIcon
} from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '../hooks/useAuth'
import apiClient from '../api/client'

const Dashboard: React.FC = () => {
  const { user, isAdmin } = useAuth()

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
      'otto-bgp-autonomous.service',
      'otto-bgp.timer'
    ]),
    refetchInterval: 30000, // Refresh every 30s
  })

  const stats = matrix?.statistics || {
    total_routers: 0,
    total_as_numbers: 0,
    total_bgp_groups: 0,
  }

  const getServiceStatus = (unitName: string) => {
    const unit = systemdData?.units.find(u => u.name === unitName)
    if (unit?.error) return { status: 'error', color: 'error' as const }
    if (unit?.activestate === 'active') return { status: 'active', color: 'success' as const }
    if (unit?.activestate === 'inactive') return { status: 'inactive', color: 'default' as const }
    return { status: 'unknown', color: 'warning' as const }
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h3" component="h1" gutterBottom>
        Otto BGP Dashboard
      </Typography>
      <Typography variant="subtitle1" color="text.secondary" gutterBottom>
        Welcome back, {user?.username}! Your role: {user?.role}
      </Typography>

      <Grid container spacing={3} sx={{ mt: 2 }}>
        {/* Statistics Cards */}
        <Grid item xs={12} md={4}>
          <Card sx={{ background: 'linear-gradient(145deg, #1e3a8a 0%, #3b82f6 100%)' }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <RouterIcon sx={{ fontSize: 48, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {stats.total_routers}
              </Typography>
              <Typography variant="body1" color="white">
                Routers Managed
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card sx={{ background: 'linear-gradient(145deg, #059669 0%, #10b981 100%)' }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <AssessmentIcon sx={{ fontSize: 48, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {stats.total_as_numbers}
              </Typography>
              <Typography variant="body1" color="white">
                AS Numbers
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card sx={{ background: 'linear-gradient(145deg, #7c3aed 0%, #a855f7 100%)' }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <SecurityIcon sx={{ fontSize: 48, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {stats.total_bgp_groups}
              </Typography>
              <Typography variant="body1" color="white">
                BGP Groups
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* System Status */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              System Services
            </Typography>
            <List dense>
              <ListItem>
                <ListItemText primary="Otto BGP Main Service" />
                <Chip 
                  label={getServiceStatus('otto-bgp.service').status}
                  color={getServiceStatus('otto-bgp.service').color}
                  size="small"
                />
              </ListItem>
              <ListItem>
                <ListItemText primary="Otto BGP Autonomous Service" />
                <Chip 
                  label={getServiceStatus('otto-bgp-autonomous.service').status}
                  color={getServiceStatus('otto-bgp-autonomous.service').color}
                  size="small"
                />
              </ListItem>
              <ListItem>
                <ListItemText primary="Otto BGP Timer" />
                <Chip 
                  label={getServiceStatus('otto-bgp.timer').status}
                  color={getServiceStatus('otto-bgp.timer').color}
                  size="small"
                />
              </ListItem>
            </List>
          </Paper>
        </Grid>

        {/* Quick Actions */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Quick Actions
            </Typography>
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Available actions based on your role ({user?.role}):
              </Typography>
              <List dense>
                <ListItem>
                  <ListItemText 
                    primary="View Reports" 
                    secondary="Deployment matrices and discovery data"
                  />
                </ListItem>
                {isAdmin && (
                  <>
                    <ListItem>
                      <ListItemText 
                        primary="Manage Configuration" 
                        secondary="SSH settings, SMTP, and system configuration"
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText 
                        primary="Service Control" 
                        secondary="Start, stop, and restart Otto BGP services"
                      />
                    </ListItem>
                  </>
                )}
              </List>
            </Box>
          </Paper>
        </Grid>

        {/* Last Update Info */}
        {matrix && (
          <Grid item xs={12}>
            <Paper sx={{ p: 2, bgcolor: 'background.default' }}>
              <Typography variant="body2" color="text.secondary">
                Last data update: {new Date(matrix.generated_at).toLocaleString()}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Run 'otto-bgp pipeline' to refresh deployment data
              </Typography>
            </Paper>
          </Grid>
        )}
      </Grid>
    </Container>
  )
}

export default Dashboard