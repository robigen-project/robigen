#!/usr/bin/env python3
"""
Download HOPE dataset preview images from GitHub.

Images are saved to datasets/hope/.
Idempotent: skips already-downloaded files.
"""

import os
import sys
import requests

GITHUB_API_URL = "https://api.github.com/repos/swtyree/hope-dataset/contents/hope-image-preview"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "datasets", "hope")


def get_image_files(api_url):
    """Fetch list of image files from GitHub API."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    response = requests.get(api_url, headers=headers)
    if response.status_code == 403:
        print("ERROR: GitHub API rate limit exceeded.")
        print("Set GITHUB_TOKEN env var to increase limit.")
        sys.exit(1)
    response.raise_for_status()

    items = response.json()

    # If it's a directory listing, recurse into subdirectories
    image_files = []
    directories = []
    for item in items:
        if item["type"] == "file" and item["name"].lower().endswith((".png", ".jpg", ".jpeg")):
            image_files.append(item)
        elif item["type"] == "dir":
            directories.append(item)

    # Recurse into subdirectories
    for d in directories:
        sub_files = get_image_files(d["url"])
        # Prefix with directory name for organization
        for f in sub_files:
            f["_subdir"] = d["name"]
        image_files.extend(sub_files)

    return image_files


def download_file(url, output_path):
    """Download a single file."""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Fetching file list from HOPE dataset...")
    files = get_image_files(GITHUB_API_URL)

    if not files:
        print("No image files found. The repository structure may have changed.")
        print(f"Check: {GITHUB_API_URL}")
        sys.exit(1)

    print(f"Found {len(files)} image files.\n")

    downloaded = 0
    skipped = 0

    for item in files:
        # Organize by subdirectory if present
        subdir = item.get("_subdir", "")
        if subdir:
            target_dir = os.path.join(OUTPUT_DIR, subdir)
            os.makedirs(target_dir, exist_ok=True)
            output_path = os.path.join(target_dir, item["name"])
        else:
            output_path = os.path.join(OUTPUT_DIR, item["name"])

        if os.path.exists(output_path):
            skipped += 1
            continue

        print(f"  Downloading: {item['name']}...", end=" ", flush=True)
        try:
            download_file(item["download_url"], output_path)
            downloaded += 1
            print("OK")
        except Exception as e:
            print(f"FAILED ({e})")

    print(f"\nDone! Downloaded: {downloaded}, Skipped (existing): {skipped}")
    print(f"Images saved to: {OUTPUT_DIR}")

    # List what we have
    total = sum(1 for _, _, files in os.walk(OUTPUT_DIR) for f in files if f.lower().endswith((".png", ".jpg", ".jpeg")))
    print(f"Total images in {OUTPUT_DIR}: {total}")


if __name__ == "__main__":
    main()
