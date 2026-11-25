"""Read a publicly shared Google Doc as plain text (ADR-0030).

With an API key (``GOOGLE_API_KEY``), the Google Drive API ``files.export`` is used. Without
one, the document's public plain-text export link is used: it returns the file itself,
the same bytes the Drive API exports, not a web page, so nothing is scraped. Both go
through the shared HTTP client (retries, backoff, timeouts, OpenTelemetry spans).
"""

from __future__ import annotations

from collectors.http import HttpClient

DRIVE_API = "https://www.googleapis.com"
DOCS = "https://docs.google.com"


class NotesClient:
    """Fetches one document's text. Read-only."""

    def __init__(self, http: HttpClient | None = None, *, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._http = http or HttpClient(DRIVE_API if api_key else DOCS)

    def fetch_text(self, document_id: str) -> str:
        """The document as UTF-8 plain text."""
        if self._api_key:
            res = self._http.get(
                f"/drive/v3/files/{document_id}/export",
                params={"mimeType": "text/plain", "key": self._api_key},
            )
        else:
            res = self._http.get(f"/document/d/{document_id}/export", params={"format": "txt"})
        return res.content.decode("utf-8-sig")

    def document_url(self, document_id: str) -> str:
        """Where a person can read the document."""
        return f"{DOCS}/document/d/{document_id}"

    def close(self) -> None:
        self._http.close()
