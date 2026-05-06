#!/usr/bin/env python3
"""
Download YCB object dataset images for adversarial testing.

Downloads Google 16k scan archives from the official YCB S3 bucket,
extracts the reference image from each, and saves to datasets/ycb/.
Requires AWS CLI (brew install awscli).
"""

import os
import sys
import subprocess
import tarfile
import tempfile
import glob

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "datasets", "ycb")

YCB_OBJECTS = [
    "002_master_chef_can",
    "003_cracker_box",
    "004_sugar_box",
    "005_tomato_soup_can",
    "006_mustard_bottle",
    "007_tuna_fish_can",
    "008_pudding_box",
    "009_gelatin_box",
    "010_potted_meat_can",
    "011_banana",
    "013_apple",
    "014_lemon",
    "019_pitcher_base",
    "021_bleach_cleanser",
    "024_bowl",
    "025_mug",
    "035_power_drill",
    "037_scissors",
    "040_large_marker",
    "061_foam_brick",
]

S3_BUCKET = "s3://ycb-benchmarks/data/google"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("YCB Dataset Downloader")
    print(f"Output directory: {OUTPUT_DIR}\n")

    # Check AWS CLI
    try:
        subprocess.run(["aws", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("AWS CLI not found. Install with: brew install awscli")
        sys.exit(1)

    downloaded = 0
    skipped = 0

    for obj_name in YCB_OBJECTS:
        # Check if we already have an image for this object
        existing = glob.glob(os.path.join(OUTPUT_DIR, f"{obj_name}.*"))
        if existing:
            skipped += 1
            print(f"  Skipping {obj_name} (already exists)")
            continue

        print(f"  Downloading {obj_name}...", end=" ", flush=True)

        tgz_name = f"{obj_name}_google_16k.tgz"
        s3_path = f"{S3_BUCKET}/{tgz_name}"

        with tempfile.TemporaryDirectory() as tmpdir:
            local_tgz = os.path.join(tmpdir, tgz_name)

            # Download the archive
            try:
                result = subprocess.run(
                    ["aws", "s3", "cp", "--no-sign-request", s3_path, local_tgz],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode != 0:
                    print(f"FAILED (S3 download)")
                    continue
            except subprocess.TimeoutExpired:
                print("TIMEOUT")
                continue

            # Extract and find image files
            try:
                with tarfile.open(local_tgz, "r:gz") as tar:
                    # List members and find image files
                    image_members = [
                        m for m in tar.getmembers()
                        if m.name.lower().endswith((".jpg", ".jpeg", ".png"))
                        and not m.name.startswith("._")
                    ]

                    if not image_members:
                        print("NO IMAGES in archive")
                        continue

                    # Extract first image
                    member = image_members[0]
                    ext = os.path.splitext(member.name)[1]
                    output_path = os.path.join(OUTPUT_DIR, f"{obj_name}{ext}")

                    # Extract to temp, then move
                    tar.extract(member, tmpdir)
                    extracted = os.path.join(tmpdir, member.name)
                    os.rename(extracted, output_path)
                    downloaded += 1
                    print(f"OK ({len(image_members)} images in archive, saved 1)")
            except Exception as e:
                print(f"EXTRACT FAILED ({e})")

    print(f"\nDone! Downloaded: {downloaded}, Skipped: {skipped}")

    # Summary
    total = sum(1 for f in os.listdir(OUTPUT_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg")))
    print(f"Total images in {OUTPUT_DIR}: {total}")

    if total > 0:
        print("\nAvailable images:")
        for f in sorted(os.listdir(OUTPUT_DIR)):
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                print(f"  - {f}")


if __name__ == "__main__":
    main()
