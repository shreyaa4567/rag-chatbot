# app/crawler.py

import os
import time
import json
import hashlib
import logging
import requests
import tldextract
from collections import deque
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import config

logger = logging.getLogger(__name__)

# ─── HEADERS ──────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent"               : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept"                   : "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language"          : "en-US,en;q=0.5",
    # Only advertise encodings `requests` can decode without extra packages.
    # Advertising "br" (brotli) without the brotli package installed causes
    # requests to return undecoded compressed bytes -> garbage content.
    "Accept-Encoding"          : "gzip, deflate",
    "Connection"               : "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def get_base_domain(url):
    """Return 'domain.suffix' (e.g. 'taylorswift.com') for robust comparison."""
    extracted = tldextract.extract(url)
    return f"{extracted.domain}.{extracted.suffix}".lower()

def is_same_domain(url, base_domain):
    """Compare full registered domain (domain.suffix), not just the domain word."""
    extracted = tldextract.extract(url)
    url_domain = f"{extracted.domain}.{extracted.suffix}".lower()
    return url_domain == base_domain

def normalize_url(url):
    """Normalize a URL to prevent duplicate crawling.
    
    - Strips fragment (#section)
    - Normalizes trailing slashes on paths
    - Lowercases scheme and host
    - Removes default ports (80/443)
    """
    parsed = urlparse(url)
    # Lowercase scheme and host
    scheme = parsed.scheme.lower()
    host   = parsed.hostname.lower() if parsed.hostname else ""
    # Remove default ports
    port   = parsed.port
    if port in (80, 443, None):
        netloc = host
    else:
        netloc = f"{host}:{port}"
    # Normalize path: strip trailing slash (keep root "/")
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    # Drop fragment entirely, keep query
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))

def clean_text(soup):
    """Extract meaningful text content from HTML, removing boilerplate."""
    # Remove non-content tags
    for tag in soup(["script", "style", "nav", "footer", "head",
                     "aside", "header", "form", "iframe", "noscript"]):
        tag.decompose()

    # Remove elements with common boilerplate CSS classes/IDs/roles. This
    # strips navigation, headers, footers, cookie bars, accessibility widgets,
    # "back to top" buttons, etc. before any text is extracted.
    boilerplate_patterns = [
        "sidebar", "breadcrumb", "cookie", "banner", "menu",
        "social", "share", "widget", "popup", "modal", "advert",
        "newsletter", "signup", "toolbar", "pagination",
        "accessib", "a11y", "skip-link", "skiplink", "screenreader",
        "screen-reader", "scroll-top", "scrolltop", "back-to-top",
        "backtotop", "gototop", "navbar", "topbar", "site-header",
        "site-footer", "mega-menu", "offcanvas",
    ]
    # NOTE: decomposing a parent nulls its descendants' .attrs. Since those
    # descendants are still in this list, skip any element already removed
    # (attrs becomes None) to avoid an AttributeError on deeply-nested pages.
    for element in soup.find_all(True, attrs={"class": True}):
        if not element.attrs:
            continue
        classes = " ".join(element.get("class") or []).lower()
        if any(pattern in classes for pattern in boilerplate_patterns):
            element.decompose()
    for element in soup.find_all(True, attrs={"id": True}):
        if not element.attrs:
            continue
        elem_id = (element.get("id") or "").lower()
        if any(pattern in elem_id for pattern in boilerplate_patterns):
            element.decompose()

    # Extract text in document order, preserving section structure. Headings
    # are emitted as Markdown lines ("## Title") so the chunker can split on
    # them; paragraph-like tags carry the body text. Container tags (div/
    # section/article) are only read when they are "leaves" (hold no block
    # children), which avoids emitting a parent's text and then its children's
    # text again as duplicates.
    HEADINGS   = ("h1", "h2", "h3", "h4", "h5", "h6")
    TEXT_TAGS  = ("p", "li", "td", "th", "blockquote", "dd", "dt", "figcaption")
    CONTAINERS = ("div", "section", "article", "main")
    BLOCK_DESC = HEADINGS + TEXT_TAGS + CONTAINERS + ("ul", "ol", "table")

    blocks = []
    seen   = set()  # Deduplicate repeated text within a page (e.g. nav leftovers)
    for tag in soup.find_all(HEADINGS + TEXT_TAGS + CONTAINERS):
        # Skip non-leaf containers; their block children are captured directly.
        if tag.name in CONTAINERS and tag.find(BLOCK_DESC):
            continue
        text = " ".join(tag.get_text(separator=" ").split())
        if not text:
            continue
        if tag.name in HEADINGS:
            level = int(tag.name[1])
            block = f"{'#' * level} {text}"
            if block in seen:
                continue
        else:
            if len(text) < 30:
                continue
            block = text
            if block in seen:
                continue
        seen.add(block)
        blocks.append(block)

    if blocks:
        return "\n\n".join(blocks)

    # Fallback: nothing structured found — return flattened text.
    combined = soup.get_text(separator=" ")
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    return "\n\n".join(lines)

