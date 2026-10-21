"""Validated pipeline configuration shared by CLI and API."""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WEIGHTS = ROOT / "YOLOv8n Results & Metrics" / "weights" / "best.pt"


@dataclass(frozen=True)
class PipelineConfig:
    weights: Path = DEFAULT_WEIGHTS
    confidence: float = 0.30
    iou: float = 0.7
    image_size: int = 1280
    tracker: str = "botsort"
    device: str = "auto"
    history_limit: int = 300
    rolling_points: int = 10
    detection_mode: str = "full"
    slice_size: int = 640
    slice_overlap: float = 0.20
    standard_prediction: bool = True
    roi_path: Path | None = None
    output_exclusions_path: Path | None = None
    max_swimmer_box_area_ratio: float | None = None
    track_high_thresh: float | None = None
    track_low_thresh: float | None = None
    new_track_thresh: float | None = None
    track_buffer: int | None = None
    gmc_method: str | None = None
    reid_model: Path | None = None

    def validate(self) -> None:
        if not self.weights.is_file():
            raise FileNotFoundError(f"Model weights not found: {self.weights}")
        if not 0 < self.confidence <= 1 or not 0 < self.iou <= 1:
            raise ValueError("Confidence and IoU must be within (0, 1].")
        if self.image_size < 32 or self.image_size % 32:
            raise ValueError("Image size must be at least 32 and divisible by 32.")
        if self.tracker not in {"botsort", "bytetrack", "deepocsort"}:
            raise ValueError("Tracker must be botsort, bytetrack, or deepocsort.")
        if self.history_limit < 2 or self.rolling_points < 2:
            raise ValueError("History and rolling window must be at least 2.")
        if self.detection_mode not in {"full", "sliced"}:
            raise ValueError("Detection mode must be full or sliced.")
        if self.slice_size < 64 or self.slice_size % 32:
            raise ValueError("Slice size must be at least 64 and divisible by 32.")
        if not 0 <= self.slice_overlap < 0.5:
            raise ValueError("Slice overlap must be within [0, 0.5).")
        for name in ("track_high_thresh", "track_low_thresh", "new_track_thresh"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.track_buffer is not None and self.track_buffer < 1:
            raise ValueError("Track buffer must be positive")
        if self.gmc_method is not None and self.gmc_method not in {"none", "sparseOptFlow", "orb", "sift", "ecc"}:
            raise ValueError("Unsupported GMC method")
        if self.reid_model is not None and not self.reid_model.is_file():
            raise FileNotFoundError(f"ReID model not found: {self.reid_model}")
        if self.reid_model is not None and self.tracker == "bytetrack":
            raise ValueError("ByteTrack does not support ReID")
        if self.max_swimmer_box_area_ratio is not None and not 0 < self.max_swimmer_box_area_ratio <= 1:
            raise ValueError("Maximum swimmer box area ratio must be within (0, 1]")
