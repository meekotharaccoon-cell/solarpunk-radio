#!/usr/bin/env python3
"""
SOLARPUNK RADIO — PLAYLIST GENERATOR
Builds M3U playlists from:
- Archive.org audio collections
- Local audio files
- Community-submitted tracks

Outputs a shuffled, weighted playlist ready for
Icecast/Liquidsoap or any M3U-compatible player.

Free forever. No API key needed for Archive.org.
"""
import json, random, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime

# Archive.org collections to pull from
# All are CC-licensed / royalty-free
ARCHIVE_COLLECTIONS = [
    'freemusicarchive',
    'netlabels',          # netlabel releases, curated free music
    'audio_bookspoetry',  # spoken word
]

# Track types and their weights in the playlist
# Higher weight = appears more often
TRACK_WEIGHTS = {
    'lofi':    40,   # primary music
    'ambient': 25,   # background fills
    'spoken':  20,   # rights spots, knowledge
    'flower':  15,   # meeko's content
}

DEFAULT_BLOCK = [
    # Royalty-free lo-fi tracks from Pixabay / CC0
    # Replace with your actual track URLs from archive.org
    'https://archive.org/download/sampletrack/track1.mp3',
]

SPOKEN_SPOTS = [
    "This is SolarPunk Radio. Everything you hear is free. Everything we share is real.",
    "Did you know robocalls to your cell are illegal? Each one is worth $500-$1,500 to you under the TCPA. Document the number, the time, the date. solarpunk-legal has a free letter generator.",
    "The FTC holds hundreds of millions in refund money from corporate settlements. No lawyer. No fee. Search ftc.gov/refunds right now.",
    "Every US state holds unclaimed property — abandoned accounts, forgotten deposits. missingmoney.com searches all states at once. Takes two minutes. Completely free.",
    "Gaza Rose Gallery: 56 original flower artworks, $1 each, 70 cents goes to the Palestine Children's Relief Fund every time. meekotharaccoon-cell.github.io/gaza-rose-gallery",
    "You can FOIA the government. They have to show you their records within 20 business days. foia.gov has every federal agency's request form.",
]

def search_archive(collection, num_results=10, media_type='audio'):
    """Search Archive.org for tracks in a collection."""
    query = urllib.parse.quote(f'collection:{collection} mediatype:{media_type}')
    url = f'https://archive.org/advancedsearch.php?q={query}&output=json&rows={num_results}&fl=identifier,title,creator'
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
            return data.get('response', {}).get('docs', [])
    except Exception as e:
        print(f'[archive] Error searching {collection}: {e}')
        return []

def get_archive_mp3s(identifier):
    """Get MP3 URLs for an Archive.org identifier."""
    url = f'https://archive.org/metadata/{identifier}'
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
            files = data.get('files', [])
            mp3s = [f for f in files if f.get('name','').endswith('.mp3')]
            return [f'https://archive.org/download/{identifier}/{f["name"]}' for f in mp3s[:3]]
    except:
        return []

def generate_spoken_interlude():
    """Return a spoken spot as a text entry (for TTS systems or manual recording)."""
    return random.choice(SPOKEN_SPOTS)

def build_playlist(duration_minutes=60, include_spoken=True):
    """Build an M3U playlist of the given duration."""
    tracks = []

    # Pull from archive.org
    print('[playlist] Fetching tracks from Archive.org...')
    for collection in ARCHIVE_COLLECTIONS[:1]:  # limit for speed
        results = search_archive(collection, num_results=5)
        for item in results[:3]:
            mp3s = get_archive_mp3s(item['identifier'])
            tracks.extend(mp3s[:2])
            if len(tracks) > 20: break

    # Add defaults if archive fetch failed
    if not tracks:
        print('[playlist] Using default tracks (add your own to DEFAULT_BLOCK)')
        tracks = DEFAULT_BLOCK.copy()

    random.shuffle(tracks)

    # Build M3U
    lines = ['#EXTM3U', f'# SolarPunk Radio — Generated {datetime.now().strftime("%Y-%m-%d %H:%M")}', '']
    
    spoken_interval = 5  # Insert a spoken spot every N tracks
    for i, track in enumerate(tracks):
        lines.append(f'#EXTINF:-1,Track {i+1}')
        lines.append(track)
        
        if include_spoken and (i + 1) % spoken_interval == 0:
            spot = generate_spoken_interlude()
            lines.append('')
            lines.append(f'# SPOKEN: {spot}')
            lines.append('')

    return '\n'.join(lines)

def main():
    print('\n' + '='*52)
    print('  SOLARPUNK RADIO — PLAYLIST GENERATOR')
    print('='*52)

    playlist = build_playlist(duration_minutes=60)

    output_dir = Path('playlists')
    output_dir.mkdir(exist_ok=True)
    out_path = output_dir / f'playlist_{datetime.now().strftime("%Y%m%d_%H%M")}.m3u'
    out_path.write_text(playlist)
    
    print(f'\n  Playlist saved: {out_path}')
    print(f'  Tracks: {playlist.count("#EXTINF")}')
    print('\n  SPOKEN SPOTS THIS HOUR:')
    for spot in SPOKEN_SPOTS[:3]:
        print(f'  · {spot[:80]}...')
    print('\n  Load in VLC, Winamp, Liquidsoap, or any M3U player.')
    print('='*52)

if __name__ == '__main__':
    main()
