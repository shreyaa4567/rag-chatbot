# app/crawler.py

import os
import time
import json
import requests
import tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin, urlparse

import config

# ─── CONSTANTS ────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RAGCrawler/1.0)"
}

# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

def get_base_domain(url):
    """Extract base domain from URL using tldextract.
    Example: http://quotes.toscrape.com/ → toscrape"""
    extracted = tldextract.extract(url)
    return extracted.domain

def is_same_domain(url, base_domain):
    """Check if a URL belongs to the same website."""
    extracted = tldextract.extract(url)
    return extracted.domain == base_domain

def clean_text(soup):
    """Extract clean readable text from a BeautifulSoup object."""
    # Remove tags that contain code/navigation, not content
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()

    # Try to find individual quote blocks and separate them with newlines
    # This handles sites like quotes.toscrape.com where quotes are in <span> or <div>
    blocks = []

    # Look for common content containers
    for tag in soup.find_all(["p", "span", "div", "li", "h1", "h2", "h3", "blockquote"]):
        text = tag.get_text(separator=" ").strip()
        if len(text) > 30:  # skip tiny fragments
            blocks.append(text)

    if blocks:
        # Join blocks with double newline — chunker will split on these naturally
        combined = "\n\n".join(blocks)
    else:
        # Fallback to plain text extraction
        combined = soup.get_text(separator=" ")

    # Clean up extra whitespace within each block
    lines = [line.strip() for line in combined.splitlines()]
    lines = [line for line in lines if line]
    return "\n\n".join(lines)

def get_page_title(soup):
    """Extract page title."""
    title_tag = soup.find("title")
    if title_tag:
        return title_tag.get_text().strip()
    return "No Title"

def save_text(filename, text):
    """Save extracted text to data/ folder."""
    filepath = os.path.join(config.DATA_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)

def log_visited(url):
    """Write successfully visited URL to log file."""
    with open(config.VISITED_LOG, "a", encoding="utf-8") as f:
        f.write(url + "\n")

def log_error(url, reason):
    """Write failed URL and reason to error log."""
    with open(config.ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"{url} | {reason}\n")

def load_metadata():
    """Load existing metadata from file, or start fresh."""
    if os.path.exists(config.METADATA_FILE):
        with open(config.METADATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_metadata(metadata):
    """Save metadata list to JSON file."""
    with open(config.METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

# ─── MAIN CRAWLER ─────────────────────────────────────────────────────────────

def crawl(start_url):
    print(f"\n Starting crawl: {start_url}")
    print(f" Max pages: {config.MAX_PAGES}")
    print(f" Delay: {config.DELAY_SECONDS}s between requests\n")

    base_domain = get_base_domain(start_url)
    print(f" Base domain detected: {base_domain}\n")

    visited    = set()          # URLs already crawled
    queued     = {start_url}    # URLs already added to queue (prevents duplicates)
    to_visit   = [start_url]    # queue of URLs to crawl next
    metadata   = load_metadata()
    page_count = 0

    while to_visit and page_count < config.MAX_PAGES:
        url = to_visit.pop(0)   # take first URL from queue

        # Skip if already visited
        if url in visited:
            continue

        # Skip non-http URLs (mailto:, javascript:, etc.)
        if not url.startswith("http"):
            continue

        print(f"[{page_count + 1}] Crawling: {url}")

        try:
            response = requests.get(
                url,
                timeout=config.REQUEST_TIMEOUT,
                headers=HEADERS
            )

            # Skip pages that didn't load successfully
            if response.status_code != 200:
                log_error(url, f"HTTP {response.status_code}")
                visited.add(url)
                continue

            # Skip non-HTML pages (PDFs, images, etc.)
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                log_error(url, f"Skipped content type: {content_type}")
                visited.add(url)
                continue

            soup  = BeautifulSoup(response.text, "lxml")
            text  = clean_text(soup)
            title = get_page_title(soup)

            # Skip pages with almost no content
            if len(text) < 50:
                log_error(url, "Too little content")
                visited.add(url)
                continue

            # ── Save text file ────────────────────────────────────────────
            safe_name = urlparse(url).path.strip("/").replace("/", "_") or "homepage"
            filename  = f"{safe_name}.txt"
            save_text(filename, text)

            # ── Save metadata entry ───────────────────────────────────────
            metadata.append({
                "url"        : url,
                "title"      : title,
                "filename"   : filename,
                "crawl_time" : datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            save_metadata(metadata)

            # ── Log success ───────────────────────────────────────────────
            log_visited(url)
            visited.add(url)
            page_count += 1

            # ── Find new links on this page ───────────────────────────────
            for a_tag in soup.find_all("a", href=True):
                href     = a_tag["href"].strip()
                full_url = urljoin(url, href)

                # Only add if same domain, not visited, not already queued
                if (
                    is_same_domain(full_url, base_domain)
                    and full_url not in visited
                    and full_url not in queued
                ):
                    to_visit.append(full_url)
                    queued.add(full_url)

            # ── Wait before next request ──────────────────────────────────
            time.sleep(config.DELAY_SECONDS)

        except requests.exceptions.Timeout:
            log_error(url, "Timeout")
            visited.add(url)

        except requests.exceptions.ConnectionError:
            log_error(url, "Connection error")
            visited.add(url)

        except Exception as e:
            log_error(url, str(e))
            visited.add(url)

    # ── Done ──────────────────────────────────────────────────────────────────
    print(f"\n Crawl complete!")
    print(f" Pages crawled       : {page_count}")
    print(f" Text files saved in : {config.DATA_DIR}/")
    print(f" Metadata saved in   : {config.METADATA_FILE}")
    print(f" Visited log         : {config.VISITED_LOG}")
    print(f" Error log           : {config.ERROR_LOG}\n")


# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    crawl(config.TARGET_URL)