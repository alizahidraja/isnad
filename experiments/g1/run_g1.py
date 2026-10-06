#!/usr/bin/env python3
"""G1 moat-gate transfer test (v1.1 — bi-encoder semantic grounding).

Does ISNAD's source-grounding (weakest-link over per-sentence semantic grounding
of a claim in its own on-chain source) transfer to AI hallucination detection?

See g1_mapping.md for the pre-committed mapping. Run inside the isnad-api image.
"""

import json
import os
import random
import re
from collections import Counter

import numpy as np
from sentence_transformers import SentenceTransformer

DATA = "/g1/data"
MODEL_NAME = "all-MiniLM-L6-v2"
PER_MODEL = int(os.environ.get("G1_PER_MODEL", "400"))
PRIMARY_THRESHOLD = 0.5
SWEEP = [0.3, 0.4, 0.5, 0.6]
SEED = 0


def source_to_text(si):
    if isinstance(si, str):
        return si
    if isinstance(si, dict):
        if "passages" in si:
            return si["passages"] or ""
        parts = []
        for k, v in si.items():
            if isinstance(v, (dict, list)):
                parts.append(f"{k}: {json.dumps(v)}")
            else:
                parts.append(f"{k}: {v}")
        return "\n".join(parts)
    return str(si)


def load():
    sources = {}
    with open(f"{DATA}/source_info.jsonl") as f:
        for line in f:
            d = json.loads(line)
            sources[d["source_id"]] = source_to_text(d.get("source_info") or d.get("source") or "")
    rows = []
    with open(f"{DATA}/response.jsonl") as f:
        for line in f:
            rows.append(json.loads(line))
    return sources, rows


def split_sentences(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if len(p.strip()) >= 10]


def metrics(y_true, y_pred):
    from sklearn.metrics import (
        accuracy_score,
        cohen_kappa_score,
        confusion_matrix,
        precision_recall_fscore_support,
    )

    kappa = cohen_kappa_score(y_true, y_pred)
    acc = accuracy_score(y_true, y_pred)
    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, labels=[1], zero_division=0)
    return {
        "kappa": round(float(kappa), 4),
        "accuracy": round(float(acc), 4),
        "precision_hallucinated": round(float(p[0]), 4),
        "recall_hallucinated": round(float(r[0]), 4),
        "f1_hallucinated": round(float(f1[0]), 4),
        "confusion_[[TN,FP],[FN,TP]]": confusion_matrix(y_true, y_pred).tolist(),
    }


def main():
    random.seed(SEED)
    sources, rows = load()

    by_model = {}
    for r in rows:
        by_model.setdefault(r["model"], []).append(r)
    sample = []
    for m, lst in by_model.items():
        random.shuffle(lst)
        sample.extend(lst[:PER_MODEL])

    resp_srcs, resp_sents, resp_gold, resp_model = [], [], [], []
    for r in sample:
        src = sources.get(r["source_id"], "")
        sents = split_sentences(r["response"])
        if not sents:
            continue
        resp_srcs.append(src)
        resp_sents.append(sents)
        resp_gold.append(bool(r.get("labels")))
        resp_model.append(r["model"])

    n_resp = len(resp_srcs)
    print(f"{n_resp} responses ({len(sample)} sampled)", flush=True)

    model = SentenceTransformer(MODEL_NAME)

    src_embs = model.encode(resp_srcs, normalize_embeddings=True, batch_size=64)
    print("embedded sources", flush=True)

    all_sents = []
    sent_resp = []
    for i, sents in enumerate(resp_sents):
        for s in sents:
            all_sents.append(s)
            sent_resp.append(i)
    sent_embs = model.encode(all_sents, normalize_embeddings=True, batch_size=64)
    print(f"embedded {len(all_sents)} sentences", flush=True)

    # cosine similarity per (source, sentence) pair via normalized dot product
    sims = np.sum(src_embs[sent_resp] * sent_embs, axis=1)

    # weakest link: per-response MIN similarity over its sentences
    min_sim = np.ones(n_resp)
    for k, ridx in enumerate(sent_resp):
        if sims[k] < min_sim[ridx]:
            min_sim[ridx] = sims[k]

    y_true = np.array([1 if g else 0 for g in resp_gold])

    out = {
        "n_responses": int(n_resp),
        "n_sentences": int(len(all_sents)),
        "model": MODEL_NAME,
        "baseline_majority_acc": round(
            max(float((y_true == 0).mean()), float((y_true == 1).mean())), 4
        ),
        "thresholds": {},
    }

    for t in SWEEP:
        pred_hall = (min_sim < t).astype(int)
        out["thresholds"][str(t)] = metrics(y_true, pred_hall)

    # per-model table at primary threshold
    pred_hall = (min_sim < PRIMARY_THRESHOLD).astype(int)
    model_truth = Counter()
    model_pred = Counter()
    for i, m in enumerate(resp_model):
        model_truth[m] += int(y_true[i])
        model_pred[m] += int(pred_hall[i])
    out["primary_threshold"] = PRIMARY_THRESHOLD
    out["model_truth_hallucination_rate"] = {
        m: round(model_truth[m] / max(1, sum(1 for x in sample if x["model"] == m)), 4)
        for m in model_truth
    }
    out["model_pred_hallucination_rate"] = {
        m: round(model_pred[m] / max(1, sum(1 for x in sample if x["model"] == m)), 4)
        for m in model_pred
    }

    print("\n===== G1 RESULT =====", flush=True)
    print(json.dumps(out, indent=2), flush=True)

    with open("/g1/results.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote /g1/results.json", flush=True)


if __name__ == "__main__":
    main()
