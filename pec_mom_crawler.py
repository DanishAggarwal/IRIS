from __future__ import annotations

import csv
import hashlib
import mimetypes
import re
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import (
    parse_qs, unquote, urldefrag, urljoin, urlparse, urlunparse
)

import requests
from bs4 import BeautifulSoup

START_URL = "https://pec.ac.in/minutes-senate-meetings"
OUTPUT_DIR = Path("PEC_Senate_MoMs")
LOG_FILE = OUTPUT_DIR / "download_log.csv"

TIMEOUT = 35
REQUEST_DELAY_SECONDS = 0.4
MAX_PAGES = 300
MAX_NESTED_PAGES = 300

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PEC-Senate-MoM-Archive-Crawler/2.0)"
    )
}

# Common office/document formats. Also accept extensionless document URLs
# when the response headers or content signature identify a file.
DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".rtf", ".txt", ".csv", ".zip"
}
SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".css", ".js",
    ".ico", ".mp4", ".mp3", ".woff", ".woff2", ".ttf", ".eot"
}
RELEVANT_TERMS = re.compile(
    r"\b(senate|minutes?|mom|meeting|agenda|proceedings|annexure|"
    r"annex|attachment|record|resolution)\b", re.I
)


def clean_filename(value: str) -> str:
    value = unquote(value)
    value = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value).strip("._")
    return (value[:160] or "pec_senate_document")


def normalize_url(url: str) -> str:
    """Remove fragments; retain query strings because they may identify files."""
    return urldefrag(url.strip())[0]


def is_same_site(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "pec.ac.in" or host.endswith(".pec.ac.in")


def path_extension(url: str) -> str:
    return Path(urlparse(url).path.lower()).suffix


def fetch(session: requests.Session, url: str):
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response


def looks_like_document_url(url: str, anchor_text: str = "") -> bool:
    ext = path_extension(url)
    if ext in DOCUMENT_EXTENSIONS:
        return True
    if ext in SKIP_EXTENSIONS:
        return False

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query_text = " ".join(
        [parsed.path, anchor_text] +
        [f"{k} {' '.join(v)}" for k, v in query.items()]
    )
    # Typical CMS file routes and download endpoints.
    return bool(
        re.search(r"(file|download|document|attachment|media|node)", query_text, re.I)
        and RELEVANT_TERMS.search(query_text + " " + anchor_text)
    )


def safe_title_from_link(anchor, url: str, fallback: str) -> str:
    text = anchor.get_text(" ", strip=True) if anchor else ""
    title = text or (anchor.get("title", "") if anchor else "") or ""
    if not title:
        title = Path(urlparse(url).path).name or fallback
    return clean_filename(title)


def get_senate_table_rows(soup: BeautifulSoup):
    """Yield meeting rows and every link contained in each row."""
    for table in soup.find_all("table"):
        header_text = " ".join(
            cell.get_text(" ", strip=True).lower()
            for cell in table.find_all(["th", "td"])[:12]
        )
        if "date of meeting" not in header_text or "description" not in header_text:
            continue

        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) < 3 or row.find("th"):
                continue

            description = cells[2].get_text(" ", strip=True)
            row_text = row.get_text(" ", strip=True)
            if not re.search(r"\bsenate\b", description + " " + row_text, re.I):
                continue

            serial = cells[0].get_text(" ", strip=True)
            number_match = re.search(r"\d+", serial)
            meeting_number = number_match.group(0) if number_match else "unknown"
            meeting_date = cells[1].get_text(" ", strip=True)
            title = f"Senate_Meeting_{meeting_number}_{meeting_date}"

            links = []
            for anchor in row.find_all("a", href=True):
                target = normalize_url(urljoin(START_URL, anchor["href"]))
                if target.startswith(("http://", "https://")):
                    links.append((anchor, target))

            yield {
                "meeting_number": meeting_number,
                "date": meeting_date,
                "title": title,
                "row_text": row_text,
                "links": links,
            }


