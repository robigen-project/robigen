#!/usr/bin/env python3
"""
Run memory ablation study.

Generates commands to run the same scenarios with and without memory,
then compares the results.

Usage:
    # Generate commands
    python scripts/run_ablation.py --generate --task pick_up --model gemini --images first.png --objects "red mug" --iterations 10

    # Compare results after running
    python scripts/run_ablation.py --compare --task pick_up --model gemini
"""

import os
import sys
import json
import argparse
from collections import defaultdict

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")


def generate_commands(args):
    """Generate paired commands for with/without memory runs."""
    base_cmd = f"python test_main.py --task {args.task} --model {args.model}"

    if args.image_dir:
        base_cmd += f" --image-dir {args.image_dir}"

    images_str = " ".join(f'"{img}"' for img in args.images)
    objects_str = " ".join(f'"{obj}"' for obj in args.objects)
    base_cmd += f" --images {images_str} --objects {objects_str} --iterations {args.iterations}"

    if args.attribute:
        base_cmd += f" --attribute {args.attribute}"

    print("=" * 60)
    print("MEMORY ABLATION STUDY - Run these commands:")
    print("=" * 60)
    print(f"\n# WITH memory (control):")
    print(f"{base_cmd}")
    print(f"\n# WITHOUT memory (ablation):")
    print(f"{base_cmd} --no-memory")
    print()


def compare_results(args):
    """Compare with-memory vs without-memory results."""
    with_mem_dir = os.path.join(RESULTS_DIR, f"{args.task}_{args.model}")
    no_mem_dir = os.path.join(RESULTS_DIR, f"{args.task}_{args.model}_nomem")

    def load_summaries(results_dir):
        summaries = []
        if not os.path.exists(results_dir):
            return summaries
        for test_name in os.listdir(results_dir):
            summary_file = os.path.join(results_dir, test_name, "summary.json")
            if os.path.exists(summary_file):
                with open(summary_file) as f:
                    summaries.append(json.load(f))
        return summaries

    with_mem = load_summaries(with_mem_dir)
    no_mem = load_summaries(no_mem_dir)

    print("=" * 60)
    print(f"MEMORY ABLATION RESULTS: {args.task} / {args.model}")
    print("=" * 60)

    for label, summaries, dirname in [("WITH memory", with_mem, with_mem_dir), ("WITHOUT memory", no_mem, no_mem_dir)]:
        if not summaries:
            print(f"\n{label}: No results found in {dirname}")
            continue

        total_iters = sum(s.get("total_iterations", 0) for s in summaries)
        total_tricks = sum(s.get("successful_tricks", 0) for s in summaries)
        asr = (total_tricks / total_iters * 100) if total_iters > 0 else 0
        scenarios = len(summaries)

        print(f"\n{label}:")
        print(f"  Scenarios: {scenarios}")
        print(f"  Total iterations: {total_iters}")
        print(f"  Successful tricks: {total_tricks}")
        print(f"  ASR: {asr:.1f}%")

    print()


def main():
    parser = argparse.ArgumentParser(description="Memory ablation study")
    parser.add_argument("--generate", action="store_true", help="Generate ablation commands")
    parser.add_argument("--compare", action="store_true", help="Compare ablation results")
    parser.add_argument("--task", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--images", nargs="+", default=[])
    parser.add_argument("--objects", nargs="+", default=[])
    parser.add_argument("--image-dir", default=None)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--attribute", default=None)
    args = parser.parse_args()

    if args.generate:
        generate_commands(args)
    elif args.compare:
        compare_results(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
