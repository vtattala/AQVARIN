"""CLI and reusable service for prerecorded maritime video analysis."""
import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from .config import PipelineConfig
from .detector import MaritimeDetector
from .exclusions import OutputExclusions
from .geometry import filter_oversized_swimmers
from .history import TrackHistory
from .overlay import draw_tracks
from .roi import PolygonROI
from .review import CandidateRecorder
from .tracker import MaritimeTracker

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessingSummary:
    frames: int
    video_fps: float
    processing_seconds: float
    processing_fps: float
    average_inference_ms: float
    average_tracking_overhead_ms: float
    raw_detections: int
    roi_rejections: int
    size_rejections: int
    tracked_observations: int
    unique_tracks: int
    output_video: str
    output_jsonl: str


def analyze_video(input_path: Path, output_video: Path, output_jsonl: Path,
                  config: PipelineConfig, max_frames: int | None = None,
                  review_dir: Path | None = None,
                  diagnostics_path: Path | None = None) -> ProcessingSummary:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is missing; install requirements.txt") from exc
    if not input_path.is_file():
        raise FileNotFoundError(f"Input video not found: {input_path}")
    if output_video.resolve() == input_path.resolve():
        raise ValueError("Output video cannot overwrite the input")
    if output_jsonl.resolve() == input_path.resolve():
        raise ValueError("JSONL output cannot overwrite the input")
    config.validate()
    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open input video: {input_path}")
    writer = None
    recorder = None
    diagnostics_sink = None
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if fps <= 0 or width <= 0 or height <= 0:
            raise ValueError("Input video has invalid FPS or dimensions")
        LOG.info("Video: %s (%dx%d at %.3f FPS)", input_path, width, height, fps)
        detector = MaritimeDetector(config)
        tracker = MaritimeTracker(config)
        roi = PolygonROI.load(config.roi_path) if config.roi_path else None
        exclusions = OutputExclusions.load(config.output_exclusions_path) if config.output_exclusions_path else None
        recorder = CandidateRecorder(review_dir) if review_dir else None
        history = TrackHistory(config.history_limit, config.rolling_points)
        output_video.parent.mkdir(parents=True, exist_ok=True)
        output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        if diagnostics_path:
            if diagnostics_path.resolve() in {input_path.resolve(), output_video.resolve(), output_jsonl.resolve()}:
                raise ValueError("Diagnostics path must differ from input and outputs")
            diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
            diagnostics_sink = diagnostics_path.open("w", encoding="utf-8")
        writer = cv2.VideoWriter(str(output_video), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError(f"Cannot create MP4 output (codec or path): {output_video}")
        frames = raw = rejected = size_rejected = tracked = infer_ms = associate_ms = 0
        identities: set[int] = set()
        started = perf_counter()
        with output_jsonl.open("w", encoding="utf-8") as sink:
            while max_frames is None or frames < max_frames:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame is None or frame.size == 0:
                    LOG.warning("Empty frame at index %d", frames)
                    continue
                timestamp_s = frames / fps
                detections, one_infer_ms = detector.detect(frame)
                raw += len(detections)
                outside = []
                if roi:
                    detections, outside = roi.filter(detections, width, height)
                    rejected += len(outside)
                detections, oversized = filter_oversized_swimmers(
                    detections, width, height, config.max_swimmer_box_area_ratio)
                size_rejected += len(oversized)
                matches, one_associate_ms = tracker.update(detections, frame)
                if recorder:
                    recorder.observe(frames, frame, detections, outside, matches, oversized)
                objects = [history.update(track_id, detection, frames, timestamp_s)
                           for track_id, detection in matches]
                serialized = [obj.to_dict() for obj in objects]
                suppressed = []
                if exclusions:
                    serialized, suppressed = exclusions.filter(serialized, width, height, frames)
                    retained_ids = {obj["track_id"] for obj in serialized}
                    objects = [obj for obj in objects if obj.track_id in retained_ids]
                if diagnostics_sink:
                    def encode(items):
                        return [{"class": item.class_name, "confidence": item.confidence,
                                 "bbox_xyxy_px": item.bbox_xyxy, "center_px": item.center} for item in items]
                    diagnostics_sink.write(json.dumps({"frame": frames, "timestamp_s": timestamp_s,
                        "kept_detections": encode(detections), "roi_rejections": encode(outside),
                        "size_rejections": encode(oversized), "output_suppressions": suppressed,
                        "matched_track_ids": [track_id for track_id, _ in matches]}) + "\n")
                sink.write(json.dumps({"schema_version": 1, "frame": frames,
                                       "timestamp_s": timestamp_s,
                                       "coordinate_space": "pixel",
                                       "objects": serialized}) + "\n")
                writer.write(draw_tracks(frame, objects))
                tracked += len(objects)
                identities.update(obj.track_id for obj in objects)
                infer_ms += one_infer_ms
                associate_ms += one_associate_ms
                frames += 1
                if frames % 100 == 0:
                    LOG.info("Processed %d frames", frames)
        if frames == 0:
            raise ValueError("Video contained no readable frames")
        elapsed = perf_counter() - started
        summary = ProcessingSummary(frames, fps, elapsed, frames / elapsed, infer_ms / frames,
                                    associate_ms / frames, raw, rejected, size_rejected, tracked, len(identities),
                                    str(output_video), str(output_jsonl))
        LOG.info("Finished: %s", json.dumps(asdict(summary)))
        if tracked == 0:
            LOG.warning("No confirmed tracks were produced; inspect model, threshold, and footage")
        return summary
    finally:
        capture.release()
        if writer is not None:
            writer.release()
        if recorder is not None:
            recorder.close()
        if diagnostics_sink is not None:
            diagnostics_sink.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a maritime video with real YOLO tracking")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--weights", type=Path)
    parser.add_argument("--conf", type=float, default=0.30)
    parser.add_argument("--iou", type=float, default=0.7)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--tracker", choices=["botsort", "bytetrack", "deepocsort"], default="botsort")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--max-frames", type=int, help="Useful for a short integration check")
    parser.add_argument("--detection-mode", choices=["full", "sliced"], default="full")
    parser.add_argument("--slice-size", type=int, default=640)
    parser.add_argument("--slice-overlap", type=float, default=0.20)
    parser.add_argument("--no-standard-pred", action="store_true")
    parser.add_argument("--roi", type=Path, help="Per-video normalized water/surf polygon JSON")
    parser.add_argument("--output-exclusions", type=Path, help="Class-specific camera region exclusions after tracking")
    parser.add_argument("--max-swimmer-box-area-ratio", type=float,
                        help="Reject swimmer boxes occupying more than this fraction of the frame")
    parser.add_argument("--diagnostics", type=Path, help="Save pre-tracking detections and filter decisions as JSONL")
    parser.add_argument("--track-high-thresh", type=float)
    parser.add_argument("--track-low-thresh", type=float)
    parser.add_argument("--new-track-thresh", type=float)
    parser.add_argument("--track-buffer", type=int)
    parser.add_argument("--gmc-method", choices=["none", "sparseOptFlow", "orb", "sift", "ecc"])
    parser.add_argument("--reid-model", type=Path, help="Locally supplied compatible ReID checkpoint")
    parser.add_argument("--review-dir", type=Path, help="Save candidate crops for human labeling")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = PipelineConfig(weights=args.weights or PipelineConfig.weights,
                            confidence=args.conf, iou=args.iou, image_size=args.imgsz,
                            tracker=args.tracker, device=args.device,
                            detection_mode=args.detection_mode, slice_size=args.slice_size,
                            slice_overlap=args.slice_overlap, standard_prediction=not args.no_standard_pred,
                            roi_path=args.roi, track_high_thresh=args.track_high_thresh,
                            output_exclusions_path=args.output_exclusions,
                            max_swimmer_box_area_ratio=args.max_swimmer_box_area_ratio,
                            track_low_thresh=args.track_low_thresh, new_track_thresh=args.new_track_thresh,
                            track_buffer=args.track_buffer, gmc_method=args.gmc_method,
                            reid_model=args.reid_model)
    try:
        analyze_video(args.input, args.output, args.jsonl or args.output.with_suffix(".jsonl"),
                      config, args.max_frames, args.review_dir, args.diagnostics)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
