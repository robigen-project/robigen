#!/usr/bin/env python3
"""
Generate paper-ready statistics from experiment results.

Produces:
- ASR per task per model with 95% confidence intervals
- Memory ablation comparison table
- Per-scenario "at least one success" rates
- LaTeX-ready tables

Usage:
    python scripts/generate_statistics.py
    python scripts/generate_statistics.py --latex
    python scripts/generate_statistics.py --csv output.csv
"""

import os
import sys
import json
import math
import argparse
from collections import defaultdict

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")


def load_all_summaries():
    """Load all summary.json files from results directory."""
    summaries = []
    if not os.path.exists(RESULTS_DIR):
        return summaries

    for task_model in sorted(os.listdir(RESULTS_DIR)):
        task_model_path = os.path.join(RESULTS_DIR, task_model)
        if not os.path.isdir(task_model_path):
            continue

        for test_name in sorted(os.listdir(task_model_path)):
            test_path = os.path.join(task_model_path, test_name)
            summary_file = os.path.join(test_path, "summary.json")
            if not os.path.exists(summary_file):
                continue
            try:
                with open(summary_file) as f:
                    data = json.load(f)
                data["_task_model"] = task_model
                data["_test_name"] = test_name
                data["_has_memory"] = "_nomem" not in task_model
                summaries.append(data)
            except Exception as e:
                print(f"Error reading {summary_file}: {e}")

    return summaries


def wilson_ci(successes, trials, z=1.96):
    """
    Wilson score confidence interval for a proportion.
    More accurate than normal approximation for small samples.
    Returns (lower, upper) bounds.
    """
    if trials == 0:
        return (0.0, 0.0)

    p_hat = successes / trials
    denom = 1 + z * z / trials
    center = (p_hat + z * z / (2 * trials)) / denom
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * trials)) / trials) / denom

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return (lower, upper)


def compute_asr_table(summaries):
    """Compute ASR per task × model with confidence intervals."""
    # Group by (task, model, has_memory)
    groups = defaultdict(lambda: {"total_iters": 0, "total_tricks": 0, "scenarios": 0,
                                   "at_least_one": 0})

    for s in summaries:
        task = s.get("task_type", "unknown")
        model = s.get("model", "unknown")
        has_mem = s["_has_memory"]
        key = (task, model, has_mem)

        total = s.get("total_iterations", 0)
        tricks = s.get("successful_tricks", 0)

        groups[key]["total_iters"] += total
        groups[key]["total_tricks"] += tricks
        groups[key]["scenarios"] += 1
        if tricks > 0:
            groups[key]["at_least_one"] += 1

    rows = []
    for (task, model, has_mem), stats in sorted(groups.items()):
        total = stats["total_iters"]
        tricks = stats["total_tricks"]
        asr = (tricks / total * 100) if total > 0 else 0
        ci_low, ci_high = wilson_ci(tricks, total)

        scenarios = stats["scenarios"]
        at_least_one = stats["at_least_one"]
        scenario_rate = (at_least_one / scenarios * 100) if scenarios > 0 else 0

        rows.append({
            "task": task,
            "model": model,
            "memory": "yes" if has_mem else "no",
            "scenarios": scenarios,
            "iterations": total,
            "successes": tricks,
            "asr": asr,
            "ci_low": ci_low * 100,
            "ci_high": ci_high * 100,
            "at_least_one": at_least_one,
            "scenario_success_rate": scenario_rate,
        })

    return rows


def compute_ablation_table(summaries):
    """Compare with-memory vs without-memory ASR per task × model."""
    # Group by (task, model)
    groups = defaultdict(lambda: {"mem": {"iters": 0, "tricks": 0},
                                   "nomem": {"iters": 0, "tricks": 0}})

    for s in summaries:
        task = s.get("task_type", "unknown")
        model = s.get("model", "unknown")
        key = (task, model)
        bucket = "mem" if s["_has_memory"] else "nomem"

        groups[key][bucket]["iters"] += s.get("total_iterations", 0)
        groups[key][bucket]["tricks"] += s.get("successful_tricks", 0)

    rows = []
    for (task, model), stats in sorted(groups.items()):
        mem = stats["mem"]
        nomem = stats["nomem"]

        if mem["iters"] == 0 and nomem["iters"] == 0:
            continue

        mem_asr = (mem["tricks"] / mem["iters"] * 100) if mem["iters"] > 0 else 0
        nomem_asr = (nomem["tricks"] / nomem["iters"] * 100) if nomem["iters"] > 0 else 0
        delta = mem_asr - nomem_asr

        rows.append({
            "task": task,
            "model": model,
            "mem_iters": mem["iters"],
            "mem_tricks": mem["tricks"],
            "mem_asr": mem_asr,
            "nomem_iters": nomem["iters"],
            "nomem_tricks": nomem["tricks"],
            "nomem_asr": nomem_asr,
            "delta": delta,
        })

    return rows


