import React, { useState } from 'react'
import {
  Paper,
  Typography,
  Box,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  IconButton,
  TextField,
  InputAdornment,
} from '@mui/material'
import {
  Refresh,
  Download,
  Search,
  Error as ErrorIcon,
  Warning,
  Info,
  CheckCircle,
} from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'

interface LogEntry {
  timestamp: string
  level: 'error' | 'warning' | 'info' | 'success'
  service: string
  message: string
}

const Logs: React.FC = () => {
  const [selectedService, setSelectedService] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')
  const [logLevel, setLogLevel] = useState('all')

  // Fetch real logs from API
  const { data: logsData, isLoading, refetch } = useQuery({
    queryKey: ['logs', selectedService, logLevel],
    queryFn: () => apiClient.getLogs({
      service: selectedService,
      level: logLevel,
      limit: 200,
    }),
    refetchInterval: 10000, // Refresh every 10 seconds
  })

  const logs: LogEntry[] = logsData?.logs || []

  const getLevelIcon = (level: string) => {
    switch (level) {
      case 'error':
        return <ErrorIcon sx={{ color: '#ff5252', fontSize: 18 }} />
      case 'warning':
        return <Warning sx={{ color: '#ffa726', fontSize: 18 }} />
      case 'info':
        return <Info sx={{ color: '#29b6f6', fontSize: 18 }} />
      case 'success':
        return <CheckCircle sx={{ color: '#00a86b', fontSize: 18 }} />
      default:
        return null
    }
  }

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'error':
        return '#ff5252'
      case 'warning':
        return '#ffa726'
      case 'info':
        return '#29b6f6'
      case 'success':
        return '#00a86b'
      default:
        return '#888'
    }
  }

  const filteredLogs = logs.filter(log => {
    const matchesService = selectedService === 'all' || log.service === selectedService
    const matchesLevel = logLevel === 'all' || log.level === logLevel
    const matchesSearch = searchTerm === '' || 
      log.message.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.service.toLowerCase().includes(searchTerm.toLowerCase())
    return matchesService && matchesLevel && matchesSearch
  })

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <Typography sx={{ color: '#888' }}>Loading logs...</Typography>
      </Box>
    )
  }

  return (
    <Box>
      {/* Header and Controls */}
      <Paper sx={{ p: 2, mb: 2, border: '1px solid #333' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h6" sx={{ color: '#f5f5f5', fontWeight: 600 }}>
            System Logs
          </Typography>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <IconButton size="small" sx={{ color: '#888' }} onClick={() => refetch()}>
              <Refresh />
            </IconButton>
            <IconButton size="small" sx={{ color: '#888' }}>
              <Download />
            </IconButton>
          </Box>
        </Box>

        {/* Filters */}
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel sx={{ color: '#888' }}>Service</InputLabel>
            <Select
              value={selectedService}
              onChange={(e) => setSelectedService(e.target.value)}
              label="Service"
              sx={{
                color: '#f5f5f5',
                '& .MuiOutlinedInput-notchedOutline': { borderColor: '#333' },
                '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#666' },
              }}
            >
              <MenuItem value="all">All Services</MenuItem>
              <MenuItem value="otto-bgp">otto-bgp</MenuItem>
              <MenuItem value="webui">webui-adapter</MenuItem>
              <MenuItem value="rpki">rpki-update</MenuItem>
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel sx={{ color: '#888' }}>Level</InputLabel>
            <Select
              value={logLevel}
              onChange={(e) => setLogLevel(e.target.value)}
              label="Level"
              sx={{
                color: '#f5f5f5',
                '& .MuiOutlinedInput-notchedOutline': { borderColor: '#333' },
                '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#666' },
              }}
            >
              <MenuItem value="all">All Levels</MenuItem>
              <MenuItem value="error">Error</MenuItem>
              <MenuItem value="warning">Warning</MenuItem>
              <MenuItem value="info">Info</MenuItem>
              <MenuItem value="success">Success</MenuItem>
            </Select>
          </FormControl>

          <TextField
            size="small"
            placeholder="Search logs..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            sx={{
              flexGrow: 1,
              minWidth: 200,
              '& .MuiOutlinedInput-root': {
                color: '#f5f5f5',
                '& fieldset': { borderColor: '#333' },
                '&:hover fieldset': { borderColor: '#666' },
              },
            }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <Search sx={{ color: '#888', fontSize: 20 }} />
                </InputAdornment>
              ),
            }}
          />
        </Box>
      </Paper>

      {/* Log Entries */}
      <Paper sx={{ border: '1px solid #333', overflow: 'hidden' }}>
        <Box
          sx={{
            maxHeight: 'calc(100vh - 280px)',
            overflow: 'auto',
            bgcolor: '#0a0a0a',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
          }}
        >
          {filteredLogs.map((log, index) => (
            <Box
              key={index}
              sx={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 2,
                p: 1.5,
                borderBottom: '1px solid #1a1a1a',
                '&:hover': { bgcolor: '#1a1a1a' },
              }}
            >
              <Typography
                variant="caption"
                sx={{
                  color: '#666',
                  fontFamily: 'monospace',
                  minWidth: 150,
                  flexShrink: 0,
                }}
              >
                {new Date(log.timestamp).toLocaleString()}
              </Typography>
              
              <Box sx={{ display: 'flex', alignItems: 'center', minWidth: 20 }}>
                {getLevelIcon(log.level)}
              </Box>

              <Chip
                label={log.service}
                size="small"
                sx={{
                  height: 20,
                  fontSize: '0.7rem',
                  bgcolor: '#1a1a1a',
                  color: '#888',
                  border: '1px solid #333',
                  minWidth: 100,
                }}
              />

              <Typography
                sx={{
                  color: getLevelColor(log.level),
                  fontFamily: 'monospace',
                  flexGrow: 1,
                  wordBreak: 'break-word',
                }}
              >
                {log.message}
              </Typography>
            </Box>
          ))}
        </Box>

        {filteredLogs.length === 0 && (
          <Box sx={{ p: 4, textAlign: 'center' }}>
            <Typography variant="body2" sx={{ color: '#666' }}>
              No logs found matching the current filters
            </Typography>
          </Box>
        )}
      </Paper>
    </Box>
  )
}

export default Logs