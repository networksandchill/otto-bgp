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
  Tabs,
  Tab,
  Button,
  CircularProgress,
} from '@mui/material'
import {
  Refresh,
  Download,
  Search,
  Error as ErrorIcon,
  Warning,
  Info,
  CheckCircle,
  Description,
  Terminal,
  Security,
} from '@mui/icons-material'
import { useQuery } from '@tanstack/react-query'
import apiClient from '../api/client'

interface LogEntry {
  timestamp: string
  level: 'error' | 'warning' | 'info' | 'success'
  service: string
  message: string
}

interface FileLogEntry {
  timestamp: string
  level: string
  message: string
  module?: string
  raw: string
}

const Logs: React.FC = () => {
  const [selectedTab, setSelectedTab] = useState(0)
  const [selectedService, setSelectedService] = useState('all')
  const [searchTerm, setSearchTerm] = useState('')
  const [logLevel, setLogLevel] = useState('all')
  const [fileSearchTerm, setFileSearchTerm] = useState('')
  const [loadMoreOffset, setLoadMoreOffset] = useState(0)

  // Fetch system logs (journalctl)
  const { data: logsData, isLoading: isLoadingLogs, refetch: refetchLogs } = useQuery({
    queryKey: ['logs', selectedService, logLevel],
    queryFn: () => apiClient.getLogs({
      service: selectedService,
      level: logLevel,
      limit: 200,
    }),
    refetchInterval: selectedTab === 0 ? 10000 : false, // Auto-refresh only for system logs
    enabled: selectedTab === 0,
  })

  // Fetch audit log
  const { data: auditLogData, isLoading: isLoadingAudit, refetch: refetchAudit } = useQuery({
    queryKey: ['audit-log', fileSearchTerm, loadMoreOffset],
    queryFn: () => apiClient.getLogFileContent('audit.log', {
      lines: 100,
      offset: loadMoreOffset,
      search: fileSearchTerm || undefined,
    }),
    enabled: selectedTab === 1,
  })

  // Fetch otto-bgp log
  const { data: ottoLogData, isLoading: isLoadingOtto, refetch: refetchOtto } = useQuery({
    queryKey: ['otto-log', fileSearchTerm, loadMoreOffset],
    queryFn: () => apiClient.getLogFileContent('otto-bgp.log', {
      lines: 100,
      offset: loadMoreOffset,
      search: fileSearchTerm || undefined,
    }),
    enabled: selectedTab === 2,
  })

  const systemLogs: LogEntry[] = logsData?.logs || []

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

  const filteredSystemLogs = systemLogs.filter(log => {
    const matchesService = selectedService === 'all' || log.service === selectedService
    const matchesLevel = logLevel === 'all' || log.level === logLevel
    const matchesSearch = searchTerm === '' || 
      log.message.toLowerCase().includes(searchTerm.toLowerCase()) ||
      log.service.toLowerCase().includes(searchTerm.toLowerCase())
    return matchesService && matchesLevel && matchesSearch
  })

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setSelectedTab(newValue)
    setLoadMoreOffset(0)
    setFileSearchTerm('')
  }

  const handleLoadMore = () => {
    setLoadMoreOffset(prev => prev + 100)
  }

  const handleFileSearch = () => {
    setLoadMoreOffset(0)
    if (selectedTab === 1) {
      refetchAudit()
    } else if (selectedTab === 2) {
      refetchOtto()
    }
  }

  const renderSystemLogs = () => {
    if (isLoadingLogs) {
      return (
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
          <CircularProgress size={24} sx={{ color: '#888' }} />
        </Box>
      )
    }

    return (
      <>
        {/* Filters */}
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 2 }}>
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
              <MenuItem value="rpki-client">rpki-client</MenuItem>
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

          <IconButton size="small" sx={{ color: '#888' }} onClick={() => refetchLogs()}>
            <Refresh />
          </IconButton>
        </Box>

        {/* Log Entries */}
        <Box
          sx={{
            maxHeight: 'calc(100vh - 350px)',
            overflow: 'auto',
            bgcolor: '#0a0a0a',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
            border: '1px solid #333',
            borderRadius: 1,
          }}
        >
          {filteredSystemLogs.map((log, index) => (
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

          {filteredSystemLogs.length === 0 && (
            <Box sx={{ p: 4, textAlign: 'center' }}>
              <Typography variant="body2" sx={{ color: '#666' }}>
                No logs found matching the current filters
              </Typography>
            </Box>
          )}
        </Box>
      </>
    )
  }

  const renderFileLog = (
    data: any,
    isLoading: boolean,
    refetch: () => void,
    icon: React.ReactNode,
    title: string
  ) => {
    if (isLoading && loadMoreOffset === 0) {
      return (
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
          <CircularProgress size={24} sx={{ color: '#888' }} />
        </Box>
      )
    }

    const entries: FileLogEntry[] = data?.entries || []

    return (
      <>
        {/* Search Bar */}
        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          <TextField
            size="small"
            placeholder={`Search ${title.toLowerCase()}...`}
            value={fileSearchTerm}
            onChange={(e) => setFileSearchTerm(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter') {
                handleFileSearch()
              }
            }}
            sx={{
              flexGrow: 1,
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

          <Button
            variant="outlined"
            size="small"
            onClick={handleFileSearch}
            sx={{
              borderColor: '#333',
              color: '#888',
              '&:hover': { borderColor: '#666' },
            }}
          >
            Search
          </Button>

          <IconButton size="small" sx={{ color: '#888' }} onClick={() => refetch()}>
            <Refresh />
          </IconButton>

          <IconButton size="small" sx={{ color: '#888' }}>
            <Download />
          </IconButton>
        </Box>

        {/* File Info */}
        {data && (
          <Box sx={{ display: 'flex', gap: 2, mb: 2, alignItems: 'center' }}>
            {icon}
            <Typography variant="body2" sx={{ color: '#888' }}>
              {title} • Total lines: {data.total_lines?.toLocaleString() || 0}
              {fileSearchTerm && ` • Filtered by: "${fileSearchTerm}"`}
            </Typography>
          </Box>
        )}

        {/* Log Entries */}
        <Box
          sx={{
            maxHeight: 'calc(100vh - 350px)',
            overflow: 'auto',
            bgcolor: '#0a0a0a',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
            border: '1px solid #333',
            borderRadius: 1,
          }}
        >
          {entries.map((entry, index) => (
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
              {entry.timestamp && (
                <Typography
                  variant="caption"
                  sx={{
                    color: '#666',
                    fontFamily: 'monospace',
                    minWidth: 150,
                    flexShrink: 0,
                  }}
                >
                  {entry.timestamp}
                </Typography>
              )}

              <Box sx={{ display: 'flex', alignItems: 'center', minWidth: 20 }}>
                {getLevelIcon(entry.level)}
              </Box>

              {entry.module && (
                <Chip
                  label={entry.module}
                  size="small"
                  sx={{
                    height: 20,
                    fontSize: '0.7rem',
                    bgcolor: '#1a1a1a',
                    color: '#888',
                    border: '1px solid #333',
                    minWidth: 80,
                  }}
                />
              )}

              <Typography
                sx={{
                  color: getLevelColor(entry.level),
                  fontFamily: 'monospace',
                  flexGrow: 1,
                  wordBreak: 'break-word',
                }}
              >
                {entry.message || entry.raw}
              </Typography>
            </Box>
          ))}

          {entries.length === 0 && !isLoading && (
            <Box sx={{ p: 4, textAlign: 'center' }}>
              <Typography variant="body2" sx={{ color: '#666' }}>
                {fileSearchTerm ? 'No logs found matching your search' : 'No log entries found'}
              </Typography>
            </Box>
          )}

          {/* Load More Button */}
          {data?.has_more && (
            <Box sx={{ p: 2, textAlign: 'center' }}>
              <Button
                variant="outlined"
                size="small"
                onClick={handleLoadMore}
                disabled={isLoading}
                sx={{
                  borderColor: '#333',
                  color: '#888',
                  '&:hover': { borderColor: '#666' },
                }}
              >
                {isLoading ? (
                  <CircularProgress size={16} sx={{ color: '#888' }} />
                ) : (
                  'Load More'
                )}
              </Button>
            </Box>
          )}
        </Box>
      </>
    )
  }

  return (
    <Box>
      {/* Header */}
      <Paper sx={{ p: 2, mb: 2, border: '1px solid #333' }}>
        <Typography variant="h6" sx={{ color: '#f5f5f5', fontWeight: 600, mb: 2 }}>
          System Logs
        </Typography>

        {/* Tabs */}
        <Tabs
          value={selectedTab}
          onChange={handleTabChange}
          sx={{
            borderBottom: '1px solid #333',
            '& .MuiTab-root': {
              color: '#888',
              '&.Mui-selected': {
                color: '#f5f5f5',
              },
            },
            '& .MuiTabs-indicator': {
              backgroundColor: '#00a86b',
            },
          }}
        >
          <Tab
            label="System Logs"
            icon={<Terminal sx={{ fontSize: 20 }} />}
            iconPosition="start"
          />
          <Tab
            label="Audit Log"
            icon={<Security sx={{ fontSize: 20 }} />}
            iconPosition="start"
          />
          <Tab
            label="Application Log"
            icon={<Description sx={{ fontSize: 20 }} />}
            iconPosition="start"
          />
        </Tabs>
      </Paper>

      {/* Content */}
      <Paper sx={{ p: 2, border: '1px solid #333' }}>
        {selectedTab === 0 && renderSystemLogs()}
        {selectedTab === 1 && renderFileLog(
          auditLogData,
          isLoadingAudit,
          refetchAudit,
          <Security sx={{ color: '#888', fontSize: 20 }} />,
          'Audit Log'
        )}
        {selectedTab === 2 && renderFileLog(
          ottoLogData,
          isLoadingOtto,
          refetchOtto,
          <Description sx={{ color: '#888', fontSize: 20 }} />,
          'Otto BGP Log'
        )}
      </Paper>
    </Box>
  )
}

export default Logs