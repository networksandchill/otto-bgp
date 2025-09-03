import React, { useEffect, useState } from 'react'
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, Typography } from '@mui/material'

interface Props {
  open: boolean
  onStaySignedIn: () => void
  onLogout: () => void
  seconds?: number // default 120
}

export const IdleWarningModal: React.FC<Props> = ({ open, onStaySignedIn, onLogout, seconds = 120 }) => {
  const [remaining, setRemaining] = useState(seconds)

  useEffect(() => {
    if (!open) return
    setRemaining(seconds)
    const t = setInterval(() => setRemaining(s => Math.max(0, s - 1)), 1000)
    return () => clearInterval(t)
  }, [open, seconds])

  useEffect(() => {
    if (open && remaining === 0) onLogout()
  }, [open, remaining, onLogout])

  return (
    <Dialog open={open} onClose={onLogout} maxWidth="xs" fullWidth>
      <DialogTitle>Are you still there?</DialogTitle>
      <DialogContent>
        <Typography gutterBottom>
          You will be signed out due to inactivity.
        </Typography>
        <Typography color="text.secondary">
          Signing out in {remaining} seconds.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onLogout} color="inherit">Log out</Button>
        <Button onClick={onStaySignedIn} variant="contained">Stay signed in</Button>
      </DialogActions>
    </Dialog>
  )
}