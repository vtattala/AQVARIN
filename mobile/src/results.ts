import type { TrackingFrame } from './schema';

export const CLASSES = ['swimmer', 'boat', 'buoy', 'jetski', 'life_saving_appliances'] as const;
export const LABELS: Record<string, string> = {swimmer: 'Swimmer', boat: 'Boat', buoy: 'Buoy', jetski: 'Jet ski', life_saving_appliances: 'Rescue equipment'};

export function frameAtTime(frames: TrackingFrame[], time: number): TrackingFrame | undefined {
  let low = 0, high = frames.length - 1;
  while (low <= high) {
    const mid = (low + high) >>> 1;
    if (frames[mid].timestamp_s <= time) low = mid + 1;
    else high = mid - 1;
  }
  return frames.length ? frames[Math.max(0, high)] : undefined;
}

export function classCounts(frames: TrackingFrame[]) {
  return CLASSES.map(name => ({name, observations: frames.reduce((total, frame) =>
    total + frame.objects.filter(o => o.class === name).length, 0)}));
}