def get_pagination_links(soup: BeautifulSoup, current_url: str):
    found = set()
    for anchor in soup.find_all("a", href=True):
        target = normalize_url(urljoin(current_url, anchor["href"]))
        if not is_same_site(target):
            continue
        parsed = urlparse(target)
        label = anchor.get_text(" ", strip=True).lower()
        classes = " ".join(anchor.get("class", [])).lower()
        is_pager = (
            "pager" in classes
            or label in {"next", "›", "»", "last", "older", "1", "2", "3"}
            or bool(re.search(r"(?:^|[?&])(?:page|paged)=\d+", parsed.query))
        )
        if is_pager:
            found.add(target)
    return found


def get_file_extension(url: str, content_type: str, first_bytes: bytes) -> str:
    ext = path_extension(url)
    if ext in DOCUMENT_EXTENSIONS:
        return ext

    content_type = content_type.split(";")[0].strip().lower()
    known = {
        "application/pdf": ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-powerpoint": ".ppt",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        "application/zip": ".zip",
        "text/plain": ".txt",
        "text/csv": ".csv",
    }
    if content_type in known:
        return known[content_type]
    if first_bytes.startswith(b"%PDF-"):
        return ".pdf"
    if first_bytes.startswith(b"PK\x03\x04"):
        return ".zip"
    guessed = mimetypes.guess_extension(content_type) if content_type else None
    return guessed or ".bin"


