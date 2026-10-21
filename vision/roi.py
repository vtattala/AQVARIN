"""Per-video normalized polygon used to reject detections outside water/surf."""
import json
from pathlib import Path

from .models import Detection


class PolygonROI:
    def __init__(self, points: list[tuple[float, float]]):
        if len(points) < 3 or any(not 0 <= x <= 1 or not 0 <= y <= 1 for x, y in points):
            raise ValueError("ROI needs at least three normalized [x, y] points")
        self.points = points

    @classmethod
    def load(cls, path: Path) -> "PolygonROI":
        if not path.is_file():
            raise FileNotFoundError(f"ROI file not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("coordinate_space") != "normalized":
            raise ValueError("ROI coordinate_space must be normalized")
        return cls([tuple(point) for point in payload["polygon"]])

    def contains(self, detection: Detection, width: int, height: int) -> bool:
        import cv2
        import numpy as np

        polygon = np.array([(x * width, y * height) for x, y in self.points], dtype=np.float32)
        x1, _, x2, y2 = detection.bbox_xyxy
        return cv2.pointPolygonTest(polygon, ((x1 + x2) / 2, y2), False) >= 0

    def filter(self, detections: list[Detection], width: int, height: int) -> tuple[list[Detection], list[Detection]]:
        inside, outside = [], []
        for detection in detections:
            (inside if self.contains(detection, width, height) else outside).append(detection)
        return inside, outside
