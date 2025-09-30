/**
 * Multi-router rollout types
 */

export interface RolloutRun {
  run_id: string
  created_at: string
  status: 'planning' | 'active' | 'paused' | 'completed' | 'failed' | 'aborted'
  initiated_by?: string
}

export interface RolloutStage {
  stage_id: string
  run_id: string
  sequencing: number
  name: string
  guardrail_snapshot?: string
  stats?: RolloutStageStats
}

export interface RolloutStageStats {
  total: number
  pending: number
  in_progress: number
  completed: number
  failed: number
  skipped: number
}

export interface RolloutTarget {
  target_id: string
  stage_id: string
  hostname: string
  policy_hash?: string
  state: 'pending' | 'in_progress' | 'completed' | 'failed' | 'skipped'
  last_error?: string
  updated_at?: string
}

export interface RolloutEvent {
  event_id: number
  run_id: string
  event_type: string
  payload?: string
  timestamp: string
}

export interface RolloutSummary {
  run: RolloutRun
  stages: RolloutStage[]
  stage_stats: Array<RolloutStage & { stats: RolloutStageStats }>
  recent_events: RolloutEvent[]
}

export interface ListRolloutsResponse {
  success: boolean
  runs: RolloutRun[]
  count: number
}

export interface RolloutStatusResponse {
  success: boolean
  summary: RolloutSummary
}

export interface StagesResponse {
  success: boolean
  run_id: string
  stages: Array<RolloutStage & { stats: RolloutStageStats }>
}

export interface TargetsResponse {
  success: boolean
  run_id: string
  stage_id: string
  targets: RolloutTarget[]
  count: number
}

export interface EventsResponse {
  success: boolean
  run_id: string
  events: RolloutEvent[]
  count: number
}