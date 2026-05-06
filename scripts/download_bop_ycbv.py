#!/usr/bin/env python3
"""
Download BOP YCB-Video keyframe images for adversarial testing.

Downloads the test keyframe subset (ycbv_test_bop19.zip, ~660MB) from
HuggingFace, extracts RGB scene images, and samples a diverse subset.

The BOP YCB-Video dataset contains multi-object tabletop scenes with
21 YCB household objects — ideal for adversarial manipulation testing.

Usage:
    python scripts/download_bop_ycbv.py
    python scripts/download_bop_ycbv.py --max-images 50
    python scripts/download_bop_ycbv.py --keep-full  # Keep all 900 keyframes
"""

import os
import sys
import shutil
import random
import zipfile
import argparse
import tempfile
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_DIR, "datasets", "bop_ycbv")

# HuggingFace download URL for keyframe test subset
YCBV_TEST_URL = "https://huggingface.co/datasets/bop-benchmark/ycbv/resolve/main/ycbv_test_bop19.zip"
YCBV_TEST_SIZE_MB = 660


def download_file(url, dest_path, desc=""):
    """Download a file with progress indicator."""
    import requests

    print(f"  Downloading {desc or url}...")
    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0

    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded / total * 100
                print(f"\r  {downloaded / 1e6:.0f} MB / {total / 1e6:.0f} MB ({pct:.0f}%)", end="", flush=True)
            else:
                print(f"\r  {downloaded / 1e6:.0f} MB downloaded", end="", flush=True)
    print()
    return dest_path


def extract_rgb_from_zip(zip_path, extract_dir):
    """Extract only RGB images from the BOP zip archive."""
    print("Extracting RGB images from archive...")
    rgb_files = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        all_members = zf.namelist()
        rgb_members = [m for m in all_members if "/rgb/" in m and m.lower().endswith(".png")]
        print(f"  Found {len(rgb_members)} RGB images (out of {len(all_members)} total files)")

        for i, member in enumerate(rgb_members):
            zf.extract(member, extract_dir)
            rgb_files.append(os.path.join(extract_dir, member))
            if (i + 1) % 50 == 0:
                print(f"\r  Extracted {i+1}/{len(rgb_members)}", end="", flush=True)
        if rgb_members:
            print(f"\r  Extracted {len(rgb_members)}/{len(rgb_members)}")

    return rgb_files


def find_rgb_images(base_dir):
    """Find all RGB images in the BOP directory structure."""
    images = []
    for root, dirs, files in os.walk(base_dir):
        if os.path.basename(root) != "rgb":
            continue
        # Get scene ID from parent directory
        scene_dir = os.path.dirname(root)
        scene_id = os.path.basename(scene_dir)
        for f in sorted(files):
            if f.lower().endswith(".png"):
                images.append({
                    "path": os.path.join(root, f),
                    "scene_id": scene_id,
                    "frame": f,
                })
    return images


def sample_diverse_images(images, max_images=50):
    """
    Sample diverse images spread across all scenes.
    Takes evenly from each scene, with random offset for variety.
    """
    # Group by scene
    scenes = {}
    for img in images:
        sid = img["scene_id"]
        if sid not in scenes:
            scenes[sid] = []
        scenes[sid].append(img)

    print(f"  {len(scenes)} scenes: {sorted(scenes.keys())}")
    for sid in sorted(scenes.keys()):
        print(f"    Scene {sid}: {len(scenes[sid])} frames")

    # Allocate images per scene
    per_scene = max(1, max_images // len(scenes)) if scenes else max_images
    remainder = max_images - per_scene * len(scenes)

    sampled = []
    random.seed(42)

    for sid in sorted(scenes.keys()):
        scene_imgs = sorted(scenes[sid], key=lambda x: x["frame"])
        n_take = per_scene + (1 if remainder > 0 else 0)
        if remainder > 0:
            remainder -= 1

        # Sample evenly across the scene's frames
        if n_take >= len(scene_imgs):
            sampled.extend(scene_imgs)
        else:
            step = len(scene_imgs) / n_take
            indices = [int(i * step) for i in range(n_take)]
            sampled.extend(scene_imgs[i] for i in indices)

    # Trim if over
    if len(sampled) > max_images:
        sampled = sampled[:max_images]

    return sampled


def main():
    parser = argparse.ArgumentParser(description="Download BOP YCB-Video keyframes")
    parser.add_argument("--max-images", type=int, default=50,
                        help="Max number of images to keep (default: 50)")
    parser.add_argument("--keep-full", action="store_true",
                        help="Keep all ~900 keyframes (don't sample)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Check if we already have images
    existing = list(Path(OUTPUT_DIR).glob("*.png"))
    if existing:
        print(f"BOP YCB-Video dataset already has {len(existing)} images in {OUTPUT_DIR}")
        print("Delete the directory to re-download.")
        return

    print("=" * 60)
    print("BOP YCB-Video Keyframe Downloader")
    print("=" * 60)
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Source: HuggingFace (ycbv_test_bop19.zip, ~{YCBV_TEST_SIZE_MB}MB)")
    print(f"Target images: {'all' if args.keep_full else args.max_images}\n")

    try:
        import requests
    except ImportError:
        print("Installing requests...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
        import requests

    with tempfile.TemporaryDirectory() as tmpdir:
        # Download the keyframe archive
        zip_path = os.path.join(tmpdir, "ycbv_test_bop19.zip")
        try:
            download_file(YCBV_TEST_URL, zip_path, f"ycbv_test_bop19.zip (~{YCBV_TEST_SIZE_MB}MB)")
        except Exception as e:
            print(f"\nDownload failed: {e}")
            print(f"\nManual download:")
            print(f"  1. Visit: https://huggingface.co/datasets/bop-benchmark/ycbv/tree/main")
            print(f"  2. Download: ycbv_test_bop19.zip")
            print(f"  3. Extract RGB images to: {OUTPUT_DIR}")
            sys.exit(1)

        # Extract RGB images
        extract_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        extract_rgb_from_zip(zip_path, extract_dir)

        # Find all RGB images
        all_images = find_rgb_images(extract_dir)
        if not all_images:
            print("ERROR: No RGB images found in extracted data.")
            sys.exit(1)

        print(f"\nFound {len(all_images)} total RGB keyframe images")

        if args.keep_full:
            selected = all_images
        else:
            print(f"Sampling {args.max_images} diverse images across scenes...")
            selected = sample_diverse_images(all_images, args.max_images)

        # Copy selected images to output directory
        print(f"\nCopying {len(selected)} images to {OUTPUT_DIR}...")
        for img in selected:
            # Name format: scene{scene_id}_{frame}
            clean_name = f"scene{img['scene_id']}_{img['frame']}"
            dest = os.path.join(OUTPUT_DIR, clean_name)
            shutil.copy2(img["path"], dest)

        print(f"\nDone! {len(selected)} images saved to {OUTPUT_DIR}")

    # Final listing
    final_images = sorted(f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".png"))
    print(f"\nTotal images: {len(final_images)}")

    # Show per-scene counts
    scene_counts = {}
    for f in final_images:
        scene = f.split("_")[0]  # "scene000048"
        scene_counts[scene] = scene_counts.get(scene, 0) + 1
    for scene in sorted(scene_counts.keys()):
        print(f"  {scene}: {scene_counts[scene]} images")


if __name__ == "__main__":
    main()
