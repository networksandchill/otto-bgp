import React, { useState } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import {
  Box,
  Drawer,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Typography,
  Divider,
  Avatar,
  Menu,
  MenuItem,
  Chip,
} from '@mui/material'
import {
  Dashboard as DashboardIcon,
  Assessment,
  Settings as SettingsIcon,
  NetworkCheck as NetworkIcon,
  Security as SecurityIcon,
  Storage as StorageIcon,
  Terminal as TerminalIcon,
  ExitToApp,
} from '@mui/icons-material'
import { useAuth } from '../hooks/useAuth'

const drawerWidth = 240

const CockpitLayout: React.FC = () => {
  const { user, logout } = useAuth()
  const location = useLocation()
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)

  const handleMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleClose = () => {
    setAnchorEl(null)
  }

  const handleLogout = async () => {
    handleClose()
    await logout()
  }

  const menuItems = [
    { path: '/dashboard', label: 'System', icon: <DashboardIcon /> },
    { path: '/reports', label: 'BGP Policies', icon: <NetworkIcon /> },
    { path: '/routing', label: 'Routing', icon: <Assessment /> },
    { path: '/rpki', label: 'RPKI Status', icon: <SecurityIcon /> },
    { path: '/logs', label: 'Logs', icon: <StorageIcon /> },
    { path: '/terminal', label: 'Terminal', icon: <TerminalIcon /> },
    { path: '/config', label: 'Configuration', icon: <SettingsIcon /> },
  ]

  return (
    <Box sx={{ display: 'flex', height: '100vh', bgcolor: '#151515' }}>
      {/* Sidebar */}
      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: drawerWidth,
            boxSizing: 'border-box',
            bgcolor: '#1a1a1a',
            borderRight: '1px solid #333',
          },
        }}
      >
        {/* Header */}
        <Box sx={{ p: 2, borderBottom: '1px solid #333' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <NetworkIcon sx={{ color: '#0066cc', mr: 1 }} />
            <Typography variant="h6" sx={{ color: '#f5f5f5', fontWeight: 600 }}>
              Otto BGP
            </Typography>
          </Box>
          <Typography variant="caption" sx={{ color: '#888' }}>
            Network Automation Platform
          </Typography>
        </Box>

        {/* Navigation */}
        <List sx={{ flexGrow: 1, py: 1 }}>
          {menuItems.map((item) => (
            <ListItem
              key={item.path}
              component={NavLink}
              to={item.path}
              sx={{
                color: '#b3b3b3',
                textDecoration: 'none',
                '&.active': {
                  bgcolor: '#0066cc',
                  color: '#fff',
                  '& .MuiListItemIcon-root': {
                    color: '#fff',
                  },
                },
                '&:hover': {
                  bgcolor: 'rgba(0, 102, 204, 0.1)',
                },
                mx: 1,
                borderRadius: 1,
                mb: 0.5,
              }}
            >
              <ListItemIcon sx={{ color: 'inherit', minWidth: 40 }}>
                {item.icon}
              </ListItemIcon>
              <ListItemText 
                primary={item.label} 
                primaryTypographyProps={{
                  fontSize: '0.875rem',
                  fontWeight: location.pathname === item.path ? 600 : 400,
                }}
              />
            </ListItem>
          ))}
        </List>

        <Divider sx={{ borderColor: '#333' }} />

        {/* User section */}
        <Box sx={{ p: 2 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              p: 1,
              borderRadius: 1,
              bgcolor: 'rgba(255, 255, 255, 0.05)',
              cursor: 'pointer',
              '&:hover': {
                bgcolor: 'rgba(255, 255, 255, 0.08)',
              },
            }}
            onClick={handleMenu}
          >
            <Avatar sx={{ width: 32, height: 32, bgcolor: '#0066cc', mr: 1 }}>
              {user?.username?.[0]?.toUpperCase()}
            </Avatar>
            <Box sx={{ flexGrow: 1 }}>
              <Typography variant="body2" sx={{ color: '#f5f5f5', lineHeight: 1.2 }}>
                {user?.username}
              </Typography>
              <Chip
                label={user?.role}
                size="small"
                sx={{
                  height: 16,
                  fontSize: '0.625rem',
                  bgcolor: user?.role === 'admin' ? '#00a86b' : '#666',
                  color: '#fff',
                }}
              />
            </Box>
          </Box>
          <Menu
            anchorEl={anchorEl}
            open={Boolean(anchorEl)}
            onClose={handleClose}
            anchorOrigin={{
              vertical: 'top',
              horizontal: 'right',
            }}
          >
            <MenuItem onClick={handleLogout}>
              <ExitToApp sx={{ mr: 1, fontSize: 20 }} />
              Logout
            </MenuItem>
          </Menu>
        </Box>
      </Drawer>

      {/* Main content */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          bgcolor: '#151515',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Top bar */}
        <Box
          sx={{
            height: 48,
            borderBottom: '1px solid #333',
            display: 'flex',
            alignItems: 'center',
            px: 3,
            bgcolor: '#1f1f1f',
          }}
        >
          <Typography variant="h6" sx={{ color: '#f5f5f5', textTransform: 'capitalize' }}>
            {location.pathname.slice(1) || 'Dashboard'}
          </Typography>
        </Box>

        {/* Page content */}
        <Box sx={{ flexGrow: 1, overflow: 'auto', p: 3 }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  )
}

export default CockpitLayout