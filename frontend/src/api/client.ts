import axios, { AxiosInstance } from 'axios'
import type {
  LoginRequest, LoginResponse, SessionInfo, SetupState, SetupAdminRequest,
  AppConfig, ConfigValidationResponse, DeploymentMatrix, SystemDResponse,
  ServiceControlRequest, SMTPConfig
} from '../types'
import { shouldRefreshToken } from '../utils/activityTracker'

class ApiClient {
  private client: AxiosInstance
  private refreshPromise: Promise<void> | null = null

  constructor() {
    this.client = axios.create({
      baseURL: '/api',
      timeout: 30000,
      withCredentials: true, // Include cookies for refresh tokens
    })

    // Request interceptor to add Authorization header
    this.client.interceptors.request.use((config) => {
      const token = this.getAccessToken()
      if (token) {
        // Axios v1 may use AxiosHeaders; support both shapes
        const h: any = (config.headers ?? {}) as any
        if (typeof h.set === 'function') {
          h.set('Authorization', `Bearer ${token}`)
          config.headers = h
        } else {
          (config.headers as any) = { ...(config.headers || {}), Authorization: `Bearer ${token}` }
        }
      }
      return config
    })

    // Response interceptor for token refresh
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config
        const reqUrl: string = (originalRequest?.url || '').toString()

        if (error.response?.status === 401 && !originalRequest._retry && !reqUrl.includes('/auth/refresh')) {
          originalRequest._retry = true
          
          // Only attempt refresh if recently active; otherwise logout
          if (!shouldRefreshToken()) {
            this.clearTokens()
            window.location.href = '/login'
            return Promise.reject(error)
          }
          
          // Use singleton refresh promise to prevent concurrent refreshes
          if (!this.refreshPromise) {
            this.refreshPromise = this.refreshToken().finally(() => {
              this.refreshPromise = null
            })
          }
          
          try {
            await this.refreshPromise
            // Update Authorization header with new token before retry
            const newToken = this.getAccessToken()
            if (newToken) {
              const hdrs: any = (originalRequest.headers ?? {}) as any
              if (typeof hdrs.set === 'function') {
                hdrs.set('Authorization', `Bearer ${newToken}`)
                originalRequest.headers = hdrs
              } else {
                originalRequest.headers = { ...(originalRequest.headers || {}), Authorization: `Bearer ${newToken}` }
              }
            }
            return this.client(originalRequest)
          } catch (refreshError) {
            // Refresh failed, redirect to login
            this.clearTokens()
            window.location.href = '/login'
            return Promise.reject(refreshError)
          }
        }
        
        return Promise.reject(error)
      }
    )
  }

  // Token management
  private setAccessToken(token: string) {
    sessionStorage.setItem('access_token', token)
  }

  private getAccessToken(): string | null {
    return sessionStorage.getItem('access_token')
  }

  public clearTokens() {
    sessionStorage.removeItem('access_token')
  }

  // Setup endpoints
  async getSetupState(): Promise<SetupState> {
    const response = await this.client.get<SetupState>('/setup/state')
    return response.data
  }

  async setupAdmin(data: SetupAdminRequest, setupToken: string): Promise<void> {
    await this.client.post('/setup/admin', data, {
      headers: { 'X-Setup-Token': setupToken }
    })
  }

  async setupConfig(config: AppConfig, setupToken: string): Promise<void> {
    await this.client.post('/setup/config', config, {
      headers: { 'X-Setup-Token': setupToken }
    })
  }

  async completeSetup(setupToken: string): Promise<void> {
    await this.client.post('/setup/complete', {}, {
      headers: { 'X-Setup-Token': setupToken }
    })
  }

  // Authentication endpoints
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const response = await this.client.post<LoginResponse>('/auth/login', credentials)
    const { access_token } = response.data
    
    // Store token
    this.setAccessToken(access_token)
    
    return response.data
  }

  async getSession(): Promise<SessionInfo> {
    const response = await this.client.get<SessionInfo>('/auth/session')
    return response.data
  }

  async refreshToken(): Promise<void> {
    const response = await this.client.post<{ access_token: string }>('/auth/refresh')
    const { access_token } = response.data
    
    this.setAccessToken(access_token)
  }

  async logout(): Promise<void> {
    try {
      await this.client.post('/auth/logout')
    } finally {
      this.clearTokens()
    }
  }

  // Configuration endpoints
  async getConfig(): Promise<AppConfig> {
    const response = await this.client.get<AppConfig>('/config/')
    return response.data
  }

  async updateConfig(config: AppConfig): Promise<{ success: boolean; backup?: string; message?: string }> {
    const response = await this.client.put('/config/', config)
    return response.data
  }

  async validateConfig(config: AppConfig): Promise<ConfigValidationResponse> {
    const response = await this.client.post<ConfigValidationResponse>('/config/validate', {
      config_json: config
    })
    return response.data
  }

  async testSmtp(smtpConfig: SMTPConfig): Promise<{ success: boolean; message?: string }> {
    const response = await this.client.post('/config/test-smtp', smtpConfig)
    return response.data
  }

  async sendTestEmail(smtp?: SMTPConfig): Promise<{ success: boolean; message?: string }> {
    const response = await this.client.post('/config/send-test-email', smtp || {})
    return response.data
  }

  async validateRpkiCache(): Promise<{ ok: boolean; issues?: string[] }> {
    const response = await this.client.post('/rpki/validate-cache', {})
    return response.data
  }

  // Config Export/Import endpoints
  async exportConfig(): Promise<Blob> {
    const response = await this.client.get('/config/export', {
      responseType: 'blob'
    })
    return response.data
  }

  async importConfig(file: File): Promise<{ success: boolean; message?: string; backup_id?: string }> {
    const formData = new FormData()
    formData.append('file', file)
    const response = await this.client.post('/config/import', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    return response.data
  }

  async listBackups(): Promise<{ backups: Array<{
    id: string
    timestamp: string
    files: Array<{ name: string; size: number }>
  }> }> {
    const response = await this.client.get('/config/backups')
    return response.data
  }

  async restoreBackup(backupId: string): Promise<{ success: boolean; message?: string; previous_backup_id?: string }> {
    const response = await this.client.post('/config/restore', { backup_id: backupId })
    return response.data
  }

  // Reports endpoints
  async getDeploymentMatrix(): Promise<DeploymentMatrix | { error: string }> {
    const response = await this.client.get<DeploymentMatrix | { error: string }>('/reports/matrix')
    return response.data
  }

  async getDiscoveryMappings(): Promise<DeploymentMatrix> {
    const response = await this.client.get<DeploymentMatrix>('/reports/discovery')
    return response.data
  }

  // SystemD endpoints
  async getSystemdUnits(unitNames: string[]): Promise<SystemDResponse> {
    const names = unitNames.join(',')
    const response = await this.client.get<SystemDResponse>(`/systemd/units?names=${names}`)
    return response.data
  }

  async controlService(request: ServiceControlRequest): Promise<{ success: boolean; message?: string }> {
    const response = await this.client.post('/systemd/control', request)
    return response.data
  }

  // Health check
  async healthCheck(): Promise<{ status: string; timestamp: string }> {
    const response = await this.client.get('/healthz')
    return response.data
  }

  // RPKI endpoints
  async getRpkiStatus(): Promise<any> {
    const response = await this.client.get('/rpki/status')
    return response.data
  }

  // RPKI Override Management
  async listRpkiOverrides(page: number = 1, perPage: number = 50): Promise<{
    overrides: Array<{
      as_number: number
      rpki_enabled: boolean
      reason: string
      modified_date: string
      modified_by: string
    }>
    total: number
    page: number
    per_page: number
  }> {
    const response = await this.client.get(`/rpki-overrides/overrides?page=${page}&per_page=${perPage}`)
    return response.data
  }

  async disableRpkiForAs(asNumber: number, reason: string): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post(`/rpki-overrides/overrides/${asNumber}/disable`, { reason })
    return response.data
  }

  async enableRpkiForAs(asNumber: number, reason: string): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post(`/rpki-overrides/overrides/${asNumber}/enable`, { reason })
    return response.data
  }

  async getRpkiOverrideHistory(asNumber?: number, limit: number = 100): Promise<{
    history: Array<{
      id: number
      as_number: number
      action: string
      reason: string
      timestamp: string
      user: string
      ip_address: string
    }>
    total: number
  }> {
    const params = new URLSearchParams()
    if (asNumber) params.append('as_number', asNumber.toString())
    params.append('limit', limit.toString())
    const response = await this.client.get(`/rpki-overrides/overrides/history?${params}`)
    return response.data
  }

  // Logs endpoints
  async getLogs(params?: { service?: string; level?: string; limit?: number }): Promise<any> {
    const searchParams = new URLSearchParams()
    if (params?.service && params.service !== 'all') {
      searchParams.append('service', params.service)
    }
    if (params?.level && params.level !== 'all') {
      searchParams.append('level', params.level)
    }
    if (params?.limit) {
      searchParams.append('limit', params.limit.toString())
    }
    const response = await this.client.get(`/logs?${searchParams}`)
    return response.data
  }

  async getLogFiles(): Promise<{ files: Array<{
    name: string
    path: string
    size: number
    modified: number
    description: string
  }> }> {
    const response = await this.client.get('/logs/files')
    return response.data
  }

  async getLogFileContent(filename: string, params?: {
    lines?: number
    offset?: number
    search?: string
  }): Promise<{
    filename: string
    entries: Array<{
      timestamp: string
      level: string
      message: string
      module?: string
      raw: string
    }>
    total_lines: number
    offset: number
    limit: number
    has_more: boolean
  }> {
    const searchParams = new URLSearchParams()
    if (params?.lines) searchParams.append('lines', params.lines.toString())
    if (params?.offset) searchParams.append('offset', params.offset.toString())
    if (params?.search) searchParams.append('search', params.search)
    
    const response = await this.client.get(`/logs/files/${filename}?${searchParams}`)
    return response.data
  }

  // Device Management
  async getDevices(): Promise<{ devices: Array<{
    address: string
    hostname: string
    role: string
    region: string
  }> }> {
    const response = await this.client.get('/devices/')
    return response.data
  }

  async addDevice(device: {
    address: string
    hostname: string
    role: string
    region: string
  }): Promise<{ success: boolean; device: any }> {
    const response = await this.client.post('/devices/', device)
    return response.data
  }

  async updateDevice(address: string, device: Partial<{
    hostname: string
    role: string
    region: string
  }>): Promise<{ success: boolean }> {
    const response = await this.client.put(`/devices/${encodeURIComponent(address)}`, device)
    return response.data
  }

  async deleteDevice(address: string): Promise<{ success: boolean }> {
    const response = await this.client.delete(`/devices/${encodeURIComponent(address)}`)
    return response.data
  }

  // Profile Management
  async getUserProfile(): Promise<{
    username: string
    email?: string
    role: string
    created_at?: string
  }> {
    const response = await this.client.get('/profile/')
    return response.data
  }

  async updateProfile(data: {
    email?: string
    current_password?: string
    new_password?: string
  }): Promise<{ success: boolean; message?: string }> {
    const response = await this.client.put('/profile/', data)
    return response.data
  }

  // User Management (Admin only)
  async getUsers(): Promise<{ users: Array<{
    username: string
    email?: string
    role: 'admin' | 'operator' | 'read_only'
    created_at?: string
    last_login?: string
  }> }> {
    const response = await this.client.get('/users/')
    return response.data
  }

  async createUser(data: {
    username: string
    email?: string
    password: string
    role: 'admin' | 'operator' | 'read_only'
  }): Promise<any> {
    const response = await this.client.post('/users/', data)
    return response.data
  }

  async updateUser(username: string, data: {
    email?: string
    password?: string
    role?: 'admin' | 'operator' | 'read_only'
  }): Promise<any> {
    const response = await this.client.put(`/users/${username}`, data)
    return response.data
  }

  async deleteUser(username: string): Promise<any> {
    const response = await this.client.delete(`/users/${username}`)
    return response.data
  }

  // SSH Key Management endpoints
  async generateSSHKey(data?: { key_type?: 'ed25519' | 'rsa' | 'ecdsa'; path?: string }): Promise<{
    success: boolean
    message: string
    public_key?: string
    fingerprints?: { sha256: string; md5: string }
  }> {
    const response = await this.client.post('/ssh/generate-key', data || { key_type: 'ed25519' })
    return response.data
  }

  async getSSHPublicKey(path?: string): Promise<{
    public_key: string
    fingerprints: { sha256: string; md5: string }
    path: string
  }> {
    const params = path ? { path } : {}
    const response = await this.client.get('/ssh/public-key', { params })
    return response.data
  }

  async uploadSSHKey(file: File, path?: string): Promise<{
    success: boolean
    message: string
    public_key?: string
    fingerprints?: { sha256: string; md5: string }
  }> {
    const formData = new FormData()
    formData.append('file', file)
    if (path) {
      formData.append('path', path)
    }
    const response = await this.client.post('/ssh/upload-key', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return response.data
  }

  async getKnownHosts(path?: string): Promise<{
    entries: Array<{
      line: number
      host: string
      key_type: string
      fingerprint: string
      raw: string
    }>
    path: string
  }> {
    const params = path ? { path } : {}
    const response = await this.client.get('/ssh/known-hosts', { params })
    return response.data
  }

  async addKnownHost(entry: string, path?: string): Promise<{
    success: boolean
    message: string
  }> {
    const params = path ? { path } : {}
    const response = await this.client.post('/ssh/known-hosts/add', { entry }, { params })
    return response.data
  }

  async fetchHostKey(host: string, port: number = 22): Promise<{
    success: boolean
    key_entry: string
    fingerprint: string
    message: string
  }> {
    const response = await this.client.post('/ssh/known-hosts/fetch', { host, port })
    return response.data
  }

  async removeKnownHost(line_number: number, path?: string): Promise<{
    success: boolean
    message: string
  }> {
    const params = path ? { path } : {}
    const response = await this.client.delete('/ssh/known-hosts/remove', {
      data: { line_number },
      params
    })
    return response.data
  }

  // IRR Proxy endpoints
  async testIrrProxy(): Promise<{ success: boolean; message?: string; stdout?: string; stderr?: string }> {
    const response = await this.client.post('/irr-proxy/test', {})
    return response.data
  }

  // Multi-Router Rollout endpoints
  async listRollouts(status?: string, limit: number = 50): Promise<any> {
    const response = await this.client.get('/pipeline/rollouts', {
      params: { status, limit }
    })
    return response.data
  }

  async getRolloutStatus(runId: string): Promise<any> {
    const response = await this.client.get(`/pipeline/rollouts/${runId}`)
    return response.data
  }

  async getRolloutStages(runId: string): Promise<any> {
    const response = await this.client.get(`/pipeline/rollouts/${runId}/stages`)
    return response.data
  }

  async getRolloutTargets(runId: string, stageId: string, state?: string): Promise<any> {
    const response = await this.client.get(`/pipeline/rollouts/${runId}/stages/${stageId}/targets`, {
      params: { state }
    })
    return response.data
  }

  async getRolloutEvents(runId: string, eventType?: string, limit: number = 100): Promise<any> {
    const response = await this.client.get(`/pipeline/rollouts/${runId}/events`, {
      params: { event_type: eventType, limit }
    })
    return response.data
  }
}

export const apiClient = new ApiClient()
export default apiClient
