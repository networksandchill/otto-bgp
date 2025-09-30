import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { apiClient } from '../../api/client'
import type { RolloutSummary } from '../../types'
import { StatusBadge } from './StatusBadge'
import { StageCard } from './StageCard'
import { EventTimeline } from './EventTimeline'
import './Rollout.css'

export const RolloutDetail: React.FC = () => {
  const { runId } = useParams<{ runId: string }>()
  const [summary, setSummary] = useState<RolloutSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!runId) return

    loadRolloutStatus()
    // Auto-refresh every 5 seconds for active rollouts
    const interval = setInterval(() => {
      if (summary?.run?.status === 'active' || summary?.run?.status === 'paused') {
        loadRolloutStatus()
      }
    }, 5000)

    return () => clearInterval(interval)
  }, [runId])

  const loadRolloutStatus = async () => {
    if (!runId) return

    try {
      const response = await apiClient.getRolloutStatus(runId)
      setSummary(response.summary)
      setError(null)
    } catch (err) {
      console.error('Failed to load rollout status:', err)
      setError('Failed to load rollout status')
    } finally {
      setLoading(false)
    }
  }

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleString()
  }

  const calculateOverallProgress = (): number => {
    if (!summary?.stage_stats || summary.stage_stats.length === 0) return 0

    const totalTargets = summary.stage_stats.reduce((sum, stage) => sum + (stage.stats?.total || 0), 0)
    const completedTargets = summary.stage_stats.reduce((sum, stage) => sum + (stage.stats?.completed || 0), 0)

    if (totalTargets === 0) return 0
    return (completedTargets / totalTargets) * 100
  }

  if (loading) {
    return (
      <div className="rollout-detail loading">
        <h2>Loading Rollout Status...</h2>
      </div>
    )
  }

  if (error || !summary) {
    return (
      <div className="rollout-detail error">
        <h2>Error</h2>
        <p>{error || 'Rollout not found'}</p>
        <Link to="/rollouts" className="back-link">← Back to Rollouts</Link>
      </div>
    )
  }

  const overallProgress = calculateOverallProgress()
  const isActive = summary.run.status === 'active' || summary.run.status === 'paused'

  return (
    <div className="rollout-detail">
      <div className="rollout-detail-header">
        <div className="breadcrumb">
          <Link to="/rollouts">Rollouts</Link>
          <span className="separator">›</span>
          <span>{summary.run.run_id}</span>
        </div>
        <h2>Rollout: {summary.run.run_id}</h2>
        {isActive && <span className="auto-refresh-indicator">🔄 Auto-refreshing...</span>}
      </div>

      <div className="rollout-info-card">
        <div className="info-row">
          <div className="info-item">
            <label>Status</label>
            <StatusBadge status={summary.run.status} />
          </div>
          <div className="info-item">
            <label>Created</label>
            <span>{formatDate(summary.run.created_at)}</span>
          </div>
          {summary.run.initiated_by && (
            <div className="info-item">
              <label>Initiated By</label>
              <span>{summary.run.initiated_by}</span>
            </div>
          )}
          <div className="info-item">
            <label>Overall Progress</label>
            <span className="progress-percentage">{overallProgress.toFixed(1)}%</span>
          </div>
        </div>

        <div className="overall-progress-bar">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${overallProgress}%` }}
            />
          </div>
        </div>
      </div>

      <div className="rollout-stages-section">
        <h3>Stages ({summary.stage_stats?.length || 0})</h3>
        {summary.stage_stats && summary.stage_stats.length > 0 ? (
          summary.stage_stats.map((stage) => (
            <StageCard key={stage.stage_id} stage={stage} runId={runId!} />
          ))
        ) : (
          <div className="empty-state">No stages configured</div>
        )}
      </div>

      <div className="rollout-events-section">
        <h3>Recent Events</h3>
        <EventTimeline events={summary.recent_events || []} />
      </div>
    </div>
  )
}