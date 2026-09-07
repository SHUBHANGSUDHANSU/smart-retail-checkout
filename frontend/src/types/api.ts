export interface HealthResponse {
  status: 'ok'
  uptime_seconds: number
}

export type ApplicationState =
  | 'initializing'
  | 'running'
  | 'stopping'
  | 'stopped'
  | 'error'

export type ReadinessComponentStatus =
  | 'initializing'
  | 'ready'
  | 'unavailable'
  | 'disabled'

export interface ReadinessResponse {
  status: 'ready' | 'not_ready'
  application_state: ApplicationState
  components: Record<string, ReadinessComponentStatus>
}

export interface MetricsResponse {
  frames_processed_total: number
  dropped_frames_total: number
  detections_total: number
  active_tracks: number
  inference_latency_ms: number
  frame_processing_latency_ms: number
  current_fps: number
  checkout_enter_events_total: number
  checkout_exit_events_total: number
  cart_additions_total: number
  cart_removals_total: number
  cart_resets_total: number
  current_cart_items: number
  current_cart_total: number
  uptime_seconds: number
  camera_errors_total: number
  persistence_errors_total: number
}
