# Auto-Label-Owl

**Open-source web UI** that turns a folder of images into a **YOLOv8-ready dataset** using a local [OwlViT](https://huggingface.co/google/owlvit-base-patch32) model, with an interactive review editor for fixing boxes by hand.

**Repository:** [github.com/ajaykumaar/Auto-Label-Owl](https://github.com/ajaykumaar/Auto-Label-Owl)

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Stack](https://img.shields.io/badge/stack-Flask%20%7C%20OwlViT%20%7C%20YOLO-informational)

> Single-user **local** tool — not a multi-tenant cloud service.

## Features

- Text-prompt object detection with OwlViT (one or more classes)
- Configurable confidence threshold and NMS (advanced settings)
- Live progress, preview gallery, and output folder listing
- Manual **Review** page: draw / move / resize / delete boxes, color-coded by class
- Exports YOLO labels plus `classes.txt` and `data.yaml`
- Zip download of selected outputs after finalize

## Requirements

- **Python 3.9+** (3.10+ recommended)
- ~1 GB disk for the OwlViT weights
- CPU works; a CUDA GPU makes labeling much faster
- See [pytorch.org](https://pytorch.org/get-started/locally/) if you need a CUDA-specific `torch` / `torchvision` install

## Quick start

```bash
git clone https://github.com/ajaykumaar/Auto-Label-Owl.git
cd Auto-Label-Owl

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python download_model.py           # saves weights to ./local_owlvit

# Put images here
mkdir -p data/images_to_be_labelled
# cp /path/to/your/*.jpg data/images_to_be_labelled/

python app.py
```

Open [http://localhost:5000](http://localhost:5000).

### Model options

```bash
python download_model.py
python download_model.py --model google/owlvit-base-patch32
python download_model.py --out ./local_owlvit
```

Weights are **not** stored in git. The app looks for `./local_owlvit`, then `../local_owlvit`.

## Usage

1. Place images in `data/images_to_be_labelled/` (or override the path in the UI).
2. Add class names and OwlViT prompts (IDs are assigned automatically: 0, 1, 2…).
3. Set confidence (and optional NMS) → **Start labeling**.
4. When finished, click **Review** to correct boxes.
5. **Finish** writes labels, moves newly labeled images out of `images_with_no_labels/`, refreshes metadata, then offers a zip download.

### Outputs

| Path | Contents |
|------|----------|
| `data/images_and_labels/images/` | Images with ≥1 box |
| `data/images_and_labels/labels/` | YOLO `.txt` labels |
| `data/images_and_labels/images_with_no_labels/` | Images with no detections |
| `data/images_and_labels/previews/` | Gallery previews (UI only) |
| `data/images_and_labels/classes.txt` | Class names |
| `data/images_and_labels/data.yaml` | YOLO dataset config |

Label format (normalized):

```text
class_id x_center y_center width height
```

## Project layout

```text
Auto-Label-Owl/
├── app.py                 # Flask server
├── labeling.py            # OwlViT inference → YOLO
├── dataset.py             # Listing, review finalize, zip download
├── download_model.py      # Fetch OwlViT into ./local_owlvit
├── templates/             # HTML
├── static/                # CSS / JS
├── data/                  # Local datasets (gitignored contents)
├── requirements.txt
├── LICENSE
└── CONTRIBUTING.md
```

## Limitations

- Designed for **one user on one machine**
- Detection quality depends on prompts, threshold, and image domain
- Large batches on CPU can be slow
- Classes can be renamed in Review, but not added/removed there (define classes before labeling)

## Attribution

- Detection model: [OwlViT](https://huggingface.co/docs/transformers/model_doc/owlvit) (`google/owlvit-base-patch32`) via [Hugging Face Transformers](https://github.com/huggingface/transformers)
- Label format compatible with [Ultralytics YOLO](https://docs.ultralytics.com/)

Model weights are subject to their upstream license on Hugging Face; this repository’s MIT license covers the application code only.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome at [github.com/ajaykumaar/Auto-Label-Owl](https://github.com/ajaykumaar/Auto-Label-Owl).

## License

[MIT](LICENSE)
