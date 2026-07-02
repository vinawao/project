import requests
from datetime import datetime
import re
from urllib.parse import urlparse

# ===== CONFIGURATION =====
# Add or remove playlist URLs here as needed
PLAYLISTS = [
    "https://project.denstv.workers.dev/playlists/tcl.m3u",
    "https://project.denstv.workers.dev/playlists/liveeventsfilter.m3u",
    "https://project.denstv.workers.dev/playlists/rctiplus.m3u"
    # Add more playlists here in the format: "URL_TO_PLAYLIST"
]

# EPG URL
EPG_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"

# Output file
OUTPUT_FILE = "3_combined_playlist.m3u"

# ===== FUNCTIONS =====
def get_playlist_name(url):
    """Extract a clean name from the playlist URL"""
    # Get the last part of URL and remove file extensions
    name = url.split('/')[-1]
    return re.sub(r'(\.m3u8?|\.txt)?$', '', name, flags=re.IGNORECASE).strip() or 'Unnamed_Playlist'

def fetch_playlist(url):
    """Fetch playlist content from URL with better error handling"""
    try:
        print(f"   📡 Fetching from: {url}")
        response = requests.get(url, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        if not response.text:
            print(f"   ⚠️  Warning: Empty response from {url}")
            return None
            
        lines = response.text.splitlines()
        print(f"   ✓ Retrieved {len(lines)} lines")
        return lines
        
    except requests.exceptions.Timeout:
        print(f"   ❌ Timeout: Request took too long for {url}")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"   ❌ HTTP Error ({e.response.status_code}): {url}")
        return None
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Connection Error: Cannot reach {url}")
        return None
    except Exception as e:
        print(f"   ❌ Error: {type(e).__name__} - {str(e)}")
        return None

def extract_channels(playlist_content):
    """
    Extract channels from playlist with proper M3U parsing.
    Returns list of tuples: (extinf_line, channel_url, group_name)
    """
    channels = []
    i = 0
    
    while i < len(playlist_content):
        line = playlist_content[i].strip()
        
        # Skip empty lines and comments (except EXTINF)
        if not line or (line.startswith('#') and not line.startswith('#EXTINF')):
            i += 1
            continue
        
        # Found a channel info line
        if line.startswith('#EXTINF'):
            extinf_line = line
            group_name = "Ungrouped"
            
            # Extract group-title from EXTINF line
            group_match = re.search(r'group-title="([^"]*)"', line)
            if group_match:
                group_title = group_match.group(1).strip()
                # Handle nested groups - take first part before comma
                group_name = group_title.split(',')[0].strip() if group_title else "Ungrouped"
            
            # Get the channel URL (next non-empty, non-comment line)
            i += 1
            while i < len(playlist_content):
                next_line = playlist_content[i].strip()
                if next_line and not next_line.startswith('#'):
                    channels.append((extinf_line, next_line, group_name))
                    i += 1
                    break
                i += 1
        else:
            i += 1
    
    return channels

def process_playlist(playlist_content, source_name, outfile, all_urls_seen):
    """
    Process and write playlist content to output file.
    Avoids duplicate channels across playlists.
    """
    if not playlist_content:
        print(f"   ⚠️  Skipping {source_name}: No content")
        return False
    
    channels = extract_channels(playlist_content)
    
    if not channels:
        print(f"   ⚠️  No valid channels found in {source_name}")
        return False
    
    # Organize by group and deduplicate URLs
    groups = {}
    added_count = 0
    skipped_count = 0
    
    for extinf_line, channel_url, group_name in channels:
        # Skip if we've seen this URL before (deduplication across playlists)
        if channel_url in all_urls_seen:
            skipped_count += 1
            continue
        
        all_urls_seen.add(channel_url)
        
        if group_name not in groups:
            groups[group_name] = []
        groups[group_name].append((extinf_line, channel_url))
        added_count += 1
    
    if not groups:
        print(f"   ⚠️  No new channels to add from {source_name} (all duplicates)")
        return False
    
    # Write playlist header for this source
    outfile.write(f'#PLAYLIST:x {source_name}\n')
    outfile.write(f'#EXTGRP:x {source_name}\n\n')
    
    # Write groups and their channels
    for group, channels in sorted(groups.items()):
        outfile.write(f'#EXTGRP:{group}\n')
        for extinf_line, channel_url in channels:
            outfile.write(f'{extinf_line}\n')
            outfile.write(f'{channel_url}\n')
        outfile.write('\n')
    
    outfile.write('\n' + '='*60 + '\n\n')  # Separator between playlists
    
    dedup_msg = f" ({skipped_count} duplicates skipped)" if skipped_count > 0 else ""
    print(f"   ✅ Added {source_name}: {added_count} new channels, {len(groups)} groups{dedup_msg}")
    return True

def main():
    """Main function to combine playlists"""
    print(f"🚀 Starting to combine {len(PLAYLISTS)} playlists...\n")
    
    success_count = 0
    all_urls_seen = set()  # Track all URLs to avoid duplicates
    
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:
            # Write header with EPG URL and timestamp
            outfile.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
            outfile.write(f'# Generated on {datetime.utcnow().isoformat()} UTC\n')
            outfile.write(f'# Combined from {len(PLAYLISTS)} playlists\n\n')
            
            # Process each playlist
            for idx, url in enumerate(PLAYLISTS, 1):
                print(f"[{idx}/{len(PLAYLISTS)}] 🔄 Processing: {url.split('/')[-1]}")
                content = fetch_playlist(url)
                if content:
                    source_name = get_playlist_name(url)
                    if process_playlist(content, source_name, outfile, all_urls_seen):
                        success_count += 1
                print()  # Empty line for readability
        
        print(f"\n{'='*70}")
        print(f"🎉 Success! Combined {success_count}/{len(PLAYLISTS)} playlists")
        print(f"📁 Output file: {OUTPUT_FILE}")
        print(f"📺 EPG URL: {EPG_URL}")
        print(f"📊 Total unique channels: {len(all_urls_seen)}")
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
