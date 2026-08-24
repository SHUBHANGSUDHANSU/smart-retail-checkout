"""Train a small grocery detector without changing the webcam application."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import torch
import yaml
from ultralytics import YOLO

from smart_retail.infrastructure.logging_config import EventFormatter, log_event

TRAINING_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TRAINING_DIR.parent
DEFAULT_DATA_CONFIG = TRAINING_DIR / "data.yaml"
DEFAULT_RUNS_DIR = TRAINING_DIR / "runs"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
LOGGER = logging.getLogger(__name__)


def select_training_device(requested_device: str) -> str:
    """Resolve ``auto`` to Apple MPS when available, otherwise CPU."""
    if requested_device != "auto":
        return requested_device

    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_built() and mps.is_available():
        return "mps"
    return "cpu"


def resolve_split_path(
    data_config: Path,
    dataset_root: str | None,
    split_path: str,
) -> Path:
    """Resolve a local YOLO split path for an early layout check."""
    root = data_config.parent
    if dataset_root:
        configured_root = Path(dataset_root).expanduser()
        root = (
            configured_root
            if configured_root.is_absolute()
            else (data_config.parent / configured_root)
        )
    split = Path(split_path).expanduser()
    return (split if split.is_absolute() else root / split).resolve()


def validate_dataset_layout(data_config: Path) -> None:
    """Fail early with a useful message when required image splits are absent."""
    if not data_config.is_file():
        raise ValueError(f"Dataset configuration does not exist: {data_config}")

    with data_config.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}

    if not isinstance(config, dict):
        raise ValueError(f"Dataset configuration must be a YAML mapping: {data_config}")
    if not config.get("names"):
        raise ValueError("Dataset configuration must define at least one class name.")

    missing_splits: list[str] = []
    empty_splits: list[str] = []
    for split_name in ("train", "val"):
        configured_split = config.get(split_name)
        if not isinstance(configured_split, str):
            missing_splits.append(f"{split_name} (not configured)")
            continue

        split_path = resolve_split_path(
            data_config,
            config.get("path"),
            configured_split,
        )
        if not split_path.is_dir():
            missing_splits.append(f"{split_name} ({split_path})")
            continue
        if not any(
            file_path.suffix.lower() in IMAGE_EXTENSIONS
            for file_path in split_path.iterdir()
            if file_path.is_file()
        ):
            empty_splits.append(f"{split_name} ({split_path})")

    if missing_splits:
        details = ", ".join(missing_splits)
        raise ValueError(
            "Dataset image directories are missing: "
            f"{details}. Follow training/README.md before training."
        )
    if empty_splits:
        details = ", ".join(empty_splits)
        raise ValueError(f"Dataset image directories contain no images: {details}")


def parse_args() -> argparse.Namespace:
    """Parse intentionally small, interview-friendly training options."""
    parser = argparse.ArgumentParser(
        description="Fine-tune YOLOv8n on a local grocery-product dataset."
    )
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_CONFIG)
    parser.add_argument("--weights", default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument(
        "--device",
        choices=("auto", "mps", "cpu"),
        default="auto",
        help="auto prefers Apple MPS and otherwise uses CPU",
    )
    parser.add_argument("--name", default="grocery_yolov8n")
    return parser.parse_args()


def main() -> int:
    """Validate the dataset and start an explicitly requested training run."""
    logging.basicConfig(
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
        force=True,
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(
            EventFormatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    args = parse_args()
    data_config = args.data.expanduser().resolve()

    try:
        validate_dataset_layout(data_config)
    except (OSError, ValueError, yaml.YAMLError) as error:
        log_event(
            LOGGER,
            logging.ERROR,
            "training_dataset_invalid",
            "Training dataset validation failed",
            reason=str(error),
        )
        return 1

    device = select_training_device(args.device)
    log_event(
        LOGGER,
        logging.INFO,
        "training_started",
        "Custom detector training started",
        starting_weights=Path(args.weights).name,
        dataset=data_config.name,
        device=device,
        epochs=args.epochs,
        image_size=args.image_size,
        batch_size=args.batch,
    )

    model = YOLO(args.weights)
    model.train(
        data=str(data_config),
        epochs=args.epochs,
        imgsz=args.image_size,
        batch=args.batch,
        device=device,
        workers=args.workers,
        patience=args.patience,
        pretrained=True,
        seed=42,
        project=str(DEFAULT_RUNS_DIR),
        name=args.name,
    )

    trainer = getattr(model, "trainer", None)
    best_weights = getattr(
        trainer,
        "best",
        DEFAULT_RUNS_DIR / args.name / "weights" / "best.pt",
    )
    log_event(
        LOGGER,
        logging.INFO,
        "training_completed",
        "Custom detector training completed",
        best_checkpoint=Path(str(best_weights)).name,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
