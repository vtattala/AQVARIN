"""Small upload/job API for a future mobile client; no UI assumptions."""
import json
import asyncio
from contextlib import suppress
import logging
from dataclasses import asdict
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import PipelineConfig, ROOT
from .pipeline import analyze_video
from .roi import PolygonROI
from .playback import prepare_playback
from .distress import analyze_distress
from .action_yolo import run_video as enrich_video
from .rip_current import analyze_rip_current
from .live import router as live_router, sessions as live_sessions
from time import perf_counter
from contextlib import asynccontextmanager
from threading import Thread

LOG = logging.getLogger(__name__)
RUNS = ROOT / "outputs" / "jobs"
UPLOADING = set()


def recover_jobs(pending):
    for path in pending:
        try:
            request_path = path.parent/'request.json'
            if not request_path.is_file():
                _save_status(path.parent.name,{'job_id':path.parent.name,'state':'failed','summary':None,
                             'error':'Analysis was interrupted by a server restart. Please analyze this older upload again.'})
                continue
            request = json.loads(request_path.read_text())
            values = request['config']
            for key in ('weights','roi_path','output_exclusions_path','reid_model'):
                if values.get(key): values[key] = Path(values[key])
            config = PipelineConfig(**values)
            config.validate()
            source = path.parent/request['source_name']
            if source.parent.resolve() != path.parent.resolve() or not source.is_file():
                raise ValueError('Saved upload is missing')
            _run_job(path.parent.name,source,config,request['scene_type'])
        except Exception as exc:
            LOG.exception('Could not recover job %s',path.parent.name)
            _save_status(path.parent.name,{'job_id':path.parent.name,'state':'failed','summary':None,
                         'error':f'Could not resume saved upload: {exc}'})


@asynccontextmanager
async def lifespan(app):
    # Snapshot before accepting requests so new uploads cannot be resumed twice.
    pending = []
    for path in RUNS.glob('*/status.json'):
        try:
            if json.loads(path.read_text()).get('state') in {'queued','processing'}:
                pending.append(path)
        except (OSError,ValueError):
            LOG.warning('Unreadable job status: %s',path)
    if pending:
        Thread(target=recover_jobs,args=(pending,),daemon=True).start()
    async def clean_live_sessions():
        while True:
            await asyncio.sleep(30)
            await asyncio.to_thread(live_sessions.reap)
    cleanup = asyncio.create_task(clean_live_sessions())
    try:
        yield
    finally:
        cleanup.cancel()
        with suppress(asyncio.CancelledError): await cleanup
        await asyncio.to_thread(live_sessions.close)


app = FastAPI(title="AQVARIN Analysis API", version="0.1.0",lifespan=lifespan)
app.include_router(live_router)
app.add_middleware(CORSMiddleware, allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|10\.[\d.]+|192\.168\.[\d.]+|172\.(1[6-9]|2\d|3[01])\.[\d.]+)(:\d+)?", allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])


@app.get("/api/health")
def health():
    from .action_yolo import ASSETS
    return {"status": "ok", "classes": ["boat", "buoy", "jetski", "life_saving_appliances", "swimmer"],
            "drowning_model": {"backend":"yolo", "installed":(ASSETS/'drowning_yolov8n.pt').is_file(),
                               "classes":["Active drowning","Possible Passive Drowner","Swimming"]},
            "rip_current_model":{"backend":"ripscout", "installed":(ROOT/'assets/models/ripscout/detect1.tflite').is_file(),
                                 "classes":["sediment_rip"]}}


def _status_path(job_id: str) -> Path:
    try:
        uuid4_value = UUID(job_id)
        if str(uuid4_value) != job_id:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(404, "Job not found") from exc
    return RUNS / job_id / "status.json"


def _save_status(job_id: str, status: dict) -> None:
    path = _status_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(status), encoding="utf-8")
    temporary.replace(path)


