import type { TrackingFrame, DistressEvent, RipCurrentReport } from './schema';

export type ModelStates = Record<string, { state: 'ready' | 'failed'; message?: string; label?: string; device?: string }>;
export interface LiveResult {
  sequence: number;
  captured_at_s: number;
  width_px: number;
  height_px: number;
  processing_ms: number;
  performance?: {sample_gap_s: number | null; coverage_limited: boolean; identification_ms: number; drowning_ms: number; rip_ms: number};
  image_base64: string;
  tracking: TrackingFrame;
  models: ModelStates;
  distress_events: DistressEvent[];
  distress_candidates?: {track_id:number;label:string;last_seen_s:number;first_seen_s:number;action_score:number;peak_score:number;distinct_predictions:number;state:'unconfirmed'}[];
  rip_regions: RipCurrentReport['samples'][number]['regions'];
  rip_events: RipCurrentReport['events'];
  rip_candidates?: {region_id:number;last_seen_s:number;model_score:number;peak_score:number;distinct_predictions:number;evidence_span_s:number;crop_only:boolean;state:'unconfirmed'}[];
}
export interface CameraHandle {
  capture(): Promise<Uint8Array>;
}
export interface CameraProps {
  deviceId?: string;
  facing: 'front' | 'back';
  onReady: () => void;
  onError: (message: string) => void;
  onDevices: (devices: { id: string; label: string }[]) => void;
}
export function decodeBase64(value: string) {
  const raw = atob(value);
  return Uint8Array.from(raw, c => c.charCodeAt(0));
}
