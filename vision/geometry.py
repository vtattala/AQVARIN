"""Optional camera-specific sanity rules for detected box geometry."""
from .models import Detection


def filter_oversized_swimmers(detections: list[Detection], width: int, height: int,
                              max_area_ratio: float | None) -> tuple[list[Detection], list[Detection]]:
    if max_area_ratio is None:
        return detections, []
    kept, rejected = [], []
    frame_area = width * height
    for detection in detections:
        x1, y1, x2, y2 = detection.bbox_xyxy
        area_ratio = max(0, x2 - x1) * max(0, y2 - y1) / frame_area
        (rejected if detection.class_name == "swimmer" and area_ratio > max_area_ratio else kept).append(detection)
    return kept, rejected
