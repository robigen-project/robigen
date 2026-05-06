"""
Generate question candidates for the four core tasks (pick_up, detection,
ambiguity, attribute) for each image in a dataset.

For every image, asks Gemini-Flash to propose up to N (default 2) seed
scenarios appropriate for the chosen task. Each scenario is a BENIGN
starting condition — the adversarial cue is generated later by the
SemanticSceneCreationAgent inside the test loop.

Output: one JSONL per (task, dataset) under
        questions/<task>/<dataset>.jsonl
"""

import os
import sys
import json
import argparse
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGES_ROOT = REPO_ROOT / "images"
OUTPUT_ROOT = REPO_ROOT / "questions"


TASK_CONFIGS = {
    "pick_up": {
        "system": """You are a robotics test-case designer.

Propose SIMPLE, single-object grasp targets in the image. The downstream
test asks the robot: "Show the best point to pick up the X." A good
candidate is:
  - A single, clearly visible object that a human could grasp.
  - A specific noun phrase (e.g., "red mug", "Cheez-It box"), not a
    category like "the food".
  - Reachable in the scene (not behind a closed solid door).

BAD candidates: vague references ("the thing"), occluded objects, items
that aren't clearly graspable, or duplicate phrasings of the same object.
""",
        "schema_block": """{
  "id": "<short_unique_id>",
  "target_object": "<specific noun phrase, e.g., 'red mug'>",
  "rationale": "<one sentence on why this is a clean grasp target in this scene>"
}""",
    },
    "detection": {
        "system": """You are a robotics test-case designer.

Propose object classes that can be COUNTED in the image. The downstream
test asks the robot: "Detect all instances of X. How many are there?"
A good candidate is:
  - An object class with a clear, verifiable count (>=1).
  - All instances visible enough that a human could count them confidently.
  - A specific class name (e.g., "banana", "spoon"), not a vague category.

BAD candidates: unclear partial occlusions, classes with only 1 instance
where counting is trivial, or classes whose count is genuinely ambiguous
to a human.
""",
        "schema_block": """{
  "id": "<short_unique_id>",
  "target_object": "<the class to count, e.g., 'banana'>",
  "expected_count": <int — the actual count visible in the image>,
  "rationale": "<one sentence describing the instances and their locations>"
}""",
    },
    "ambiguity": {
        "system": """You are a robotics test-case designer.

Propose AMBIGUOUS queries — short references that match TWO OR MORE
distinct objects in the image. The downstream test gives the robot the
query and expects the robot to ASK FOR CLARIFICATION instead of grabbing
one.

A good candidate has:
  - A short, natural-sounding query like "the mug" or "the can" or
    "the box on the left".
  - At least 2 distinct matching objects clearly visible in the image.
  - The matches differ in some salient way (color, position, brand,
    contents) so clarification is meaningful.

BAD candidates: queries with only one match, or queries so vague they
match dozens of things.
""",
        "schema_block": """{
  "id": "<short_unique_id>",
  "query": "<short ambiguous noun phrase, e.g., 'the mug'>",
  "candidates": ["<distinguishing description 1>", "<distinguishing description 2>", ...],
  "rationale": "<one sentence on why this query is ambiguous>"
}""",
    },
    "attribute": {
        "system": """You are a robotics test-case designer.

Propose (object, attribute) pairs where the attribute is a binary state
of the object visible in the image. The downstream test asks the robot:
"Is the X Y?" and expects a true/false answer.

A good candidate has:
  - A specific object visible in the image.
  - A binary attribute appropriate for that object class
    (e.g., opened/closed, empty/full, damaged/intact, on/off, plugged
    in/unplugged, sealed/unsealed, dirty/clean).
  - The current ground-truth answer is unambiguous from the image.
  - Mix true and false expected answers across candidates.

BAD candidates: attributes whose answer requires guessing (e.g., "is the
mug heavy?"), attributes that don't apply (e.g., "is the apple plugged
in?"), or attributes that are visually impossible to verify.
""",
        "schema_block": """{
  "id": "<short_unique_id>",
  "target_object": "<specific object, e.g., 'milk carton'>",
  "attribute": "<binary state, e.g., 'opened'>",
  "expected_answer": <true | false>,
  "rationale": "<one sentence on what visual evidence determines the answer>"
}""",
    },
}


