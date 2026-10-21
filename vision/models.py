"""Pixel-space records used by the pipeline and serialized for mobile clients."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox_xyxy
        return ((x1 + x2) / 2, (y1 + y2) / 2)


@dataclass(frozen=True)
class TrackPoint:
    frame: int
    timestamp_s: float
    x_px: float
    y_px: float


@dataclass(frozen=True)
class MotionState:
    displacement_px: float = 0.0
    velocity_px_s: tuple[float, float] = (0.0, 0.0)
    rolling_velocity_px_s: tuple[float, float] = (0.0, 0.0)
    speed_px_s: float = 0.0
    heading_deg: float | None = None


@dataclass(frozen=True)
class TrackedObject:
    track_id: int
    detection: Detection
    motion: MotionState
    track_age_frames: int
    consecutive_observed_frames: int
    missed_frames: int
    trail: tuple[TrackPoint, ...]

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "class_id": self.detection.class_id,
            "class": self.detection.class_name,
            "confidence": self.detection.confidence,
            "bbox_xyxy_px": list(self.detection.bbox_xyxy),
            "center_px": list(self.detection.center),
            "motion": asdict(self.motion),
            "track_age_frames": self.track_age_frames,
            "consecutive_observed_frames": self.consecutive_observed_frames,
            "missed_frames": self.missed_frames,
            "trail": [asdict(point) for point in self.trail],
        }
