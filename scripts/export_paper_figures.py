#!/usr/bin/env python3
"""
Export paper-ready figures from experiment results.

Generates:
- Comparison grids: original image → adversarial image → model output text
- ASR bar charts per model per task
- Before/after side-by-side pairs

Usage:
    python scripts/export_paper_figures.py
    python scripts/export_paper_figures.py --top-n 5 --output-dir paper_figures
    python scripts/export_paper_figures.py --task pick_up --model gemini
"""

import os
import sys
import json
import glob
import argparse
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow required: pip install Pillow")
    sys.exit(1)

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")
DEFAULT_OUTPUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "paper_figures")


def find_successful_cases(task_filter=None, model_filter=None):
    """Find all successful attack cases with their image paths."""
    cases = []

    if not os.path.exists(RESULTS_DIR):
        return cases

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
            except Exception:
                continue

            task = data.get("task_type", "unknown")
            model = data.get("model", "unknown")

            if task_filter and task != task_filter:
                continue
            if model_filter and model != model_filter:
                continue

            tricked_iters = data.get("tricked_iterations", [])
            tricked_details = {d.get("iteration"): d for d in data.get("tricked_details", [])}

            for it in tricked_iters:
                iter_dir = os.path.join(test_path, f"iteration_{it}")
                if not os.path.isdir(iter_dir):
                    continue

                # Find original and adversarial images
                original = data.get("image", "")
                adv_images = sorted(glob.glob(os.path.join(iter_dir, "modified_retry_*.png")))
                if not adv_images:
                    adv_images = sorted(glob.glob(os.path.join(iter_dir, "modified_*.png")))

                detail = tricked_details.get(it, {})

                cases.append({
                    "task": task,
                    "model": model,
                    "test_name": test_name,
                    "iteration": it,
                    "original_image": original,
                    "adversarial_image": adv_images[-1] if adv_images else None,
                    "target_object": data.get("target", ""),
                    "significance": detail.get("significance", 0),
                    "categories": detail.get("categories", []),
                    "reason": detail.get("reason", ""),
                    "iter_dir": iter_dir,
                })

    # Sort by significance (highest first)
    cases.sort(key=lambda c: c["significance"], reverse=True)
    return cases


