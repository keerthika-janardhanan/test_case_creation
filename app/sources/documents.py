# sources/documents.py
import os
import logging
from typing import Iterator, Tuple, Dict, Optional
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# --- Optional: LangChain loaders ---
_HAVE_LC_LOADERS = False
try:
    from langchain_community.document_loaders import PyPDFLoader, UnstructuredWordDocumentLoader, TextLoader
    _HAVE_LC_LOADERS = True
except ImportError:
    try:
        from langchain.document_loaders import PyPDFLoader, UnstructuredWordDocumentLoader, TextLoader
        _HAVE_LC_LOADERS = True
    except ImportError:
        _HAVE_LC_LOADERS = False


# --------------------------
# Utilities
# --------------------------
def _is_url(path_or_url: str) -> bool:
    p = urlparse(path_or_url)
    return p.scheme in ("http", "https")


def _chunk_text_by_words(text: str, chunk_size_words: int = 400, overlap_words: int = 50) -> Iterator[str]:
    """Yield chunks of text instead of building large list in memory."""
    if not text:
        return
    words = text.split()
    n = len(words)
    if n <= chunk_size_words:
        yield " ".join(words)
        return

    start = 0
    while start < n:
        end = min(start + chunk_size_words, n)
        yield " ".join(words[start:end])
        if end == n:
            break
        start = max(0, end - overlap_words)


def _extract_text_from_html(html: str) -> Tuple[str, str]:
    """Extract title and main text from HTML using <article>/<main> or <p> tags."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    article = soup.find("article") or soup.find("main")
    paragraphs = article.find_all("p") if article else soup.find_all("p")
    text = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
    if not text.strip():
        text = soup.get_text(separator=" ", strip=True)
    return title, text


def _fetch_url_page(url: str, timeout: int = 10) -> Tuple[str, str]:
    """Fetch a single URL and return (title, cleaned_text)."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return _extract_text_from_html(resp.text)


# --------------------------
# Main loader
# --------------------------
def load_documents(
    path_or_url: str,
    chunk_size_words: int = 400,
    overlap_words: int = 50,
    crawl_depth: int = 0,
    max_pages: Optional[int] = 50
) -> Iterator[Tuple[str, str, Dict]]:
    """
    Yield documents from local files or web pages.
    Returns an iterator of (doc_id, content, metadata).
    """

    # --- Case A: URL ---
    if _is_url(path_or_url):
        visited = set()
        to_visit = [(path_or_url, 0)]

        while to_visit and (max_pages is None or len(visited) < max_pages):
            url, depth = to_visit.pop(0)
            if url in visited or depth > crawl_depth:
                continue
            visited.add(url)

            try:
                title, text = _fetch_url_page(url)
            except Exception as e:
                logger.warning("Failed to fetch URL %s: %s", url, e)
                continue

            for i, chunk in enumerate(_chunk_text_by_words(text, chunk_size_words, overlap_words)):
                doc_id = f"{url}::chunk_{i}"
                metadata = {
                    "source": "web",
                    "url": url,
                    "title": title,
                    "chunk_index": i,
                }
                yield (doc_id, chunk, metadata)

            # enqueue new links if depth allows
            if depth < crawl_depth:
                try:
                    resp = requests.get(url, timeout=10)
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for link in soup.find_all("a", href=True):
                        new_url = urljoin(url, link["href"])
                        if urlparse(new_url).netloc == urlparse(path_or_url).netloc:
                            if new_url not in visited:
                                to_visit.append((new_url, depth + 1))
                except Exception as e:
                    logger.warning("Could not parse links from %s: %s", url, e)

        return  # generator ends here

    # --- Case B: Local path ---
    path = os.path.expanduser(path_or_url)
    files = []
    if os.path.isdir(path):
        for root, _, filenames in os.walk(path):
            for fn in filenames:
                files.append(os.path.join(root, fn))
    else:
        files = [path]

    for fpath in files:
        if not os.path.exists(fpath):
            continue
        ext = os.path.splitext(fpath)[1].lower()

        # Use LangChain loaders if available
        if _HAVE_LC_LOADERS:
            try:
                if ext == ".pdf":
                    loader = PyPDFLoader(fpath)
                    docs = loader.load()
                elif ext in (".docx", ".doc"):
                    loader = UnstructuredWordDocumentLoader(fpath)
                    docs = loader.load()
                else:
                    loader = TextLoader(fpath)
                    docs = loader.load()

                for i, doc in enumerate(docs):
                    text = getattr(doc, "page_content", str(doc))
                    for j, chunk in enumerate(_chunk_text_by_words(text, chunk_size_words, overlap_words)):
                        doc_id = f"{fpath}::p{i}::c{j}"
                        metadata = {"source": "document", "file": fpath, "page_index": i, "chunk_index": j}
                        yield (doc_id, chunk, metadata)
                continue
            except Exception as e:
                logger.warning("LangChain loader failed for %s: %s — fallback to plain text.", fpath, e)

        # Fallback: read as plain text
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            for j, chunk in enumerate(_chunk_text_by_words(text, chunk_size_words, overlap_words)):
                doc_id = f"{fpath}::chunk_{j}"
                metadata = {"source": "document", "file": fpath, "chunk_index": j}
                yield (doc_id, chunk, metadata)
        except Exception:
            logger.warning("Unable to read %s as text. Skipping.", fpath)
