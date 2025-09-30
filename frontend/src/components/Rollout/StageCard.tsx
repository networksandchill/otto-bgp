import React, { useState } from 'react'
import type { RolloutStage, RolloutStageStats } from '../../types'
import { TargetList } from './TargetList'
import './Rollout.css'

interface StageCardProps {
  stage: RolloutStage & { stats: RolloutStageStats }
  runId: string
}

export const StageCard: React.FC<StageCardProps> = ({ stage, runId }) => {
  const [expanded, setExpanded] = useState(false)

  const calculateProgress = (): number => {
    if (!stage.stats || stage.stats.total === 0) return 0
    return (stage.stats.completed / stage.stats.total) * 100
  }

  const progress = calculateProgress()

  return (
    <div className="stage-card">
      <div
        className="stage-header"
        onClick={() => setExpanded(!expanded)}
        style={{ cursor: 'pointer' }}
      >
        <div className="stage-title">
          <h4>
            Stage {stage.sequencing}: {stage.name}
            <span className="expand-icon">{expanded ? '▼' : '▶'}</span>
          </h4>
        </div>
        <div className="stage-stats">
          <span className="stat completed" title="Completed">
            ✓ {stage.stats?.completed || 0}
          </span>
          <span className="stat in-progress" title="In Progress">
            ▶ {stage.stats?.in_progress || 0}
          </span>
          <span className="stat pending" title="Pending">
            ⏸ {stage.stats?.pending || 0}
          </span>
          <span className="stat failed" title="Failed">
            ✗ {stage.stats?.failed || 0}
          </span>
          {(stage.stats?.skipped || 0) > 0 && (
            <span className="stat skipped" title="Skipped">
              ⊘ {stage.stats.skipped}
            </span>
          )}
        </div>
      </div>

      <div className="progress-bar-container">
        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${progress}%` }}
            title={`${progress.toFixed(1)}% complete`}
          />
        </div>
        <span className="progress-text">{progress.toFixed(1)}%</span>
      </div>

      {expanded && (
        <div className="stage-details">
          <TargetList runId={runId} stageId={stage.stage_id} />
        </div>
      )}
    </div>
  )
}