// API Response Types
export interface ApiResponse<T = any> {
  data?: T
  error?: string
  success?: boolean
  message?: string
}

// User and Authentication
export interface User {
  username: string
  role: 'admin' | 'read_only'
  email?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  user: string
  role: 'admin' | 'read_only'
  access_token: string
}

export interface SessionInfo {
  user: string
  role: 'admin' | 'read_only'
  expires_at: string
}

// Setup Types
export interface SetupState {
  needs_setup: boolean
  reasons: string[]
  hostname: string
}

export interface SetupAdminRequest {
  username: string
  email: string
  password: string
}

// Configuration Types
export interface SSHConfig {
  hostname: string
  username: string
  password?: string
  key_path?: string
  port?: number
}

// SSH Key Management Types
export interface KnownHostEntry {
  line: number
  host: string
  key_type: string
  fingerprint: string
  raw: string
}

// NETCONF Configuration Type
export interface NetconfConfig {
  username?: string
  password?: string
  ssh_key?: string
  port?: number
  timeout?: number
  default_confirmed_commit?: number
  commit_comment_prefix?: string
}

export interface SMTPConfig {
  enabled: boolean
  delivery_method?: 'sendmail' | 'smtp'
  sendmail_path?: string
  host?: string
  port?: number
  username?: string
  password?: string
  use_tls?: boolean
  from_address?: string
  to_addresses?: string[]
  // Phase 1: Notification preferences
  subject_prefix?: string
  send_on_success?: boolean
  send_on_failure?: boolean
  alert_on_manual?: boolean
}

export interface RPKIConfig {
  enabled?: boolean
  cache_dir?: string
  validator_url?: string
  refresh_interval?: number
  strict_validation?: boolean
  // Phase 2: Advanced RPKI options
  fail_closed?: boolean
  max_vrp_age_hours?: number
  vrp_cache_path?: string
  allowlist_path?: string
  max_invalid_percent?: number
  max_notfound_percent?: number
  require_vrp_data?: boolean
  vrp_sources?: string[]
}

export interface BGPq4Config {
  mode?: string
  timeout?: number
  irr_source?: string
  aggregate_prefixes?: boolean
  ipv4_enabled?: boolean
  ipv6_enabled?: boolean
}

export interface GuardrailConfig {
  // List of enabled guardrail names
  // Critical guardrails are always enforced server-side
  enabled_guardrails?: string[]

  // Per-guardrail strictness levels
  strictness?: {
    prefix_count?: 'low' | 'medium' | 'high' | 'strict'
    bogon_prefix?: 'low' | 'medium' | 'high' | 'strict'
    rpki_validation?: 'low' | 'medium' | 'high' | 'strict'
  }

  // Prefix count thresholds (optional overrides)
  prefix_count_thresholds?: {
    max_total_prefixes?: number      // Positive integer
    max_prefixes_per_as?: number     // Positive integer
    warning_threshold?: number       // 0.0-1.0 ratio
    critical_threshold?: number      // 0.0-1.0 ratio
  }
}

export interface NetworkSecurityConfig {
  ssh_known_hosts?: string
  ssh_connection_timeout?: number
  ssh_max_workers?: number
  strict_host_verification?: boolean
  allowed_networks?: string[]
  blocked_networks?: string[]
}

export interface AppConfig {
  ssh: SSHConfig
  smtp?: SMTPConfig
  rpki?: RPKIConfig
  bgpq4?: BGPq4Config
  guardrails?: GuardrailConfig
  network_security?: NetworkSecurityConfig
  irr_proxy?: IRRProxyConfig
  autonomous_mode?: AutonomousModeConfig
  netconf?: NetconfConfig
  [key: string]: any
}

export interface ConfigValidationIssue {
  path: string
  msg: string
}

export interface ConfigValidationResponse {
  valid: boolean
  issues: ConfigValidationIssue[]
}

// Reports Types
export interface RouterInfo {
  hostname: string
  ip_address: string
  site?: string
  role?: string
  bgp_groups: string[]
  as_numbers: number[]
}

export interface DeploymentMatrix {
  routers: Record<string, RouterInfo>
  as_distribution: Record<string, string[]>
  bgp_groups: Record<string, string[]>
  statistics: {
    total_routers: number
    total_as_numbers: number
    total_bgp_groups: number
  }
  generated_at: string
}

// SystemD Types
export interface SystemDUnit {
  name: string
  activestate?: string
  substate?: string
  description?: string
  error?: string
}

export interface SystemDResponse {
  units: SystemDUnit[]
}

export interface ServiceControlRequest {
  action: 'start' | 'stop' | 'restart' | 'reload'
  service: string
}

// IRR Proxy Types
export interface IRRProxyTunnel {
  name: string
  local_port: number
  remote_host: string
  remote_port: number
}

export interface IRRProxyConfig {
  enabled: boolean
  method?: 'ssh_tunnel'
  jump_host?: string
  jump_user?: string
  ssh_key_file?: string | null
  known_hosts_file?: string | null
  connection_timeout?: number
  tunnels?: IRRProxyTunnel[]
}

// Autonomous Mode Types
export interface SafetyOverridesConfig {
  max_session_loss_percent?: number
  max_route_loss_percent?: number
  monitoring_duration_seconds?: number
}

export interface AutonomousModeConfig {
  enabled: boolean
  auto_apply_threshold?: number
  require_confirmation?: boolean
  safety_overrides?: SafetyOverridesConfig
}

// Re-export rollout types
export * from './rollout'