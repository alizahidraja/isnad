# OpenTelemetry → ISNAD mapping

`isnad ingest --otlp` grades an existing OpenTelemetry GenAI trace as an isnād.
This documents the span→narrator mapping and — just as important — what it
*can't* do.

## The mapping

| OTel | ISNAD |
|---|---|
| span with `gen_ai.response.model` / `gen_ai.request.model` | transmitter, `narrator_id = model:<model>` |
| span with only `gen_ai.operation.name` | transmitter, `narrator_id = <operation>` |
| span with no `gen_ai.*` attribute (DB, HTTP, …) | not a transmitter — skipped |
| `startTimeUnixNano` order | transmission order (who handled it, in order) |
| last transmitter's `gen_ai.completion` | the claim text (if present) |

The chain is graded **weakest-link** over the registry grades, exactly like a
hand-built isnād. An ungraded transmitter caps at **ḍaʿīf** by default
(`--lenient` caps at ḥasan instead).

## Honest limits (the important part)

1. **The GenAI conventions are in Development status** — attribute names may
   change. The parser is tolerant (missing attributes → skipped), but the
   mapping should be re-checked against the current spec before relying on it.

2. **OTel spans do not carry the claim text.** The conventions standardise
   model/token/latency, not output content. The isnād (transmission chain) is
   fully reconstructable; the matn (claim) is only available if a span emits the
   legacy `gen_ai.completion` attribute. When it's absent, `isnad ingest`
   reports `claim_text: null` and grades the *chain* only — content criticism
   cannot run without the claim.

3. **Grades are operator-assigned.** Ingesting a trace looks models up in the
   registry; it does not auto-grade them. Seed grades first (`isnad seed`), or
   every transmitter reads as UNGRADED → ḍaʿīf.

4. **This is the inverse of #47.** #47 proposes emitting OTel spans *from* the
   callback (ISNAD → OTel, requiring ISNAD's format). This ingests OTel spans
   *into* ISNAD (OTel → ISNAD, zero ISNAD-format adoption).

## Example

```bash
isnad seed <<'EOF'
ISNAD_SEED_CONFIG='[{"narrator_id":"model:gpt-4","domain":"general","grade":"acceptable"}]'
EOF
isnad ingest --otlp trace.json
```

```json
{
  "trace_id": "abc123",
  "transmitter_count": 2,
  "chain": [
    {"narrator_id": "retrieve", "grade": "ungraded", "span_name": "retrieve docs", "model": null},
    {"narrator_id": "model:gpt-4", "grade": "acceptable", "span_name": "chat gpt-4", "model": "gpt-4"}
  ],
  "chain_grade": "daif",
  "weakest_link": "retrieve",
  "claim_text": "F=ma"
}
```
