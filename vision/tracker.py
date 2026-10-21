"""Tracker association shared by full-frame and SAHI detector modes."""
import logging
from dataclasses import replace
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

from .config import PipelineConfig
from .models import Detection

LOG = logging.getLogger(__name__)


class MaritimeTracker:
    def __init__(self, config: PipelineConfig):
        import ultralytics
        import yaml
        from ultralytics.trackers.bot_sort import BOTSORT
        from ultralytics.trackers.byte_tracker import BYTETracker
        from ultralytics.trackers.deep_oc_sort import DeepOCSORT

        path = Path(ultralytics.__file__).parent / "cfg" / "trackers" / f"{config.tracker}.yaml"
        options = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name in ("track_high_thresh", "track_low_thresh", "new_track_thresh", "track_buffer", "gmc_method"):
            value = getattr(config, name)
            if value is not None:
                options[name] = value
        if config.reid_model is not None:
            options["with_reid"] = True
            options["model"] = str(config.reid_model)
        self.engine = {"botsort": BOTSORT, "bytetrack": BYTETracker, "deepocsort": DeepOCSORT}[config.tracker](
            SimpleNamespace(**options)
        )
        LOG.info("Tracker: %s; GMC=%s; buffer=%s; ReID=%s", config.tracker,
                 options.get("gmc_method", "none"), options["track_buffer"], options.get("with_reid", False))

    def update(self, detections: list[Detection], frame) -> tuple[list[tuple[int, Detection]], float]:
        import numpy as np
        from ultralytics.engine.results import Boxes

        start = perf_counter()
        rows = np.array([[*d.bbox_xyxy, d.confidence, d.class_id] for d in detections], dtype=np.float32)
        boxes = Boxes(rows.reshape(-1, 6), frame.shape[:2])
        tracks = self.engine.update(boxes.cpu().numpy(), frame)
        output = []
        for row in tracks:
            # Tracker output: xyxy, ID, confidence, class, source detection index.
            source = detections[int(row[7])]
            observed = replace(source, confidence=float(row[5]),
                               bbox_xyxy=tuple(float(v) for v in row[:4]))
            output.append((int(row[4]), observed))
        return output, (perf_counter() - start) * 1000
