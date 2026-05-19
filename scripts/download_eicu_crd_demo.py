#!/usr/bin/env python3
"""Download eICU-CRD demo v2.0.1 from PhysioNet into data/eicu-crd-demo/."""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

DEFAULT_BASE_URL = "https://physionet.org/files/eicu-crd-demo/2.0.1/"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "eicu-crd-demo"

# Apache index: href, optional size (bytes); directories end with size "-"
_INDEX_LINE = re.compile(
    r'<a href="([^"]+)">[^<]*</a>\s+\d{2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}\s+(\d+|-)'
)
_HREF_ONLY = re.compile(r'<a href="([^"]+)">')

USER_AGENT = "ICU-pipeline-eicu-downloader/1.0"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def setup_logging(log_file: Path | None) -> logging.Logger:
    logger = logging.getLogger("eicu_download")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger


def fetch_index(url: str, timeout: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_index(html: str) -> list[tuple[str, int | None]]:
    """Return (href, expected_size) pairs. size is None for subdirectories."""
    entries: list[tuple[str, int | None]] = []
    for line in html.splitlines():
        match = _INDEX_LINE.search(line)
        if not match:
            continue
        href, size_token = match.group(1), match.group(2)
        if href in ("../", "./"):
            continue
        if href.endswith("/"):
            entries.append((href, None))
        else:
            entries.append((href, int(size_token)))
    return entries


def file_complete(path: Path, expected_size: int | None) -> bool:
    if not path.is_file():
        return False
    if expected_size is None:
        return path.stat().st_size > 0
    return path.stat().st_size == expected_size


def download_file(url: str, dest: Path, expected_size: int | None, timeout: int, log: logging.Logger) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    if file_complete(dest, expected_size):
        log.info("skip (complete): %s", dest.relative_to(repo_root()))
        return

    if tmp.is_file() and expected_size is not None and tmp.stat().st_size >= expected_size:
        tmp.replace(dest)
        log.info("renamed partial -> %s", dest.name)
        return

    log.info("download: %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length", 0)) or expected_size
        chunk_size = 1024 * 256
        downloaded = 0
        with open(tmp, "wb") as out:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if total and downloaded % (10 * 1024 * 1024) < chunk_size:
                    pct = 100.0 * downloaded / total
                    log.info("  %s: %.1f%% (%d / %d bytes)", dest.name, pct, downloaded, total)

    if expected_size is not None and tmp.stat().st_size != expected_size:
        raise RuntimeError(
            f"size mismatch for {dest.name}: got {tmp.stat().st_size}, expected {expected_size}"
        )

    tmp.replace(dest)
    log.info("saved: %s (%d bytes)", dest.relative_to(repo_root()), dest.stat().st_size)


def walk_and_download(
    base_url: str,
    out_dir: Path,
    timeout: int,
    log: logging.Logger,
) -> None:
    base_url = base_url if base_url.endswith("/") else base_url + "/"
    html = fetch_index(base_url, timeout)

    entries = parse_index(html)
    if not entries:
        log.warning("no sized entries parsed; falling back to href-only listing")
        for href in _HREF_ONLY.findall(html):
            if href in ("../", "./") or href.startswith("?"):
                continue
            if href.endswith("/"):
                entries.append((href, None))
            else:
                entries.append((href, None))

    for href, expected_size in entries:
        if href.endswith("/"):
            sub_name = href.rstrip("/")
            walk_and_download(urljoin(base_url, href), out_dir / sub_name, timeout, log)
        else:
            download_file(
                urljoin(base_url, href),
                out_dir / href,
                expected_size,
                timeout,
                log,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=DEFAULT_BASE_URL,
        help=f"PhysioNet files base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Log file path (default: <out-dir>/download.log)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="HTTP timeout in seconds (default: 300)",
    )
    args = parser.parse_args()

    out_dir = args.out_dir.resolve()
    log_file = (args.log_file or out_dir / "download.log").resolve()
    log = setup_logging(log_file)

    log.info("eICU-CRD demo download started")
    log.info("source: %s", args.url)
    log.info("destination: %s", out_dir)

    try:
        walk_and_download(args.url, out_dir, args.timeout, log)
    except urllib.error.URLError as exc:
        log.error("network error: %s", exc)
        return 1
    except Exception as exc:
        log.exception("download failed: %s", exc)
        return 1

    log.info("download finished successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
