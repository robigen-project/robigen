#!/usr/bin/env python3
"""
Download OCID (Object Clutter Indoor Dataset) for adversarial testing.

Downloads from TU Wien Research Data Repository (OCID-dataset.tar.gz, ~6.8GB),
streams through the archive extracting only RGB table-scene images, and samples
a diverse subset of 50 images.

Usage:
    python scripts/download_ocid.py
    python scripts/download_ocid.py --max-images 50
    python scripts/download_ocid.py --keep-full
"""

import os
import sys
import shutil
import random
import tarfile
import argparse
import tempfile
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_DIR, "datasets", "ocid")

# Direct download URL (discovered from TU Wien API)
TUWIEN_CONTENT_URL = "https://researchdata.tuwien.at/api/records/pcbjd-4wa12/files/OCID-dataset.tar.gz/content"
ARCHIVE_SIZE_GB = 6.8


def download_archive(dest_path):
    """Download the OCID archive from TU Wien."""
    import requests

    print(f"Downloading OCID-dataset.tar.gz (~{ARCHIVE_SIZE_GB}GB)...")
    print("This will take a while. Be patient.\n")

    resp = requests.get(TUWIEN_CONTENT_URL, stream=True, timeout=60)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0

    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded / total * 100
                print(f"\r  {downloaded / 1e9:.2f} GB / {total / 1e9:.2f} GB ({pct:.0f}%)", end="", flush=True)
            else:
                print(f"\r  {downloaded / 1e9:.2f} GB downloaded", end="", flush=True)
    print()
    return dest_path


def extract_rgb_table_images(archive_path, extract_dir):
    """
    Extract only RGB images from table scenes in the OCID tar.gz.
    Filters for: /table/ paths with /rgb/ subdirectory, .png files only.
    """
    print("Scanning archive for table-scene RGB images...")
    extracted = []

    with tarfile.open(archive_path, "r:gz") as tf:
        for member in tf:
            name_lower = member.name.lower()
            # Only extract RGB PNGs from table scenes
            if (member.isfile()
                    and "/table/" in name_lower
                    and "/rgb/" in name_lower
                    and name_lower.endswith(".png")):
                tf.extract(member, extract_dir)
                extracted.append({
                    "path": os.path.join(extract_dir, member.name),
                    "archive_path": member.name,
                })
                if len(extracted) % 100 == 0:
                    print(f"\r  Extracted {len(extracted)} RGB images so far...", end="", flush=True)

    print(f"\r  Extracted {len(extracted)} RGB table-scene images total")
    return extracted


def sample_diverse_images(images, max_images=50):
    """
    Sample diverse images favoring higher clutter levels.

    OCID sequences have objects placed incrementally:
    frames 1-9 = free, 10-16 = touching, 17-20 = stacked.
    We prefer the more cluttered frames (later in each sequence).
    """
    # Group by sequence (everything up to /rgb/)
    sequences = {}
    for img in images:
        parts = img["archive_path"].split("/")
        # Find the rgb/ part and use everything before it as sequence key
        try:
            rgb_idx = parts.index("rgb")
            seq_key = "/".join(parts[:rgb_idx])
        except ValueError:
            seq_key = "unknown"

        if seq_key not in sequences:
            sequences[seq_key] = []
        sequences[seq_key].append(img)

    print(f"  Found {len(sequences)} sequences")

    # From each sequence, prefer the last few frames (most cluttered)
    per_seq = max(1, max_images // len(sequences)) if sequences else max_images
    sampled = []

    for seq_key in sorted(sequences.keys()):
        seq_imgs = sorted(sequences[seq_key], key=lambda x: x["archive_path"])
        n = len(seq_imgs)
        # Take frames from the last third (most objects, most clutter)
        start = max(0, n * 2 // 3)
        cluttered = seq_imgs[start:]
        # Evenly space within that range
        step = max(1, len(cluttered) // per_seq)
        selected = cluttered[::step][:per_seq]
        sampled.extend(selected)

    # Trim to target
    if len(sampled) > max_images:
        random.seed(42)
        sampled = random.sample(sampled, max_images)

    # If too few, add more from remaining
    if len(sampled) < max_images:
        used = set(img["archive_path"] for img in sampled)
        remaining = [img for img in images if img["archive_path"] not in used]
        random.seed(42)
        extra = random.sample(remaining, min(max_images - len(sampled), len(remaining)))
        sampled.extend(extra)

    return sampled


def main():
    parser = argparse.ArgumentParser(description="Download OCID dataset")
    parser.add_argument("--max-images", type=int, default=50,
                        help="Max number of images to keep (default: 50)")
    parser.add_argument("--keep-full", action="store_true",
                        help="Keep all extracted table-scene RGB images")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Check if we already have images
    existing = list(Path(OUTPUT_DIR).glob("*.png"))
    if existing:
        print(f"OCID dataset already has {len(existing)} images in {OUTPUT_DIR}")
        print("Delete the directory to re-download.")
        return

    print("=" * 60)
    print("OCID Dataset Downloader")
    print("=" * 60)
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Source: TU Wien Research Data Repository (~{ARCHIVE_SIZE_GB}GB)")
    print(f"Target images: {'all table scenes' if args.keep_full else args.max_images}\n")

    try:
        import requests
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = os.path.join(tmpdir, "OCID-dataset.tar.gz")

        # Download
        try:
            download_archive(archive_path)
        except Exception as e:
            print(f"\nDownload failed: {e}")
            print(f"\nManual download options:")
            print(f"  1. Visit: https://researchdata.tuwien.at/records/pcbjd-4wa12")
            print(f"  2. Google Drive: https://drive.google.com/drive/folders/1mR_YcmfKqV4R_E6xMt8-yDjLk10w2-fo")
            print(f"\nExtract table-scene RGB images to: {OUTPUT_DIR}")
            sys.exit(1)

        # Extract RGB images from table scenes only
        extract_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        all_images = extract_rgb_table_images(archive_path, extract_dir)

        if not all_images:
            print("ERROR: No RGB table-scene images found.")
            sys.exit(1)

        print(f"\nFound {len(all_images)} total table-scene RGB images")

        if args.keep_full:
            selected = all_images
        else:
            print(f"Sampling {args.max_images} diverse images...")
            selected = sample_diverse_images(all_images, args.max_images)

        # Copy to output directory with clean names
        print(f"\nCopying {len(selected)} images to {OUTPUT_DIR}...")
        for img in selected:
            # Build clean filename from path parts
            parts = img["archive_path"].replace("\\", "/").split("/")
            # Remove 'rgb' from parts for cleaner name
            clean_parts = [p for p in parts if p and p != "rgb" and not p.startswith(".")]
            clean_name = "_".join(clean_parts)
            if not clean_name.endswith(".png"):
                clean_name += ".png"
            dest = os.path.join(OUTPUT_DIR, clean_name)
            shutil.copy2(img["path"], dest)

        print(f"\nDone! {len(selected)} images saved to {OUTPUT_DIR}")

    # Final listing
    final_images = sorted(f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".png"))
    print(f"\nTotal images: {len(final_images)}")
    if len(final_images) <= 10:
        for f in final_images:
            print(f"  - {f}")
    else:
        for f in final_images[:5]:
            print(f"  - {f}")
        print(f"  ... and {len(final_images) - 5} more")


if __name__ == "__main__":
    main()
