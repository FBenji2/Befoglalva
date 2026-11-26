#!/usr/bin/env python3
"""Download Google My Maps placemark photos from a KML or KMZ export.

Supports NetworkLink KMZ files by fetching their linked KML in memory.

Usage:
    python backup_mymaps.py

Dependencies:
    pip install requests pillow
"""

import argparse
import csv
from email.message import Message
from email import policy
import re
from urllib.parse import unquote
import io
import sys
import time
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image

import requests

DEFAULT_FOLDER_PATH = "Képek"
KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


CSV_URLS = [
    "https://www.google.com/maps/d/csv?mid=1hjOcx3VIAH9MZLk4EHSbGdCHQHe35R0&lid=LrJCwzgIg1s&cid=mp&cv=ZUs_2CdilBg.en_GB.",
    "https://www.google.com/maps/d/csv?mid=1hjOcx3VIAH9MZLk4EHSbGdCHQHe35R0&lid=HR65bL9sW5E&cid=mp&cv=ZUs_2CdilBg.en_GB.",
    "https://www.google.com/maps/d/csv?mid=1hjOcx3VIAH9MZLk4EHSbGdCHQHe35R0&lid=w6rptsxLgFQ&cid=mp&cv=ZUs_2CdilBg.en_GB."
]


def download_csv(session, url, folder):
    response = session.get(url, timeout=60)
    response.raise_for_status()
    disposition = response.headers.get("Content-Disposition", "")
    # Prefer RFC 5987 filename* over the ASCII fallback filename.
    extended = re.search(
        r'(?:^|;)\s*filename\*\s*=\s*(?:"([^"]*)"|([^;]*))', disposition, re.IGNORECASE)
    if extended:
        encoded = (extended.group(1) or extended.group(2)).strip()
        charset, language, value = encoded.split("'", 2)
        filename = unquote(value, encoding=charset or "utf-8", errors="strict")
    else:
        message = Message(policy=policy.default)
        message["Content-Disposition"] = disposition
        filename = message.get_filename()
    if not filename:
        raise ValueError("Google did not supply a CSV filename")
    filename = re.sub(r"^Befoglalva\s*-\s*", "", filename).strip()
    if not filename.lower().endswith(".csv") or any(c in filename for c in ("/", "\\", ":", "\x00")):
        raise ValueError(f"Invalid CSV filename: {filename!r}")
    text = response.content.decode("utf-8-sig")
    if text.lstrip().startswith("<") or "text/html" in response.headers.get("Content-Type", "").lower():
        raise ValueError("Google returned HTML instead of CSV")
    header = next(csv.reader(io.StringIO(text)), [])
    if len(header) < 2:
        raise ValueError("Missing or invalid CSV header")
    destination = folder / filename
    if destination.is_file() and destination.read_bytes() == response.content:
        print(f"  CSV unchanged: {filename}")
        return
    tmp = destination.with_name(destination.name + ".part")
    try:
        tmp.write_bytes(response.content)
        tmp.replace(destination)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"  CSV updated: {filename}")


def read_kml(path):
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist(
            ) if name.lower().endswith(".kml")]
            if not names:
                raise ValueError("KMZ contains no KML file")
            selected = next((n for n in names if Path(
                n).name.lower() == "doc.kml"), names[0])
            return archive.read(selected)
    return path.read_bytes()


