# app/crawler.py

import os
import time
import json
import requests
import tldextract
from collections import deque
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import config

# ─── HEADERS ──────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent"               : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept"                   : "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language"          : "en-US,en;q=0.5",
    "Accept-Encoding"          : "gzip, deflate, br",
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
    for tag in soup(["script", "style", "nav", "footer", "head"]):
        tag.decompose()
    blocks = []
    for tag in soup.find_all(["p", "span", "div", "li", "h1", "h2", "h3", "blockquote"]):
        text = tag.get_text(separator=" ").strip()
        if len(text) > 30:
            blocks.append(text)
    if blocks:
        combined = "\n\n".join(blocks)
    else:
        combined = soup.get_text(separator=" ")
    lines = [line.strip() for line in combined.splitlines()]
    lines = [line for line in lines if line]
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
        text  = clean_text(soup)
        title = get_page_title(soup)
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
    print(f"\n Starting crawl: {start_url}")
    print(f" Max pages: {config.MAX_PAGES}")

    start_url   = normalize_url(start_url)
    base_domain = get_base_domain(start_url)
    print(f" Base domain: {base_domain}\n")

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

                # Save text with unique sequential filename to prevent collisions
                page_count += 1
                filename = f"page_{page_count:04d}.txt"
                save_text(filename, text)

                metadata.append({
                    "url"        : url,
                    "title"      : title,
                    "filename"   : filename,
                    "crawl_time" : datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                save_metadata(metadata)
                log_visited(url)

                print(f"[{page_count}] Crawled: {url}")

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

    print(f"\n Crawl complete! Pages crawled: {page_count}")

# ─── RUN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    crawl(config.TARGET_URL)