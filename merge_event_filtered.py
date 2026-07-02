#!/usr/bin/env python3
"""
merge_event_filtered.py

Improved playlist merger that reads M3U/M3U8 files from a directory (or a specified list),
checks which stream URLs are online, and writes a merged playlist containing only active
streams. The script is configurable via command-line arguments and contains sensible
defaults.

Usage examples:
    python merge_event_filtered.py --playlist-dir playlists --all --output events_merged_filt.m3u
    python merge_event_filtered.py --playlist-dir playlists --targets events.m3u8,rctiplus.m3u --workers 40
"""

    python merge_event_filtered.py --playlist-dir playlists --all --output events_merged_filt.m3u
    python merge_event_filtered.py --playlist-dir playlists --targets events.m3u8,liveeventsfilter.m3u8,rctiplus.m3u --workers 40


from __future__ import annotations
import os
import re
import glob
import argparse
import concurrent.futures
from collections import OrderedDict
from typing import Dict, Tuple, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Default configuration
DEFAULT_PLAYLIST_DIR = "playlists"
DEFAULT_OUTPUT_FILE = "events_merged_filt.m3u"
DEFAULT_TIMEOUT = 8  # seconds
DEFAULT_MAX_WORKERS = 20
DEFAULT_RETRIES = 2
URL_SCHEME_RE = re.compile(r"^(https?|rtmp|rtsp)://\S+", re.IGNORECASE)


def make_session(timeout: int = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES) -> requests.Session:
    """Create a requests Session with a retry policy."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("HEAD", "GET", "OPTIONS"),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def parse_playlists(files: list[str]) -> OrderedDict[str, str]:
    """Parse playlist files and return OrderedDict[url] = extinf_line (first seen).

    Keeps the first EXTINF metadata encountered for each unique URL so the output
    preserves a meaningful title/group where available.
    """
    streams: OrderedDict[str, str] = OrderedDict()
    for file in files:
        print(f"Reading playlist: {file}")
        try:
            with open(file, "r", encoding="utf-8", errors="replace") as fh:
                current_extinf = None
                for raw in fh:
                    line = raw.strip()
                    if not line:
                        continue
                    if line.startswith("#EXTINF"):
                        current_extinf = line
                        continue
                    # If line looks like a URL (http/https/rtmp/rtsp) treat as stream
                    if URL_SCHEME_RE.match(line):
                        url = line.split()[0]
                        if url not in streams:
                            streams[url] = current_extinf or "#EXTINF:-1,Unnamed"
                        current_extinf = None
                    else:
                        # Non-URL non-EXTINF line: ignore, reset current_extinf
                        current_extinf = None
        except FileNotFoundError:
            print(f"Warning: playlist file not found: {file}")
        except Exception as e:
            print(f"Warning: failed to read {file}: {e}")
    return streams


def check_url_online(session: requests.Session, url: str, timeout: int) -> bool:
    """Return True if the URL seems online. Strategy:
    - Try HEAD first (fast), accept success (200 or 206).
    - If HEAD fails or is disallowed, try GET with stream=True and read a small chunk.
    - Consider redirects as long as final status is acceptable.
    """
    try:
        # Some servers block HEAD; allow redirects
        resp = session.head(url, allow_redirects=True, timeout=timeout)
        if resp.status_code in (200, 206):
            return True
        # Some servers return 403/405 for HEAD; fallthrough to GET
    except requests.RequestException:
        # We'll attempt GET below
        pass

    try:
        resp = session.get(url, stream=True, allow_redirects=True, timeout=timeout)
        # Accept 200 or 206 as typically valid for streaming
        if resp.status_code in (200, 206):
            # Try to read a byte to ensure it's serving content (don't hang)
            try:
                _ = next(resp.iter_content(chunk_size=64), None)
                return True
            except Exception:
                return True
        return False
    except requests.RequestException:
        return False


def check_streams(urls: list[str], timeout: int, max_workers: int, retries: int, verbose: bool = False) -> Dict[str, bool]:
    session = make_session(timeout=timeout, retries=retries)
    results: Dict[str, bool] = {}
    total = len(urls)
    print(f"Checking {total} streams with {max_workers} workers (timeout={timeout}s, retries={retries})...")

    def worker(u: str) -> Tuple[str, bool]:
        ok = check_url_online(session, u, timeout)
        if verbose:
            print(f"{'ONLINE ' if ok else 'OFFLINE'} - {u}")
        return u, ok

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(worker, u): u for u in urls}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            u, ok = fut.result()
            results[u] = ok
            if i % 50 == 0 or i == total:
                print(f"Checked {i}/{total}")
    return results


def write_playlist(output_path: str, streams: OrderedDict[str, str], online_map: Dict[str, bool], write_offline_list: Optional[str] = None) -> None:
    """Write the merged playlist containing only online streams.

    Optionally write an offline list with the streams that were filtered out.
    """
    online_count = 0
    with open(output_path, "w", encoding="utf-8") as out:
        out.write("#EXTM3U\n")
        for url, extinf in streams.items():
            if online_map.get(url):
                if extinf:
                    out.write(f"{extinf}\n")
                else:
                    out.write(f"#EXTINF:-1,{url}\n")
                out.write(f"{url}\n")
                online_count += 1
    print(f"Wrote {online_count} online streams to: {output_path}")

    if write_offline_list:
        offline_count = 0
        with open(write_offline_list, "w", encoding="utf-8") as off:
            off.write("#EXTM3U\n")
            for url, extinf in streams.items():
                if not online_map.get(url):
                    off.write(f"{extinf or '#EXTINF:-1,'}\n")
                    off.write(f"{url}\n")
                    offline_count += 1
        print(f"Wrote {offline_count} offline streams to: {write_offline_list}")


def gather_playlist_files(playlist_dir: str, targets: Optional[list[str]], use_all: bool) -> list[str]:
    if targets:
        files = [os.path.join(playlist_dir, t) for t in targets]
    elif use_all:
        pattern = os.path.join(playlist_dir, "**", "*.m3u*")
        files = glob.glob(pattern, recursive=True)
    else:
        files = []
    # Filter existing
    files = [f for f in files if os.path.isfile(f)]
    return files


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Merge M3U playlists and keep only active streams")
    p.add_argument("--playlist-dir", default=DEFAULT_PLAYLIST_DIR, help="Directory containing playlist files")
    p.add_argument("--targets", help="Comma-separated playlist filenames to process (names only, no dir)")
    p.add_argument("--all", action="store_true", help="Process all .m3u/.m3u8 files under playlist-dir recursively")
    p.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Output merged playlist path")
    p.add_argument("--offline-list", default=None, help="Optional file path to save offline streams list")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Per-request timeout in seconds")
    p.add_argument("--workers", type=int, default=DEFAULT_MAX_WORKERS, help="Number of concurrent workers")
    p.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Number of retries for HTTP requests")
    p.add_argument("--verbose", action="store_true", help="Verbose output while checking streams")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.targets:
        targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    else:
        targets = None

    playlist_files = gather_playlist_files(args.playlist_dir, targets, args.all)
    if not playlist_files:
        print("No playlist files found to process. Specify --targets or --all and ensure the directory exists.")
        return

    streams = parse_playlists(playlist_files)
    if not streams:
        print("No streams parsed from playlists.")
        return

    print(f"Total unique streams found: {len(streams)}")

    online_map = check_streams(list(streams.keys()), timeout=args.timeout, max_workers=args.workers, retries=args.retries, verbose=args.verbose)

    write_playlist(args.output, streams, online_map, write_offline_list=args.offline_list)


if __name__ == "__main__":
    main()