def _run_job(job_id: str, source: Path, config: PipelineConfig, scene_type='auto') -> None:
    directory = source.parent
    _save_status(job_id, {"job_id": job_id, "state": "processing", "summary": None, "error": None})
    try:
        started = perf_counter()
        summary = analyze_video(source, directory / "tracked.mp4", directory / "tracks.jsonl", config)
        identification_summary = asdict(summary)
        # An optional action layer must never fail a successful identification job.
        distress_status = "complete"
        enrichment = None
        try:
            from .distress import settings_from_file
            settings = settings_from_file()
            if settings['backend'] == 'yolo':
                enrichment = enrich_video(source, directory/'tracks.jsonl', directory/'swimmer_actions.jsonl',
                                          directory/'analysis.jsonl', directory/'analysis.mp4', settings['device'],scene_type)
            analyze_distress(source, directory / ("analysis.jsonl" if enrichment else "tracks.jsonl"), directory / "distress.json",
                             actions_path=directory/'swimmer_actions.jsonl' if enrichment else None,
                             classifier_metadata=enrichment)
        except Exception as exc:
            LOG.exception("Distress sidecar failed for %s", job_id)
            distress_status = "failed"
            (directory / "distress.json").write_text(json.dumps({"schema_version": 1, "status": "failed",
                "error": str(exc), "events": [], "samples": []}), encoding="utf-8")
        # Independent environmental analysis never writes identification/action files.
        try:
            rip_report = analyze_rip_current(source, directory/'rip_current.json')
        except Exception as exc:
            LOG.exception('Rip-current sidecar failed for %s',job_id)
            rip_report = {'schema_version':1,'status':'failed','error':str(exc),
                          'model':{'state':'failed','backend':'ripscout','label':'sediment_rip'},'samples':[],'events':[]}
            (directory/'rip_current.json').write_text(json.dumps(rip_report),encoding='utf-8')
        prepare_playback(directory / ("analysis.mp4" if enrichment else "tracked.mp4"), directory / "playback.mp4")
        displayed_summary = dict(identification_summary)
        if enrichment:
            displayed_summary.update(tracked_observations=enrichment['tracked_observations'],unique_tracks=enrichment['unique_tracks'],
                                     output_video=str(directory/'analysis.mp4'),output_jsonl=str(directory/'analysis.jsonl'))
        displayed_summary['processing_seconds'] = perf_counter()-started
        displayed_summary['processing_fps'] = displayed_summary['frames']/displayed_summary['processing_seconds']
        _save_status(job_id, {"job_id": job_id, "state": "completed", "summary": displayed_summary,
                              "identification_summary": identification_summary, "enrichment": enrichment,
                              "error": None, "distress_status": distress_status, "rip_current_status":rip_report['status']})
    except Exception as exc:
        LOG.exception("Analysis job %s failed", job_id)
        _save_status(job_id, {"job_id": job_id, "state": "failed", "summary": None, "error": str(exc)})


