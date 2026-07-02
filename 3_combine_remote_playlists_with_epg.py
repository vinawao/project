import requests
from datetime import datetime
from pathlib import Path
import re

# ===== CONFIGURATION =====
PLAYLISTS = [
    "https://raw.githubusercontent.com/vinawao/project/refs/heads/main/playlists/events.m3u8",
    "https://raw.githubusercontent.com/vinawao/project/refs/heads/main/playlists/rctiplus.m3u",
    "https://raw.githubusercontent.com/apistech/project/refs/heads/main/IndihomeTV.m3u"
]

# EPG URL
EPG_URL =  "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz", 
 EPG_URL = "https://github.com/apistech/project/raw/refs/heads/main/epgs/guide.xml.gz", 
EPG_URL = "https://github.com/apistech/project/raw/refs/heads/main/epgs/guide.xml.gz" 
          


OUTPUT_DIR = Path("logo")
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "3_combined_playlist.m3u"


# ===== FUNCTIONS =====
def get_playlist_name(url):
    """Extract a clean name from the playlist URL"""
    name = url.split('/')[-1]
    return re.sub(r'(\.m3u8?|\.txt)?$', '', name, flags=re.IGNORECASE).strip() or 'Unnamed_Playlist'

def fetch_playlist(url):
    """Fetch playlist content from URL with better error handling"""
    try:
        print(f" 📡 Fetching from: {url}")
        # Added headers to masquerade as a normal client, helping bypass some basic blocks
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        if not response.text:
            print(f" ⚠️ Warning: Empty response from {url}")
            return None
            
        lines = response.text.splitlines()
        print(f" ✓ Retrieved {len(lines)} lines")
        return lines
        
    except requests.exceptions.Timeout:
        print(f" ❌ Timeout: Request took too long for {url}")
        return None
    except requests.exceptions.HTTPError as e:
        print(f" ❌ HTTP Error ({e.response.status_code}): {url}")
        return None
    except requests.exceptions.ConnectionError:
        print(f" ❌ Connection Error: Cannot reach {url}")
        return None
    except Exception as e:
        print(f" ❌ Error: {type(e).__name__} - {str(e)}")
        return None

def extract_channels_with_metadata(playlist_content):
    """
    Extract channels from playlist by grouping ALL metadata before a URL.
    This guarantees 100% preservation of KODIPROP, EXTVLCOPT, DRM, etc.
    """
    channels = []
    current_block = []
    group_name = "Ungrouped"
    
    for line in playlist_content:
        stripped = line.strip()
        if not stripped:
            continue
            
        # Skip global header so it doesn't duplicate per channel
        if stripped.startswith('#EXTM3U'):
            continue
            
        if stripped.startswith('#'):
            # Collect ANY tag starting with # (EXTINF, KODIPROP, EXTVLCOPT, etc.)
            current_block.append(line)
            
            # Extract group name from EXTINF if present
            if stripped.startswith('#EXTINF'):
                group_match = re.search(r'group-title="([^"]*)"', stripped)
                if group_match:
                    group_title = group_match.group(1).strip()
                    group_name = group_title.split(',')[0].strip() if group_title else "Ungrouped"
        else:
            # We hit a URL! Bind it with the collected metadata block
            channels.append((current_block.copy(), line, group_name))
            
            # Reset block and group name for the next channel
            current_block = []
            group_name = "Ungrouped"
            
    return channels

def process_playlist(playlist_content, source_name, outfile, all_urls_seen):
    """
    Process and write playlist content to output file.
    Deduplicates across playlists based on stream URL.
    """
    if not playlist_content:
        print(f" ⚠️ Skipping {source_name}: No content")
        return False
        
    channels = extract_channels_with_metadata(playlist_content)
    if not channels:
        print(f" ⚠️ No valid channels found in {source_name}")
        return False

    groups = {}
    added_count = 0
    skipped_count = 0

    for current_block, channel_url, group_name in channels:
        clean_url = channel_url.strip()
        
        # Deduplication check
        if clean_url in all_urls_seen:
            skipped_count += 1
            continue
        all_urls_seen.add(clean_url)
        
        if group_name not in groups:
            groups[group_name] = []
        groups[group_name].append((current_block, channel_url))
        added_count += 1

    if not groups:
        print(f" ⚠️ No new channels to add from {source_name} (all duplicates)")
        return False

    # Write source header separators
    outfile.write(f'#PLAYLIST: {source_name}\n')
    outfile.write(f'#EXTGRP: {source_name}\n\n')

    # Write out channels
    for group, group_channels in sorted(groups.items()):
        for current_block, channel_url in group_channels:
            # 1. Write every single metadata line perfectly intact in original order
            for meta_line in current_block:
                outfile.write(meta_line + '\n')
            
            # 2. Write the stream URL
            outfile.write(channel_url)
            if not channel_url.endswith('\n'):
                outfile.write('\n')
            outfile.write('\n')
            
    outfile.write('='*60 + '\n\n') # Separator between playlists

    dedup_msg = f" ({skipped_count} duplicates skipped)" if skipped_count > 0 else ""
    print(f" ✅ Added {source_name}: {added_count} new channels, {len(groups)} groups{dedup_msg}")
    return True

def main():
    print(f"🚀 Starting to combine {len(PLAYLISTS)} playlists...\n")
    success_count = 0
    all_urls_seen = set()
    
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:
            # Write Global Header
            outfile.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
            outfile.write(f'# Generated on {datetime.utcnow().isoformat()} UTC\n')
            outfile.write(f'# Combined from {len(PLAYLISTS)} playlists\n\n')

            for idx, url in enumerate(PLAYLISTS, 1):
                print(f"[{idx}/{len(PLAYLISTS)}] 🔄 Processing: {url.split('/')[-1]}")
                content = fetch_playlist(url)
                if content:
                    source_name = get_playlist_name(url)
                    if process_playlist(content, source_name, outfile, all_urls_seen):
                        success_count += 1
                print() 

        print(f"\n{'='*70}")
        print(f"🎉 Success! Combined {success_count}/{len(PLAYLISTS)} playlists")
        print(f"📁 Output file: {OUTPUT_FILE}")
        print(f"📺 EPG URL: {EPG_URL}")
        print(f"📊 Total unique channels: {len(all_urls_seen)}")
        print(f"✨ All metadata preserved (KODIPROP, EXTVLCOPT, DRM info, Referers, etc)")
        print(f"{'='*70}\n")
        
    except IOError as e:
        print(f"\n❌ Error writing to {OUTPUT_FILE}: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False
        
    return success_count > 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
