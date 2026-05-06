"""
Curate the multi-step instruction candidates produced by
generate_multistep_questions.py.

For each image, opens the image with the system viewer (macOS `open`)
and walks through every candidate. Keys:

  y   keep this candidate (verdict = "keep")
  n   drop this candidate  (verdict = "drop")
  e   edit instruction / cue inline, then keep
  s   skip (verdict left as None — revisit later)
  q   save and quit

Output: questions/multi_step/<dataset>_curated.jsonl
        Same schema as input, with `human_verdict` and `human_notes` filled.

Re-running with --resume picks up where you left off (entries with
human_verdict already set are skipped).
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_ROOT = REPO_ROOT / "questions"


def open_image(path: Path):
    """Open the image with the OS default viewer (macOS only here)."""
    try:
        subprocess.run(["open", str(path)], check=False)
    except Exception as e:
        print(f"  (could not open image: {e})")


def prompt_key(prompt: str, valid: str) -> str:
    while True:
        try:
            ch = input(prompt).strip().lower()
        except EOFError:
            return "q"
        if ch and ch[0] in valid:
            return ch[0]
        print(f"  invalid; expected one of: {', '.join(valid)}")


def edit_field(label: str, current: str) -> str:
    print(f"    current {label}: {current}")
    new = input(f"    new {label} (blank = keep): ").strip()
    return new if new else current


TASK_DISPLAY = {
    "multi_step": [
        ("verb", "verb"),
        ("instruction", "instruction"),
        ("target_object", "target"),
        ("benign_expected_behavior", "benign_behavior"),
        ("cue", "cue"),
        ("failure_mode", "failure_mode"),
        ("expected_failure", "expected_fail"),
        ("why_human_succeeds", "why_human_ok"),
    ],
    "pick_up": [
        ("target_object", "target"),
        ("rationale", "rationale"),
    ],
    "detection": [
        ("target_object", "target"),
        ("expected_count", "expected_count"),
        ("rationale", "rationale"),
    ],
    "ambiguity": [
        ("query", "query"),
        ("candidates", "matching"),
        ("rationale", "rationale"),
    ],
    "attribute": [
        ("target_object", "target"),
        ("attribute", "attribute"),
        ("expected_answer", "expected_answer"),
        ("rationale", "rationale"),
    ],
}

TASK_EDITABLE = {
    "multi_step": ["instruction", "cue", "expected_failure"],
    "pick_up": ["target_object"],
    "detection": ["target_object", "expected_count"],
    "ambiguity": ["query"],
    "attribute": ["target_object", "attribute", "expected_answer"],
}


def review_candidate(idx: int, total: int, c: dict, task: str) -> dict:
    print(f"\n  --- Candidate {idx}/{total} (id={c.get('id')}) ---")
    for field, label in TASK_DISPLAY.get(task, TASK_DISPLAY["multi_step"]):
        print(f"    {label:18s}: {c.get(field)}")
    if task == "multi_step":
        cc = c.get("constraint_check", {})
        if cc:
            print(f"    C1 physics        : {cc.get('C1_physics')}")
            print(f"    C2 semantic       : {cc.get('C2_semantic')}")
            print(f"    C3 perceptual     : {cc.get('C3_perceptual')}")
            print(f"    C4 task_pres      : {cc.get('C4_task_preservation')}")

    ch = prompt_key("    [y]keep  [n]drop  [e]edit  [s]skip  [q]quit > ", "ynesq")

    if ch == "q":
        return {"_quit": True}
    if ch == "s":
        c["human_verdict"] = None
        return c
    if ch == "n":
        c["human_verdict"] = "drop"
        notes = input("    notes (optional): ").strip()
        if notes:
            c["human_notes"] = notes
        return c
    if ch == "e":
        for field in TASK_EDITABLE.get(task, []):
            c[field] = edit_field(field, str(c.get(field, "")))
        c["human_verdict"] = "keep"
        return c
    # y
    c["human_verdict"] = "keep"
    notes = input("    notes (optional): ").strip()
    if notes:
        c["human_notes"] = notes
    return c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="Dataset name (must match generated JSONL).")
    parser.add_argument(
        "--task",
        default="multi_step",
        choices=["multi_step", "pick_up", "detection", "ambiguity", "attribute"],
        help="Task type (default multi_step).",
    )
    parser.add_argument("--resume", action="store_true", help="Skip candidates already with a verdict.")
    args = parser.parse_args()

    questions_dir = QUESTIONS_ROOT / args.task
    src = questions_dir / f"{args.dataset}.jsonl"
    if not src.exists():
        sys.exit(f"Not found: {src}")
    out = questions_dir / f"{args.dataset}_curated.jsonl"

    if args.resume and out.exists():
        records = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
        print(f"Resume: loaded {len(records)} existing curated records.")
    else:
        records = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]

    total_imgs = len(records)
    quit_now = False

    for i, rec in enumerate(records, 1):
        if quit_now:
            break
        if rec.get("error"):
            print(f"\n[{i}/{total_imgs}] {rec['image']} — generator error, skipping")
            continue

        cands = rec.get("candidates", [])
        if not cands:
            print(f"\n[{i}/{total_imgs}] {rec['image']} — no candidates, skipping")
            continue

        if args.resume and all(c.get("human_verdict") is not None for c in cands):
            continue

        img_full = REPO_ROOT / rec["image"]
        print(f"\n=========================================================")
        print(f"[{i}/{total_imgs}] {rec['image']}")
        print(f"  scene: {rec.get('scene_description', '')}")
        print(f"=========================================================")
        open_image(img_full)

        for j, c in enumerate(cands, 1):
            if args.resume and c.get("human_verdict") is not None:
                continue
            updated = review_candidate(j, len(cands), c, args.task)
            if updated.get("_quit"):
                quit_now = True
                break
            cands[j - 1] = updated

        # Save after every image so partial work survives Ctrl-C / quit
        with out.open("w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    kept = sum(
        1
        for r in records
        for c in r.get("candidates", [])
        if c.get("human_verdict") == "keep"
    )
    dropped = sum(
        1
        for r in records
        for c in r.get("candidates", [])
        if c.get("human_verdict") == "drop"
    )
    pending = sum(
        1
        for r in records
        for c in r.get("candidates", [])
        if c.get("human_verdict") is None
    )
    print(f"\nSaved: {out}")
    print(f"  kept={kept}  dropped={dropped}  pending={pending}")


if __name__ == "__main__":
    main()
