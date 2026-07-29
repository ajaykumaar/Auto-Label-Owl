"""OwlViT-based image labeling for YOLO format."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import cv2
import torch
import yaml
from torchvision.ops import nms
from transformers import OwlViTForObjectDetection, OwlViTProcessor

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

ProgressCallback = Callable[[dict], None]


@dataclass
class ClassSpec:
    """A YOLO class with its OwlViT detection prompt."""

    name: str
    prompt: str

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.prompt = (self.prompt or self.name).strip()
        if not self.name:
            raise ValueError("Class name cannot be empty")
        if not self.prompt:
            raise ValueError("Detection prompt cannot be empty")


@dataclass
class LabelingConfig:
    image_folder: Path
    output_root: Path
    classes: list[ClassSpec]
    confidence_threshold: float = 0.15
    nms_iou_threshold: float = 0.4
    apply_nms: bool = True

    @property
    def images_dir(self) -> Path:
        return self.output_root / "images"

    @property
    def labels_dir(self) -> Path:
        return self.output_root / "labels"

    @property
    def no_labels_dir(self) -> Path:
        return self.output_root / "images_with_no_labels"

    @property
    def previews_dir(self) -> Path:
        return self.output_root / "previews"


@dataclass
class LabelingResult:
    total: int = 0
    labeled: int = 0
    unlabeled: int = 0
    errors: list[str] = field(default_factory=list)


class OwlLabeler:
    """Loads OwlViT once and runs batch labeling jobs."""

    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir)
        self.processor: Optional[OwlViTProcessor] = None
        self.model: Optional[OwlViTForObjectDetection] = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def load(self) -> None:
        if not self.model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {self.model_dir}")
        self.processor = OwlViTProcessor.from_pretrained(str(self.model_dir), use_fast=False)
        self.model = OwlViTForObjectDetection.from_pretrained(str(self.model_dir))
        self.model.to(self.device)
        self.model.eval()

    @property
    def ready(self) -> bool:
        return self.processor is not None and self.model is not None

    def _detect(self, image_bgr, prompts: list[str], threshold: float, nms_iou: float, apply_nms_flag: bool):
        assert self.processor is not None and self.model is not None
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        inputs = self.processor(text=[prompts], images=image_rgb, return_tensors="pt")
        inputs = {k: v.to(self.device) if hasattr(v, "to") else v for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)

        target_sizes = torch.tensor([image_bgr.shape[:2]], device=self.device)
        results = self.processor.post_process_object_detection(
            outputs=outputs,
            threshold=threshold,
            target_sizes=target_sizes,
        )[0]

        boxes = results["boxes"]
        scores = results["scores"]
        labels = results["labels"]

        if apply_nms_flag and len(boxes) > 0:
            keep = nms(boxes, scores, nms_iou)
            boxes = boxes[keep]
            scores = scores[keep]
            labels = labels[keep]

        return boxes, scores, labels

    def run(self, config: LabelingConfig, on_progress: Optional[ProgressCallback] = None) -> LabelingResult:
        if not self.ready:
            raise RuntimeError("Model is not loaded")

        for d in (
            config.images_dir,
            config.labels_dir,
            config.no_labels_dir,
            config.previews_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

        image_folder = Path(config.image_folder)
        if not image_folder.is_dir():
            raise FileNotFoundError(f"Image folder not found: {image_folder}")

        image_files = sorted(
            f for f in image_folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
        )

        result = LabelingResult(total=len(image_files))
        prompts = [c.prompt for c in config.classes]
        class_names = [c.name for c in config.classes]

        if on_progress:
            on_progress({"type": "start", "total": result.total, "classes": class_names})

        if result.total == 0:
            self._write_metadata(config)
            if on_progress:
                on_progress(
                    {
                        "type": "complete",
                        "total": 0,
                        "labeled": 0,
                        "unlabeled": 0,
                    }
                )
            return result

        for idx, img_path in enumerate(image_files, start=1):
            event: dict = {
                "type": "progress",
                "current": idx,
                "total": result.total,
                "filename": img_path.name,
            }
            try:
                img = cv2.imread(str(img_path))
                if img is None:
                    msg = f"Could not read {img_path.name}"
                    result.errors.append(msg)
                    event.update({"status": "error", "message": msg})
                    if on_progress:
                        on_progress(event)
                    continue

                boxes, scores, labels = self._detect(
                    img,
                    prompts,
                    config.confidence_threshold,
                    config.nms_iou_threshold,
                    config.apply_nms,
                )

                if len(boxes) < 1:
                    dest = config.no_labels_dir / img_path.name
                    shutil.copy2(img_path, dest)
                    result.unlabeled += 1
                    event.update({"status": "no_label", "detections": 0})
                else:
                    bbox = boxes.detach().cpu().numpy()
                    label_ids = labels.detach().cpu().numpy()
                    score_vals = scores.detach().cpu().numpy()

                    img_h, img_w = img.shape[:2]
                    preview = img.copy()
                    label_lines: list[str] = []

                    for box, label_id, score in zip(bbox, label_ids, score_vals):
                        class_id = int(label_id)
                        if class_id < 0 or class_id >= len(config.classes):
                            continue

                        x_min, y_min, x_max, y_max = box
                        x_center = (x_min + x_max) / 2 / img_w
                        y_center = (y_min + y_max) / 2 / img_h
                        width = (x_max - x_min) / img_w
                        height = (y_max - y_min) / img_h

                        label_lines.append(
                            f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
                        )

                        pt1 = (int(x_min), int(y_min))
                        pt2 = (int(x_max), int(y_max))
                        cv2.rectangle(preview, pt1, pt2, (34, 139, 34), 2)
                        label_text = f"{config.classes[class_id].name}: {score:.2f}"
                        cv2.putText(
                            preview,
                            label_text,
                            (int(x_min), max(20, int(y_min) - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.55,
                            (34, 139, 34),
                            2,
                        )

                    if not label_lines:
                        dest = config.no_labels_dir / img_path.name
                        shutil.copy2(img_path, dest)
                        result.unlabeled += 1
                        event.update({"status": "no_label", "detections": 0})
                    else:
                        shutil.copy2(img_path, config.images_dir / img_path.name)
                        label_path = config.labels_dir / f"{img_path.stem}.txt"
                        label_path.write_text("\n".join(label_lines) + "\n", encoding="utf-8")

                        preview_name = f"{img_path.stem}_preview.jpg"
                        preview_path = config.previews_dir / preview_name
                        cv2.imwrite(str(preview_path), preview)

                        result.labeled += 1
                        event.update(
                            {
                                "status": "labeled",
                                "detections": len(label_lines),
                                "preview_url": f"/api/preview/{preview_name}",
                            }
                        )

            except Exception as exc:  # noqa: BLE001 — surface per-image failures to UI
                msg = f"{img_path.name}: {exc}"
                result.errors.append(msg)
                event.update({"status": "error", "message": msg})

            if on_progress:
                on_progress(event)

        self._write_metadata(config)

        if on_progress:
            on_progress(
                {
                    "type": "complete",
                    "total": result.total,
                    "labeled": result.labeled,
                    "unlabeled": result.unlabeled,
                    "errors": result.errors,
                }
            )
        return result

    def _write_metadata(self, config: LabelingConfig) -> None:
        names = [c.name for c in config.classes]
        classes_path = config.output_root / "classes.txt"
        classes_path.write_text("\n".join(names) + ("\n" if names else ""), encoding="utf-8")

        # Paths relative to this data.yaml location (never embed absolute host paths)
        data_yaml = {
            "path": ".",
            "train": "images",
            "val": "images",
            "nc": len(names),
            "names": {i: name for i, name in enumerate(names)},
        }
        yaml_path = config.output_root / "data.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data_yaml, f, sort_keys=False, default_flow_style=False)
