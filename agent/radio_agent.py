#!/usr/bin/env python3
"""
SOLARPUNK RADIO -- STATION AGENT
Manages the full broadcast lifecycle:
  - Show schedule from data/schedule.json
  - Daily playlist generation from schedule + CC music catalogs
  - Listener engagement tracking in data/analytics.json
  - Auto-generated show descriptions and social posts
  - Creative Commons music discovery (Jamendo, Free Music Archive via Archive.org)

Run:  python -m agent.radio_agent
Deps: requests (for Jamendo API), stdlib only for Archive.org

AGPL-3.0 -- Free forever.
"""
import json, os, random, hashlib, urllib.request, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCHEDULE_PATH = DATA / "schedule.json"
ANALYTICS_PATH = DATA / "analytics.json"
PLAYLISTS_DIR = ROOT / "playlists"

# ---------- default schedule seed ----------
DEFAULT_SCHEDULE = {
    "station": "SolarPunk Radio",
    "timezone": "UTC",
    "blocks": [
        {"slot": "06:00-08:00", "name": "Dawn Frequencies",    "genre": "ambient",      "contributor": "auto",      "description": "Ambient wake-up -- CC ambient from the commons."},
        {"slot": "08:00-10:00", "name": "Morning Mesh",        "genre": "lofi",         "contributor": "auto",      "description": "Lo-fi beats while you plan the revolution."},
        {"slot": "10:00-12:00", "name": "Spoken Roots",        "genre": "spoken",       "contributor": "community", "description": "Community-submitted spoken word, poetry, know-your-rights spots."},
        {"slot": "12:00-14:00", "name": "Midday Mycelium",     "genre": "mixed",        "contributor": "auto",      "description": "Genre shuffle -- whatever the mesh delivers."},
        {"slot": "14:00-16:00", "name": "Afternoon Signal",    "genre": "electronic",   "contributor": "auto",      "description": "Electronic / synthwave from netlabels."},
        {"slot": "16:00-18:00", "name": "The Commons Hour",    "genre": "folk",         "contributor": "community", "description": "Folk, acoustic, singer-songwriter -- all CC-licensed."},
        {"slot": "18:00-20:00", "name": "Evening Dispatch",    "genre": "mixed",        "contributor": "auto",      "description": "News remix, interviews, dispatches from the network."},
        {"slot": "20:00-22:00", "name": "Night Garden",        "genre": "ambient",      "contributor": "auto",      "description": "Deep ambient for winding down."},
        {"slot": "22:00-00:00", "name": "Late Transmissions",  "genre": "experimental", "contributor": "auto",      "description": "Experimental / noise / field recordings."},
        {"slot": "00:00-06:00", "name": "Overnight Drift",     "genre": "ambient",      "contributor": "auto",      "description": "Six-hour ambient drift. Sleep well."},
    ]
}

SOCIAL_TEMPLATES = [
    "NOW PLAYING on SolarPunk Radio: {show} -- {desc} Tune in free: solarpunk-radio #CommunityRadio #CreativeCommons",
    "Up next on the mesh: {show}. {desc} No ads. No algorithms. Just signal. #SolarPunkRadio",
    "{show} is LIVE. {desc} Everything you hear is free. #SolarPunk #FreeRadio",
]

# ---------- schedule management ----------

def load_schedule():
    """Load schedule from disk or create default."""
    if SCHEDULE_PATH.exists():
        return json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    DATA.mkdir(parents=True, exist_ok=True)
    SCHEDULE_PATH.write_text(json.dumps(DEFAULT_SCHEDULE, indent=2), encoding="utf-8")
    print(f"[schedule] Created default schedule at {SCHEDULE_PATH}")
    return DEFAULT_SCHEDULE


def current_block(schedule):
    """Return the block matching the current UTC hour."""
    now_hour = datetime.now(timezone.utc).hour
    for block in schedule.get("blocks", []):
        start_str, end_str = block["slot"].split("-")
        start_h = int(start_str.split(":")[0])
        end_h = int(end_str.split(":")[0]) or 24
        if start_h <= now_hour < end_h:
            return block
    return schedule.get("blocks", [{}])[0]


# ---------- music discovery ----------

def search_archive_org(genre, limit=8):
    """Search Archive.org for CC audio by genre keyword."""
    query = urllib.parse.quote(f"subject:{genre} mediatype:audio")
    url = f"https://archive.org/advancedsearch.php?q={query}&output=json&rows={limit}&fl=identifier,title,creator"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
            docs = data.get("response", {}).get("docs", [])
            results = []
            for doc in docs:
                ident = doc.get("identifier", "")
                results.append({
                    "source": "archive.org",
                    "id": ident,
                    "title": doc.get("title", ident),
                    "artist": doc.get("creator", "Unknown"),
                    "url": f"https://archive.org/details/{ident}",
                    "stream": f"https://archive.org/download/{ident}",
                })
            return results
    except Exception as e:
        print(f"[discovery] Archive.org error: {e}")
        return []


