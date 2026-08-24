# Custom grocery detector training

This optional workflow fine-tunes pretrained YOLOv8 nano weights for a small,
local grocery dataset. It is separate from `app.py` and never runs unless you
explicitly execute `training/train.py`.

## Dataset layout

Create this structure at the project root:

```text
dataset/
├── images/
│   ├── train/
│   └── val/
├── labels/
│   ├── train/
│   └── val/
└── data.yaml          # optional copy; training/data.yaml is used by default
```

The provided `training/data.yaml` points to these directories and defines five
starter classes:

```text
0  water_bottle_500ml
1  coffee_cup
2  juice_carton
3  chips_packet
4  cereal_box
```

Change the names before annotation if your actual products differ. Do not
rename or reorder classes after labels have been created, because each label
stores the numeric class ID.

Every image has a matching `.txt` file under `labels/` with the same relative
path and stem. Each object occupies one line in standard YOLO detection format:

```text
class_id x_center y_center width height
```

Coordinates are normalized from `0.0` to `1.0`. Label every visible instance,
including partially occluded products. Images intentionally containing no
target product may use an empty label file and provide useful negatives.

## Small initial dataset strategy

Start with three visually distinct products, then expand to five after the
pipeline works. A realistic local experiment is 120-200 annotated images per
class: approximately 80% training and 20% validation. For three classes this is
roughly 360-600 images, which is manageable on an Apple Silicon Mac.

Capture short sessions with a webcam or phone, but do not randomly split nearly
identical neighboring video frames between train and validation. Split by
capture session or scene so validation measures generalization rather than
memorization.

For every product, include:

- Plain, cluttered, light, and dark backgrounds.
- Front, side, tilted, and rotated views.
- Daylight, warm indoor light, dim light, and mild glare.
- Clear views and partial hand or product occlusions.
- Close, medium, and far distances.
- Single products, multiple products, and multiple instances of one class.
- A small number of scenes containing no supported product.

Keep validation representative of the intended webcam setup. Aim for at least
20-30 validation images per class. Review bounding boxes carefully; a smaller
clean dataset is generally more useful than a larger inconsistently labeled
one.

## Train locally

Activate the same Python 3.11 environment used by the application:

```bash
cd /path/to/smart-retail-checkout
source .venv/bin/activate
python training/train.py --help
```

Training is not started by setup or by the main application. After the dataset
is present and annotated, explicitly start the small baseline run:

```bash
python training/train.py
```

Defaults are YOLOv8n pretrained weights, 50 epochs, 640-pixel images, batch size
8, patience 10, and a fixed seed. `--device auto` prefers MPS on a supported
Apple Silicon Mac and falls back to CPU when MPS is unavailable. CUDA and a
cloud GPU are not required. CPU training is slower but valid:

```bash
python training/train.py --device cpu --epochs 30 --batch 4
```

If MPS reports an unsupported operation or memory pressure, retry with CPU or a
smaller batch. Training output is written below:

```text
training/runs/grocery_yolov8n/
└── weights/
    ├── best.pt
    └── last.pt
```

Do not judge the model only by training loss. Review validation precision,
recall, mAP, confusion matrix, and predictions on held-out webcam scenes. Add
data for recurring failure conditions before increasing model size.

## Use the custom checkpoint later

Copy the best checkpoint into the ignored local model directory:

```bash
mkdir -p models
cp training/runs/grocery_yolov8n/weights/best.pt models/best.pt
```

Before running it, set `SMART_RETAIL_MODEL_ALLOWED_CLASSES` and update the
product keys in `src/smart_retail/configs/products.json` so they exactly match the names in
`training/data.yaml`. Then select the checkpoint through configuration:

```bash
SMART_RETAIL_MODEL_PATH=models/best.pt \
SMART_RETAIL_MODEL_ALLOWED_CLASSES=water_bottle_500ml,coffee_cup,juice_carton,chips_packet,cereal_box \
python app.py
```

If a configured allowed class is absent from the model, startup stops with a
clear error instead of silently detecting the wrong categories. Keep
`yolov8n.pt` as the default until the custom checkpoint has been validated.
