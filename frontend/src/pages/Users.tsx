import React, { useState } from 'react'
import {
  Box, Paper, Typography, Button, IconButton, Dialog, DialogTitle,
  DialogContent, DialogActions, TextField, Select, MenuItem, FormControl,
  InputLabel, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Alert, Chip, InputAdornment, FormHelperText
} from '@mui/material'
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
  Person as PersonIcon,
  AdminPanelSettings as AdminIcon,
  Engineering as EngineeringIcon,
  RemoveRedEye as ViewIcon
} from '@mui/icons-material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import { useAuth } from '../hooks/useAuth'

interface User {
  username: string
  email?: string
  role: 'admin' | 'operator' | 'read_only'
  created_at?: string
  last_login?: string
}

interface UserFormData {
  username: string
  email: string
  password: string
  confirmPassword: string
  role: 'admin' | 'operator' | 'read_only'
}

const Users: React.FC = () => {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const [openDialog, setOpenDialog] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<User | null>(null)
  const [showPassword, setShowPassword] = useState(false)
  const [formData, setFormData] = useState<UserFormData>({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'read_only'
  })
  const [formErrors, setFormErrors] = useState<Partial<UserFormData>>({})

  // Fetch users
  const { data, isLoading, error } = useQuery({
    queryKey: ['users'],
    queryFn: () => apiClient.getUsers(),
    refetchInterval: 30000
  })

  // Create user mutation
  const createMutation = useMutation({
    mutationFn: (data: Omit<UserFormData, 'confirmPassword'>) => 
      apiClient.createUser(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      handleCloseDialog()
    }
  })

  // Update user mutation
  const updateMutation = useMutation({
    mutationFn: ({ username, data }: { username: string; data: any }) =>
      apiClient.updateUser(username, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      handleCloseDialog()
    }
  })

  // Delete user mutation
  const deleteMutation = useMutation({
    mutationFn: (username: string) => apiClient.deleteUser(username),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setDeleteConfirm(null)
    }
  })

  const handleOpenDialog = (user?: User) => {
    if (user) {
      setEditingUser(user)
      setFormData({
        username: user.username,
        email: user.email || '',
        password: '',
        confirmPassword: '',
        role: user.role
      })
    } else {
      setEditingUser(null)
      setFormData({
        username: '',
        email: '',
        password: '',
        confirmPassword: '',
        role: 'read_only'
      })
    }
    setFormErrors({})
    setOpenDialog(true)
  }

  const handleCloseDialog = () => {
    setOpenDialog(false)
    setEditingUser(null)
    setFormData({
      username: '',
      email: '',
      password: '',
      confirmPassword: '',
      role: 'read_only'
    })
    setFormErrors({})
    setShowPassword(false)
  }

  const validateForm = (): boolean => {
    const errors: Partial<UserFormData> = {}
    
    if (!editingUser && !formData.username) {
      errors.username = 'Username is required'
    }
    
    if (!editingUser && !formData.password) {
      errors.password = 'Password is required'
    }
    
    if (formData.password && formData.password !== formData.confirmPassword) {
      errors.confirmPassword = 'Passwords do not match'
    }
    
    if (formData.password && formData.password.length < 8) {
      errors.password = 'Password must be at least 8 characters'
    }
    
    if (formData.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      errors.email = 'Invalid email address'
    }
    
    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = () => {
    if (!validateForm()) return

    const submitData: any = {
      role: formData.role
    }
    
    if (!editingUser) {
      submitData.username = formData.username
      submitData.password = formData.password
    }
    
    if (formData.email) {
      submitData.email = formData.email
    }
    
    if (editingUser && formData.password) {
      submitData.password = formData.password
    }

    if (editingUser) {
      updateMutation.mutate({ username: editingUser.username, data: submitData })
    } else {
      createMutation.mutate(submitData)
    }
  }

  const getRoleIcon = (role: string) => {
    switch (role) {
      case 'admin':
        return <AdminIcon fontSize="small" />
      case 'operator':
        return <EngineeringIcon fontSize="small" />
      default:
        return <ViewIcon fontSize="small" />
    }
  }

  const getRoleColor = (role: string): "error" | "warning" | "info" => {
    switch (role) {
      case 'admin':
        return 'error'
      case 'operator':
        return 'warning'
      default:
        return 'info'
    }
  }

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Never'
    return new Date(dateString).toLocaleString()
  }

  if (isLoading) return <Box>Loading users...</Box>
  if (error) return <Alert severity="error">Failed to load users</Alert>

  const users = data?.users || []

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1">
          User Management
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => handleOpenDialog()}
        >
          Add User
        </Button>
      </Box>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Username</TableCell>
              <TableCell>Email</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Created</TableCell>
              <TableCell>Last Login</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.username}>
                <TableCell>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <PersonIcon fontSize="small" color="action" />
                    {user.username}
                    {typeof currentUser === 'string' && user.username === currentUser ? (
                      <Chip label="You" size="small" color="primary" />
                    ) : null}
                  </Box>
                </TableCell>
                <TableCell>{user.email || '-'}</TableCell>
                <TableCell>
                  <Chip
                    icon={getRoleIcon(user.role)}
                    label={user.role.replace('_', ' ')}
                    size="small"
                    color={getRoleColor(user.role)}
                  />
                </TableCell>
                <TableCell>{formatDate(user.created_at)}</TableCell>
                <TableCell>{formatDate(user.last_login)}</TableCell>
                <TableCell align="right">
                  <IconButton
                    size="small"
                    onClick={() => handleOpenDialog(user)}
                    title="Edit user"
                  >
                    <EditIcon />
                  </IconButton>
                  <IconButton
                    size="small"
                    onClick={() => setDeleteConfirm(user)}
                    disabled={typeof currentUser === 'string' && user.username === currentUser}
                    title="Delete user"
                  >
                    <DeleteIcon />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Create/Edit Dialog */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingUser ? `Edit User: ${editingUser.username}` : 'Create New User'}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 2 }}>
            {!editingUser && (
              <TextField
                label="Username"
                value={formData.username}
                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                error={!!formErrors.username}
                helperText={formErrors.username}
                fullWidth
                required
              />
            )}
            
            <TextField
              label="Email"
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              error={!!formErrors.email}
              helperText={formErrors.email}
              fullWidth
            />
            
            <TextField
              label={editingUser ? "New Password (leave empty to keep current)" : "Password"}
              type={showPassword ? 'text' : 'password'}
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              error={!!formErrors.password}
              helperText={formErrors.password}
              fullWidth
              required={!editingUser}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={() => setShowPassword(!showPassword)}
                      edge="end"
                    >
                      {showPassword ? <VisibilityOffIcon /> : <VisibilityIcon />}
                    </IconButton>
                  </InputAdornment>
                )
              }}
            />
            
            <TextField
              label="Confirm Password"
              type={showPassword ? 'text' : 'password'}
              value={formData.confirmPassword}
              onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
              error={!!formErrors.confirmPassword}
              helperText={formErrors.confirmPassword}
              fullWidth
              required={!editingUser || !!formData.password}
            />
            
            <FormControl fullWidth>
              <InputLabel>Role</InputLabel>
              <Select
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value as any })}
                label="Role"
              >
                <MenuItem value="admin">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <AdminIcon fontSize="small" />
                    Admin
                  </Box>
                </MenuItem>
                <MenuItem value="operator">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <EngineeringIcon fontSize="small" />
                    Operator
                  </Box>
                </MenuItem>
                <MenuItem value="read_only">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <ViewIcon fontSize="small" />
                    Read Only
                  </Box>
                </MenuItem>
              </Select>
              <FormHelperText>
                Admin: Full access | Operator: Can modify settings | Read Only: View only
              </FormHelperText>
            </FormControl>
            
            {(createMutation.error || updateMutation.error) && (
              <Alert severity="error">
                {(createMutation.error as any)?.response?.data?.error ||
                 (updateMutation.error as any)?.response?.data?.error ||
                 'An error occurred'}
              </Alert>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={createMutation.isPending || updateMutation.isPending}
          >
            {editingUser ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteConfirm} onClose={() => setDeleteConfirm(null)}>
        <DialogTitle>Confirm Delete</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete user "{deleteConfirm?.username}"?
            This action cannot be undone.
          </Typography>
          {deleteMutation.error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {(deleteMutation.error as any)?.response?.data?.error || 'Failed to delete user'}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirm(null)}>Cancel</Button>
          <Button
            onClick={() => deleteConfirm && deleteMutation.mutate(deleteConfirm.username)}
            color="error"
            variant="contained"
            disabled={deleteMutation.isPending}
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default Users