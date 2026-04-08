#!/usr/bin/env python3
"""
SOLARPUNK RADIO -- ARCHIVE MANAGER
Track all aired shows, generate RSS for podcast distribution,
index by contributor/genre/date, CLI interface.

Run:
  python -m agent.archive_manager add-show --name "Dawn Frequencies" --date 2026-04-08 --genre ambient --contributor auto --file playlists/dawn_frequencies_20260408_0600.m3u
  python -m agent.archive_manager list-archive
  python -m agent.archive_manager list-archive --genre ambient
  python -m agent.archive_manager generate-feed

AGPL-3.0 -- Free forever.
"""
import json, sys, hashlib, argparse, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ARCHIVE_PATH = DATA / "archive.json"
FEED_PATH = ROOT / "feed.xml"

STATION_NAME = "SolarPunk Radio"
STATION_URL = "https://github.com/meekotharaccoon-cell/solarpunk-radio"
STATION_DESC = "Community radio for the commons. No ads. No algorithms. All Creative Commons. AGPL-3.0."


# ---------- archive CRUD ----------

def load_archive():
    """Load the show archive from disk."""
    if ARCHIVE_PATH.exists():
        return json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    return {"shows": [], "index": {"by_contributor": {}, "by_genre": {}, "by_date": {}}}


def save_archive(archive):
    """Persist archive to disk."""
    DATA.mkdir(parents=True, exist_ok=True)
    ARCHIVE_PATH.write_text(json.dumps(archive, indent=2), encoding="utf-8")


def add_show(name, date, genre, contributor="auto", file_path=None, description=None):
    """Add an aired show to the archive."""
    archive = load_archive()
    show_id = hashlib.sha256(f"{name}{date}{genre}".encode()).hexdigest()[:12]

    show = {
        "id": show_id,
        "name": name,
        "date": date,
        "genre": genre,
        "contributor": contributor,
        "file": file_path,
        "description": description or f"{name} -- aired {date}, genre: {genre}",
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }

    # Deduplicate by id
    existing_ids = {s["id"] for s in archive["shows"]}
    if show_id in existing_ids:
        print(f"[archive] Show already archived: {show_id}")
        return archive

    archive["shows"].append(show)

    # Update indices
    idx = archive["index"]
    idx["by_contributor"].setdefault(contributor, []).append(show_id)
    idx["by_genre"].setdefault(genre, []).append(show_id)
    idx["by_date"].setdefault(date, []).append(show_id)

    save_archive(archive)
    print(f"[archive] Added: {name} ({date}) [{show_id}]")
    return archive


def list_archive(genre=None, contributor=None, date=None):
    """List archived shows, optionally filtered."""
    archive = load_archive()
    shows = archive["shows"]

    if genre:
        ids = set(archive["index"].get("by_genre", {}).get(genre, []))
        shows = [s for s in shows if s["id"] in ids]
    if contributor:
        ids = set(archive["index"].get("by_contributor", {}).get(contributor, []))
        shows = [s for s in shows if s["id"] in ids]
    if date:
        ids = set(archive["index"].get("by_date", {}).get(date, []))
        shows = [s for s in shows if s["id"] in ids]

    if not shows:
        print("[archive] No shows found matching criteria.")
        return []

    print(f"\n{'=' * 60}")
    print(f"  SOLARPUNK RADIO -- ARCHIVE ({len(shows)} shows)")
    print(f"{'=' * 60}")
    for s in shows:
        print(f"  [{s['id']}] {s['name']}")
        print(f"    Date: {s['date']}  Genre: {s['genre']}  By: {s['contributor']}")
        if s.get("file"):
            print(f"    File: {s['file']}")
        print()
    return shows


# ---------- RSS feed generation ----------

def generate_feed():
    """Generate an RSS 2.0 podcast feed from the archive."""
    archive = load_archive()
    shows = archive["shows"]

    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = STATION_NAME
    ET.SubElement(channel, "link").text = STATION_URL
    ET.SubElement(channel, "description").text = STATION_DESC
    ET.SubElement(channel, "language").text = "en"
    ET.SubElement(channel, "generator").text = "solarpunk-radio/archive_manager"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )

    # iTunes metadata for podcast directories
    itunes_author = ET.SubElement(channel, "itunes:author")
    itunes_author.text = "SolarPunk Radio Collective"
    itunes_category = ET.SubElement(channel, "itunes:category")
    itunes_category.set("text", "Music")
    itunes_explicit = ET.SubElement(channel, "itunes:explicit")
    itunes_explicit.text = "false"
    itunes_summary = ET.SubElement(channel, "itunes:summary")
    itunes_summary.text = STATION_DESC

    # Add episodes (most recent first)
    for show in sorted(shows, key=lambda s: s.get("date", ""), reverse=True):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = f"{show['name']} ({show['date']})"
        ET.SubElement(item, "description").text = show.get("description", "")
        ET.SubElement(item, "pubDate").text = _rfc822_date(show["date"])
        guid = ET.SubElement(item, "guid")
        guid.text = f"{STATION_URL}#show-{show['id']}"
        guid.set("isPermaLink", "false")

        if show.get("file"):
            enclosure = ET.SubElement(item, "enclosure")
            enclosure.set("url", show["file"])
            enclosure.set("type", "audio/mpeg")
            enclosure.set("length", "0")

        ET.SubElement(item, "itunes:duration").text = "01:00:00"
        ET.SubElement(item, "itunes:author").text = show.get("contributor", "auto")

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(FEED_PATH, encoding="unicode", xml_declaration=True)
    print(f"[feed] RSS feed written to {FEED_PATH} ({len(shows)} episodes)")
    return FEED_PATH


def _rfc822_date(date_str):
    """Convert YYYY-MM-DD to RFC 822 date string."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt.strftime("%a, %d %b %Y 12:00:00 +0000")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(
        prog="archive_manager",
        description="SolarPunk Radio -- Show Archive Manager",
    )
    sub = parser.add_subparsers(dest="command")

    # add-show
    add_p = sub.add_parser("add-show", help="Archive an aired show")
    add_p.add_argument("--name", required=True, help="Show name")
    add_p.add_argument("--date", required=True, help="Air date (YYYY-MM-DD)")
    add_p.add_argument("--genre", required=True, help="Genre tag")
    add_p.add_argument("--contributor", default="auto", help="Contributor name")
    add_p.add_argument("--file", default=None, help="Path or URL to audio file")
    add_p.add_argument("--description", default=None, help="Show description")

    # list-archive
    list_p = sub.add_parser("list-archive", help="List archived shows")
    list_p.add_argument("--genre", default=None, help="Filter by genre")
    list_p.add_argument("--contributor", default=None, help="Filter by contributor")
    list_p.add_argument("--date", default=None, help="Filter by date (YYYY-MM-DD)")

    # generate-feed
    sub.add_parser("generate-feed", help="Generate RSS podcast feed")

    args = parser.parse_args()

    if args.command == "add-show":
        add_show(args.name, args.date, args.genre, args.contributor, args.file, args.description)
    elif args.command == "list-archive":
        list_archive(genre=args.genre, contributor=args.contributor, date=args.date)
    elif args.command == "generate-feed":
        generate_feed()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