def compute_significance_stats(summaries):
    """Compute average significance per task × model."""
    groups = defaultdict(lambda: {"sig_values": [], "count": 0})

    for s in summaries:
        task = s.get("task_type", "unknown")
        model = s.get("model", "unknown")
        key = (task, model)

        for detail in s.get("tricked_details", []):
            sig = detail.get("significance", 0)
            if sig > 0:
                groups[key]["sig_values"].append(sig)
                groups[key]["count"] += 1

    rows = []
    for (task, model), stats in sorted(groups.items()):
        vals = stats["sig_values"]
        if not vals:
            continue
        avg_sig = sum(vals) / len(vals)
        max_sig = max(vals)
        rows.append({
            "task": task,
            "model": model,
            "count": len(vals),
            "avg_significance": round(avg_sig, 1),
            "max_significance": max_sig,
        })

    return rows


# ============================================================================
# Output formatters
# ============================================================================

def print_text_tables(asr_rows, ablation_rows, sig_rows, overall):
    """Print human-readable tables."""
    # ASR Table
    print("\n" + "=" * 90)
    print("ATTACK SUCCESS RATE (ASR) BY TASK × MODEL")
    print("=" * 90)
    print(f"{'Task':<12} {'Model':<12} {'Mem':<5} {'Scen.':<6} {'Iters':<7} {'Tricks':<7} {'ASR':<8} {'95% CI':<16} {'≥1 Succ':<8}")
    print("-" * 90)

    for r in asr_rows:
        ci_str = f"[{r['ci_low']:.1f}%, {r['ci_high']:.1f}%]"
        scen_str = f"{r['at_least_one']}/{r['scenarios']}"
        print(f"{r['task']:<12} {r['model']:<12} {r['memory']:<5} {r['scenarios']:<6} "
              f"{r['iterations']:<7} {r['successes']:<7} {r['asr']:<7.1f}% {ci_str:<16} {scen_str:<8}")

    # Overall
    print("-" * 90)
    print(f"{'OVERALL':<12} {'':<12} {'':<5} {overall['scenarios']:<6} "
          f"{overall['iterations']:<7} {overall['successes']:<7} {overall['asr']:<7.1f}%")

    # Ablation Table
    if any(r["nomem_iters"] > 0 for r in ablation_rows):
        print("\n" + "=" * 90)
        print("MEMORY ABLATION: WITH vs WITHOUT ADVERSARY MEMORY")
        print("=" * 90)
        print(f"{'Task':<12} {'Model':<12} {'Mem ASR':<10} {'NoMem ASR':<10} {'Delta':<8} {'Mem':<12} {'NoMem':<12}")
        print("-" * 90)

        for r in ablation_rows:
            if r["nomem_iters"] == 0:
                continue
            mem_str = f"{r['mem_tricks']}/{r['mem_iters']}"
            nomem_str = f"{r['nomem_tricks']}/{r['nomem_iters']}"
            delta_sign = "+" if r["delta"] > 0 else ""
            print(f"{r['task']:<12} {r['model']:<12} {r['mem_asr']:<9.1f}% {r['nomem_asr']:<9.1f}% "
                  f"{delta_sign}{r['delta']:<7.1f}% {mem_str:<12} {nomem_str:<12}")

    # Significance Table
    if sig_rows:
        print("\n" + "=" * 60)
        print("ATTACK SIGNIFICANCE (SUCCESSFUL ATTACKS ONLY)")
        print("=" * 60)
        print(f"{'Task':<12} {'Model':<12} {'Count':<7} {'Avg Sig':<10} {'Max Sig':<10}")
        print("-" * 60)
        for r in sig_rows:
            print(f"{r['task']:<12} {r['model']:<12} {r['count']:<7} {r['avg_significance']:<10} {r['max_significance']:<10}")

    print()


