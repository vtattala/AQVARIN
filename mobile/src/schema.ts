/** Shared wire contract for an eventual React Native / Expo interface. */
export type PixelPoint = [number, number];
export type PixelBox = [number, number, number, number];

export interface TrackPoint {
  frame: number;
  timestamp_s: number;
  x_px: number;
  y_px: number;
}

export interface MotionState {
  displacement_px: number;
  velocity_px_s: PixelPoint;
  rolling_velocity_px_s: PixelPoint;
  speed_px_s: number;
  heading_deg: number | null;
}

export interface TrackedObject {
  track_id: number;
  source_track_id?: number;
  identity?: { method: 'new' | 'continuity' | 'reacquired'; gap_seconds: number };
  class_id: number;
  class: string;
  confidence: number;
  bbox_xyxy_px: PixelBox;
  center_px: PixelPoint;
  motion: MotionState;
  track_age_frames: number;
  consecutive_observed_frames: number;
  missed_frames: number;
  trail: TrackPoint[];
  distress_action?: { label: string; score: number; requires_review: boolean };
}

export interface TrackingFrame {
  schema_version: 1;
  frame: number;
  timestamp_s: number;
  coordinate_space: "pixel";
  objects: TrackedObject[];
  unobserved_swimmers?: { track_id: number; bbox_xyxy_px: PixelBox; last_seen_s: number;
    missing_seconds: number; visibility: 'unobserved'; confidence: null; action_score: null;
    last_action?: TrackedObject['distress_action']; reason: string }[];
}

export interface ProcessingSummary {
  frames: number;
  video_fps: number;
  processing_seconds: number;
  processing_fps: number;
  average_inference_ms: number;
  average_tracking_overhead_ms: number;
  raw_detections: number;
  roi_rejections: number;
  size_rejections: number;
  tracked_observations: number;
  unique_tracks: number;
  output_video: string;
  output_jsonl: string;
}

export interface AnalysisJob {
  job_id: string;
  state: "queued" | "processing" | "completed" | "failed";
  summary: ProcessingSummary | null;
  error: string | null;
  video_url?: string;
  tracks_url?: string;
  distress_url?: string;
  rip_current_url?: string;
}

export interface RipCurrentReport {
  schema_version: 1;
  status: 'complete' | 'failed';
  error?: string;
  model: { state: 'ready' | 'failed'; backend: 'ripscout'; label: 'sediment_rip' };
  width_px?: number;
  height_px?: number;
  observations?: number;
  sampled_frames?: number;
  samples: { frame: number; timestamp_s: number; regions: { region_id: number; label: string; score: number; bbox_xyxy_px: PixelBox }[] }[];
  events: { region_id: number; frame: number; timestamp_s: number; start_s: number; type: 'possible_rip_current';
    requires_review: true; bbox_xyxy_px: PixelBox; model_score: number; peak_score: number; distinct_predictions: number }[];
}

export interface DistressEvent {
  track_id: number;
  frame: number;
  timestamp_s: number;
  start_s: number;
  type: 'possible_distress';
  requires_review: true;
  signals: string[];
  action_score: number | null;
  score_basis?: string;
  metrics?: { distinct_predictions?: number; peak_action_score?: number; evidence_span_seconds?: number };
}

export interface DistressReport {
  schema_version: 1;
  status: 'complete' | 'failed';
  error?: string;
  classifier?: { state: 'ready' | 'missing_checkpoint' | 'failed'; message: string; backend?: 'yolo' | 'z5cc'; observed_actions?: Record<string,number> };
  indicator_capabilities?: Record<string, string>;
  motion_reference?: 'uncalibrated' | 'stationary' | 'stabilized';
  water_confirmed?: boolean;
  events: DistressEvent[];
}
