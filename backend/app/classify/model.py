"""Photo -> material suggestion. Lazy: torch loads on the first photo, not at API start.

The feature is on only if a trained head exists AND its held-out test accuracy
cleared MIN_ACCURACY. Otherwise status() says why and classify() raises Unavailable,
so the bot and dashboard fall back to the plain material list ("in development").
"""
import io
import json
import threading

from app.classify.labels import HEAD_FILE, LABELS, META_FILE, MIN_ACCURACY, suggestion

_lock = threading.Lock()
_loaded = None  # (backbone, head, transform)


class Unavailable(Exception):
    pass


def _meta() -> dict | None:
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status() -> dict:
    meta = _meta()
    base = {"available": False, "test_accuracy": None, "labels": LABELS, "trained_at": None,
            "min_accuracy": MIN_ACCURACY}
    if meta is None or not HEAD_FILE.exists():
        return {**base, "reason": "Photo classifier in development: not trained yet "
                                  "(uv run python -m app.classify.train)."}
    acc = meta.get("test_accuracy", 0.0)
    base.update(test_accuracy=acc, trained_at=meta.get("trained_at"))
    if acc < MIN_ACCURACY:
        return {**base, "reason": f"Photo classifier in development: held-out accuracy {acc:.0%} "
                                  f"is below the {MIN_ACCURACY:.0%} bar."}
    return {**base, "available": True,
            "reason": f"Suggestion only: {acc:.0%} accuracy on held-out TrashNet photos. "
                      "The collector always confirms the material."}


def _load():
    global _loaded
    with _lock:
        if _loaded is None:
            import torch
            from torch import nn
            from torchvision import models

            weights = models.MobileNet_V3_Large_Weights.IMAGENET1K_V1
            try:
                backbone = models.mobilenet_v3_large(weights=weights)  # cached after first download
            except Exception as e:  # offline and not cached yet
                raise Unavailable("Photo classifier unavailable: backbone weights could not be "
                                  "loaded (needs internet once).") from e
            backbone.classifier = backbone.classifier[:3]
            head = nn.Linear(1280, len(LABELS))
            head.load_state_dict(torch.load(HEAD_FILE, weights_only=True))
            _loaded = (backbone.eval(), head.eval(), weights.transforms())
        return _loaded


def classify(image: bytes) -> dict:
    """Suggest a material for a photo. Raises Unavailable, or ValueError for a non-image."""
    s = status()
    if not s["available"]:
        raise Unavailable(s["reason"])
    from PIL import Image, UnidentifiedImageError
    try:
        img = Image.open(io.BytesIO(image)).convert("RGB")
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("not a readable image") from e

    import torch
    backbone, head, tf = _load()
    with torch.inference_mode():
        probs = torch.softmax(head(backbone(tf(img).unsqueeze(0))), dim=1)[0].tolist()
    return suggestion(dict(zip(LABELS, probs)))
