"""Baselines comparison runner.

Runs the 4 conditions (main / random_action / no_memory / one_shot) on
the SAME 20 scenarios so they are directly comparable in a paper table.

Usage:
    python scripts/run_baselines.py <condition> [--model gemini]
    where <condition> is one of: main | random | nomem | oneshot
"""
import json
import os
import sys
import argparse
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS = ["pick_up", "detection", "ambiguity", "attribute", "multi_step"]
PER_TASK = 4   # scenarios per task -> 20 total


def load_scenarios():
    """Pick the first PER_TASK kept candidates per task with distinct images.

    Deterministic so every condition uses the exact same scenario set.
    """
    queue = []
    for task in TASKS:
        fp = REPO_ROOT / "questions" / task / "final_dataset_curated.jsonl"
        if not fp.exists():
            print(f"WARN: missing {fp}", file=sys.stderr)
            continue
        seen_imgs = set()
        picks = 0
        for line in open(fp):
            rec = json.loads(line)
            if rec["image"] in seen_imgs:
                continue
            for c in rec.get("candidates", []):
                if c.get("human_verdict") != "keep":
                    continue
                queue.append((task, os.path.basename(rec["image"]), c))
                seen_imgs.add(rec["image"])
                picks += 1
                break
            if picks >= PER_TASK:
                break
    return queue


def candidate_to_args(task: str, c: dict) -> dict:
    if task == "pick_up":   return {"objects": c["target_object"]}
    if task == "detection": return {"objects": c["target_object"]}
    if task == "ambiguity": return {"objects": c["query"]}
    if task == "attribute": return {"objects": c["target_object"], "attribute": c["attribute"]}
    if task == "multi_step":return {"objects": c["instruction"]}
    raise ValueError(task)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("condition", choices=["main", "random", "nomem", "oneshot"])
    p.add_argument("--model", default="gemini")
    args = p.parse_args()

    queue = load_scenarios()
    print(f"Loaded {len(queue)} scenarios ({PER_TASK} per task across {len(TASKS)} tasks)\n")

    # Per-condition flags
    extra = []
    iters = 10
    if args.condition == "random":
        extra.append("--random-action")
    elif args.condition == "nomem":
        extra.append("--no-memory")
    elif args.condition == "oneshot":
        iters = 1
    # else "main" -> no extra flags, K=10

    print(f"Condition: {args.condition}  model={args.model}  iterations={iters}  extra={extra}\n")

    for i, (task, img, cand) in enumerate(queue, 1):
        kw = candidate_to_args(task, cand)
        cmd = [
            "python", str(REPO_ROOT / "test_main.py"),
            "--task", task,
            "--model", args.model,
            "--image-dir", "final_dataset",
            "--images", img,
            "--objects", kw["objects"],
            "--iterations", str(iters),
        ] + extra
        if "attribute" in kw:
            cmd += ["--attribute", kw["attribute"]]

        print()
        print("=" * 72)
        print(f"[{args.condition}/{args.model}] {i}/{len(queue)}  task={task}  img={img}")
        print(f"  objects={kw['objects']!r}" + (f"  attr={kw['attribute']!r}" if 'attribute' in kw else ""))
        print("=" * 72)
        sys.stdout.flush()
        try:
            subprocess.run(cmd, check=False)
        except KeyboardInterrupt:
            sys.exit(1)


if __name__ == "__main__":
    main()