def download_document(session: requests.Session, url: str, destination_base: Path):
    temp_path = destination_base.with_suffix(".download")
    digest = hashlib.sha256()
    first_bytes = b""

    with session.get(url, stream=True, timeout=TIMEOUT) as response:
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        content_disposition = response.headers.get("Content-Disposition", "")

        with temp_path.open("wb") as out:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                if not first_bytes:
                    first_bytes = chunk[:32]
                digest.update(chunk)
                out.write(chunk)

    # A link may look like a document but return an HTML error/login page.
    if (b"<html" in first_bytes.lower() or b"<!doctype" in first_bytes.lower()):
        temp_path.unlink(missing_ok=True)
        raise ValueError("Server returned HTML instead of a document")

    ext = get_file_extension(url, content_type, first_bytes)
    if ext == ".bin" and not (
        first_bytes.startswith(b"%PDF-") or first_bytes.startswith(b"PK\x03\x04")
    ):
        temp_path.unlink(missing_ok=True)
        raise ValueError(f"Unrecognised file response ({content_type or 'unknown type'})")

    # Prefer the filename supplied by the server when useful.
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', content_disposition, re.I)
    server_name = clean_filename(match.group(1)) if match else ""
    if server_name and Path(server_name).suffix:
        final_name = server_name
    else:
        final_name = destination_base.name + ext

    destination = OUTPUT_DIR / final_name
    counter = 2
    while destination.exists():
        # Existing file with identical content is a duplicate; reuse it.
        existing_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
        if existing_hash == digest.hexdigest():
            temp_path.unlink(missing_ok=True)
            return destination, digest.hexdigest(), True
        destination = OUTPUT_DIR / f"{Path(final_name).stem}_{counter}{Path(final_name).suffix}"
        counter += 1

    temp_path.replace(destination)
    return destination, digest.hexdigest(), False


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    page_queue = deque([(START_URL, "archive")])
    visited_pages = set()
    discovered_files = {}  # URL -> metadata
    missing_rows = []
    nested_page_count = 0

    print(f"Starting crawl: {START_URL}")

    while page_queue and len(visited_pages) < MAX_PAGES:
        page_url, page_kind = page_queue.popleft()
        page_url = normalize_url(page_url)
        if page_url in visited_pages:
            continue
        if not is_same_site(page_url):
            continue

        try:
            response = fetch(session, page_url)
            content_type = response.headers.get("Content-Type", "").lower()
            if "html" not in content_type and not response.text.lstrip().startswith("<"):
                continue
            soup = BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as exc:
            print(f"[PAGE ERROR] {page_url}: {exc}")
            visited_pages.add(page_url)
            continue

        visited_pages.add(page_url)
        print(f"[PAGE] {page_url}")

        # On archive pages, inspect Senate rows and collect every linked document.
        for meeting in get_senate_table_rows(soup):
            qualifying = []
            for anchor, target in meeting["links"]:
                label = anchor.get_text(" ", strip=True)
                if looks_like_document_url(target, label) or RELEVANT_TERMS.search(
                    label + " " + target
                ):
                    qualifying.append((anchor, target))

            if not qualifying:
                missing_rows.append({
                    "meeting_number": meeting["meeting_number"],
                    "date": meeting["date"],
                    "title": meeting["title"],
                    "url": page_url,
                    "status": "NO RELEVANT DOCUMENT LINK FOUND IN ROW",
                    "filename": "",
                })

            for link_index, (anchor, target) in enumerate(qualifying, start=1):
                discovered_files.setdefault(target, {
                    "meeting_number": meeting["meeting_number"],
                    "date": meeting["date"],
                    "title": meeting["title"],
                    "link_title": safe_title_from_link(
                        anchor, target, meeting["title"]
                    ),
                    "source_page": page_url,
                })

                # If a relevant link is an HTML landing page rather than a file,
                # queue it to inspect its child attachments.
                if path_extension(target) not in DOCUMENT_EXTENSIONS and is_same_site(target):
                    if target not in visited_pages and nested_page_count < MAX_NESTED_PAGES:
                        page_queue.append((target, "nested"))
                        nested_page_count += 1

        # Follow pagination/archive links, plus clearly relevant same-site links
        # that may be separate Senate minutes archive pages.
        for anchor in soup.find_all("a", href=True):
            target = normalize_url(urljoin(page_url, anchor["href"]))
            if not is_same_site(target) or target in visited_pages:
                continue
            label = anchor.get_text(" ", strip=True)
            if target in get_pagination_links(soup, page_url):
                page_queue.append((target, "archive"))
            elif (
                RELEVANT_TERMS.search(label + " " + target)
                and path_extension(target) not in DOCUMENT_EXTENSIONS
                and nested_page_count < MAX_NESTED_PAGES
            ):
                page_queue.append((target, "nested"))
                nested_page_count += 1

        time.sleep(REQUEST_DELAY_SECONDS)

    # Download all collected document candidates. Non-document candidates that
    # are actually HTML pages will be reported as failed rather than saved as PDFs.
    log_rows = list(missing_rows)
    downloaded_hashes = set()

    for index, (file_url, info) in enumerate(discovered_files.items(), start=1):
        base = clean_filename(
            f"{info['title']}_{info['link_title']}"
            if info["link_title"] != info["title"]
            else info["title"]
        )
        destination_base = OUTPUT_DIR / base

        try:
            print(f"[{index}/{len(discovered_files)}] {file_url}")
            saved_path, digest, duplicate = download_document(
                session, file_url, destination_base
            )
            duplicate = duplicate or digest in downloaded_hashes
            downloaded_hashes.add(digest)
            status = "DOWNLOADED (DUPLICATE CONTENT)" if duplicate else "DOWNLOADED"
            log_rows.append({
                "meeting_number": info["meeting_number"],
                "date": info["date"],
                "title": info["title"],
                "url": file_url,
                "status": status,
                "filename": saved_path.name,
            })
        except (requests.RequestException, OSError, ValueError) as exc:
            log_rows.append({
                "meeting_number": info["meeting_number"],
                "date": info["date"],
                "title": info["title"],
                "url": file_url,
                "status": f"FAILED: {exc}",
                "filename": "",
            })
            print(f"[SKIPPED/ERROR] {file_url}: {exc}")

        time.sleep(REQUEST_DELAY_SECONDS)

    columns = ["meeting_number", "date", "title", "url", "status", "filename"]
    with LOG_FILE.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(log_rows)

    successes = sum(row["status"].startswith("DOWNLOADED") for row in log_rows)
    failures = sum(row["status"].startswith("FAILED") for row in log_rows)
    print("\nCrawl complete.")
    print(f"Pages visited: {len(visited_pages)}")
    print(f"Document links discovered: {len(discovered_files)}")
    print(f"Download records successful: {successes}")
    print(f"Failed links: {failures}")
    print(f"Output folder: {OUTPUT_DIR.resolve()}")
    print(f"CSV log: {LOG_FILE.resolve()}")
    print("Review the CSV for missing or failed links.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by user.")
        sys.exit(130)