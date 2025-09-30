import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient } from '../../api/client'
import type { RolloutRun } from '../../types'
import { StatusBadge } from './StatusBadge'
import './Rollout.css'

export const RolloutList: React.FC = () => {
  const [rollouts, setRollouts] = useState<RolloutRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')

  useEffect(() => {
    loadRollouts()
    // Refresh every 10 seconds
    const interval = setInterval(loadRollouts, 10000)
    return () => clearInterval(interval)
  }, [statusFilter])

  const loadRollouts = async () => {
    try {
      const response = await apiClient.listRollouts(statusFilter || undefined, 50)
      setRollouts(response.runs || [])
      setError(null)
    } catch (err) {
      console.error('Failed to load rollouts:', err)
      setError('Failed to load rollouts')
    } finally {
      setLoading(false)
    }
  }

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleString()
  }

  if (loading) {
    return (
      <div className="rollout-list loading">
        <h2>Multi-Router Rollouts</h2>
        <p>Loading rollouts...</p>
      </div>
    )
  }

  return (
    <div className="rollout-list">
      <div className="rollout-header">
        <h2>Multi-Router Rollouts</h2>
        <div className="rollout-controls">
          <select
            className="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="paused">Paused</option>
            <option value="aborted">Aborted</option>
          </select>
          <button className="refresh-button" onClick={loadRollouts}>
            🔄 Refresh
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {!error && rollouts.length === 0 ? (
        <div className="empty-state">
          <p>No rollouts found</p>
          <p className="hint">
            Start a multi-router rollout using the CLI:
            <code>./otto-bgp pipeline devices.csv --multi-router</code>
          </p>
        </div>
      ) : (
        <table className="rollout-table">
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Status</th>
              <th>Created</th>
              <th>Initiated By</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rollouts.map((run) => (
              <tr key={run.run_id}>
                <td className="run-id-cell">
                  <Link to={`/rollouts/${run.run_id}`}>{run.run_id}</Link>
                </td>
                <td className="status-cell">
                  <StatusBadge status={run.status} />
                </td>
                <td className="date-cell">{formatDate(run.created_at)}</td>
                <td className="user-cell">{run.initiated_by || 'N/A'}</td>
                <td className="actions-cell">
                  <Link to={`/rollouts/${run.run_id}`} className="view-button">
                    View Details
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}