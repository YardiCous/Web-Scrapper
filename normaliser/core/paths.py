from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # the normaliser/ folder
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"                        # generated files (git-ignored)

REAL_DATA_PATHS = [
    str(DATA_DIR / "cartlane.json"),
    str(DATA_DIR / "Tao_Market.json"),
    str(DATA_DIR / "Lazora.json"),
]