def search_jamendo(genre, limit=8):
    """Search Jamendo for CC music. Uses public client ID for discovery."""
    tag = urllib.parse.quote(genre)
    url = (
        f"https://api.jamendo.com/v3.0/tracks/?client_id=b6747d04"
        f"&format=json&limit={limit}&tags={tag}"
        f"&include=musicinfo&order=popularity_total"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
            results = []
            for track in data.get("results", []):
                results.append({
                    "source": "jamendo",
                    "id": str(track.get("id", "")),
                    "title": track.get("name", "Untitled"),
                    "artist": track.get("artist_name", "Unknown"),
                    "url": track.get("shareurl", ""),
                    "stream": track.get("audio", ""),
                    "duration": track.get("duration", 0),
                    "license": track.get("license_ccurl", ""),
                })
            return results
    except Exception as e:
        print(f"[discovery] Jamendo error: {e}")
        return []


def discover_tracks(genre, limit=12):
    """Merge tracks from all discovery sources."""
    tracks = []
    tracks.extend(search_archive_org(genre, limit=limit // 2))
    tracks.extend(search_jamendo(genre, limit=limit // 2))
    random.shuffle(tracks)
    return tracks[:limit]


# ---------- playlist generation ----------

def generate_playlist(block, tracks):
    """Generate an M3U playlist for a scheduled block."""
    PLAYLISTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    slug = block["name"].lower().replace(" ", "_")
    path = PLAYLISTS_DIR / f"{slug}_{ts}.m3u"

    lines = [
        "#EXTM3U",
        f"# SolarPunk Radio -- {block['name']}",
        f"# Generated {ts} UTC",
        f"# Genre: {block.get('genre', 'mixed')}",
        "",
    ]
    for i, t in enumerate(tracks):
        dur = t.get("duration", -1)
        lines.append(f"#EXTINF:{dur},{t['artist']} - {t['title']}")
        lines.append(t.get("stream", t.get("url", "")))
        if (i + 1) % 5 == 0:
            lines.append("")
            lines.append("# -- STATION ID: SolarPunk Radio. Free. No ads. No algorithms. --")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[playlist] Saved: {path} ({len(tracks)} tracks)")
    return path


# ---------- analytics ----------

def load_analytics():
    """Load or initialize analytics store."""
    if ANALYTICS_PATH.exists():
        return json.loads(ANALYTICS_PATH.read_text(encoding="utf-8"))
    return {"days": [], "total_shows": 0, "total_tracks_played": 0, "contributors": {}}


def record_play(analytics, block, track_count):
    """Record a block play event."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = {
        "date": today,
        "show": block["name"],
        "genre": block.get("genre", "mixed"),
        "tracks": track_count,
        "contributor": block.get("contributor", "auto"),
    }
    analytics["days"].append(entry)
    analytics["total_shows"] += 1
    analytics["total_tracks_played"] += track_count
    contrib = block.get("contributor", "auto")
    analytics["contributors"][contrib] = analytics["contributors"].get(contrib, 0) + 1
    DATA.mkdir(parents=True, exist_ok=True)
    ANALYTICS_PATH.write_text(json.dumps(analytics, indent=2), encoding="utf-8")
    return analytics


# ---------- social / descriptions ----------

def generate_social_post(block):
    """Generate a social media post for the current block."""
    template = random.choice(SOCIAL_TEMPLATES)
    return template.format(show=block["name"], desc=block.get("description", ""))


def generate_show_description(block, tracks):
    """Generate a human-readable show description."""
    artists = list({t["artist"] for t in tracks if t.get("artist", "Unknown") != "Unknown"})[:5]
    artist_str = ", ".join(artists) if artists else "various CC artists"
    return (
        f"{block['name']} ({block['slot']} UTC)\n"
        f"{block.get('description', '')}\n"
        f"Featuring: {artist_str}\n"
        f"Tracks: {len(tracks)} | Genre: {block.get('genre', 'mixed')}\n"
        f"All music is Creative Commons licensed. Free to listen, free to share."
    )


# ---------- main agent loop ----------

def run():
    """Execute one radio agent cycle: load schedule, discover music, generate playlist, log."""
    print("\n" + "=" * 56)
    print("  SOLARPUNK RADIO -- STATION AGENT")
    print("=" * 56)

    schedule = load_schedule()
    block = current_block(schedule)
    print(f"\n  Current block: {block['name']} ({block['slot']})")
    print(f"  Genre: {block.get('genre', 'mixed')}")
    print(f"  Contributor: {block.get('contributor', 'auto')}")

    # Discover tracks
    genre = block.get("genre", "mixed")
    if genre == "mixed":
        genre = random.choice(["lofi", "ambient", "electronic", "folk"])
    tracks = discover_tracks(genre, limit=12)
    print(f"  Discovered: {len(tracks)} tracks")

    # Generate playlist
    if tracks:
        playlist_path = generate_playlist(block, tracks)
    else:
        print("  [warn] No tracks found, skipping playlist generation")
        playlist_path = None

    # Show description
    desc = generate_show_description(block, tracks)
    print(f"\n--- SHOW DESCRIPTION ---\n{desc}\n")

    # Social post
    post = generate_social_post(block)
    print(f"--- SOCIAL POST ---\n{post}\n")

    # Analytics
    analytics = load_analytics()
    record_play(analytics, block, len(tracks))
    print(f"  Total shows logged: {analytics['total_shows']}")
    print(f"  Total tracks played: {analytics['total_tracks_played']}")

    print("\n" + "=" * 56)
    return {
        "block": block["name"],
        "tracks": len(tracks),
        "playlist": str(playlist_path) if playlist_path else None,
        "social_post": post,
    }


if __name__ == "__main__":
    run()
