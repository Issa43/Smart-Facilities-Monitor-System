"""
File locations -- DEPLOYMENT copy.

This is the only file that differs between the two copies of the pipeline:
this one reads every path from an environment variable, so a Docker container
or the backend can point the pipeline at mounted weights, inputs and output
folders without editing code. A variable left unset falls back to a location
inside this folder, which is what a plain `python Main.py` uses.
Every other file is shared with the local test copy unchanged.

    variable                  what                                  default
    ALPR_MODEL_PATH           fine-tuned plate detector weights     ./best.pt
    ALPR_VEHICLE_MODEL_PATH   COCO vehicle model                    yolo26n.pt (downloaded on first use)
    ALPR_INPUT_PATH           a video, a photo, or a folder of both ./VID_sample.mp4
    ALPR_OUTPUT_PATH          annotated video for a single video    ./output_fast.mp4
    ALPR_OUTPUT_DIR           annotated files for photos / folders  ./outputs
    ALPR_DEBUG_DIR            saved plate crops                     ./debug_plates
"""
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent


def _path(variable, default):
    value = os.environ.get(variable)
    return Path(value) if value else default


MODEL_PATH = _path("ALPR_MODEL_PATH", PROJECT_DIR / "best.pt")

# A bare file name lets Ultralytics download the weights on first use.
VEHICLE_MODEL_PATH = os.environ.get("ALPR_VEHICLE_MODEL_PATH") or "yolo26n.pt"

INPUT_PATH = _path("ALPR_INPUT_PATH", PROJECT_DIR / "VID_sample.mp4")

OUTPUT_PATH = _path("ALPR_OUTPUT_PATH", PROJECT_DIR / "output_fast.mp4")
OUTPUT_DIR = _path("ALPR_OUTPUT_DIR", PROJECT_DIR / "outputs")

DEBUG_FOLDER = _path("ALPR_DEBUG_DIR", PROJECT_DIR / "debug_plates")
