import requests
from datetime import datetime
import re

# ===== CONFIGURATION =====
# Add or remove playlist URLs here as needed
PLAYLISTS = [
    "",
    "",
    "https://raw.githubusercontent.com/vinawao/project/refs/heads/main/playlists/rctiplus.m3u"
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

def process_playlist(playlist_content, source_name, outfile):
    """Process and write playlist content to output file"""
    if not playlist_content:
        print(f"   ⚠️  Skipping {source_name}: No content")
        return False
    
    # Create a dictionary to store groups and their channels
    groups = {}
    current_group = "Ungrouped"
    channel_count = 0
    
    # First pass: organize channels by their groups
    i = 0
    while i < len(playlist_content):
        line = playlist_content[i]
        
        # Check if this is a group title line
        if line.startswith("#EXTGRP:"):
            current_group = line.split(':', 1)[1].strip()
            i += 1
            continue
            
        # Check if this is a channel info line
        if line.startswith("#EXTINF"):
            # Extract group-title if it exists
            group_match = re.search(r'group-title="([^"]*)"', line)
            if group_match:
                current_group = group_match.group(1).split(',')[0].strip() or "Ungrouped"
            
            # Get the channel URL (next line)
            if i + 1 < len(playlist_content) and not playlist_content[i+1].startswith('#'):
                channel_url = playlist_content[i+1].strip()
                if channel_url:  # Only add non-empty URLs
                    if current_group not in groups:
                        groups[current_group] = []
                    groups[current_group].append((line, channel_url))
                    channel_count += 1
                i += 2
                continue
        
        i += 1
    
    if not groups:
        print(f"   ⚠️  No valid channels found in {source_name}")
        return False
    
    # Write the playlist header
    outfile.write(f'#PLAYLIST:x {source_name}\n')
    outfile.write(f'#EXTGRP:x {source_name}\n\n')
    
    # Write groups and their channels
    for group, channels in groups.items():
        outfile.write(f'#GROUP:{group}\n')
        for channel_info, channel_url in channels:
            outfile.write(f'{channel_info}\n')
            outfile.write(f'{channel_url}\n')
        outfile.write('\n')
    
    outfile.write('\n' + '='*50 + '\n\n')  # Separator between playlists
    
    print(f"   ✅ Added {source_name}: {channel_count} channels, {len(groups)} groups")
    return True

def main():
    """Main function to combine playlists"""
    print(f"🚀 Starting to combine {len(PLAYLISTS)} playlists...\n")
    
    success_count = 0
    
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:
            # Write header with EPG URL and timestamp
            outfile.write(f'#EXTM3U x-tvg-url="{EPG_URL}"\n')
            outfile.write(f'# Generated on {datetime.utcnow().isoformat()} UTC\n\n')
            
            # Process each playlist
            for idx, url in enumerate(PLAYLISTS, 1):
                print(f"[{idx}/{len(PLAYLISTS)}] 🔄 Processing: {url.split('/')[-1]}")
                content = fetch_playlist(url)
                if content:
                    source_name = get_playlist_name(url)
                    if process_playlist(content, source_name, outfile):
                        success_count += 1
                print()  # Empty line for readability
        
        print(f"\n{'='*60}")
        print(f"🎉 Success! Combined {success_count}/{len(PLAYLISTS)} playlists")
        print(f"📁 Output file: {OUTPUT_FILE}")
        print(f"📺 EPG URL: {EPG_URL}")
        print(f"{'='*60}")
        
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
