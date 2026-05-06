"""
Per-model runner: walks every kept (image, task, instruction) triple from
questions/<task>/final_dataset_curated.jsonl and invokes test_main.py for it.

Usage:
    python scripts/run_all5_per_model.py <model> [--iterations N]

Single-model design lets us launch 3 workers in parallel (one per model)
under caffeinate so they don't compete for the same results dir.
"""
import json
import os
import sys
import argparse
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS = ["pick_up", "detection", "ambiguity", "attribute", "multi_step"]


def load_kept(task: str):
    """Yield (image_basename, instruction_args_dict) for each kept candidate."""
    fp = REPO_ROOT / "questions" / task / "final_dataset_curated.jsonl"
    if not fp.exists():
        return
    for line in open(fp):
        rec = json.loads(line)
        img = os.path.basename(rec["image"])
        for c in rec.get("candidates", []):
            if c.get("human_verdict") != "keep":
                continue
            yield img, _candidate_to_args(task, c)


def _candidate_to_args(task: str, c: dict) -> dict:
    """Produce the --objects/--attribute CLI args from a curated candidate."""
    if task == "pick_up":
        return {"objects": c["target_object"]}
    if task == "detection":
        # detection takes an object name; expected_count is for evaluation
        return {"objects": c["target_object"]}
    if task == "ambiguity":
        return {"objects": c["query"]}
    if task == "attribute":
        return {"objects": c["target_object"], "attribute": c["attribute"]}
    if task == "multi_step":
        return {"objects": c["instruction"]}
    raise ValueError(f"unknown task {task}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model", help="gemini | gpt | gemini-er-1.6")
    p.add_argument("--iterations", type=int, default=10)
    p.add_argument("--start-from", type=int, default=1,
                   help="1-indexed scenario number to start from (resume after a stall).")
    args = p.parse_args()

    queue = []
    for task in TASKS:
        for img, kwargs in load_kept(task):
            queue.append((task, img, kwargs))

    print(f"Model: {args.model}")
    print(f"Total scenarios queued: {len(queue)}")
    print(f"Iterations per scenario: {args.iterations}")
    print(f"Starting from scenario: {args.start_from}")
    print()

    for i, (task, img, kwargs) in enumerate(queue, 1):
        if i < args.start_from:
            continue
        cmd = [
            "python", str(REPO_ROOT / "test_main.py"),
            "--task", task,
            "--model", args.model,
            "--image-dir", "final_dataset",
            "--images", img,
            "--objects", kwargs["objects"],
            "--iterations", str(args.iterations),
        ]
        if "attribute" in kwargs:
            cmd += ["--attribute", kwargs["attribute"]]

        print()
        print("=" * 72)
        print(f" [{args.model}] {i}/{len(queue)}  task={task}  img={img}")
        print(f"  objects={kwargs['objects']!r}"
              + (f"  attribute={kwargs['attribute']!r}" if "attribute" in kwargs else ""))
        print("=" * 72)
        sys.stdout.flush()

        try:
            subprocess.run(cmd, check=False)
        except KeyboardInterrupt:
            print("\nInterrupted.")
            sys.exit(1)


if __name__ == "__main__":
    main()
