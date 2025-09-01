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

export interface SMTPConfig {
  enabled: boolean
  host?: string
  port?: number
  username?: string
  password?: string
  use_tls?: boolean
  from_address?: string
  to_addresses?: string[]
}

export interface RPKIConfig {
  enabled?: boolean
  cache_dir?: string
  validator_url?: string
  refresh_interval?: number
  strict_validation?: boolean
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
  enabled?: boolean
  max_prefix_threshold?: number
  max_session_loss_percent?: number
  max_route_loss_percent?: number
  bogon_check_enabled?: boolean
  require_confirmation?: boolean
  monitoring_duration?: number
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