"""Photo-classifier labels and their mapping to MITRA material categories. No torch here.

TrashNet (Thung & Yang, 2016) has 6 photo classes that do not line up 1:1 with
MITRA's 6 material categories:
  cardboard + paper -> paper          glass -> glass          metal -> metal
  plastic -> pet OR hdpe (a photo cannot tell them apart; the collector picks)
  trash   -> no recyclable category
  (no e-waste photos in TrashNet: e-waste is never suggested)
The model is a SUGGESTION the collector confirms; it never sets the material itself.
"""
from pathlib import Path

LABELS = ["paper", "glass", "metal", "plastic", "trash"]

FOLDER_TO_LABEL = {
    "cardboard": "paper", "paper": "paper", "glass": "glass",
    "metal": "metal", "plastic": "plastic", "trash": "trash",
}

LABEL_TO_CATEGORIES: dict[str, list[str]] = {
    "paper": ["paper"],
    "glass": ["glass"],
    "metal": ["metal"],
    "plastic": ["pet", "hdpe"],
    "trash": [],
}

LABEL_TEXT = {
    "paper": "cardboard / paper",
    "glass": "glass",
    "metal": "metal",
    "plastic": "plastic (PET or HDPE)",
    "trash": "non-recyclable waste",
}

MIN_ACCURACY = 0.70  # held-out test accuracy needed to switch the feature on
CONFIDENT = 0.50  # below this the bot says it is not sure

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATASET_DIR = DATA_DIR / "trashnet" / "dataset-resized"
MODEL_DIR = DATA_DIR / "models"
HEAD_FILE = MODEL_DIR / "mitra_cv_head.pt"
META_FILE = MODEL_DIR / "mitra_cv_meta.json"


def suggestion(probs: dict[str, float]) -> dict:
    """Class probabilities -> what to suggest to the collector."""
    ranked = sorted(probs.items(), key=lambda kv: -kv[1])
    label, confidence = ranked[0]
    return {
        "label": label,
        "confidence": round(confidence, 3),
        "categories": LABEL_TO_CATEGORIES[label],
        "confident": confidence >= CONFIDENT,
        "alternatives": [{"label": lb, "confidence": round(p, 3)} for lb, p in ranked[1:3]],
    }
