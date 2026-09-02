# CLI Reference

Every `isnad` subcommand. Run `isnad <command> --help` for the full flag set.

| Command | What it does |
| --- | --- |
| `isnad serve` | Run the HTTP API (`POST /v1/claims`, `GET /v1/claims`, admin-grade mutations). |
| `isnad seed` | Seed the registry (defaults or operator config). |
| `isnad ingest` | Ingest a claim + its chain from JSON. |
| `isnad export` | Export audit records (`--format json | jsonl | csv`,`--verify` re-hashes). |
| `isnad verify` | Recompute an audit record's hash and check integrity. |
| `isnad verify-chain` | Replay a hash chain log (`.jsonl`) and check each link. |
| `isnad verify-merkle` | Replay a Merkle batch log and verify the root. |
| `isnad scan` | Map a pipeline's transmitter ids onto the warm registry: `vouched` vs `cold` (UNGRADED → REVIEW). Evidence listing only — ordinal grade + provenance, never a numeric score. |
| `isnad mcp` | Run the Model Context Protocol server (verify/grades over MCP). |
| `isnad bench` | Config-driven benchmark of *your* corpus (`--config mine.json`). |

## The reproducible benchmark

The classical ISNAD-Bench (κ = 0.87 over 575,060 graded hadith chains) is **not** the
`isnad bench` command — it lives in the `bench/` harness:

```bash
python -m bench.run --reproduce --limit 1   # hard-fails on a DB SHA-256 mismatch
```

`--reproduce` pins the hadith-kg database by SHA-256 and records `db_hash` + `harness_rev`
in the JSON receipt, so κ = 0.87 is **independently re-runnable, not self-asserted**.

## Exit codes

Every command exits `0` on success and non-zero on failure. `--reproduce` exits `2` on a
database hash mismatch (hard fail, by design).
