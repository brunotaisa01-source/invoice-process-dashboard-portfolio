"""Serve the pack dashboard and write Calendar/Override JSONs into pack-local queues."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ABSENCE_TYPES = frozenset({"Holiday", "Sickness", "Other", "Half Day"})
WORK_TYPES = frozenset({"manual", "csv", "envoy"})
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CALENDAR_FILENAME_PATTERN = re.compile(
    r"^invoice_calendar_pending_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}_[A-Za-z0-9._-]+\.json$"
)
PRODUCTION_FILENAME_PATTERN = re.compile(
    r"^invoice_production_overrides_pending_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}_[A-Za-z0-9._-]+\.json$"
)
MAX_BODY_BYTES = 1_000_000


def _pack_id(path: Path) -> str:
    normalized = str(path.resolve()).lower().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:16]


def _validate_absence(row: Any, *, allow_type: bool) -> None:
    if not isinstance(row, dict):
        raise ValueError("absence entry must be an object")
    if not isinstance(row.get("member"), str) or not row["member"].strip():
        raise ValueError("absence member is required")
    if not isinstance(row.get("date"), str) or not DATE_PATTERN.fullmatch(row["date"]):
        raise ValueError("absence date must use YYYY-MM-DD")
    if allow_type and row.get("type") not in ABSENCE_TYPES:
        raise ValueError("absence type is invalid")


def _validate_request(body: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(body, dict):
        raise ValueError("request body must be an object")

    filename = body.get("filename")
    payload = body.get("payload")
    if not isinstance(filename, str) or Path(filename).name != filename or not CALENDAR_FILENAME_PATTERN.fullmatch(filename):
        raise ValueError("filename is invalid")
    if not isinstance(payload, dict) or payload.get("version") != 1 or payload.get("app") != "invoice-process-dashboard":
        raise ValueError("calendar payload header is invalid")
    if not isinstance(payload.get("created_at"), str) or not payload["created_at"].strip():
        raise ValueError("created_at is required")
    if not isinstance(payload.get("created_by"), str) or not payload["created_by"].strip():
        raise ValueError("created_by is required")

    added = payload.get("added")
    deleted = payload.get("deleted")
    if not isinstance(added, list) or not isinstance(deleted, list):
        raise ValueError("added and deleted must be arrays")
    for row in added:
        _validate_absence(row, allow_type=True)
    for row in deleted:
        _validate_absence(row, allow_type=False)
    return filename, payload


def _validate_production_override(row: Any, *, deletion: bool) -> None:
    if not isinstance(row, dict):
        raise ValueError("production override entry must be an object")
    if deletion:
        if not isinstance(row.get("override_id"), str) or not row["override_id"].strip():
            raise ValueError("override_id is required")
        return
    if not isinstance(row.get("date"), str) or not DATE_PATTERN.fullmatch(row["date"]):
        raise ValueError("override date must use YYYY-MM-DD")
    for field in ("from_member", "to_member"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f"{field} is required")
    if row["from_member"] == row["to_member"]:
        raise ValueError("from_member and to_member must be different")
    if isinstance(row.get("count"), bool) or not isinstance(row.get("count"), int) or row["count"] <= 0:
        raise ValueError("count must be a positive integer")
    if row.get("work_type") not in WORK_TYPES:
        raise ValueError("work_type is invalid")
    for field in ("country", "company_code", "document_type", "reference", "reason"):
        value = row.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{field} must be text when provided")


def _validate_production_request(body: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(body, dict):
        raise ValueError("request body must be an object")

    filename = body.get("filename")
    payload = body.get("payload")
    if not isinstance(filename, str) or Path(filename).name != filename or not PRODUCTION_FILENAME_PATTERN.fullmatch(filename):
        raise ValueError("production override filename is invalid")
    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or payload.get("app") != "invoice-process-dashboard"
        or payload.get("feature") != "production-credit-overrides"
    ):
        raise ValueError("production override payload header is invalid")
    if not isinstance(payload.get("created_at"), str) or not payload["created_at"].strip():
        raise ValueError("created_at is required")
    if not isinstance(payload.get("created_by"), str) or not payload["created_by"].strip():
        raise ValueError("created_by is required")

    added = payload.get("added")
    deleted = payload.get("deleted")
    if not isinstance(added, list) or not isinstance(deleted, list):
        raise ValueError("added and deleted must be arrays")
    for row in added:
        _validate_production_override(row, deletion=False)
    for row in deleted:
        _validate_production_override(row, deletion=True)
    return filename, payload


def _atomic_write_json(directory: Path, filename: str, payload: dict[str, Any]) -> Path:
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = (directory / filename).resolve()
    if target.parent != directory:
        raise ValueError("target must stay inside Calendar pending")

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f".{filename}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    return target


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    """Serve static dashboard files and the two narrow pending write endpoints."""

    server: "DashboardServer"

    def __init__(self, request: Any, client_address: Any, server: "DashboardServer") -> None:
        super().__init__(request, client_address, server, directory=str(server.dashboard_dir))

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json_response(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self) -> None:
        if urlsplit(self.path).path.startswith("/api/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            return
        self.send_error(404)

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/api/health":
            self._json_response(
                200,
                {
                    "ok": True,
                    "service": "invoice-process-dashboard",
                    "bridge_version": 3,
                    "pack_id": self.server.pack_id,
                    "features": ["calendar", "production-overrides"],
                },
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/calendar/pending":
            validator = _validate_request
            target_dir = self.server.calendar_pending_dir
        elif path == "/api/production-overrides/pending":
            validator = _validate_production_request
            target_dir = self.server.production_pending_dir
        else:
            self.send_error(404)
            return

        raw_length = self.headers.get("Content-Length")
        try:
            content_length = int(raw_length or "0")
        except ValueError:
            self._json_response(400, {"ok": False, "error": "invalid content length"})
            return
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._json_response(413, {"ok": False, "error": "request body is too large or empty"})
            return

        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            filename, payload = validator(body)
            target = _atomic_write_json(target_dir, filename, payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            self._json_response(400, {"ok": False, "error": str(error)})
            return
        except OSError as error:
            self._json_response(500, {"ok": False, "error": f"could not write pending JSON: {error}"})
            return

        self._json_response(201, {"ok": True, "filename": target.name})


class DashboardServer(ThreadingHTTPServer):
    """HTTP server bound to localhost and scoped to one operator pack."""

    allow_reuse_address = True

    def __init__(
        self,
        bind: str,
        port: int,
        dashboard_dir: Path,
        calendar_pending_dir: Path,
        production_pending_dir: Path,
        pack_id: str,
    ) -> None:
        self.dashboard_dir = dashboard_dir.resolve()
        self.calendar_pending_dir = calendar_pending_dir.resolve()
        self.production_pending_dir = production_pending_dir.resolve()
        self.pack_id = pack_id
        super().__init__((bind, port), DashboardRequestHandler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboard-dir", required=True, type=Path)
    parser.add_argument("--calendar-pending-dir", required=True, type=Path)
    parser.add_argument("--production-pending-dir", required=True, type=Path)
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dashboard_dir = args.dashboard_dir.resolve()
    calendar_pending_dir = args.calendar_pending_dir.resolve()
    production_pending_dir = args.production_pending_dir.resolve()
    if not (dashboard_dir / "index.html").is_file():
        raise SystemExit(f"Dashboard index missing: {dashboard_dir / 'index.html'}")
    calendar_pending_dir.mkdir(parents=True, exist_ok=True)
    production_pending_dir.mkdir(parents=True, exist_ok=True)
    server = DashboardServer(
        args.bind,
        args.port,
        dashboard_dir,
        calendar_pending_dir,
        production_pending_dir,
        args.pack_id,
    )
    print(f"[OK] Dashboard server listening on bind={args.bind} port={args.port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
