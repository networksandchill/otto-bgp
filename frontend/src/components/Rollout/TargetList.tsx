import React, { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import type { RolloutTarget } from '../../types'
import './Rollout.css'

interface TargetListProps {
  runId: string
  stageId: string
}

export const TargetList: React.FC<TargetListProps> = ({ runId, stageId }) => {
  const [targets, setTargets] = useState<RolloutTarget[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadTargets()
  }, [runId, stageId])

  const loadTargets = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.getRolloutTargets(runId, stageId)
      setTargets(response.targets || [])
    } catch (err) {
      console.error('Failed to load targets:', err)
      setError('Failed to load targets')
    } finally {
      setLoading(false)
    }
  }

  const getStatusIcon = (state: string): string => {
    const icons: Record<string, string> = {
      pending: '⏸',
      in_progress: '▶',
      completed: '✓',
      failed: '✗',
      skipped: '⊘'
    }
    return icons[state] || '?'
  }

  const getStatusClass = (state: string): string => {
    return `target-status-${state}`
  }

  if (loading) {
    return <div className="target-list loading">Loading targets...</div>
  }

  if (error) {
    return <div className="target-list error">{error}</div>
  }

  if (targets.length === 0) {
    return <div className="target-list empty">No targets in this stage</div>
  }

  return (
    <div className="target-list">
      <table className="target-table">
        <thead>
          <tr>
            <th>Status</th>
            <th>Hostname</th>
            <th>Policy Hash</th>
            <th>Updated</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {targets.map((target) => (
            <tr key={target.target_id} className={getStatusClass(target.state)}>
              <td className="status-cell">
                <span className="status-icon">{getStatusIcon(target.state)}</span>
                <span className="status-text">{target.state}</span>
              </td>
              <td className="hostname-cell">{target.hostname}</td>
              <td className="hash-cell">{target.policy_hash || '-'}</td>
              <td className="time-cell">
                {target.updated_at ? new Date(target.updated_at).toLocaleString() : '-'}
              </td>
              <td className="error-cell">
                {target.last_error && (
                  <span className="error-message" title={target.last_error}>
                    {target.last_error.length > 50
                      ? target.last_error.substring(0, 50) + '...'
                      : target.last_error
                    }
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}