"""Download claim JSON files from Google Drive into data/claims/.

Google rate-limits anonymous folder downloads, so this lists the folder once
and then downloads only the files that are missing locally, retrying with
backoff. Safe to re-run until all files are present.
"""

import sys
import time
from pathlib import Path

import gdown

FOLDER_URL = "https://drive.google.com/drive/folders/1oIQOxL09UvUmHcX7eo3Zm6yN7BGcdqnb"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "claims"
MAX_PASSES = 30
SLEEP_BETWEEN_PASSES = 15


def list_remote_files():
    """Return the list of files in the Drive folder without downloading them."""
    files = gdown.download_folder(
        FOLDER_URL,
        skip_download=True,
        quiet=True,
        remaining_ok=True,
        output=str(OUTPUT_DIR),
    )
    return files or []


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = list_remote_files()
    if not files:
        print("Could not list the Drive folder (rate limited?). Try again shortly.")
        sys.exit(1)

    total = len(files)
    print(f"Folder lists {total} files.")

    for attempt in range(1, MAX_PASSES + 1):
        missing = [f for f in files if not Path(f.local_path).exists()]
        have = total - len(missing)
        print(f"[pass {attempt}] have {have}/{total}; {len(missing)} missing")

        if not missing:
            print("All files downloaded.")
            return

        for f in missing:
            dest = Path(f.local_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                gdown.download(id=f.id, output=str(dest), quiet=True)
            except Exception as exc:  # noqa: BLE001 - keep going, retry next pass
                print(f"  failed {dest.name}: {exc}")

        time.sleep(SLEEP_BETWEEN_PASSES)

    remaining = [f for f in files if not Path(f.local_path).exists()]
    print(f"Stopped after {MAX_PASSES} passes; {len(remaining)} still missing.")
    sys.exit(1 if remaining else 0)


if __name__ == "__main__":
    main()
