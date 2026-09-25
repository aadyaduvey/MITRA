"""Photo classifier: pure suggestion logic, status gating, and the API routes.

No network: routes use a stand-in classifier. One optional test runs the real model
on held-out TrashNet photos, only if the trained head, cached backbone weights and
dataset are all present locally.
"""
import json
from pathlib import Path

import pytest

from app.classify import labels
from app.classify import model as cv


def test_suggestion_maps_labels_to_categories():
    s = labels.suggestion({"plastic": 0.7, "glass": 0.2, "metal": 0.05, "paper": 0.03, "trash": 0.02})
    assert s["label"] == "plastic" and s["categories"] == ["pet", "hdpe"] and s["confident"]
    assert [a["label"] for a in s["alternatives"]] == ["glass", "metal"]
    low = labels.suggestion({"metal": 0.4, "glass": 0.35, "paper": 0.1, "plastic": 0.1, "trash": 0.05})
    assert not low["confident"]
    assert labels.suggestion({"trash": 0.9, "metal": 0.1, "glass": 0, "paper": 0, "plastic": 0})["categories"] == []


def test_every_label_maps_to_known_categories():
    known = {"pet", "hdpe", "paper", "glass", "metal", "ewaste"}
    for label in labels.LABELS:
        assert set(labels.LABEL_TO_CATEGORIES[label]) <= known
    assert "ewaste" not in {c for cs in labels.LABEL_TO_CATEGORIES.values() for c in cs}  # never suggested


def _point_model_at(tmp_path, monkeypatch, meta: dict | None, head: bool = True):
    head_file, meta_file = tmp_path / "head.pt", tmp_path / "meta.json"
    if head:
        head_file.write_bytes(b"x")
    if meta is not None:
        meta_file.write_text(json.dumps(meta))
    monkeypatch.setattr(cv, "HEAD_FILE", head_file)
    monkeypatch.setattr(cv, "META_FILE", meta_file)


def test_status_in_development_when_untrained(tmp_path, monkeypatch):
    _point_model_at(tmp_path, monkeypatch, meta=None, head=False)
    s = cv.status()
    assert not s["available"] and "in development" in s["reason"]
    with pytest.raises(cv.Unavailable):
        cv.classify(b"anything")


def test_status_in_development_below_accuracy_bar(tmp_path, monkeypatch):
    _point_model_at(tmp_path, monkeypatch, meta={"test_accuracy": 0.62, "trained_at": "t"})
    s = cv.status()
    assert not s["available"] and "62%" in s["reason"] and "70%" in s["reason"]


def test_status_available_above_bar(tmp_path, monkeypatch):
    _point_model_at(tmp_path, monkeypatch, meta={"test_accuracy": 0.905, "trained_at": "t"})
    s = cv.status()
    assert s["available"] and s["test_accuracy"] == 0.905 and "Suggestion only" in s["reason"]


# ---------- API ----------


@pytest.fixture
def fake_classifier(monkeypatch):
    calls = []

    def classify(data: bytes) -> dict:
        calls.append(data)
        if data == b"not-an-image":
            raise ValueError("not a readable image")
        return labels.suggestion({"glass": 0.83, "plastic": 0.1, "metal": 0.04, "paper": 0.02, "trash": 0.01})

    monkeypatch.setattr(cv, "classify", classify)
    return calls


def test_classify_route(client, fake_classifier):
    r = client.post("/api/classify", files={"file": ("p.jpg", b"jpeg-bytes", "image/jpeg")})
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "glass" and body["categories"] == ["glass"] and body["confidence"] == 0.83
    assert "Suggestion only" in body["note"]
    assert fake_classifier == [b"jpeg-bytes"]


def test_classify_route_errors(client, fake_classifier, monkeypatch):
    assert client.post("/api/classify", files={"file": ("p.jpg", b"not-an-image", "image/jpeg")}).status_code == 422
    assert client.post("/api/classify").status_code == 422  # no file
    monkeypatch.setattr("app.api.routes_classify.MAX_BYTES", 10)
    assert client.post("/api/classify", files={"file": ("p.jpg", b"x" * 11, "image/jpeg")}).status_code == 413


def test_classify_route_in_development(client, monkeypatch):
    def unavailable(data):
        raise cv.Unavailable("Photo classifier in development: not trained yet.")

    monkeypatch.setattr(cv, "classify", unavailable)
    r = client.post("/api/classify", files={"file": ("p.jpg", b"img", "image/jpeg")})
    assert r.status_code == 503 and "in development" in r.json()["detail"]


def test_status_route(client):
    s = client.get("/api/classify/status").json()
    assert set(s) >= {"available", "reason", "test_accuracy", "min_accuracy", "labels"}
    assert s["min_accuracy"] == 0.7


# ---------- optional: the real model on held-out photos ----------


def _real_model_ready() -> bool:
    cache = Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / "mobilenet_v3_large-8738ca79.pth"
    return cv.status()["available"] and cache.exists() and labels.DATASET_DIR.exists()


@pytest.mark.skipif(not _real_model_ready(), reason="trained model, cached backbone or TrashNet not present")
def test_real_model_on_held_out_photos():
    from app.classify.train import list_images, stratified_split

    _, _, test = stratified_split(list_images(labels.DATASET_DIR), seed=42)
    sample = test[::10]  # every 10th held-out photo, all classes
    right = sum(cv.classify(p.read_bytes())["label"] == labels.LABELS[y] for p, y in sample)
    assert right / len(sample) >= labels.MIN_ACCURACY
    sample_photo = labels.DATA_DIR / "samples" / "metal_sample.jpg"
    assert cv.classify(sample_photo.read_bytes())["label"] == "metal"
