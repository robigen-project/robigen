#!/usr/bin/env python3
"""
Analyze failure modes across all experiments.

Reads all summary.json files from results/ and produces:
- Attack Success Rate (ASR) per task per model
- Failure category breakdown per model
- Vulnerability profiles
"""

import os
import json
import sys
from collections import defaultdict

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")


def load_all_summaries():
    """Load all summary.json files from results directory."""
    summaries = []

    if not os.path.exists(RESULTS_DIR):
        print(f"No results directory found at {RESULTS_DIR}")
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
                summaries.append(data)
            except Exception as e:
                print(f"Error reading {summary_file}: {e}")

    return summaries


def compute_asr(summaries):
    """Compute Attack Success Rate per task per model."""
    # Group by task_type and model
    groups = defaultdict(lambda: {"total_iterations": 0, "total_tricks": 0, "scenarios": 0})

    for s in summaries:
        task = s.get("task_type", "unknown")
        model = s.get("model", "unknown")
        key = (task, model)
        total_iters = s.get("total_iterations", 0)
        tricks = s.get("successful_tricks", 0)

        groups[key]["total_iterations"] += total_iters
        groups[key]["total_tricks"] += tricks
        groups[key]["scenarios"] += 1

    return groups


def compute_category_breakdown(summaries):
    """Compute failure category counts per model."""
    # model -> category -> count
    breakdown = defaultdict(lambda: defaultdict(int))

    for s in summaries:
        model = s.get("model", "unknown")
        details = s.get("tricked_details", [])
        for detail in details:
            for cat in detail.get("categories", ["uncategorized"]):
                breakdown[model][cat] += 1

    return breakdown


def print_asr_table(asr_data):
    """Print ASR table."""
    print("\n" + "=" * 70)
    print("ATTACK SUCCESS RATE (ASR) BY TASK AND MODEL")
    print("=" * 70)
    print(f"{'Task':<15} {'Model':<15} {'Scenarios':<10} {'Iters':<8} {'Tricks':<8} {'ASR':<8}")
    print("-" * 70)

    for (task, model), stats in sorted(asr_data.items()):
        total = stats["total_iterations"]
        tricks = stats["total_tricks"]
        asr = (tricks / total * 100) if total > 0 else 0
        print(f"{task:<15} {model:<15} {stats['scenarios']:<10} {total:<8} {tricks:<8} {asr:<7.1f}%")

    print()


def print_category_table(category_data):
    """Print category vulnerability table."""
    if not category_data:
        print("\nNo failure categories found (run more experiments with categorization enabled).")
        return

    print("\n" + "=" * 70)
    print("FAILURE CATEGORY BREAKDOWN BY MODEL")
    print("=" * 70)

    # Collect all categories
    all_categories = set()
    for model_cats in category_data.values():
        all_categories.update(model_cats.keys())

    if not all_categories:
        print("No categories found.")
        return

    # Header
    models = sorted(category_data.keys())
    header = f"{'Category':<30}" + "".join(f"{m:<15}" for m in models)
    print(header)
    print("-" * len(header))

    for cat in sorted(all_categories):
        row = f"{cat:<30}"
        for model in models:
            count = category_data[model].get(cat, 0)
            row += f"{count:<15}"
        print(row)

    print()


def main():
    print("Loading experiment results...")
    summaries = load_all_summaries()

    if not summaries:
        print("No results found. Run some experiments first.")
        return

    print(f"Found {len(summaries)} test scenarios.\n")

    # ASR
    asr_data = compute_asr(summaries)
    print_asr_table(asr_data)

    # Category breakdown
    category_data = compute_category_breakdown(summaries)
    print_category_table(category_data)

    # Summary stats
    total_tricks = sum(s.get("successful_tricks", 0) for s in summaries)
    total_iters = sum(s.get("total_iterations", 0) for s in summaries)
    overall_asr = (total_tricks / total_iters * 100) if total_iters > 0 else 0

    print(f"OVERALL: {total_tricks}/{total_iters} iterations tricked ({overall_asr:.1f}% ASR)")


if __name__ == "__main__":
    main()
