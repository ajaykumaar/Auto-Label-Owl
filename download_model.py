#!/usr/bin/env python3
"""Download OwlViT weights into ./local_owlvit for offline use."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# Avoid noisy hub cache warnings when the default cache is not writable
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

DEFAULT_MODEL = "google/owlvit-base-patch32"
APP_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = APP_DIR / "local_owlvit"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download OwlViT for Auto Label")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Hugging Face model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    config = out / "config.json"
    if config.is_file() and (out / "model.safetensors").is_file():
        print(f"Model already present at {out}")
        print("Delete that folder first if you want to re-download.")
        return

    print(f"Downloading {args.model} → {out} …")
    from transformers import OwlViTForObjectDetection, OwlViTProcessor

    processor = OwlViTProcessor.from_pretrained(args.model)
    model = OwlViTForObjectDetection.from_pretrained(args.model)
    processor.save_pretrained(str(out))
    model.save_pretrained(str(out))
    print("Done. You can start the app with: python app.py")


if __name__ == "__main__":
    main()
