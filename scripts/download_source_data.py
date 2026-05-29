"""Download policy admin CSVs from Google Drive into data/source/."""

from pathlib import Path

import gdown

FOLDER_URL = "https://drive.google.com/drive/folders/1Zvcr9TATydqPiFwMOMv25f31M-W00i8r"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "source"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    gdown.download_folder(FOLDER_URL, output=str(OUTPUT_DIR), quiet=False, remaining_ok=True)
    print(f"Downloaded to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
