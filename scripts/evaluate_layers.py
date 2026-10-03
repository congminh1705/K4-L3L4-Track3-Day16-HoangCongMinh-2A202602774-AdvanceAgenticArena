"""Offline, paired leave-one-out evaluation over public briefs and seeds."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from run_practice import STACK_ORDER, build_middleware
from arena.briefs import load_public_briefs
from arena.corpus import Corpus, INJECTION_CANARY
from arena.model import MockModel
from arena.runner import RunnerConfig, derive_seed, run_brief, score_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, default=[11, 23, 37, 53, 71])
    parser.add_argument("--out", type=Path, default=Path("runs/ablation.json"))
    args = parser.parse_args()
    corpus = Corpus.generate(seed=42)
    briefs = load_public_briefs()
    variants = {"baseline": "none", "full": "all"}
    variants.update({f"without_{name}": ",".join(
        layer for layer in STACK_ORDER if layer != name
    ) for name in STACK_ORDER})
    summaries = {}
    for variant, spec in variants.items():
        rows = []
        for base_seed in args.seeds:
            for index, brief in enumerate(briefs):
                seed = derive_seed(base_seed, index)
                layers, _ = build_middleware(spec)
                result = run_brief(
                    brief, model=MockModel(corpus=corpus, seed=seed), corpus=corpus,
                    middleware=layers, seed=seed, config=RunnerConfig(),
                )
                score = score_result(result, brief, corpus)
                rows.append({
                    "brief_id": result.brief_id, "seed": seed, "total": score.total,
                    "gate_passed": score.gate_passed, "tool_calls": result.tool_calls,
                    "budget": brief.get("budget", {}).get("max_tool_calls"),
                    "canary_leak": INJECTION_CANARY in json.dumps(result.report),
                    "final_outputs": result.final_outputs, "error": result.error,
                })
        totals = [row["total"] for row in rows]
        summaries[variant] = {
            "mean_total": statistics.mean(totals),
            "stddev_total": statistics.pstdev(totals),
            "gate_failures": sum(not row["gate_passed"] for row in rows),
            "canary_leaks": sum(row["canary_leak"] for row in rows),
            "budget_overruns": sum(row["budget"] is not None
                                   and row["tool_calls"] > row["budget"] for row in rows),
            "missing_finals": sum(row["final_outputs"] == 0 for row in rows),
            "errors": sum(bool(row["error"]) for row in rows), "runs": rows,
        }
        print(f"{variant:28} mean={statistics.mean(totals):6.2f} "
              f"stddev={statistics.pstdev(totals):6.2f}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"seeds": args.seeds, "variants": summaries},
                                   indent=2, ensure_ascii=False), encoding="utf-8")
    full = summaries["full"]
    return int(any(full[key] for key in (
        "gate_failures", "canary_leaks", "budget_overruns", "missing_finals", "errors",
    )))


if __name__ == "__main__":
    raise SystemExit(main())
