#!/usr/bin/env python3
"""G1 v2 — LLM-critic grounding test (DeepSeek V4 Flash).

Replaces the weak bi-encoder cosine signal with an LLM entailment judge.
Pure stdlib (no numpy/sklearn) — metrics computed manually.
"""
import concurrent.futures
import json
import os
import random
import time
import urllib.request
from collections import Counter

API_KEY = os.environ["DEEPSEEK_API_KEY"]  # read from env, never committed
URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-flash"
PER_MODEL = 300
WORKERS = 16
SEED = 0

DATA = os.environ.get("RAGTRUTH_DATA_DIR", "ragtruth/dataset")  # download from github.com/ParticleMedia/RAGTruth


def source_to_text(si):
    if isinstance(si, str):
        return si
    if isinstance(si, dict):
        if "passages" in si:
            return si["passages"] or ""
        parts = []
        for k, v in si.items():
            parts.append(f"{k}: {v if not isinstance(v, (dict, list)) else json.dumps(v)}")
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


def judge(source, response):
    prompt = (
        "You are a strict grounding judge. Given a SOURCE and a RESPONSE generated from that source, "
        "determine whether the RESPONSE is fully grounded in the SOURCE.\n\n"
        "- GROUNDED: every factual claim in the RESPONSE is supported by the SOURCE.\n"
        "- HALLUCINATED: the RESPONSE contains factual claims NOT present in (or contradicting) the SOURCE.\n\n"
        f"SOURCE:\n{source}\n\nRESPONSE:\n{response}\n\n"
        "Reply with exactly one word: GROUNDED or HALLUCINATED."
    )
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 1024,
    }).encode()
    req = urllib.request.Request(URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
            content = (data["choices"][0]["message"].get("content") or "").strip().upper()
            if "HALLUCINATED" in content:
                return 1
            if "GROUNDED" in content:
                return 0
            return None
        except Exception:
            time.sleep(2 ** attempt)
    return None


def cohen_kappa(y_true, y_pred):
    """Cohen's kappa for binary labels (0/1)."""
    tp = fp = fn = tn = 0
    for t, p in zip(y_true, y_pred):
        if t == 1 and p == 1:
            tp += 1
        elif t == 0 and p == 1:
            fp += 1
        elif t == 1 and p == 0:
            fn += 1
        else:
            tn += 1
    n = tp + fp + fn + tn
    if n == 0:
        return 0.0, (tn, fp, fn, tp)
    po = (tp + tn) / n
    pe = (((tp + fn) / n) * ((tp + fp) / n)) + (((fp + tn) / n) * ((fn + tn) / n))
    kappa = 0.0 if pe == 1 else (po - pe) / (1 - pe)
    return kappa, (tn, fp, fn, tp)


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

    items = []
    for r in sample:
        src = sources.get(r["source_id"], "")
        resp = r["response"] or ""
        if not resp.strip():
            continue
        items.append((r["model"], src, resp, bool(r.get("labels"))))

    print(f"judging {len(items)} responses with {MODEL} ...", flush=True)

    preds = [None] * len(items)
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(judge, s, r): i for i, (m, s, r, g) in enumerate(items)}
        for fut in concurrent.futures.as_completed(futs):
            i = futs[fut]
            preds[i] = fut.result()
            done += 1
            if done % 200 == 0:
                print(f"  judged {done}/{len(items)} ...", flush=True)

    y_true, y_pred = [], []
    model_truth = Counter()
    model_pred = Counter()
    unknown = 0
    for i, (m, s, r, gold) in enumerate(items):
        p = preds[i]
        if p is None:
            unknown += 1
            continue
        y_true.append(1 if gold else 0)
        y_pred.append(p)
        model_truth[m] += int(gold)
        model_pred[m] += int(p)

    kappa, (tn, fp, fn, tp) = cohen_kappa(y_true, y_pred)
    n = tn + fp + fn + tp
    acc = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    # majority-class baseline = accuracy of always predicting the most common TRUE class
    baseline = max((tn + fp) / n, (fn + tp) / n) if n else 0.0

    out = {
        "model": MODEL,
        "n_responses": int(n),
        "unknown_parse": int(unknown),
        "kappa": round(kappa, 4),
        "accuracy": round(acc, 4),
        "precision_hallucinated": round(precision, 4),
        "recall_hallucinated": round(recall, 4),
        "f1_hallucinated": round(f1, 4),
        "baseline_majority_acc": round(baseline, 4),
        "confusion_[[TN,FP],[FN,TP]]": [[tn, fp], [fn, tp]],
        "model_truth_hallucination_rate": {m: round(model_truth[m] / max(1, sum(1 for x in items if x[0] == m)), 4) for m in model_truth},
        "model_pred_hallucination_rate": {m: round(model_pred[m] / max(1, sum(1 for x in items if x[0] == m)), 4) for m in model_pred},
    }

    print("\n===== G1 v2 RESULT (LLM critic) =====", flush=True)
    print(json.dumps(out, indent=2), flush=True)

    with open("results_llm.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nwrote g1-data/results_llm.json", flush=True)


if __name__ == "__main__":
    main()
