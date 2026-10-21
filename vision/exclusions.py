"""Camera-specific output exclusions; do not alter detector or tracker state."""
import json
from pathlib import Path


class OutputExclusions:
    def __init__(self, payload: dict):
        import cv2
        import numpy as np

        if payload.get("coordinate_space") != "normalized":
            raise ValueError("Exclusions require normalized coordinates")
        self.rules = payload.get("rules", [])
        if not self.rules:
            raise ValueError("Exclusions require at least one rule")
        for rule in self.rules:
            points = rule["polygon"]
            if len(points) < 3 or any(len(p) != 2 or not all(0 <= v <= 1 for v in p) for p in points):
                raise ValueError("Invalid exclusion polygon")
            if not rule.get("classes") or not 0 < rule.get("min_box_overlap", .6) <= 1:
                raise ValueError("Exclusion requires classes and overlap within (0, 1]")
            if not cv2.isContourConvex(np.array(points, dtype=np.float32)):
                raise ValueError("Output exclusion polygon must be convex")
            if rule.get("start_frame", 0) < 0 or rule.get("end_frame", float("inf")) < rule.get("start_frame", 0):
                raise ValueError("Invalid exclusion frame range")

    @classmethod
    def load(cls, path: Path):
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def filter(self, objects: list[dict], width: int, height: int, frame: int):
        import cv2
        import numpy as np

        kept, rejected = [], []
        for obj in objects:
            reject = False
            x1, y1, x2, y2 = obj["bbox_xyxy_px"]
            area = max(0, x2-x1) * max(0, y2-y1)
            if area:
                box = np.array([[x1,y1],[x2,y1],[x2,y2],[x1,y2]], dtype=np.float32)
                for rule in self.rules:
                    if obj["class"] not in rule["classes"] or not rule.get("start_frame", 0) <= frame <= rule.get("end_frame", float("inf")):
                        continue
                    polygon = np.array([[x*width,y*height] for x,y in rule["polygon"]], dtype=np.float32)
                    if not cv2.isContourConvex(polygon):
                        raise ValueError("Output exclusion polygon must be convex")
                    overlap, _ = cv2.intersectConvexConvex(box, polygon)
                    if overlap / area >= rule.get("min_box_overlap", .6):
                        reject = True
                        break
            (rejected if reject else kept).append(obj)
        return kept, rejected
