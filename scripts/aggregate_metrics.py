"""
Aggregate per-iteration metrics.json files across a run directory.

Usage:
    python scripts/aggregate_metrics.py results/pick_up_gpt/<run_folder>/

Walks all iteration_*/metrics.json under the given directory, averages across
iterations that completed the full 6-step pipeline, and prints per-step means
plus total cost and compute time. Emits a LaTeX stub for the paper.
"""

import glob
import json
import math
import os
import sys

EXPECTED_STEPS = [
    "target_baseline",
    "evaluator_baseline",
    "action",
    "image",
    "target_adversarial",
    "evaluator_adversarial",
]


def load_iterations(run_dir: str):
    """Load all metrics.json files. Return list of dicts."""
    # Support two layouts: run_dir/iteration_*/metrics.json
    # and run_dir/*/iteration_*/metrics.json (scenario-level run dir).
    patterns = [
        os.path.join(run_dir, "iteration_*", "metrics.json"),
        os.path.join(run_dir, "*", "iteration_*", "metrics.json"),
    ]
    paths = []
    for p in patterns:
        paths.extend(glob.glob(p))
    paths = sorted(set(paths))
    results = []
    for p in paths:
        try:
            with open(p) as f:
                results.append((p, json.load(f)))
        except Exception as e:
            print(f"[warn] skip {p}: {e}", file=sys.stderr)
    return results


def is_complete(m: dict) -> bool:
    """An iteration is 'complete' if it recorded at least one entry for each of the 6 steps."""
    names = {s["name"] for s in m.get("steps", [])}
    return all(n in names for n in EXPECTED_STEPS)


def step_sum(m: dict, step_name: str) -> tuple[float, float, int]:
    """Sum elapsed, cost, calls across all entries with the given step name (handles retries)."""
    elapsed = 0.0
    cost = 0.0
    calls = 0
    for s in m.get("steps", []):
        if s["name"] == step_name:
            elapsed += s.get("elapsed_s", 0.0)
            cost += s.get("step_cost_usd", 0.0)
            calls += len(s.get("calls", []))
    return elapsed, cost, calls


def mean_std(xs):
    if not xs:
        return 0.0, 0.0
    n = len(xs)
    mean = sum(xs) / n
    if n < 2:
        return mean, 0.0
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    return mean, math.sqrt(var)


def main():
    if len(sys.argv) < 2:
        print("usage: aggregate_metrics.py <run_dir>", file=sys.stderr)
        sys.exit(1)
    run_dir = sys.argv[1]
    iterations = load_iterations(run_dir)
    if not iterations:
        print(f"no metrics.json files found under {run_dir}", file=sys.stderr)
        sys.exit(1)

    complete = [(p, m) for p, m in iterations if is_complete(m)]
    incomplete = len(iterations) - len(complete)
    print(f"Found {len(iterations)} iterations ({len(complete)} complete, {incomplete} partial)")
    if not complete:
        print("no complete iterations to average", file=sys.stderr)
        sys.exit(1)

    per_step = {n: {"elapsed": [], "cost": [], "calls": []} for n in EXPECTED_STEPS}
    tot_compute = []
    tot_wall = []
    tot_cost = []
    tot_calls = []

    for _, m in complete:
        for step_name in EXPECTED_STEPS:
            e, c, k = step_sum(m, step_name)
            per_step[step_name]["elapsed"].append(e)
            per_step[step_name]["cost"].append(c)
            per_step[step_name]["calls"].append(k)
        totals = m.get("totals", {})
        tot_compute.append(totals.get("compute_time_s", 0.0))
        tot_wall.append(totals.get("wall_clock_s", 0.0))
        tot_cost.append(totals.get("cost_usd", 0.0))
        tot_calls.append(totals.get("api_calls", 0))

    print()
    print(f"{'Step':<24} {'time (s)':>18} {'cost ($)':>14} {'calls':>8}")
    print("-" * 66)
    for step_name in EXPECTED_STEPS:
        e_mean, e_std = mean_std(per_step[step_name]["elapsed"])
        c_mean, _ = mean_std(per_step[step_name]["cost"])
        k_mean, _ = mean_std(per_step[step_name]["calls"])
        print(f"{step_name:<24} {e_mean:>10.2f} ± {e_std:<5.2f} {c_mean:>12.4f}  {k_mean:>7.1f}")
    print("-" * 66)
    cm, cs = mean_std(tot_compute)
    wm, ws = mean_std(tot_wall)
    csm, css = mean_std(tot_cost)
    km, ks = mean_std(tot_calls)
    print(f"{'TOTAL (compute)':<24} {cm:>10.2f} ± {cs:<5.2f} {csm:>12.4f}  {km:>7.1f}")
    print(f"{'TOTAL (wall-clock)':<24} {wm:>10.2f} ± {ws:<5.2f}")
    print()
    print(f"N iterations averaged: {len(complete)}")
    print()

    # LaTeX stub for the paper
    print("=" * 66)
    print("LaTeX stub for \\subsection{Execution Time.}")
    print("=" * 66)
    print()
    print("\\subsection{Execution Time.}")
    print(
        f"Each adversarial iteration issues {km:.0f} API calls across the six-stage "
        f"pipeline (target baseline evaluation, consensus baseline, action planning, "
        f"image generation, target re-evaluation, and consensus re-evaluation) and "
        f"takes on average \\textbf{{{cm:.1f}\\,s}} of compute time "
        f"(std.\\ {cs:.1f}\\,s) at an average cost of "
        f"\\textbf{{\\${csm:.3f}}} per iteration "
        f"(averaged over $N={len(complete)}$ iterations of the "
        f"pick-up task with GPT-4o as the target model). "
        "Table~\\ref{tab:execution_time} reports the per-stage breakdown."
    )
    print()
    print("\\begin{table}[t]")
    print("\\centering")
    print("\\small")
    print("\\begin{tabular}{lrrr}")
    print("\\toprule")
    print("Stage & Time (s) & Cost (\\$) & Calls \\\\")
    print("\\midrule")
    labels = {
        "target_baseline":        "Target (baseline)",
        "evaluator_baseline":     "Consensus (baseline)",
        "action":                 "Action planner",
        "image":                  "Image generation",
        "target_adversarial":     "Target (adversarial)",
        "evaluator_adversarial":  "Consensus (adversarial)",
    }
    for step_name in EXPECTED_STEPS:
        e_mean, e_std = mean_std(per_step[step_name]["elapsed"])
        c_mean, _ = mean_std(per_step[step_name]["cost"])
        k_mean, _ = mean_std(per_step[step_name]["calls"])
        print(f"{labels[step_name]} & {e_mean:.2f} $\\pm$ {e_std:.2f} & {c_mean:.4f} & {k_mean:.1f} \\\\")
    print("\\midrule")
    print(f"\\textbf{{Total}} & \\textbf{{{cm:.2f} $\\pm$ {cs:.2f}}} & \\textbf{{{csm:.4f}}} & \\textbf{{{km:.0f}}} \\\\")
    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\caption{Per-iteration execution time and cost, averaged over "
          f"$N={len(complete)}$ iterations.}}")
    print("\\label{tab:execution_time}")
    print("\\end{table}")


if __name__ == "__main__":
    main()