def get_page_title(soup):
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text().strip()
    return "No Title"

def save_text(filename, text):
    filepath = os.path.join(config.DATA_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)

def log_visited(url):
    with open(config.VISITED_LOG, "a", encoding="utf-8") as f:
        f.write(url + "\n")

def log_error(url, reason):
    with open(config.ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"{url} | {reason}\n")

def load_metadata():
    if os.path.exists(config.METADATA_FILE):
        with open(config.METADATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_metadata(metadata):
    with open(config.METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

# ─── FETCH SINGLE PAGE ────────────────────────────────────────────────────────

def fetch_page(url):
    try:
        response = requests.get(url, timeout=config.REQUEST_TIMEOUT, headers=HEADERS)
        if response.status_code != 200:
            return url, None, None, None, f"HTTP {response.status_code}"
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return url, None, None, None, f"Skipped: {content_type}"
        soup  = BeautifulSoup(response.text, "lxml")
        # Extract the title BEFORE clean_text(), which decomposes <head>
        # (and therefore <title>). Otherwise every page becomes "No Title".
        title = get_page_title(soup)
        text  = clean_text(soup)
        if len(text) < 50:
            return url, None, None, None, "Too little content"
        links = []
        for a_tag in soup.find_all("a", href=True):
            href     = a_tag["href"].strip()
            full_url = urljoin(url, href)
            links.append(normalize_url(full_url))
        return url, text, title, links, None
    except requests.exceptions.Timeout:
        return url, None, None, None, "Timeout"
    except requests.exceptions.ConnectionError:
        return url, None, None, None, "Connection error"
    except Exception as e:
        return url, None, None, None, str(e)

# ─── MAIN CRAWLER ─────────────────────────────────────────────────────────────

def crawl(start_url, progress_callback=None):
    logger.info("Starting crawl: %s", start_url)
    logger.info("Max pages: %s", config.MAX_PAGES)

    start_url   = normalize_url(start_url)
    base_domain = get_base_domain(start_url)
    logger.info("Base domain: %s", base_domain)

    visited    = set()
    queued     = {start_url}
    to_visit   = deque([start_url])
    metadata   = load_metadata()
    page_count = 0

    with ThreadPoolExecutor(max_workers=5) as executor:
        while to_visit and page_count < config.MAX_PAGES:

            # Take up to 5 URLs at once
            batch = []
            while to_visit and len(batch) < 5 and page_count + len(batch) < config.MAX_PAGES:
                url = to_visit.popleft()
                if url in visited:
                    continue
                if not url.startswith("http"):
                    continue
                if url.lower().endswith((".pdf", ".jpg", ".png", ".zip", ".doc", ".docx", ".xls")):
                    continue
                batch.append(url)

            if not batch:
                break

            # Fetch batch in parallel
            futures = {executor.submit(fetch_page, url): url for url in batch}

            for future in as_completed(futures):
                url, text, title, links, error = future.result()

                visited.add(url)

                if error:
                    log_error(url, error)
                    continue

                # Save text with an MD5 hash of the URL as the filename.
                # This guarantees a unique, collision-free name per URL and is
                # idempotent if the same URL is crawled again.
                page_count += 1
                filename = hashlib.md5(url.encode()).hexdigest()[:12] + ".txt"
                save_text(filename, text)

                metadata.append({
                    "url"        : url,
                    "title"      : title,
                    "filename"   : filename,
                    "crawl_time" : datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                save_metadata(metadata)
                log_visited(url)

                logger.info("[%d] Crawled: %s", page_count, url)

                # Add new links
                if links:
                    for link_url in links:
                        if (
                            is_same_domain(link_url, base_domain)
                            and link_url not in visited
                            and link_url not in queued
                        ):
                            to_visit.append(link_url)
                            queued.add(link_url)

                # Update progress
                if progress_callback:
                    progress_callback(page_count, config.MAX_PAGES)

            time.sleep(0.2)

    # Always persist metadata (even empty) so downstream steps never hit a
    # missing-file error; they can react to an empty list instead.
    save_metadata(metadata)

    logger.info("Crawl complete! Pages crawled: %d", page_count)

    if page_count == 0:
        raise RuntimeError(
            f"No pages could be crawled from {start_url}. The site may block "
            f"automated requests, require JavaScript to render, or be "
            f"unreachable. Try a different URL."
        )

# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    crawl(config.TARGET_URL)