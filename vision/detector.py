"""Real maritime detections from full frames or SAHI sliced inference."""
import logging
import shutil
import tempfile
from pathlib import Path
from time import perf_counter

from .config import PipelineConfig
from .models import Detection

LOG = logging.getLogger(__name__)
ALLOWED_CLASSES = {"swimmer", "boat", "jetski", "jet ski", "buoy",
                   "life_saving_appliances", "life-saving appliance", "floater"}


class MaritimeDetector:
    def __init__(self, config: PipelineConfig):
        config.validate()
        try:
            import torch
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("Install Python dependencies from requirements.txt") from exc
        self.config = config
        if config.device == "auto":
            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        elif config.device.startswith("cuda") and not torch.cuda.is_available():
            LOG.warning("CUDA requested but unavailable; falling back to CPU")
            self.device = "cpu"
        else:
            self.device = config.device
        self._temporary_weights = None
        model_path = config.weights
        # Ultralytics strips apostrophes from paths; this user's workspace has one.
        if "'" in str(model_path):
            self._temporary_weights = tempfile.TemporaryDirectory(prefix="aegis-weights-")
            copied = Path(self._temporary_weights.name) / model_path.name
            shutil.copy2(model_path, copied)
            model_path = copied
        try:
            self.model = YOLO(str(model_path))
        except Exception as exc:
            raise RuntimeError(f"Cannot load compatible YOLO weights: {config.weights}") from exc
        self.class_names = {int(k): str(v) for k, v in self.model.names.items()}
        self.enabled_ids = [i for i, name in self.class_names.items() if name.lower() in ALLOWED_CLASSES]
        if not self.enabled_ids:
            raise ValueError(f"Weights have no supported maritime classes: {self.class_names}")
        self.sahi_model = None
        if config.detection_mode == "sliced":
            try:
                from sahi.models.ultralytics import UltralyticsDetectionModel
            except ImportError as exc:
                raise RuntimeError("SAHI is missing; install requirements.txt") from exc
            self.sahi_model = UltralyticsDetectionModel(
                model=self.model, device=self.device, confidence_threshold=config.confidence,
                image_size=config.image_size, load_at_init=False,
            )
            self.sahi_model.set_model(self.model)
        LOG.info("Detector loaded: %s; device=%s; mode=%s; classes=%s", config.weights,
                 self.device, config.detection_mode, self.class_names)

    def detect(self, frame) -> tuple[list[Detection], float]:
        if self.config.detection_mode == "sliced":
            return self._detect_sliced(frame)
        start = perf_counter()
        result = self.model.predict(frame, conf=self.config.confidence, iou=self.config.iou,
                                    imgsz=self.config.image_size, device=self.device,
                                    classes=self.enabled_ids, verbose=False)[0]
        detections = [Detection(int(box.cls.item()), self.class_names[int(box.cls.item())],
                                float(box.conf.item()), tuple(float(v) for v in box.xyxy[0].tolist()))
                      for box in result.boxes]
        return detections, (perf_counter() - start) * 1000

    def _detect_sliced(self, frame) -> tuple[list[Detection], float]:
        import cv2
        from sahi.predict import get_sliced_prediction

        start = perf_counter()
        result = get_sliced_prediction(
            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), self.sahi_model,
            slice_height=self.config.slice_size, slice_width=self.config.slice_size,
            overlap_height_ratio=self.config.slice_overlap,
            overlap_width_ratio=self.config.slice_overlap,
            perform_standard_pred=self.config.standard_prediction,
            postprocess_type="GREEDYNMM", postprocess_match_metric="IOS",
            postprocess_match_threshold=0.5, verbose=0,
        )
        detections = []
        for item in result.object_prediction_list:
            class_id = int(item.category.id)
            if class_id not in self.enabled_ids:
                continue
            detections.append(Detection(class_id, self.class_names[class_id], float(item.score.value),
                                        tuple(float(v) for v in item.bbox.to_xyxy())))
        return detections, (perf_counter() - start) * 1000
