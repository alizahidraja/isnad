"""Live (keyed) model-drift runner for #71 — DeepSeek `deepseek-flash` as both the
chain narrators and the content critic.

The API key is read from the ``DEEPSEEK_API_KEY`` environment variable and is NEVER
committed, logged, or written to a file. A hard USD cap (default $2) is enforced before
every call; actual spend is derived from the token counts the API returns (raw token
totals are recorded as ground truth, cost is a disclosed multiplication).

Honesty controls:
- the ground-truth labels come from ``corpus_hard.live_label`` (LLM-free), never the critic.
- the critic is the model under test; the "perfect" and "empty" brackets from the
  offline phase remain the reference extremes.
- an optional independent LLM audit re-labels a sample of claims to cross-check the
  deterministic oracle, and the agreement rate is reported (disclosed: same model
  family, so it is a sanity check, not an independent ground truth).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from typing import cast

import httpx

from isnad.core.decision import decide
from isnad.core.grading import grade_chain
from isnad.types import Action, ChainGrade, ContentVerdict, NarratorGrade, TransformType

from experiments.model_drift.corpus_hard import HARD_CORPUS, HardFact, corpus_sha256, live_label

BASE_URL = "https://api.deepseek.com/v1"
MODEL = "deepseek-flash"
# V4-Flash flat rate card, USD per 1M tokens (public pricing, disclosed not asserted).
PRICE_IN_PER_M = 0.14
PRICE_OUT_PER_M = 0.28
PRICE_IN_PER_M_V4PRO = 0.435
PRICE_OUT_PER_M_V4PRO = 0.87
MODEL_V4PRO = "deepseek-v4-pro"
CAP_USD = 2.0
DEPTHS = (1, 2, 3, 4, 5)


@dataclass
class LiveClient:
    api_key: str = field(repr=False)
    model: str = MODEL
    base_url: str = BASE_URL
    temperature: float = 0.0
    cap_usd: float = CAP_USD
    price_in: float = PRICE_IN_PER_M
    price_out: float = PRICE_OUT_PER_M
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    retries: int = 0
    truncated: int = 0
    _client: httpx.Client = field(default_factory=httpx.Client, repr=False)

    @property
    def cost_usd(self) -> float:
        return (self.prompt_tokens / 1_000_000) * self.price_in + (
            self.completion_tokens / 1_000_000
        ) * self.price_out

    def complete(self, messages: list[dict[str, str]], max_tokens: int) -> str:
        if self.cost_usd >= self.cap_usd:
            raise RuntimeError(f"cost cap ${self.cap_usd:.2f} reached at ${self.cost_usd:.4f}")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": self.temperature,
        }
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = self._client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=body,
                    timeout=60,
                )
                if resp.status_code == 429:
                    raise RuntimeError("rate-limited (429)")
                resp.raise_for_status()
                data = resp.json()
                usage = data.get("usage", {})
                self.prompt_tokens += int(usage.get("prompt_tokens", 0))
                self.completion_tokens += int(usage.get("completion_tokens", 0))
                self.calls += 1
                self.retries += attempt
                choice = data.get("choices", [{}])[0]
                if choice.get("finish_reason") == "length":
                    self.truncated += 1
                return (choice.get("message", {}).get("content") or "").strip()
            except Exception as exc:  # noqa: BLE001 - surface as UNVERIFIABLE upstream
                last_err = exc
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"live call failed after retries: {last_err}")


def answer_from_memory(client: LiveClient, question: str) -> str:
    prompt = (
        "Answer the following question from memory in a single sentence. "
        "State the specific fact you believe is correct, including the number "
        "or date. Do not say you are unsure.\n\n"
        f"Question: {question}"
    )
    return client.complete([{"role": "user", "content": prompt}], max_tokens=4096)


def relay(client: LiveClient, claim: str, depth: int, hop: int) -> str:
    prompt = (
        f"You are agent {hop + 1} of {depth} in a multi-agent chain. Summarize the "
        f"previous agent's answer in a single sentence for the next agent, "
        f"conveying its essential factual claim. Keep it brief and in your own words.\n\n"
        f"Previous answer: {claim}"
    )
    return client.complete([{"role": "user", "content": prompt}], max_tokens=4096)


def critique(client: LiveClient, claim: str, evidence: str) -> ContentVerdict:
    prompt = (
        "You are a fact-checker. Judge whether the claim is CONSISTENT with, "
        "CONTRADICTS, or is UNVERIFIABLE from the evidence.\n\n"
        f"Evidence: {evidence}\n\nClaim: {claim}\n\n"
        "Answer with exactly one word: CONSISTENT, CONTRADICTION, or UNVERIFIABLE."
    )
    text = client.complete([{"role": "user", "content": prompt}], max_tokens=4096)
    from isnad.critics.llm import _parse_verdict  # local import: negation-aware

    return _parse_verdict(text)


def audit_label(client: LiveClient, claim: str, fact: HardFact) -> str:
    """Independent LLM re-label (audit only): FAITHFUL/HALLUCINATED/UNVERIFIABLE."""
    prompt = (
        "You are an auditor. The ground-truth fact is:\n"
        f'"{fact.assertion}"\n\n'
        "A generated claim says:\n"
        f'"{claim}"\n\n'
        "Does the claim state the SAME fact (FAITHFUL), a DIFFERENT or contradictory "
        "fact (HALLUCINATED), or is it too vague to tell (UNVERIFIABLE)? "
        "Answer with exactly one word: FAITHFUL, HALLUCINATED, or UNVERIFIABLE."
    )
    text = client.complete([{"role": "user", "content": prompt}], max_tokens=4096)
    t = text.strip().rstrip(".!?,;:'\"").upper()
    for token in ("FAITHFUL", "HALLUCINATED", "UNVERIFIABLE"):
        if t.split() and t.split()[-1] == token:
            return token.lower()
    for token in ("FAITHFUL", "HALLUCINATED", "UNVERIFIABLE"):
        if token in t:
            return token.lower()
    return "unverifiable"


def _chain_grade_for_depth(depth: int) -> ChainGrade:
    return grade_chain(
        [NarratorGrade.RELIABLE] * depth,
        [TransformType.GENERATIVE] * depth,
        is_complete=True,
    )


def run_depth_live(
    narrator: LiveClient, critic: LiveClient, depth: int, fact: HardFact
) -> dict[str, object]:
    claim = answer_from_memory(narrator, fact.question)
    hops: list[str] = [claim]
    for hop in range(1, depth):
        claim = relay(narrator, claim, depth, hop)
        hops.append(claim)
    gt = live_label(claim, fact)
    verdict = critique(critic, claim, fact.assertion)
    chain_grade = _chain_grade_for_depth(depth)
    action = decide(chain_grade, verdict)
    served = action in (Action.SERVE, Action.SERVE_WITH_CAVEAT)
    row: dict[str, object] = {
        "fact_id": fact.fact_id,
        "tier": fact.tier,
        "depth": depth,
        "final_claim": claim,
        "hops": hops,
        "ground_truth": gt,
        "critic_verdict": verdict.value,
        "action": action.value,
        "served": served,
    }
    return row


def run_live(
    narrator: LiveClient,
    critic: LiveClient,
    depths: tuple[int, ...] = DEPTHS,
    facts: tuple[HardFact, ...] = HARD_CORPUS,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for fact in facts:
        for depth in depths:
            rows.append(run_depth_live(narrator, critic, depth, fact))

    per_depth: dict[int, dict[str, object]] = {}
    for depth in depths:
        dr = [r for r in rows if r["depth"] == depth]
        hall = [r for r in dr if r["ground_truth"] == "hallucinated"]
        served_hall = [r for r in hall if r["served"]]
        per_depth[depth] = {
            "n": len(dr),
            "n_hallucinated": len(hall),
            "n_served_hallucinated": len(served_hall),
            "hallucination_rate": round(len(hall) / len(dr), 4) if dr else 0.0,
            "served_error_rate": round(len(served_hall) / len(hall), 4) if hall else None,
        }

    record: dict[str, object] = {
        "schema_version": 2,
        "generated_date": date.today().isoformat(),
        "narrator_model": narrator.model,
        "critic_model": critic.model,
        "base_url": narrator.base_url,
        "temperature": narrator.temperature,
        "narrator_price_in_per_m": narrator.price_in,
        "narrator_price_out_per_m": narrator.price_out,
        "critic_price_in_per_m": critic.price_in,
        "critic_price_out_per_m": critic.price_out,
        "cap_usd": narrator.cap_usd,
        "dataset_sha256": corpus_sha256(),
        "n_facts": len(facts),
        "depths": list(depths),
        "prompt_tokens": narrator.prompt_tokens + critic.prompt_tokens,
        "completion_tokens": narrator.completion_tokens + critic.completion_tokens,
        "calls": narrator.calls + critic.calls,
        "retries": narrator.retries + critic.retries,
        "truncated": narrator.truncated + critic.truncated,
        "cost_usd": round(narrator.cost_usd + critic.cost_usd, 6),
        "narrator_cost_usd": round(narrator.cost_usd, 6),
        "critic_cost_usd": round(critic.cost_usd, 6),
        "per_depth": {str(k): v for k, v in per_depth.items()},
        "rows": rows,
    }
    return record


def run_audit(
    client: LiveClient, rows: list[dict[str, object]], sample: int = 30
) -> dict[str, object]:
    """Cross-check the deterministic oracle with an independent LLM pass."""
    hallucinated = [r for r in rows if r["ground_truth"] == "hallucinated"]
    faithful = [r for r in rows if r["ground_truth"] == "faithful"]
    sampled = (
        (hallucinated[: sample // 2] + faithful[: sample // 2])
        if (hallucinated and faithful)
        else (hallucinated + faithful)[:sample]
    )
    agreements = 0
    checks: list[dict[str, object]] = []
    for r in sampled:
        fact = next(f for f in HARD_CORPUS if f.fact_id == r["fact_id"])
        llm = audit_label(client, str(r["final_claim"]), fact)
        oracle = str(r["ground_truth"])
        agree = llm == oracle
        agreements += int(agree)
        checks.append({
            "fact_id": str(r["fact_id"]),
            "oracle": oracle,
            "llm_audit": llm,
            "agree": agree,
        })
    return {
        "n_checked": len(sampled),
        "n_agree": agreements,
        "agreement_rate": round(agreements / len(sampled), 4) if sampled else 0.0,
        "note": "same model family as the critic under test — a sanity check, not independent ground truth",
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live model-drift leaderboard (#71, DeepSeek)")
    parser.add_argument("--depths", type=int, nargs="+", default=list(DEPTHS))
    parser.add_argument(
        "--facts", type=str, nargs="+", default=None, help="fact ids (default: all)"
    )
    parser.add_argument("--cap-usd", type=float, default=CAP_USD)
    parser.add_argument("--audit", action="store_true", help="run the LLM cross-check audit")
    parser.add_argument("--audit-sample", type=int, default=30)
    parser.add_argument(
        "--critic-model",
        type=str,
        default=MODEL,
        help="critic model (e.g. deepseek-v4-pro for cross-model)",
    )
    args = parser.parse_args(argv)

    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        print(
            "DEEPSEEK_API_KEY is not set — refusing to run (would fabricate nothing).",
            file=sys.stderr,
        )
        return 1

    facts = HARD_CORPUS
    if args.facts:
        want = set(args.facts)
        facts = tuple(f for f in HARD_CORPUS if f.fact_id in want)
        if not facts:
            print(f"no matching facts for {args.facts}", file=sys.stderr)
            return 1

    narrator = LiveClient(api_key=key, model=MODEL, cap_usd=args.cap_usd)
    critic = LiveClient(
        api_key=key,
        model=args.critic_model,
        cap_usd=args.cap_usd,
        price_in=PRICE_IN_PER_M_V4PRO if args.critic_model == MODEL_V4PRO else PRICE_IN_PER_M,
        price_out=PRICE_OUT_PER_M_V4PRO if args.critic_model == MODEL_V4PRO else PRICE_OUT_PER_M,
    )
    record = run_live(narrator, critic, tuple(args.depths), facts)
    if args.audit:
        record["audit"] = run_audit(
            critic, cast(list[dict[str, object]], record["rows"]), args.audit_sample
        )

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "live_results.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"wrote {out_path}")
    print(
        f"narrator={record['narrator_model']} critic={record['critic_model']} calls={record['calls']} "
        f"cost=${record['cost_usd']:.5f} "
        f"(in={record['prompt_tokens']} out={record['completion_tokens']})"
    )
    per_depth = cast(dict[str, dict[str, object]], record["per_depth"])
    for depth, d in per_depth.items():
        ser = d["served_error_rate"]
        ser_str = f"{ser:.3f}" if ser is not None else "n/a"
        print(
            f"  depth={depth} hallucination_rate={d['hallucination_rate']:.3f} "
            f"served_error_rate={ser_str}"
        )
    if "audit" in record:
        a = cast(dict[str, object], record["audit"])
        print(
            f"audit: oracle-vs-LLM agreement {a['agreement_rate']:.3f} ({a['n_agree']}/{a['n_checked']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