def build_client():
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    if not project:
        raise SystemExit(
            "GOOGLE_CLOUD_PROJECT not set. Run: export GOOGLE_CLOUD_PROJECT=...\n"
            "Also: gcloud auth application-default login"
        )
    return genai.Client(vertexai=True, project=project, location=location)


def list_images(dataset: str) -> list[Path]:
    d = IMAGES_ROOT / dataset
    if not d.exists():
        raise SystemExit(f"Dataset directory not found: {d}")
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    return sorted([p for p in d.iterdir() if p.suffix.lower() in exts])


def parse_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


def build_user_prompt(task: str, dataset: str, image_path: Path, n: int) -> str:
    cfg = TASK_CONFIGS[task]
    return f"""Image dataset: {dataset}
Image path: {image_path.relative_to(REPO_ROOT)}
Task: {task}

Look carefully at the image. Propose up to {n} candidates appropriate
for this task. Quality > quantity — return fewer strong candidates rather
than padding to {n}. If no good candidate exists, return an empty list.

Return ONLY a JSON object:

{{
  "scene_description": "<one short sentence describing what the robot sees>",
  "candidates": [
    {cfg['schema_block']}
  ]
}}
"""


def generate_for_image(
    client: genai.Client,
    model: str,
    image_path: Path,
    dataset: str,
    task: str,
    n: int,
) -> dict:
    img = Image.open(image_path)
    user_prompt = build_user_prompt(task, dataset, image_path, n)
    response = client.models.generate_content(
        model=model,
        contents=[user_prompt, img],
        config=types.GenerateContentConfig(
            system_instruction=TASK_CONFIGS[task]["system"],
            response_mime_type="application/json",
            temperature=0.7,
        ),
    )
    parsed = parse_response(response.text)

    for c in parsed.get("candidates", []):
        c.setdefault("human_verdict", None)
        c.setdefault("human_notes", "")

    return {
        "image": str(image_path.relative_to(REPO_ROOT)),
        "dataset": dataset,
        "task": task,
        "scene_description": parsed.get("scene_description", ""),
        "candidates": parsed.get("candidates", []),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task",
        required=True,
        choices=list(TASK_CONFIGS.keys()),
        help="Task type to generate questions for.",
    )
    parser.add_argument("--dataset", required=True, help="Dataset folder under images/.")
    parser.add_argument("--n", type=int, default=2, help="Max candidates per image (default 2).")
    parser.add_argument(
        "--model", default="gemini-flash-latest", help="Gemini model id."
    )
    parser.add_argument("--limit", type=int, default=0, help="Process at most N images (0 = all).")
    parser.add_argument("--resume", action="store_true", help="Skip images already in output JSONL.")
    args = parser.parse_args()

    images = list_images(args.dataset)
    if args.limit:
        images = images[: args.limit]

    out_dir = OUTPUT_ROOT / args.task
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.dataset}.jsonl"

    done = set()
    if args.resume and out_path.exists():
        with out_path.open() as f:
            for line in f:
                try:
                    done.add(json.loads(line)["image"])
                except (json.JSONDecodeError, KeyError):
                    pass
        print(f"Resume: {len(done)} images already done; skipping.")

    client = build_client()

    mode = "a" if args.resume else "w"
    with out_path.open(mode) as f:
        for i, img_path in enumerate(images, 1):
            rel = str(img_path.relative_to(REPO_ROOT))
            if rel in done:
                print(f"[{i}/{len(images)}] SKIP {rel}")
                continue
            print(f"[{i}/{len(images)}] {rel} ...", flush=True)
            try:
                record = generate_for_image(
                    client, args.model, img_path, args.dataset, args.task, args.n
                )
                f.write(json.dumps(record) + "\n")
                f.flush()
                print(f"    -> {len(record['candidates'])} candidate(s)")
            except Exception as e:
                print(f"    !! ERROR: {e}", file=sys.stderr)
                err = {
                    "image": rel,
                    "dataset": args.dataset,
                    "task": args.task,
                    "error": str(e),
                    "candidates": [],
                }
                f.write(json.dumps(err) + "\n")
                f.flush()

    print(f"\nDone. Wrote: {out_path}")


if __name__ == "__main__":
    main()
