import os
import glob
import requests
import concurrent.futures

# Konfigurasi
PLAYLIST_DIR = 'playlists'
OUTPUT_FILE = 'events_merged.m3u'
TIMEOUT = 5 # Waktu maksimal (detik) untuk menunggu respons server
MAX_WORKERS = 20 # Jumlah thread paralel (sesuaikan dengan kebutuhan)

def check_stream(extinf_line, url):
    """Mengecek apakah stream URL aktif/online."""
    try:
        # Menggunakan GET dengan stream=True lebih akurat untuk link IPTV
        # karena beberapa server memblokir method HEAD
        response = requests.get(url, stream=True, timeout=TIMEOUT)
        if response.status_code == 200:
            return extinf_line, url
    except requests.RequestException:
        pass
    return None, None

def main():
    # Tentukan nama file yang ingin diproses saja (tanpa path folder)
    TARGET_PLAYLISTS = ['events.m3u8', 'liveeventsfilter.m3u8', 'rctiplus.m3u']
    
    print(f"Memproses {len(TARGET_PLAYLISTS)} playlist yang ditentukan di folder '{PLAYLIST_DIR}/'...")
    
    playlist_files = []
    for file_name in TARGET_PLAYLISTS:
        full_path = os.path.join(PLAYLIST_DIR, file_name)
        # Pastikan filenya benar-benar ada di dalam folder sebelum dimasukkan
        if os.path.exists(full_path):
            playlist_files.append(full_path)
        else:
            print(f"Peringatan: File {file_name} tidak ditemukan di folder '{PLAYLIST_DIR}'")
            
    if not playlist_files:
        print("Tidak ada file playlist yang valid untuk diproses.")
        return

    streams_to_check = []

    
    # Membaca dan mem-parsing semua file M3U
    for file in playlist_files:
        print(f"Memproses file: {file}")
        with open(file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        current_extinf = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#EXTINF'):
                current_extinf = line
            elif line.startswith('http'):
                if current_extinf:
                    streams_to_check.append((current_extinf, line))
                    current_extinf = "" # Reset setelah menemukan URL

    print(f"Total stream yang akan dicek: {len(streams_to_check)}")
    print("Memulai pengecekan status stream (Online/Offline)...")

    valid_streams = []
    
    # Mengecek link secara paralel menggunakan ThreadPool
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit semua tugas
        future_to_url = {executor.submit(check_stream, extinf, url): url for extinf, url in streams_to_check}
        
        for future in concurrent.futures.as_completed(future_to_url):
            extinf, url = future.result()
            if extinf and url:
                valid_streams.append((extinf, url))

    print(f"Selesai! Ditemukan {len(valid_streams)} stream aktif.")

    # Menulis ke file output
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for extinf, url in valid_streams:
            f.write(f"{extinf}\n{url}\n")
            
    print(f"Playlist berhasil disimpan di: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
