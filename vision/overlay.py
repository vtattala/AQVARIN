"""Render track boxes and trails without changing inference records."""
from .models import TrackedObject


def draw_tracks(frame, objects: list[TrackedObject]):
    import cv2

    for obj in objects:
        x1, y1, x2, y2 = (round(v) for v in obj.detection.bbox_xyxy)
        color = (44, 206, 126) if obj.detection.class_name == "swimmer" else (255, 190, 50)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{obj.detection.class_name.title()} #{obj.track_id} | {obj.detection.confidence:.2f}"
        cv2.putText(frame, label, (x1, max(16, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        trail = [(round(p.x_px), round(p.y_px)) for p in obj.trail]
        for a, b in zip(trail, trail[1:]):
            cv2.line(frame, a, b, color, 2)
    return frame
