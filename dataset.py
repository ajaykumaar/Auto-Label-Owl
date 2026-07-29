"""Dataset listing, annotation I/O, finalize, and download helpers."""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path
from typing import Any

import cv2
import yaml

from labeling import IMAGE_EXTENSIONS

CLASS_COLORS = [
    "#e11d48",
    "#2563eb",
    "#16a34a",
    "#ca8a04",
    "#9333ea",
    "#0891b2",
    "#ea580c",
    "#4f46e5",
    "#db2777",
    "#059669",
    "#7c3aed",
    "#0d9488",
]


def list_dir_files(folder: Path, extensions: set[str] | None = None) -> list[str]:
    if not folder.is_dir():
        return []
    files = []
    for p in sorted(folder.iterdir()):
        if not p.is_file():
            continue
        if extensions is not None and p.suffix.lower() not in extensions:
            continue
        files.append(p.name)
    return files


def read_classes(output_root: Path) -> list[str]:
    classes_path = output_root / "classes.txt"
    if classes_path.is_file():
        names = [ln.strip() for ln in classes_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if names:
            return names

    yaml_path = output_root / "data.yaml"
    if yaml_path.is_file():
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        names = data.get("names")
        if isinstance(names, dict):
            return [names[k] for k in sorted(names, key=lambda x: int(x))]
        if isinstance(names, list):
            return list(names)
    return []


def write_metadata(output_root: Path, class_names: list[str]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    classes_path = output_root / "classes.txt"
    classes_path.write_text("\n".join(class_names) + ("\n" if class_names else ""), encoding="utf-8")

    # Use "." so data.yaml never embeds a machine-specific absolute path
    data_yaml = {
        "path": ".",
        "train": "images",
        "val": "images",
        "nc": len(class_names),
        "names": {i: name for i, name in enumerate(class_names)},
    }
    with open(output_root / "data.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data_yaml, f, sort_keys=False, default_flow_style=False)


def parse_yolo_label(label_path: Path) -> list[dict[str, float]]:
    boxes: list[dict[str, float]] = []
    if not label_path.is_file():
        return boxes
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            continue
        class_id, xc, yc, w, h = map(float, parts)
        boxes.append(
            {
                "class_id": int(class_id),
                "x_center": xc,
                "y_center": yc,
                "width": w,
                "height": h,
            }
        )
    return boxes


def yolo_to_xyxy(box: dict[str, float], img_w: int, img_h: int) -> dict[str, float]:
    xc, yc, w, h = box["x_center"], box["y_center"], box["width"], box["height"]
    bw, bh = w * img_w, h * img_h
    x1 = (xc * img_w) - bw / 2
    y1 = (yc * img_h) - bh / 2
    x2 = x1 + bw
    y2 = y1 + bh
    return {
        "class_id": int(box["class_id"]),
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
    }


def xyxy_to_yolo(box: dict[str, Any], img_w: int, img_h: int) -> str:
    x1, y1, x2, y2 = float(box["x1"]), float(box["y1"]), float(box["x2"]), float(box["y2"])
    x1, x2 = sorted((max(0.0, x1), min(float(img_w), x2)))
    y1, y2 = sorted((max(0.0, y1), min(float(img_h), y2)))
    bw = max(x2 - x1, 1.0)
    bh = max(y2 - y1, 1.0)
    xc = (x1 + x2) / 2 / img_w
    yc = (y1 + y2) / 2 / img_h
    ww = bw / img_w
    hh = bh / img_h
    class_id = int(box["class_id"])
    return f"{class_id} {xc:.6f} {yc:.6f} {ww:.6f} {hh:.6f}"


def display_relpath(path: Path, depth: int = 2) -> str:
    """Return a short relative-looking path (no absolute / home username)."""
    parts = Path(path).resolve().parts
    if len(parts) >= depth:
        return "/".join(parts[-depth:])
    return Path(path).name


def dataset_listing(output_root: Path) -> dict[str, Any]:
    images_dir = output_root / "images"
    labels_dir = output_root / "labels"
    no_labels_dir = output_root / "images_with_no_labels"
    return {
        "root": display_relpath(output_root, depth=2),
        "images": list_dir_files(images_dir, IMAGE_EXTENSIONS),
        "labels": list_dir_files(labels_dir, {".txt"}),
        "images_with_no_labels": list_dir_files(no_labels_dir, IMAGE_EXTENSIONS),
        "has_classes": (output_root / "classes.txt").is_file() or (output_root / "data.yaml").is_file(),
        "has_content": False,
    }


def enrich_listing(listing: dict[str, Any]) -> dict[str, Any]:
    listing["has_content"] = bool(
        listing["images"] or listing["labels"] or listing["images_with_no_labels"]
    )
    return listing


def build_review_session(output_root: Path) -> dict[str, Any]:
    class_names = read_classes(output_root)
    classes = [
        {"id": i, "name": name, "color": CLASS_COLORS[i % len(CLASS_COLORS)]}
        for i, name in enumerate(class_names)
    ]

    items: list[dict[str, Any]] = []
    images_dir = output_root / "images"
    no_labels_dir = output_root / "images_with_no_labels"
    labels_dir = output_root / "labels"

    for source, folder in (("images", images_dir), ("images_with_no_labels", no_labels_dir)):
        if not folder.is_dir():
            continue
        for name in list_dir_files(folder, IMAGE_EXTENSIONS):
            path = folder / name
            img = cv2.imread(str(path))
            if img is None:
                continue
            h, w = img.shape[:2]
            boxes_xyxy: list[dict[str, Any]] = []
            if source == "images":
                for yolo_box in parse_yolo_label(labels_dir / f"{Path(name).stem}.txt"):
                    boxes_xyxy.append(yolo_to_xyxy(yolo_box, w, h))
            items.append(
                {
                    "filename": name,
                    "source": source,
                    "width": w,
                    "height": h,
                    "boxes": boxes_xyxy,
                    "image_url": f"/api/dataset/file/{source}/{name}",
                }
            )

    items.sort(key=lambda x: x["filename"].lower())
    return {
        "classes": classes,
        "images": items,
        "root": display_relpath(output_root, depth=2),
    }


def collect_overwrite_targets(
    output_root: Path,
    annotations: list[dict[str, Any]],
) -> list[str]:
    """Return relative paths that already exist and would be overwritten."""
    targets: list[str] = []
    images_dir = output_root / "images"
    labels_dir = output_root / "labels"

    for item in annotations:
        filename = item["filename"]
        source = item.get("source", "images")
        boxes = item.get("boxes") or []
        stem = Path(filename).stem

        if source == "images":
            img_path = images_dir / filename
            label_path = labels_dir / f"{stem}.txt"
            if img_path.is_file():
                targets.append(f"images/{filename}")
            if label_path.is_file():
                targets.append(f"labels/{stem}.txt")
        elif source == "images_with_no_labels" and boxes:
            # Moving into images/ — overwrite if destination already exists
            if (images_dir / filename).is_file():
                targets.append(f"images/{filename}")
            if (labels_dir / f"{stem}.txt").is_file():
                targets.append(f"labels/{stem}.txt")

    # Metadata always rewritten if present
    if (output_root / "classes.txt").is_file():
        targets.append("classes.txt")
    if (output_root / "data.yaml").is_file():
        targets.append("data.yaml")

    # Unique, stable order
    seen = set()
    ordered = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def finalize_review(
    output_root: Path,
    class_names: list[str],
    annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write labels, move newly labeled images, refresh metadata."""
    images_dir = output_root / "images"
    labels_dir = output_root / "labels"
    no_labels_dir = output_root / "images_with_no_labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    no_labels_dir.mkdir(parents=True, exist_ok=True)

    moved = 0
    written_labels = 0
    still_unlabeled = 0

    for item in annotations:
        filename = item["filename"]
        source = item.get("source", "images")
        boxes = item.get("boxes") or []
        img_w = int(item.get("width") or 0)
        img_h = int(item.get("height") or 0)
        stem = Path(filename).stem

        if source == "images_with_no_labels":
            src_path = no_labels_dir / filename
            if boxes:
                if not src_path.is_file():
                    # Already moved in a prior finalize attempt
                    src_path = images_dir / filename
                if src_path.is_file() and src_path.parent == no_labels_dir:
                    shutil.move(str(src_path), str(images_dir / filename))
                    moved += 1
                if img_w <= 0 or img_h <= 0:
                    img = cv2.imread(str(images_dir / filename))
                    if img is not None:
                        img_h, img_w = img.shape[:2]
                lines = [xyxy_to_yolo(b, img_w, img_h) for b in boxes]
                (labels_dir / f"{stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
                written_labels += 1
            else:
                still_unlabeled += 1
        else:
            # Labeled (or was labeled)
            img_path = images_dir / filename
            if img_w <= 0 or img_h <= 0:
                img = cv2.imread(str(img_path))
                if img is not None:
                    img_h, img_w = img.shape[:2]

            if boxes:
                lines = [xyxy_to_yolo(b, img_w, img_h) for b in boxes]
                (labels_dir / f"{stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
                written_labels += 1
            else:
                # All boxes deleted → move to no_labels and remove label file
                label_path = labels_dir / f"{stem}.txt"
                if label_path.is_file():
                    label_path.unlink()
                if img_path.is_file():
                    dest = no_labels_dir / filename
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(img_path), str(dest))
                    still_unlabeled += 1

    write_metadata(output_root, class_names)
    return {
        "moved": moved,
        "written_labels": written_labels,
        "still_unlabeled": still_unlabeled,
        "classes": class_names,
    }


def build_download_zip(output_root: Path, selections: dict[str, bool]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if selections.get("images"):
            folder = output_root / "images"
            for name in list_dir_files(folder, IMAGE_EXTENSIONS):
                zf.write(folder / name, arcname=f"images/{name}")

        if selections.get("labels"):
            folder = output_root / "labels"
            for name in list_dir_files(folder, {".txt"}):
                zf.write(folder / name, arcname=f"labels/{name}")

        if selections.get("images_with_no_labels"):
            folder = output_root / "images_with_no_labels"
            for name in list_dir_files(folder, IMAGE_EXTENSIONS):
                zf.write(folder / name, arcname=f"images_with_no_labels/{name}")

        if selections.get("classes_txt"):
            path = output_root / "classes.txt"
            if path.is_file():
                zf.write(path, arcname="classes.txt")

        if selections.get("data_yaml"):
            path = output_root / "data.yaml"
            if path.is_file():
                zf.write(path, arcname="data.yaml")

    return buf.getvalue()