def create_comparison_figure(case, output_path, fig_width=1800):
    """
    Create a side-by-side comparison figure:
    [Original Image] | [Adversarial Image]
    with labels and metadata.
    """
    original_path = case["original_image"]
    adv_path = case["adversarial_image"]

    if not adv_path or not os.path.exists(adv_path):
        return False

    # Load images
    try:
        if original_path and os.path.exists(original_path):
            orig_img = Image.open(original_path).convert("RGB")
        else:
            # Create placeholder
            orig_img = Image.new("RGB", (400, 300), (200, 200, 200))
            draw = ImageDraw.Draw(orig_img)
            draw.text((100, 140), "Original\nNot Found", fill=(100, 100, 100))

        adv_img = Image.open(adv_path).convert("RGB")
    except Exception as e:
        print(f"  Error loading images: {e}")
        return False

    # Resize to same height
    target_h = 400
    img_width = fig_width // 2 - 30  # Leave margin between images

    def resize_to_height(img, h):
        ratio = h / img.height
        return img.resize((int(img.width * ratio), h), Image.LANCZOS)

    orig_resized = resize_to_height(orig_img, target_h)
    adv_resized = resize_to_height(adv_img, target_h)

    # Crop/pad to consistent width
    def crop_or_pad(img, w):
        if img.width > w:
            left = (img.width - w) // 2
            return img.crop((left, 0, left + w, img.height))
        elif img.width < w:
            new = Image.new("RGB", (w, img.height), (255, 255, 255))
            left = (w - img.width) // 2
            new.paste(img, (left, 0))
            return new
        return img

    orig_resized = crop_or_pad(orig_resized, img_width)
    adv_resized = crop_or_pad(adv_resized, img_width)

    # Create figure canvas
    header_h = 60
    caption_h = 80
    total_h = header_h + target_h + caption_h
    canvas = Image.new("RGB", (fig_width, total_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Try to load a font
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except Exception:
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        except Exception:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

    # Header
    draw.text((20, 15), "(a) Original Scene", fill=(0, 0, 0), font=font_large)
    draw.text((fig_width // 2 + 20, 15), "(b) Adversarial Scene", fill=(180, 0, 0), font=font_large)

    # Paste images
    y_offset = header_h
    canvas.paste(orig_resized, (15, y_offset))
    canvas.paste(adv_resized, (fig_width // 2 + 15, y_offset))

    # Draw separator line
    draw.line([(fig_width // 2, header_h), (fig_width // 2, header_h + target_h)],
              fill=(200, 200, 200), width=2)

    # Caption
    caption_y = header_h + target_h + 10
    task_label = case["task"].replace("_", " ").title()
    caption = f"Task: {task_label} | Target: {case['target_object']} | Model: {case['model']}"
    if case["significance"]:
        caption += f" | Significance: {case['significance']}/10"
    draw.text((20, caption_y), caption, fill=(80, 80, 80), font=font_small)

    if case["reason"]:
        reason_short = case["reason"][:120] + "..." if len(case["reason"]) > 120 else case["reason"]
        draw.text((20, caption_y + 25), reason_short, fill=(120, 120, 120), font=font_small)

    # Save
    canvas.save(output_path, "PNG", dpi=(300, 300))
    return True


def create_grid_figure(cases, output_path, cols=3, fig_width=2400):
    """
    Create a grid of comparison figures for paper.
    Each cell shows original → adversarial.
    """
    if not cases:
        return False

    cell_w = fig_width // cols
    cell_h = 350
    header_h = 40
    rows = (len(cases) + cols - 1) // cols
    total_h = rows * (cell_h + header_h + 30) + 20

    canvas = Image.new("RGB", (fig_width, total_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
    except Exception:
        font = ImageFont.load_default()

    for idx, case in enumerate(cases):
        row = idx // cols
        col = idx % cols

        x_base = col * cell_w
        y_base = row * (cell_h + header_h + 30) + 10

        adv_path = case["adversarial_image"]
        if not adv_path or not os.path.exists(adv_path):
            continue

        try:
            adv_img = Image.open(adv_path).convert("RGB")
            # Resize to fit cell
            ratio = min((cell_w - 20) / adv_img.width, cell_h / adv_img.height)
            new_size = (int(adv_img.width * ratio), int(adv_img.height * ratio))
            adv_resized = adv_img.resize(new_size, Image.LANCZOS)

            # Center in cell
            x_offset = x_base + (cell_w - new_size[0]) // 2
            y_offset = y_base + header_h
            canvas.paste(adv_resized, (x_offset, y_offset))

            # Label
            label = f"{case['task']} / {case['model']} / {case['target_object']}"
            draw.text((x_base + 10, y_base + 5), label, fill=(0, 0, 0), font=font)

        except Exception as e:
            draw.text((x_base + 10, y_base + 50), f"Error: {str(e)[:30]}", fill=(200, 0, 0), font=font)

    canvas.save(output_path, "PNG", dpi=(300, 300))
    return True


def main():
    parser = argparse.ArgumentParser(description="Export paper figures")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="Output directory")
    parser.add_argument("--top-n", type=int, default=10, help="Top N cases per task/model")
    parser.add_argument("--task", default=None, help="Filter by task type")
    parser.add_argument("--model", default=None, help="Filter by model")
    parser.add_argument("--grid", action="store_true", help="Also generate grid figure")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print("Finding successful attack cases...")
    cases = find_successful_cases(task_filter=args.task, model_filter=args.model)

    if not cases:
        print("No successful attacks found. Run experiments first.")
        return

    print(f"Found {len(cases)} successful attacks")

    # Group by task/model and take top-N
    groups = {}
    for case in cases:
        key = f"{case['task']}_{case['model']}"
        if key not in groups:
            groups[key] = []
        groups[key].append(case)

    exported = 0
    all_top_cases = []

    for key, group_cases in sorted(groups.items()):
        top = group_cases[:args.top_n]
        all_top_cases.extend(top)

        # Create individual comparison figures
        group_dir = os.path.join(args.output_dir, key)
        os.makedirs(group_dir, exist_ok=True)

        for i, case in enumerate(top):
            output_path = os.path.join(group_dir, f"comparison_{i+1}.png")
            success = create_comparison_figure(case, output_path)
            if success:
                exported += 1
                print(f"  {key}/comparison_{i+1}.png - {case['target_object']} (sig={case['significance']})")

    # Grid figure
    if args.grid and all_top_cases:
        grid_path = os.path.join(args.output_dir, "attack_grid.png")
        # Take top 9 or 12 for a clean grid
        grid_cases = all_top_cases[:12]
        if create_grid_figure(grid_cases, grid_path):
            print(f"\n  Grid figure: {grid_path} ({len(grid_cases)} cases)")

    print(f"\nDone! Exported {exported} comparison figures to {args.output_dir}/")

    # Write index
    index = []
    for case in all_top_cases:
        index.append({
            "task": case["task"],
            "model": case["model"],
            "target": case["target_object"],
            "significance": case["significance"],
            "categories": case["categories"],
            "adversarial_image": case["adversarial_image"],
        })

    index_path = os.path.join(args.output_dir, "index.json")
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2, default=str)
    print(f"Index: {index_path}")


if __name__ == "__main__":
    main()