def resolve_network_links(kml_bytes, session, max_depth=5):
    """Follow KML NetworkLinks in order, returning a root with all placemarks.

    Downloads stay in memory. Supports linked KML and KMZ responses.
    """
    seen = set()
    combined = ET.Element(f"{{{KML_NS['kml']}}}kml")

    def visit(data, depth):
        if depth > max_depth:
            raise ValueError("Too many nested NetworkLinks")
        if data[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                candidates = [n for n in archive.namelist()
                              if n.lower().endswith(".kml")]
                if not candidates:
                    raise ValueError("Linked KMZ contains no KML")
                selected = next((n for n in candidates if Path(
                    n).name.lower() == "doc.kml"), candidates[0])
                data = archive.read(selected)
        root = ET.fromstring(data)
        # Collect placemarks from this document before following its links.
        for placemark in root.findall(".//kml:Placemark", KML_NS):
            combined.append(placemark)
        for link in root.findall(".//kml:NetworkLink", KML_NS):
            href = link.find("./kml:Link/kml:href", KML_NS)
            if href is None:
                href = link.find("./kml:Url/kml:href", KML_NS)
            if href is None or not href.text or not href.text.strip():
                continue
            url = href.text.strip()
            if not url.startswith(("https://", "http://")):
                print(
                    f"  Ignoring non-HTTP NetworkLink: {url}", file=sys.stderr)
                continue
            if url in seen:
                continue
            seen.add(url)
            print(f"Fetching linked map: {url}")
            response = session.get(url, timeout=60)
            response.raise_for_status()
            visit(response.content, depth + 1)

    visit(kml_bytes, 0)
    return combined


def get_urls(placemark):
    """Read image URLs ONLY from ExtendedData/gx_media_links, in listed order."""
    urls = []
    for data in placemark.findall("./kml:ExtendedData/kml:Data", KML_NS):
        if data.get("name") != "gx_media_links":
            continue
        value = data.find("kml:value", KML_NS)
        if value is not None and value.text:
            # My Maps separates image URLs with whitespace in this field.
            urls.extend(url for url in value.text.split()
                        if url.startswith(("https://", "http://")))
    return urls


def get_coordinates(placemark):
    node = placemark.find(".//kml:Point/kml:coordinates", KML_NS)
    if node is None or not node.text:
        return None
    parts = node.text.strip().split(",")
    if len(parts) < 2:
        return None
    # Preserve the original precision, but name files latitude,longitude.
    return f"{parts[1].strip()},{parts[0].strip()}"


def download_image(session, url, destination, timeout=35):
    # Download into memory and only write after verifying an image response.
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get(
        "Content-Type", "").split(";")[0].strip().lower()
    data = response.content
    if not content_type.startswith("image/"):
        raise ValueError(
            f"URL returned {content_type or 'unknown content type'}, not an image")
    # Preserve the requested .png extension by converting JPEG/WebP/etc to PNG.
    # Pillow is needed for conversion; it also validates the image.
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
        tmp = destination.with_name(destination.name + ".part")
        try:
            im.save(tmp, format="PNG")
            tmp.replace(destination)
        finally:
            tmp.unlink(missing_ok=True)


def process_map(kmz, session, delay):
    output_folder = kmz.parent / DEFAULT_FOLDER_PATH / kmz.stem
    root = resolve_network_links(read_kml(kmz), session)

    output_folder.mkdir(parents=True, exist_ok=True)
    stats = {"downloaded": 0, "skipped": 0, "failed": 0, "placemarks": 0}

    for placemark in root.findall(".//kml:Placemark", KML_NS):
        coordinates = get_coordinates(placemark)
        if coordinates is None:
            continue
        urls = get_urls(placemark)
        if not urls:
            continue
        stats["placemarks"] += 1
        name_node = placemark.find("kml:name", KML_NS)
        name = name_node.text if name_node is not None else "Unnamed"
        print(f"\n{name} [{coordinates}]: {len(urls)} image(s)")

        for index, url in enumerate(urls, start=1):
            destination = output_folder / f"{coordinates} ({index}.).png"
            if destination.is_file():
                print(f"  SKIP {destination.name}")
                stats["skipped"] += 1
                continue
            try:
                download_image(session, url, destination)
                print(f"  OK   {destination.name}")
                stats["downloaded"] += 1
            except (requests.RequestException, ValueError, OSError, ImportError) as exc:
                print(f"  FAIL {destination.name}: {exc}", file=sys.stderr)
                stats["failed"] += 1
            time.sleep(max(0, delay))

    print("\nFinished:", ", ".join(
        f"{key}={value}" for key, value in stats.items()))
    if stats["failed"]:
        print("Some downloads failed. Re-run the script later to retry missing files.")

    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", type=float, default=0.2,
                        help="Seconds between downloads (default: 0.2)")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    maps = sorted((p for p in folder.iterdir()
                   if p.is_file() and p.suffix.lower() == ".kmz"),
                  key=lambda p: p.name.casefold())
    if not maps:
        print(f"No KMZ files found in {folder}")
    totals = {"downloaded": 0, "skipped": 0, "failed": 0, "placemarks": 0}
    failed_maps = 0
    failed_csvs = 0
    with requests.Session() as session:
        session.headers.update(
            {"User-Agent": "Mozilla/5.0 (compatible; MyMapsPhotoBackup/1.0)"})
        for url in CSV_URLS:
            try:
                download_csv(session, url, folder)
            except (requests.RequestException, ValueError, OSError, csv.Error) as exc:
                print(f"  CSV download failed: {exc}", file=sys.stderr)
                failed_csvs += 1
        for index, kmz in enumerate(maps, 1):
            print(f"\n=== Map {index}/{len(maps)}: {kmz.name} ===")
            try:
                stats = process_map(kmz, session, args.delay)
            except (ET.ParseError, zipfile.BadZipFile, ValueError,
                    requests.RequestException, OSError) as exc:
                print(
                    f"  Could not process {kmz.name}: {exc}", file=sys.stderr)
                failed_maps += 1
                continue
            for key in totals:
                totals[key] += stats[key]
    print(
        f"\nAll maps finished: {len(maps) - failed_maps}/{len(maps)} processed")
    print(", ".join(f"{key}={value}" for key, value in totals.items()))
    print(
        f"CSV files processed: {len(CSV_URLS) - failed_csvs}/{len(CSV_URLS)}")
    if failed_maps or totals["failed"] or failed_csvs:
        sys.exit(1)


if __name__ == "__main__":
    main()
