import argparse
import shutil
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def rm(path: Path, dry_run: bool):
    if not path.exists():
        return
    if dry_run:
        print(f"[dry-run] remove: {path}")
        return
    if path.is_file() or path.is_symlink():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path, ignore_errors=True)


def clean_saved_flows(dry_run: bool):
    saved = ROOT / "app" / "saved_flows"
    if saved.exists():
        for p in saved.glob("*.json"):
            rm(p, dry_run)


def clean_generated_flows(dry_run: bool):
    gen = ROOT / "app" / "generated_flows"
    rm(gen, dry_run)
    locs = ROOT / "app" / "locators"
    # keep locators unless forced
    

def clean_recordings(keep_latest: int, dry_run: bool):
    rec = ROOT / "recordings"
    if not rec.exists():
        return
    dirs = [d for d in rec.iterdir() if d.is_dir() and d.name not in {"README.md"}]
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    for d in dirs[keep_latest:]:
        rm(d, dry_run)


def reset_vector_store(dry_run: bool):
    # Remove local Chroma persistence directories
    chroma1 = ROOT / "vector_store"
    chroma2 = ROOT / "chroma_db"
    rm(chroma1, dry_run)
    rm(chroma2, dry_run)


def clean_pycache(dry_run: bool):
    """Remove __pycache__ folders and *.pyc/*.pyo files under the repo root."""
    for p in ROOT.rglob("__pycache__"):
        rm(p, dry_run)
    for ext in ("*.pyc", "*.pyo"):
        for f in ROOT.rglob(ext):
            rm(f, dry_run)


def main():
    parser = argparse.ArgumentParser(description="Cleanup old recordings and artifacts so generator stops referencing stale flows.")
    parser.add_argument("--keep-latest", type=int, default=1, help="Number of most recent recordings to keep")
    parser.add_argument("--clear-saved-flows", action="store_true", help="Delete app/saved_flows/*.json")
    parser.add_argument("--clear-generated", action="store_true", help="Delete app/generated_flows directory")
    parser.add_argument("--reset-vector-store", action="store_true", help="Delete local Chroma/vector_store persistence to force a fresh ingest")
    parser.add_argument("--clear-pycache", action="store_true", help="Delete __pycache__ folders and Python bytecode files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    args = parser.parse_args()

    clean_recordings(args.keep_latest, args.dry_run)
    if args.clear_saved_flows:
        clean_saved_flows(args.dry_run)
    if args.clear_generated:
        clean_generated_flows(args.dry_run)
    if args.reset_vector_store:
        reset_vector_store(args.dry_run)
    if args.clear_pycache:
        clean_pycache(args.dry_run)

    print("Cleanup complete.")


if __name__ == "__main__":
    main()
