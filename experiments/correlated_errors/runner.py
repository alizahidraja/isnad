"""ISNAD φ study — model runner.

Runs ONE model over the corpus, temperature 0, max_tokens 2048, and writes
``results/<model_slug>.json``. Supports OpenRouter free models and DeepSeek
(direct). Retries 429/5xx with exponential backoff and space out calls to avoid
the shared free-pool rate limit. Parsing handles reasoning models (answer in
``reasoning``/``reasoning_content`` when ``content`` is empty).

Run:  OPENROUTER_API_KEY=… DEEPSEEK_API_KEY=… \
      python -m experiments.correlated_errors.runner --model google/gemma-4-31b-it:free
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_PROVIDERS = {
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "kimi": ("https://api.moonshot.ai/v1", "KIMI_API_KEY"),
    "glm": ("https://open.bigmodel.cn/api/paas/v4", "GLM_API_KEY"),
    "perplexity": ("https://api.perplexity.ai", "PERPLEXITY_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}

# Kimi (Moonshot) reasoning models only accept temperature=1; every other provider
# here accepts temperature=0. This is a disclosed deviation from the protocol.
_TEMPERATURE = {"kimi": 1.0}
_NUM = re.compile(
    r"[+\-\u2012\u2013\u2212]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
)  # sign: -, U+2212 minus, U+2013 en-dash, U+2012 figure dash


def _endpoint_and_key(model: str) -> tuple[str, str, str]:
    """Return (base_url, api_key, model_name) for the given model id."""
    prefix = model.split("/", 1)[0]
    base, env = _PROVIDERS.get(prefix, _PROVIDERS["openrouter"])
    key = os.environ.get(env, "")
    model_name = model.split("/", 1)[1] if "/" in model else model
    return base, key, model_name


def _parse_number(text: str | None) -> str | None:
    if not text:
        return None
    nums = _NUM.findall(text)
    if not nums:
        return None
    return nums[-1].replace("\u2212", "-").replace("\u2013", "-").replace("\u2012", "-")


def _slug(model: str) -> str:
    return model.replace("/", "_").replace(":", "_").replace(".", "_")


def run_model(
    model: str, corpus: list[dict[str, str]], limit: int | None
) -> list[dict[str, object]]:
    base, key, model_name = _endpoint_and_key(model)
    if not key:
        raise SystemExit(
            f"no API key for model {model!r} (set the provider env var (DEEPSEEK_API_KEY / KIMI_API_KEY / GLM_API_KEY / PERPLEXITY_API_KEY))"
        )
    rows: list[dict[str, object]] = []
    for i, fact in enumerate(corpus):
        if limit is not None and i >= limit:
            break
        prompt = (
            f"Answer the following question with just the numeric value (no units, no prose): "
            f"{fact['claim_text']}"
        )
        body = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": _TEMPERATURE.get(model.split("/", 1)[0], 0.0),
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        content = reasoning = None
        finish = error = None
        for attempt in range(5):
            try:
                r = httpx.post(f"{base}/chat/completions", json=body, headers=headers, timeout=90)
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2**attempt)
                    continue
                r.raise_for_status()
                data = r.json()
                msg = (data.get("choices") or [{}])[0].get("message") or {}
                content = msg.get("content")
                reasoning = msg.get("reasoning") or msg.get("reasoning_content")
                finish = (data.get("choices") or [{}])[0].get("finish_reason")
                break
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                time.sleep(2**attempt)
        if content is None and reasoning is None and error is None:
            error = "no response after retries (likely rate-limited)"
        answer = _parse_number(content)
        if answer is None and reasoning:
            answer = _parse_number(reasoning)
        rows.append({
            "claim_id": fact["id"],
            "model": model,
            "answer_value": answer,
            "answer_unit": "",
            "raw": (content or reasoning or "")[:200],
            "finish_reason": finish,
            "error": error,
        })
        time.sleep(0.6)  # space out calls on the shared free pool
    return rows


_UNICODE_SIGN_NUM = re.compile(r"[\u2212\u2013\u2012]\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


def reparse_results() -> None:
    """Offline: fix the Unicode-minus sign-drop in stored ``results/*.json``.

    The pre-fix regex ``[+-]?`` dropped U+2212 MINUS SIGN (and en-dash / figure
    dash), so a model answer like "\u2212273.15" was parsed as "273.15". This
    NORMALIZES ONLY that pattern: a Unicode-signed number whose ASCII absolute
    value equals the stored answer is rewritten as "-<abs>". It deliberately
    does NOT re-derive the answer from ``raw`` in general — ``raw`` is truncated
    to 200 chars and reasoning models put the final answer after long reasoning,
    so a full re-parse would corrupt answers. Safe because it only flips the
    sign on an exact absolute-value match.
    """
    out_dir = _HERE / "results"
    for path in sorted(out_dir.glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        fixed = 0
        for r in rows:
            stored = r.get("answer_value")
            raw = r.get("raw") or ""
            if stored is None:
                continue
            for tok in _UNICODE_SIGN_NUM.findall(raw):
                body = tok[1:]
                try:
                    if abs(float(stored) - float(body)) < 1e-9 and not str(stored).startswith("-"):
                        r["answer_value"] = "-" + body
                        fixed += 1
                        break
                except ValueError:
                    pass
        if fixed:
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"reparsed {path.name}: {fixed} sign-fixed")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=False, help="model id (e.g. deepseek/deepseek-chat)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--smoke", action="store_true", help="run only the first 3 facts")
    ap.add_argument(
        "--reparse", action="store_true", help="offline: re-parse stored raw answers, no API"
    )
    args = ap.parse_args(argv)

    if args.reparse:
        reparse_results()
        return

    corpus = json.loads((_HERE / "corpus.json").read_text(encoding="utf-8"))
    limit = 3 if args.smoke else args.limit
    rows = run_model(args.model, corpus, limit)
    out_dir = _HERE / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{_slug(args.model)}.json"
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    n_answered = sum(1 for r in rows if r["answer_value"] is not None)
    print(f"wrote {len(rows)} rows to {out_path} ({n_answered} with a parsed number)")


if __name__ == "__main__":
    main()
