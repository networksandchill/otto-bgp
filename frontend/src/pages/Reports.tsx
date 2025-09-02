import React, { useState } from 'react'
import { 
  Container, Typography, Paper, Box, Grid, 
  Tab, Tabs, Table, TableBody, TableCell, TableContainer, 
  TableHead, TableRow, Chip, Alert
} from '@mui/material'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'

interface TabPanelProps {
  children?: React.ReactNode
  index: number
  value: number
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index, ...other }) => (
  <div
    role="tabpanel"
    hidden={value !== index}
    id={`reports-tabpanel-${index}`}
    aria-labelledby={`reports-tab-${index}`}
    {...other}
  >
    {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
  </div>
)

const Reports: React.FC = () => {
  const [tabValue, setTabValue] = useState(0)

  // Query deployment matrix
  const { data: matrix, isLoading, error } = useQuery({
    queryKey: ['deployment-matrix'],
    queryFn: async () => {
      const result = await apiClient.getDeploymentMatrix()
      // Check if backend returned an error object instead of matrix data
      if ('error' in result && !('routers' in result)) {
        throw new Error((result as any).error)
      }
      return result
    },
    retry: false,
  })

  const handleTabChange = (_: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue)
  }

  if (isLoading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4 }}>
        <Typography>Loading reports...</Typography>
      </Container>
    )
  }

  if (error) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4 }}>
        <Alert severity="warning">
          No deployment data available. Run 'otto-bgp pipeline' to generate reports.
        </Alert>
      </Container>
    )
  }

  const routers = matrix && 'routers' in matrix ? Object.entries(matrix.routers as Record<string, any>) : []
  const asDistribution = matrix && 'as_distribution' in matrix ? Object.entries(matrix.as_distribution as Record<string, any>) : []

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h3" component="h1" gutterBottom>
        Reports & Analytics
      </Typography>
      <Typography variant="subtitle1" color="text.secondary" gutterBottom>
        Deployment matrices and network discovery data
      </Typography>

      <Paper sx={{ mt: 3 }}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={tabValue} onChange={handleTabChange} aria-label="reports tabs">
            <Tab label="Deployment Matrix" />
            <Tab label="Router Details" />
            <Tab label="AS Distribution" />
          </Tabs>
        </Box>

        <TabPanel value={tabValue} index={0}>
          <Typography variant="h5" gutterBottom>
            Deployment Matrix Overview
          </Typography>
          
          {matrix && 'statistics' in matrix && (
            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={12} md={4}>
                <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'primary.main', color: 'white' }}>
                  <Typography variant="h4">{matrix.statistics.total_routers}</Typography>
                  <Typography variant="body1">Total Routers</Typography>
                </Paper>
              </Grid>
              <Grid item xs={12} md={4}>
                <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'secondary.main', color: 'white' }}>
                  <Typography variant="h4">{matrix.statistics.total_as_numbers}</Typography>
                  <Typography variant="body1">AS Numbers</Typography>
                </Paper>
              </Grid>
              <Grid item xs={12} md={4}>
                <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'success.main', color: 'white' }}>
                  <Typography variant="h4">{matrix.statistics.total_bgp_groups}</Typography>
                  <Typography variant="body1">BGP Groups</Typography>
                </Paper>
              </Grid>
            </Grid>
          )}

          <Typography variant="body2" color="text.secondary">
            Generated: {matrix && 'generated_at' in matrix ? new Date(matrix.generated_at).toLocaleString() : 'N/A'}
          </Typography>
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          <Typography variant="h5" gutterBottom>
            Router Configuration Details
          </Typography>
          
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Hostname</TableCell>
                  <TableCell>IP Address</TableCell>
                  <TableCell>Site</TableCell>
                  <TableCell>BGP Groups</TableCell>
                  <TableCell>AS Numbers</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {routers.map(([hostname, router]: [string, any]) => (
                  <TableRow key={hostname}>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {router.hostname}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {router.ip_address}
                      </Typography>
                    </TableCell>
                    <TableCell>{router.site || 'N/A'}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {router.bgp_groups.map((group: string) => (
                          <Chip 
                            key={group} 
                            label={group} 
                            size="small" 
                            variant="outlined"
                          />
                        ))}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {router.as_numbers.map((asn: number) => (
                          <Chip 
                            key={asn} 
                            label={`AS${asn}`} 
                            size="small" 
                            color="primary"
                          />
                        ))}
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          <Typography variant="h5" gutterBottom>
            AS Number Distribution
          </Typography>
          
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>AS Number</TableCell>
                  <TableCell>Routers</TableCell>
                  <TableCell>Router Count</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {asDistribution.map(([asn, routerList]: [string, any]) => (
                  <TableRow key={asn}>
                    <TableCell>
                      <Chip 
                        label={`AS${asn}`} 
                        color="primary" 
                        variant="filled"
                      />
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {routerList.map((router: string) => (
                          <Chip 
                            key={router} 
                            label={router} 
                            size="small" 
                            variant="outlined"
                          />
                        ))}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="h6" color="primary">
                        {routerList.length}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </TabPanel>
      </Paper>
    </Container>
  )
}

export default Reports