def generate_latex(asr_rows, ablation_rows, overall):
    """Generate LaTeX table code."""
    lines = []

    # ASR Table
    lines.append("% ASR Table")
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\caption{Attack Success Rate (ASR) by task and model.}")
    lines.append("\\label{tab:asr}")
    lines.append("\\begin{tabular}{llccccc}")
    lines.append("\\toprule")
    lines.append("Task & Model & Scenarios & Iterations & Successes & ASR (\\%) & 95\\% CI \\\\")
    lines.append("\\midrule")

    # Only with-memory rows for main table
    mem_rows = [r for r in asr_rows if r["memory"] == "yes"]
    for r in mem_rows:
        ci = f"[{r['ci_low']:.1f}, {r['ci_high']:.1f}]"
        lines.append(f"{r['task']} & {r['model']} & {r['scenarios']} & {r['iterations']} & "
                      f"{r['successes']} & {r['asr']:.1f} & {ci} \\\\")

    lines.append("\\midrule")
    lines.append(f"\\textbf{{Overall}} & & {overall['scenarios']} & {overall['iterations']} & "
                  f"{overall['successes']} & \\textbf{{{overall['asr']:.1f}}} & \\\\")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    lines.append("")

    # Ablation Table
    ablation_with_data = [r for r in ablation_rows if r["nomem_iters"] > 0]
    if ablation_with_data:
        lines.append("% Memory Ablation Table")
        lines.append("\\begin{table}[t]")
        lines.append("\\centering")
        lines.append("\\caption{Memory ablation: effect of adversary history on attack success.}")
        lines.append("\\label{tab:ablation}")
        lines.append("\\begin{tabular}{llccc}")
        lines.append("\\toprule")
        lines.append("Task & Model & With Memory (\\%) & Without Memory (\\%) & $\\Delta$ \\\\")
        lines.append("\\midrule")

        for r in ablation_with_data:
            delta_sign = "+" if r["delta"] > 0 else ""
            lines.append(f"{r['task']} & {r['model']} & {r['mem_asr']:.1f} & "
                          f"{r['nomem_asr']:.1f} & {delta_sign}{r['delta']:.1f} \\\\")

        lines.append("\\bottomrule")
        lines.append("\\end{tabular}")
        lines.append("\\end{table}")

    return "\n".join(lines)


def generate_csv(asr_rows, output_path):
    """Write ASR data to CSV."""
    import csv
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=asr_rows[0].keys())
        writer.writeheader()
        writer.writerows(asr_rows)
    print(f"CSV written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate paper statistics")
    parser.add_argument("--latex", action="store_true", help="Output LaTeX tables")
    parser.add_argument("--csv", type=str, default=None, help="Write ASR data to CSV file")
    parser.add_argument("--json", type=str, default=None, help="Write all stats to JSON file")
    args = parser.parse_args()

    print("Loading experiment results...")
    summaries = load_all_summaries()

    if not summaries:
        print("No results found. Run some experiments first.")
        return

    print(f"Loaded {len(summaries)} test scenarios.\n")

    # Compute statistics
    asr_rows = compute_asr_table(summaries)
    ablation_rows = compute_ablation_table(summaries)
    sig_rows = compute_significance_stats(summaries)

    # Overall stats (with-memory only)
    mem_summaries = [s for s in summaries if s["_has_memory"]]
    total_iters = sum(s.get("total_iterations", 0) for s in mem_summaries)
    total_tricks = sum(s.get("successful_tricks", 0) for s in mem_summaries)
    overall = {
        "scenarios": len(mem_summaries),
        "iterations": total_iters,
        "successes": total_tricks,
        "asr": (total_tricks / total_iters * 100) if total_iters > 0 else 0,
    }

    # Print text tables
    print_text_tables(asr_rows, ablation_rows, sig_rows, overall)

    # LaTeX output
    if args.latex:
        print("\n" + "=" * 60)
        print("LATEX OUTPUT")
        print("=" * 60)
        print(generate_latex(asr_rows, ablation_rows, overall))

    # CSV output
    if args.csv and asr_rows:
        generate_csv(asr_rows, args.csv)

    # JSON output
    if args.json:
        all_stats = {
            "asr": asr_rows,
            "ablation": ablation_rows,
            "significance": sig_rows,
            "overall": overall,
        }
        with open(args.json, "w") as f:
            json.dump(all_stats, f, indent=2)
        print(f"JSON written to: {args.json}")


if __name__ == "__main__":
    main()
