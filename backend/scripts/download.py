"""Resumable download with a progress bar: uv run python -m scripts.download URL DEST"""
import sys
from pathlib import Path

import requests
from tqdm import tqdm


def fetch(url: str, dest: Path, chunk: int = 1 << 20) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    have = dest.stat().st_size if dest.exists() else 0
    r = requests.get(url, stream=True, headers={"Accept-Encoding": "identity", **({"Range": f"bytes={have}-"} if have else {})}, timeout=60)
    if r.status_code == 416:  # already complete
        return dest
    r.raise_for_status()
    resumed = r.status_code == 206
    total = int(r.headers.get("content-length", 0)) + (have if resumed else 0)
    with open(dest, "ab" if resumed else "wb") as f, tqdm(total=total or None, initial=have if resumed else 0, unit="B", unit_scale=True, desc=dest.name) as bar:
        for b in r.iter_content(chunk):
            f.write(b)
            bar.update(len(b))
    return dest


if __name__ == "__main__":
    fetch(sys.argv[1], Path(sys.argv[2]))
