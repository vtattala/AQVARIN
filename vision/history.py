"""Bounded trajectory and pixel-motion calculation."""
from collections import defaultdict, deque
from math import atan2, degrees, hypot

from .models import Detection, MotionState, TrackedObject, TrackPoint


class TrackHistory:
    def __init__(self, limit: int = 300, rolling_points: int = 10):
        if limit < 2 or rolling_points < 2:
            raise ValueError("History limits must be at least 2")
        self._points: dict[int, deque[TrackPoint]] = defaultdict(lambda: deque(maxlen=limit))
        self._first_frame: dict[int, int] = {}
        self._last_frame: dict[int, int] = {}
        self._consecutive: dict[int, int] = {}
        self.rolling_points = rolling_points

    def update(self, track_id: int, detection: Detection, frame: int, timestamp_s: float) -> TrackedObject:
        previous_frame = self._last_frame.get(track_id)
        if previous_frame is not None and frame <= previous_frame:
            raise ValueError(f"Track {track_id} received a non-increasing frame number")
        self._first_frame.setdefault(track_id, frame)
        consecutive = self._consecutive.get(track_id, 0) + 1 if previous_frame == frame - 1 else 1
        self._consecutive[track_id] = consecutive
        self._last_frame[track_id] = frame
        cx, cy = detection.center
        points = self._points[track_id]
        points.append(TrackPoint(frame, timestamp_s, cx, cy))
        motion = self._motion(points)
        return TrackedObject(track_id, detection, motion, frame - self._first_frame[track_id] + 1,
                             consecutive, 0 if previous_frame is None else frame - previous_frame - 1,
                             tuple(points))

    def points(self, track_id: int) -> tuple[TrackPoint, ...]:
        return tuple(self._points.get(track_id, ()))

    def _motion(self, points: deque[TrackPoint]) -> MotionState:
        if len(points) < 2:
            return MotionState()
        a, b = points[-2], points[-1]
        dt = b.timestamp_s - a.timestamp_s
        dx, dy = b.x_px - a.x_px, b.y_px - a.y_px
        velocity = (dx / dt, dy / dt) if dt > 0 else (0.0, 0.0)
        start = points[-min(len(points), self.rolling_points)]
        rolling_dt = b.timestamp_s - start.timestamp_s
        rolling = ((b.x_px - start.x_px) / rolling_dt, (b.y_px - start.y_px) / rolling_dt) if rolling_dt > 0 else (0.0, 0.0)
        speed = hypot(*velocity)
        return MotionState(hypot(dx, dy), velocity, rolling, speed,
                           degrees(atan2(velocity[1], velocity[0])) if speed else None)
