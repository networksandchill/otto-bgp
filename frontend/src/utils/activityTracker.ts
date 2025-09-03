// Lightweight user activity tracking for idle gating
let lastActivity = Date.now()
let warningTimer: ReturnType<typeof setTimeout> | null = null
let logoutTimer: ReturnType<typeof setTimeout> | null = null
let throttleTimer: ReturnType<typeof setTimeout> | null = null

// Defaults: 18-minute warning, 20-minute logout
const DEFAULT_WARNING_MS = 18 * 60 * 1000
const DEFAULT_TIMEOUT_MS = 20 * 60 * 1000
const THROTTLE_MS = 1000

export function shouldRefreshToken(): boolean {
  // Only refresh if user active within last 30 seconds
  return Date.now() - lastActivity < 30_000
}

export function markActivity(): void {
  if (!throttleTimer) {
    lastActivity = Date.now()
    throttleTimer = setTimeout(() => { throttleTimer = null }, THROTTLE_MS)
  }
}

export function initActivityTracking(options: {
  warningMs?: number
  timeoutMs?: number
  onWarning: () => void
  onTimeout: () => void
}) {
  const warningMs = options.warningMs ?? DEFAULT_WARNING_MS
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS

  const resetTimers = () => {
    if (warningTimer) clearTimeout(warningTimer)
    if (logoutTimer) clearTimeout(logoutTimer)
    warningTimer = setTimeout(options.onWarning, warningMs)
    logoutTimer = setTimeout(options.onTimeout, timeoutMs)
  }

  // Events indicating user activity
  const events: Array<keyof DocumentEventMap> = [
    'mousedown', 'keydown', 'scroll', 'touchstart', 'pointerdown', 'visibilitychange'
  ]

  const onEvent = () => {
    if (document.hidden) return
    markActivity()
    resetTimers()
  }

  events.forEach(ev => document.addEventListener(ev, onEvent, { passive: true } as any))
  resetTimers()

  // Cleanup
  return () => {
    if (warningTimer) clearTimeout(warningTimer)
    if (logoutTimer) clearTimeout(logoutTimer)
    if (throttleTimer) clearTimeout(throttleTimer)
    events.forEach(ev => document.removeEventListener(ev, onEvent))
  }
}