@app.post("/api/analyze-video", status_code=202)
async def analyze_upload(background: BackgroundTasks, video: UploadFile = File(...),
                         detection_mode: str = Form("full"), roi_json: str | None = Form(None),
                         tracking_preset: str = Form("original"), scene_type: str = Form('auto'),
                         request_id: str | None = Form(None)) -> dict:
    if not video.filename or Path(video.filename).suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv"}:
        raise HTTPException(400, "Upload an MP4, MOV, AVI, or MKV video")
    if detection_mode not in {"full", "sliced"}:
        raise HTTPException(400, "detection_mode must be full or sliced")
    if tracking_preset not in {"original", "continuity"}:
        raise HTTPException(400, "tracking_preset must be original or continuity")
    if scene_type not in {'auto','swimmers_only'}:
        raise HTTPException(400,'scene_type must be auto or swimmers_only')
    if request_id:
        try:
            if str(UUID(request_id)) != request_id:
                raise ValueError('Noncanonical UUID')
        except ValueError as exc:
            raise HTTPException(400,'request_id must be a canonical UUID') from exc
    job_id = request_id or str(uuid4())
    if _status_path(job_id).is_file():
        await video.close()
        return get_job(job_id)
    if job_id in UPLOADING:
        await video.close()
        raise HTTPException(409,'Upload is already being received; retry shortly',headers={'Retry-After':'1'})
    directory = RUNS / job_id
    directory.mkdir(parents=True, exist_ok=True)
    roi_path = None
    if roi_json:
        try:
            payload = json.loads(roi_json)
            if payload.get("coordinate_space") != "normalized":
                raise ValueError("coordinate_space must be normalized")
            PolygonROI([tuple(point) for point in payload["polygon"]])
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(400, f"Invalid roi_json: {exc}") from exc
        roi_path = directory / "roi.json"
        roi_path.write_text(roi_json, encoding="utf-8")
    tuning = dict(confidence=.10, track_high_thresh=.30, track_low_thresh=.10,
                  new_track_thresh=.30, track_buffer=60) if tracking_preset == "continuity" else {}
    config = PipelineConfig(detection_mode=detection_mode, roi_path=roi_path, **tuning)
    source = directory / f"source{Path(video.filename).suffix.lower()}"
    UPLOADING.add(job_id)
    try:
        with source.open("wb") as target:
            while chunk := await video.read(1024 * 1024):
                target.write(chunk)
        if source.stat().st_size == 0:
            source.unlink()
            raise HTTPException(400, "Uploaded video is empty")
        saved_config = {k:str(v) if isinstance(v,Path) else v for k,v in asdict(config).items()}
        request_path = directory/'request.json'
        temporary = request_path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'config':saved_config,'source_name':source.name,'scene_type':scene_type}))
        temporary.replace(request_path)
        _save_status(job_id, {"job_id": job_id, "state": "queued", "summary": None, "error": None})
        background.add_task(_run_job, job_id, source, config, scene_type)
    finally:
        UPLOADING.discard(job_id)
        await video.close()
    return {"job_id": job_id, "state": "queued", "status_url": f"/api/jobs/{job_id}"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    path = _status_path(job_id)
    if not path.is_file():
        raise HTTPException(404, "Job not found")
    status = json.loads(path.read_text(encoding="utf-8"))
    if status["state"] == "completed":
        status["video_url"] = f"/api/jobs/{job_id}/video"
        status["tracks_url"] = f"/api/jobs/{job_id}/tracks"
        if (path.parent / "distress.json").is_file():
            status["distress_url"] = f"/api/jobs/{job_id}/distress"
        if (path.parent / "rip_current.json").is_file():
            status["rip_current_url"] = f"/api/jobs/{job_id}/rip-current"
    return status


@app.get("/api/jobs/{job_id}/video")
def get_video(job_id: str):
    if get_job(job_id)["state"] != "completed":
        raise HTTPException(409, "Analysis is not complete")
    directory = _status_path(job_id).parent
    video = directory / "playback.mp4"
    return FileResponse(video if video.is_file() else directory / "tracked.mp4", media_type="video/mp4",headers={'Cache-Control':'no-store'})


@app.get("/api/jobs/{job_id}/tracks")
def get_tracks(job_id: str):
    job = get_job(job_id)
    if job["state"] != "completed":
        raise HTTPException(409, "Analysis is not complete")
    directory = _status_path(job_id).parent
    return FileResponse(directory / ("analysis.jsonl" if job.get('enrichment') else "tracks.jsonl"), media_type="application/x-ndjson",headers={'Cache-Control':'no-store'})


@app.get("/api/jobs/{job_id}/distress")
def get_distress(job_id: str):
    if get_job(job_id)["state"] != "completed":
        raise HTTPException(409, "Analysis is not complete")
    path = _status_path(job_id).parent / "distress.json"
    if not path.is_file():
        raise HTTPException(404, "This earlier job has no distress analysis")
    return FileResponse(path, media_type="application/json",headers={'Cache-Control':'no-store'})


@app.get('/api/jobs/{job_id}/rip-current')
def get_rip_current(job_id: str):
    if get_job(job_id)['state'] != 'completed':
        raise HTTPException(409, 'Analysis is not complete')
    path = _status_path(job_id).parent/'rip_current.json'
    if not path.is_file():
        raise HTTPException(404, 'This earlier job has no rip-current analysis')
    return FileResponse(path,media_type='application/json',headers={'Cache-Control':'no-store'})
