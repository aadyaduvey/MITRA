"""Train the MITRA photo classifier on TrashNet (CPU-friendly).

MobileNetV3-Large pretrained on ImageNet is used as a frozen feature extractor;
only a small linear head is trained. Split 70/15/15 (stratified, fixed seed): the
head is chosen on validation, and accuracy is reported on a test split it never saw.

    uv run python -m app.classify.train              # dataset in data/trashnet/dataset-resized
    uv run python -m app.classify.train --views 3    # train-time augmented views per image

Writes data/models/mitra_cv_head.pt and data/models/mitra_cv_meta.json.
"""
import argparse
import json
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import torch
from PIL import Image
from torch import nn
from torchvision import models, transforms

from app.classify.labels import (
    DATASET_DIR, FOLDER_TO_LABEL, HEAD_FILE, LABELS, META_FILE, MIN_ACCURACY, MODEL_DIR,
)

FEATURES = 1280  # MobileNetV3-Large penultimate layer


def list_images(root: Path) -> list[tuple[Path, int]]:
    items = []
    for folder, label in FOLDER_TO_LABEL.items():
        for p in sorted((root / folder).glob("*.jpg")):
            items.append((p, LABELS.index(label)))
    if not items:
        raise SystemExit(f"No images under {root}. Download TrashNet first (see backend/README.md).")
    return items


def stratified_split(items, seed: int, fractions=(0.70, 0.15)):
    rng = random.Random(seed)
    train, val, test = [], [], []
    for label in range(len(LABELS)):
        group = [it for it in items if it[1] == label]
        rng.shuffle(group)
        a = round(len(group) * fractions[0])
        b = a + round(len(group) * fractions[1])
        train += group[:a]
        val += group[a:b]
        test += group[b:]
    return train, val, test


def backbone():
    weights = models.MobileNet_V3_Large_Weights.IMAGENET1K_V1
    m = models.mobilenet_v3_large(weights=weights)
    m.classifier = m.classifier[:3]  # Linear(960,1280) + Hardswish + Dropout -> 1280-d features
    return m.eval(), weights.transforms()


@torch.inference_mode()
def extract(model, items, tfs: list, batch: int = 64):
    """Features for every (image, transform) pair."""
    xs, ys = [], []
    jobs = [(p, y, tf) for p, y in items for tf in tfs]
    for i in range(0, len(jobs), batch):
        chunk = jobs[i:i + batch]
        imgs = torch.stack([tf(Image.open(p).convert("RGB")) for p, _, tf in chunk])
        xs.append(model(imgs))
        ys += [y for _, y, _ in chunk]
        print(f"\r  features {min(i + batch, len(jobs))}/{len(jobs)}", end="", flush=True)
    print()
    return torch.cat(xs), torch.tensor(ys)


def train_head(xtr, ytr, xva, yva, seed: int, epochs: int = 400):
    torch.manual_seed(seed)
    head = nn.Sequential(nn.Dropout(0.2), nn.Linear(FEATURES, len(LABELS)))
    counts = torch.bincount(ytr, minlength=len(LABELS)).float()
    loss_fn = nn.CrossEntropyLoss(weight=counts.sum() / (len(LABELS) * counts))  # trash is rare
    opt = torch.optim.AdamW(head.parameters(), lr=1e-3, weight_decay=1e-2)
    best, best_state, best_epoch = -1.0, None, 0
    for epoch in range(epochs):
        head.train()
        perm = torch.randperm(len(xtr))
        for i in range(0, len(perm), 256):
            idx = perm[i:i + 256]
            opt.zero_grad()
            loss_fn(head(xtr[idx]), ytr[idx]).backward()
            opt.step()
        acc = accuracy(head, xva, yva)
        if acc > best:
            best, best_epoch = acc, epoch
            best_state = {k: v.clone() for k, v in head.state_dict().items()}
        elif epoch - best_epoch > 60:
            break
    head.load_state_dict(best_state)
    return head.eval(), best, best_epoch


@torch.inference_mode()
def predict(head, x):
    head.eval()
    return head(x).argmax(1)


def accuracy(head, x, y) -> float:
    return (predict(head, x) == y).float().mean().item()


def report(head, x, y) -> dict:
    pred = predict(head, x)
    n = len(LABELS)
    confusion = [[int(((y == t) & (pred == p)).sum()) for p in range(n)] for t in range(n)]
    per_class = {}
    for i, label in enumerate(LABELS):
        tp = confusion[i][i]
        support = sum(confusion[i])
        predicted = sum(confusion[t][i] for t in range(n))
        per_class[label] = {
            "precision": round(tp / predicted, 3) if predicted else 0.0,
            "recall": round(tp / support, 3) if support else 0.0,
            "support": support,
        }
    return {"accuracy": round((pred == y).float().mean().item(), 4), "per_class": per_class,
            "confusion": confusion}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=DATASET_DIR)
    ap.add_argument("--views", type=int, default=3, help="views per training image (1 = no augmentation)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    torch.set_num_threads(max(1, torch.get_num_threads()))
    t0 = time.time()
    items = list_images(args.data)
    train, val, test = stratified_split(items, args.seed)
    print(f"TrashNet: {len(items)} images -> train {len(train)}, val {len(val)}, test {len(test)}")
    print("  per label:", dict(Counter(LABELS[y] for _, y in items)))

    model, eval_tf = backbone()
    aug_tf = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.6, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.2, 0.2, 0.2),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    torch.manual_seed(args.seed)
    xtr, ytr = extract(model, train, [eval_tf] + [aug_tf] * (args.views - 1))
    xva, yva = extract(model, val, [eval_tf])
    xte, yte = extract(model, test, [eval_tf])

    head, val_acc, epoch = train_head(xtr, ytr, xva, yva, args.seed)
    result = report(head, xte, yte)
    passed = result["accuracy"] >= MIN_ACCURACY

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(head[1].state_dict(), HEAD_FILE)  # the Linear layer; dropout has no weights
    meta = {
        "backbone": "torchvision mobilenet_v3_large IMAGENET1K_V1 (frozen), 1280-d features",
        "dataset": "TrashNet dataset-resized (Thung & Yang 2016); cardboard+paper merged into paper",
        "labels": LABELS,
        "split": {"train": len(train), "val": len(val), "test": len(test), "seed": args.seed},
        "train_views": args.views,
        "val_accuracy": round(val_acc, 4),
        "best_epoch": epoch,
        "test_accuracy": result["accuracy"],
        "per_class": result["per_class"],
        "confusion": result["confusion"],
        "min_accuracy": MIN_ACCURACY,
        "enabled": passed,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "train_seconds": round(time.time() - t0),
    }
    META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\nValidation accuracy {val_acc:.1%} (epoch {epoch}).")
    print(f"HELD-OUT TEST ACCURACY: {result['accuracy']:.1%} on {len(test)} images never used in training")
    print(f"  {'label':<8} {'precision':>9} {'recall':>7} {'n':>4}")
    for label, m in result["per_class"].items():
        print(f"  {label:<8} {m['precision']:>9.1%} {m['recall']:>7.1%} {m['support']:>4}")
    print("  confusion (rows = true, cols = predicted):", LABELS)
    for label, row in zip(LABELS, result["confusion"]):
        print(f"  {label:<8} {row}")
    print(f"\n{'ENABLED' if passed else 'DISABLED (below 70%): CV stays in development'} · "
          f"saved {HEAD_FILE.name} + {META_FILE.name} · {meta['train_seconds']} s")


if __name__ == "__main__":
    main()
