"""Flask webapp for OwlViT → YOLO auto-labeling and manual review."""

from __future__ import annotations

import io
import json
import queue
import threading
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file, send_from_directory

from dataset import (
    build_download_zip,
    build_review_session,
    collect_overwrite_targets,
    dataset_listing,
    enrich_listing,
    finalize_review,
)
from labeling import ClassSpec, LabelingConfig, OwlLabeler

APP_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = APP_DIR / "data" / "images_to_be_labelled"
DEFAULT_OUTPUT = APP_DIR / "data" / "images_and_labels"


def _resolve_model_dir() -> Path:
    """Prefer ./local_owlvit; fall back to ../local_owlvit for legacy layouts."""
    candidates = [
        APP_DIR / "local_owlvit",
        APP_DIR.parent / "local_owlvit",
    ]
    for path in candidates:
        if (path / "config.json").is_file():
            return path
    return candidates[0]


MODEL_DIR = _resolve_model_dir()

app = Flask(__name__)
labeler = OwlLabeler(MODEL_DIR)

_job_lock = threading.Lock()
_job_running = False
_event_queue: queue.Queue = queue.Queue()


def _emit(event: dict) -> None:
    _event_queue.put(event)


def _ui_path(path: Path) -> str:
    """Path relative to the app directory for UI/API (no absolute host paths)."""
    try:
        return str(path.resolve().relative_to(APP_DIR.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


@app.route("/")
def index():
    return render_template(
        "index.html",
        default_input=_ui_path(DEFAULT_INPUT),
        model_ready=labeler.ready,
        device=str(labeler.device),
        output_root=_ui_path(DEFAULT_OUTPUT),
    )


@app.route("/review")
def review_page():
    return render_template("review.html", output_root=_ui_path(DEFAULT_OUTPUT))


@app.route("/api/status")
def status():
    listing = enrich_listing(dataset_listing(DEFAULT_OUTPUT))
    return jsonify(
        {
            "model_ready": labeler.ready,
            "device": str(labeler.device),
            "job_running": _job_running,
            "default_input": _ui_path(DEFAULT_INPUT),
            "default_output": _ui_path(DEFAULT_OUTPUT),
            "has_dataset": listing["has_content"],
        }
    )


@app.route("/api/dataset")
def api_dataset():
    return jsonify(enrich_listing(dataset_listing(DEFAULT_OUTPUT)))


@app.route("/api/dataset/file/<source>/<path:filename>")
def dataset_file(source: str, filename: str):
    if source not in ("images", "images_with_no_labels", "previews"):
        return jsonify({"error": "Invalid source"}), 400
    folder = DEFAULT_OUTPUT / source
    return send_from_directory(folder, filename)


@app.route("/api/preview/<path:filename>")
def preview(filename: str):
    return send_from_directory(DEFAULT_OUTPUT / "previews", filename)


@app.route("/api/review/session")
def review_session():
    session = build_review_session(DEFAULT_OUTPUT)
    if not session["images"] and not session["classes"]:
        return jsonify({"error": "No labeled dataset found. Run labeling first."}), 404
    return jsonify(session)


@app.route("/api/review/finish", methods=["POST"])
def review_finish():
    data = request.get_json(force=True, silent=True) or {}
    class_names = data.get("classes") or []
    annotations = data.get("annotations") or []
    overwrite = bool(data.get("overwrite", False))
    always_overwrite = bool(data.get("always_overwrite", False))

    if not class_names:
        return jsonify({"error": "Class names are required."}), 400
    if any(not str(n).strip() for n in class_names):
        return jsonify({"error": "Class names cannot be empty."}), 400

    class_names = [str(n).strip() for n in class_names]

    conflicts = collect_overwrite_targets(DEFAULT_OUTPUT, annotations)
    if conflicts and not overwrite and not always_overwrite:
        return jsonify(
            {
                "needs_overwrite_confirm": True,
                "files": conflicts,
                "message": "Some files already exist and will be overwritten.",
            }
        )

    result = finalize_review(DEFAULT_OUTPUT, class_names, annotations)
    listing = enrich_listing(dataset_listing(DEFAULT_OUTPUT))
    return jsonify({"ok": True, "result": result, "dataset": listing})


@app.route("/api/review/download", methods=["POST"])
def review_download():
    data = request.get_json(force=True, silent=True) or {}
    selections = {
        "images": bool(data.get("images", True)),
        "labels": bool(data.get("labels", True)),
        "classes_txt": bool(data.get("classes_txt", True)),
        "data_yaml": bool(data.get("data_yaml", True)),
        "images_with_no_labels": bool(data.get("images_with_no_labels", False)),
    }
    if not any(selections.values()):
        return jsonify({"error": "Select at least one item to download."}), 400

    payload = build_download_zip(DEFAULT_OUTPUT, selections)
    return send_file(
        path_or_file=io.BytesIO(payload),
        mimetype="application/zip",
        as_attachment=True,
        download_name="images_and_labels.zip",
    )


@app.route("/api/start", methods=["POST"])
def start_labeling():
    global _job_running

    data = request.get_json(force=True, silent=True) or {}

    image_folder = Path(data.get("image_folder") or DEFAULT_INPUT).expanduser()
    if not image_folder.is_absolute():
        image_folder = (APP_DIR / image_folder).resolve()
    else:
        image_folder = image_folder.resolve()

    raw_classes = data.get("classes") or []
    if not raw_classes:
        return jsonify({"error": "Add at least one class (name + prompt)."}), 400

    try:
        classes = [
            ClassSpec(name=c.get("name", ""), prompt=c.get("prompt", ""))
            for c in raw_classes
        ]
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        confidence = float(data.get("confidence_threshold", 0.15))
        nms_iou = float(data.get("nms_iou_threshold", 0.4))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid threshold values."}), 400

    if not 0.0 <= confidence <= 1.0:
        return jsonify({"error": "Confidence threshold must be between 0 and 1."}), 400
    if not 0.0 <= nms_iou <= 1.0:
        return jsonify({"error": "NMS IoU threshold must be between 0 and 1."}), 400

    apply_nms = bool(data.get("apply_nms", True))

    if not labeler.ready:
        return jsonify({"error": "Model is not loaded yet."}), 503

    if not image_folder.is_dir():
        return jsonify({"error": f"Image folder not found: {_ui_path(image_folder)}"}), 400

    with _job_lock:
        if _job_running:
            return jsonify({"error": "A labeling job is already running."}), 409
        _job_running = True

    while not _event_queue.empty():
        try:
            _event_queue.get_nowait()
        except queue.Empty:
            break

    config = LabelingConfig(
        image_folder=image_folder,
        output_root=DEFAULT_OUTPUT,
        classes=classes,
        confidence_threshold=confidence,
        nms_iou_threshold=nms_iou,
        apply_nms=apply_nms,
    )

    def worker():
        global _job_running
        try:
            labeler.run(config, on_progress=_emit)
        except Exception as exc:  # noqa: BLE001
            _emit({"type": "error", "message": str(exc)})
        finally:
            with _job_lock:
                _job_running = False

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"ok": True, "image_folder": _ui_path(image_folder)})


@app.route("/api/events")
def events():
    def stream():
        while True:
            try:
                event = _event_queue.get(timeout=25)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue

            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") in ("complete", "error"):
                break

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def create_app() -> Flask:
    return app


if __name__ == "__main__":
    print(f"Loading OwlViT from {MODEL_DIR} ...")
    labeler.load()
    print(f"Model ready on {labeler.device}")
    DEFAULT_INPUT.mkdir(parents=True, exist_ok=True)
    for sub in ("images", "labels", "images_with_no_labels", "previews"):
        (DEFAULT_OUTPUT / sub).mkdir(parents=True, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
