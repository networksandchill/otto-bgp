import React from 'react'
import './Rollout.css'

interface StatusBadgeProps {
  status: string
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const getStatusClass = (status: string): string => {
    const classes: Record<string, string> = {
      planning: 'status-planning',
      active: 'status-active',
      paused: 'status-paused',
      completed: 'status-completed',
      failed: 'status-failed',
      aborted: 'status-aborted',
      pending: 'status-pending',
      in_progress: 'status-in-progress',
      skipped: 'status-skipped'
    }
    return classes[status] || 'status-unknown'
  }

  return (
    <span className={`status-badge ${getStatusClass(status)}`}>
      {status.toUpperCase().replace('_', ' ')}
    </span>
  )
}