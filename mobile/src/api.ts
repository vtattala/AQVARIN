import type { AnalysisJob, DistressReport, TrackingFrame, RipCurrentReport } from "./schema";

/** Use a network-reachable backend URL on physical phones, not localhost. */
export class AegisCoastClient {
  constructor(private readonly baseUrl: string) {}

  async health(): Promise<void> {
    let response: Response;
    try {
      try {
        response = await fetch(`${this.baseUrl}/api/health`, { signal: AbortSignal.timeout(8000),cache:'no-store' });
      } catch {
        await new Promise(resolve => setTimeout(resolve,1000));
        response = await fetch(`${this.baseUrl}/api/health`, { signal: AbortSignal.timeout(8000),cache:'no-store' });
      }
    } catch {
      throw new Error(`Cannot reach the analysis server at ${this.baseUrl}. Start AQVARIN on your computer, then retry. On a phone, use the same Wi-Fi and check the server address in Settings.`);
    }
    if (!response.ok) throw new Error(`Analysis server returned ${response.status}. Check the server address in Settings.`);
  }

  async uploadVideo(uri: string, filename: string, mimeType = "video/mp4",
                    options: { file?: File; trackingPreset?: "original" | "continuity"; sceneType?: "auto" | "swimmers_only"; detectionMode?: "full" | "sliced"; roi?: { coordinate_space: "normalized"; polygon: [number, number][] } } = {}): Promise<AnalysisJob> {
    const body = new FormData();
    // One ID per upload attempt: retries cannot schedule duplicate analyses.
    const requestId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c => {
      const n = Math.floor(Math.random()*16);
      return (c === 'x' ? n : (n&3)|8).toString(16);
    });
    body.append('request_id',requestId);
    body.append("video", options.file ?? ({ uri, name: filename, type: mimeType } as unknown as Blob));
    body.append("tracking_preset", options.trackingPreset ?? "original");
    body.append("detection_mode", options.detectionMode ?? "full");
    body.append('scene_type', options.sceneType ?? 'auto');
    if (options.roi) body.append("roi_json", JSON.stringify(options.roi));
    for (let attempt=0;attempt<3;attempt++) {
      try {
        const response = await fetch(`${this.baseUrl}/api/analyze-video`, { method: "POST", body });
        if ([409,502,503,504].includes(response.status) && attempt<2) {
          await new Promise(resolve=>setTimeout(resolve,1000*(attempt+1)));
          continue;
        }
        return this.readJson<AnalysisJob>(response);
      } catch (error) {
        if (attempt===2) throw new Error(`Upload connection lost. The server may be restarting. Retry once it is connected. ${error instanceof Error ? error.message : ''}`);
        await new Promise(resolve=>setTimeout(resolve,1000*(attempt+1)));
      }
    }
    throw new Error('Upload could not be completed.');
  }

  async getJob(jobId: string): Promise<AnalysisJob> {
    return this.readJson<AnalysisJob>(await fetch(`${this.baseUrl}/api/jobs/${encodeURIComponent(jobId)}`, {cache:'no-store',signal:AbortSignal.timeout(12000)}));
  }

  videoUrl(job: AnalysisJob): string | null {
    if (!job.video_url) return null;
    const url = new URL(job.video_url,this.baseUrl);
    url.searchParams.set('revision',String(job.summary?.processing_seconds ?? 0));
    return url.toString();
  }

  async getFrames(job: AnalysisJob): Promise<TrackingFrame[]> {
    if (!job.tracks_url) throw new Error("Tracking results are not ready");
    const response = await fetch(new URL(job.tracks_url, this.baseUrl), {cache:'no-store'});
    if (!response.ok) throw new Error(`Tracks request failed: ${response.status}`);
    const text = await response.text();
    return text.trim() ? text.trim().split("\n").map(line => JSON.parse(line) as TrackingFrame) : [];
  }

  async getDistress(job: AnalysisJob): Promise<DistressReport | null> {
    if (!job.distress_url) return null;
    return this.readJson<DistressReport>(await fetch(new URL(job.distress_url, this.baseUrl), {cache:'no-store'}));
  }

  async getRipCurrent(job: AnalysisJob): Promise<RipCurrentReport | null> {
    if (!job.rip_current_url) return null;
    return this.readJson<RipCurrentReport>(await fetch(new URL(job.rip_current_url,this.baseUrl), {cache:'no-store'}));
  }

  private async readJson<T>(response: Response): Promise<T> {
    if (!response.ok) throw new Error(`Analysis API error ${response.status}: ${await response.text()}`);
    return response.json() as Promise<T>;
  }
}
