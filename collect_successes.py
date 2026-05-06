import os
import json
import shutil
import argparse


def collect_successes(min_significance=0, category=None, top_n=0):
    RESULTS_DIR = "results"
    OUTPUT_DIR = "success_cases"

    # Create main output directory
    if os.path.exists(OUTPUT_DIR):
        print(f"Warning: '{OUTPUT_DIR}' already exists. Merging/Overwriting...")
    else:
        os.makedirs(OUTPUT_DIR)
        print(f"Created '{OUTPUT_DIR}'")

    if not os.path.exists(RESULTS_DIR):
        print(f"Error: '{RESULTS_DIR}' directory not found.")
        return

    count = 0
    all_cases = []  # For index.json and top-n filtering

    # 1. Iterate over Task_Model directories (e.g., pick_up_gemini)
    for task_model in sorted(os.listdir(RESULTS_DIR)):
        task_model_path = os.path.join(RESULTS_DIR, task_model)
        if not os.path.isdir(task_model_path):
            continue

        # 2. Iterate over Test/Object directories (e.g., Red_Bowl_test_3)
        for test_name in sorted(os.listdir(task_model_path)):
            test_path = os.path.join(task_model_path, test_name)
            if not os.path.isdir(test_path):
                continue

            summary_file = os.path.join(test_path, "summary.json")
            if not os.path.exists(summary_file):
                continue

            # 3. Read Summary JSON to find successful iterations
            try:
                with open(summary_file, 'r') as f:
                    data = json.load(f)

                tricked_iterations = data.get("tricked_iterations", [])
                tricked_details = data.get("tricked_details", [])

                if not tricked_iterations:
                    continue

                # Build detail lookup
                detail_map = {}
                for detail in tricked_details:
                    detail_map[detail.get("iteration")] = detail

                for i in tricked_iterations:
                    detail = detail_map.get(i, {})
                    sig = detail.get("significance", 0)
                    cats = detail.get("categories", [])

                    # Filter by significance
                    if min_significance > 0 and sig < min_significance:
                        continue

                    # Filter by category
                    if category and category not in cats:
                        continue

                    case = {
                        "task_model": task_model,
                        "test_name": test_name,
                        "iteration": i,
                        "significance": sig,
                        "categories": cats,
                        "reason": detail.get("reason", ""),
                        "src_path": os.path.join(test_path, f"iteration_{i}"),
                        "image": data.get("image", ""),
                        "target": data.get("target", ""),
                        "task_type": data.get("task_type", ""),
                        "model": data.get("model", ""),
                    }
                    all_cases.append(case)

            except json.JSONDecodeError:
                print(f"  Error reading JSON: {summary_file}")
            except Exception as e:
                print(f"  Error processing {test_name}: {e}")

    # Apply top-n filtering per task_model if requested
    if top_n > 0:
        # Group by task_model, sort by significance desc, take top_n
        grouped = {}
        for case in all_cases:
            key = case["task_model"]
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(case)

        filtered = []
        for key, cases in grouped.items():
            cases.sort(key=lambda c: c["significance"], reverse=True)
            filtered.extend(cases[:top_n])
        all_cases = filtered

    # Copy cases
    for case in all_cases:
        src = case["src_path"]
        if not os.path.exists(src):
            print(f"  Warning: {src} not found, skipping.")
            continue

        dest = os.path.join(OUTPUT_DIR, case["task_model"], case["test_name"], f"iteration_{case['iteration']}")
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

        # Also copy summary.json alongside
        src_summary = os.path.join(os.path.dirname(src), "summary.json")
        if os.path.exists(src_summary):
            dest_summary = os.path.join(OUTPUT_DIR, case["task_model"], case["test_name"], "summary.json")
            if not os.path.exists(dest_summary):
                shutil.copy2(src_summary, dest_summary)

        count += 1

    # Write index.json
    index = []
    for case in all_cases:
        index.append({
            "task_model": case["task_model"],
            "test_name": case["test_name"],
            "iteration": case["iteration"],
            "task_type": case["task_type"],
            "model": case["model"],
            "image": case["image"],
            "target": case["target"],
            "significance": case["significance"],
            "categories": case["categories"],
            "reason": case["reason"][:200],
        })

    index_path = os.path.join(OUTPUT_DIR, "index.json")
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)

    print("\n" + "=" * 50)
    print(f"Done! Copied {count} successful iterations to '{OUTPUT_DIR}/'")
    if min_significance > 0:
        print(f"  Filtered by significance >= {min_significance}")
    if category:
        print(f"  Filtered by category: {category}")
    if top_n > 0:
        print(f"  Top {top_n} per task/model combination")
    print(f"  Index written to: {index_path}")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect successful adversarial cases")
    parser.add_argument("--min-significance", type=float, default=0,
                        help="Only collect cases with significance >= this value")
    parser.add_argument("--category", type=str, default=None,
                        help="Only collect cases matching this failure category")
    parser.add_argument("--top-n", type=int, default=0,
                        help="Collect top N cases per task/model (sorted by significance)")
    args = parser.parse_args()

    collect_successes(
        min_significance=args.min_significance,
        category=args.category,
        top_n=args.top_n,
    )
