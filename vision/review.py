"""Save uncertain detections for human labeling, without assigning truth labels."""
import json
from pathlib import Path

from .models import Detection


class CandidateRecorder:
    def __init__(self, directory: Path, max_per_kind: int = 100, low_confidence: float = 0.45):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_per_kind = max_per_kind
        self.low_confidence = low_confidence
        self.counts: dict[str, int] = {}
        self.last_seen: dict[int, int] = {}
        self.metadata = (directory / "candidates.jsonl").open("w", encoding="utf-8")

    def observe(self, frame_number: int, frame, detections: list[Detection],
                rejected_by_roi: list[Detection], matches: list[tuple[int, Detection]],
                rejected_by_size: list[Detection] | None = None) -> None:
        for detection in rejected_by_roi:
            self._save("outside_roi", frame_number, frame, detection)
        for detection in rejected_by_size or []:
            self._save("oversized_swimmer", frame_number, frame, detection)
        for detection in detections:
            if detection.confidence < self.low_confidence:
                self._save("low_confidence", frame_number, frame, detection)
        for track_id, detection in matches:
            previous = self.last_seen.get(track_id)
            if previous is not None and frame_number > previous + 1:
                self._save("reappeared_track", frame_number, frame, detection,
                           {"track_id": track_id, "gap_frames": frame_number - previous - 1})
            self.last_seen[track_id] = frame_number

    def _save(self, kind: str, frame_number: int, frame, detection: Detection,
              extra: dict | None = None) -> None:
        import cv2

        index = self.counts.get(kind, 0)
        if index >= self.max_per_kind:
            return
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = detection.bbox_xyxy
        pad = max(12, int(max(x2 - x1, y2 - y1) * 0.5))
        left, top = max(0, int(x1) - pad), max(0, int(y1) - pad)
        right, bottom = min(width, int(x2) + pad), min(height, int(y2) + pad)
        crop = frame[top:bottom, left:right]
        if crop.size == 0:
            return
        kind_dir = self.directory / kind
        kind_dir.mkdir(exist_ok=True)
        name = f"frame_{frame_number:06d}_{index:03d}.jpg"
        if not cv2.imwrite(str(kind_dir / name), crop):
            return
        self.counts[kind] = index + 1
        self.metadata.write(json.dumps({"kind": kind, "frame": frame_number,
                                        "crop": f"{kind}/{name}", "class": detection.class_name,
                                        "confidence": detection.confidence,
                                        "bbox_xyxy_px": detection.bbox_xyxy,
                                        **(extra or {})}) + "\n")

    def close(self) -> None:
        self.metadata.close()
