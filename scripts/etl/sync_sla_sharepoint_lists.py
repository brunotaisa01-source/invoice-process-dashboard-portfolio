"""Sync SLA Local Fixture Store lists into controlled local snapshot files.

The Microsoft Lists endpoint requires interactive Microsoft 365 authentication.
This module uses the local Office/Excel authenticated session to refresh a
temporary IQY web query, then atomically publishes .xlsx snapshots for the
SQLite importer.
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)

DEFAULT_SLA_SITE_URL = ""

DEFAULT_LIST_NAMES = (
    "SLA_Folder_Summary_FAST",
    "SLA_Folder_Summary_Daily_History",
    "SLA_Weekly_Owner_Summary",
    "SLA_Email_Tracker",
    "SLA_Action_Log",
    "SLA_Folder_Audit_State",
)


@dataclass(frozen=True)
class SyncResult:
    list_name: str
    output_path: Path
    rows_hint: int | None
    status: str
    error: str = ""


def _clean_site_url(value: str | None) -> str:
    return (value or "").strip().rstrip("/")


def _site_url_from_env() -> str:
    env_site_url = _clean_site_url(os.environ.get("INVOICE_DASHBOARD_SLA_SITE_URL"))
    if env_site_url:
        return env_site_url

    try:
        from scripts.paths import DEFAULT_SLA_SITE_URL as configured_default_url  # type: ignore[attr-defined]  # noqa: PLC0415
    except ImportError:
        configured_default_url = ""
    else:
        configured_default_url = _clean_site_url(configured_default_url)

    site_url = configured_default_url or DEFAULT_SLA_SITE_URL
    if not site_url:
        raise RuntimeError(
            "SLA fixture site URL is empty. Set INVOICE_DASHBOARD_SLA_SITE_URL "
            "or configure DEFAULT_SLA_SITE_URL in the local SLA sync adapter."
        )
    return site_url


def _default_snapshot_dir() -> Path:
    from scripts.paths import DATA_DIR  # noqa: PLC0415

    try:
        from scripts.paths import SLA_TRACKER_SNAPSHOT_DIR  # type: ignore[attr-defined]  # noqa: PLC0415
    except ImportError:
        return DATA_DIR / "sla_tracker_snapshots"
    return SLA_TRACKER_SNAPSHOT_DIR


def _build_iqy(site_url: str, list_name: str) -> str:
    encoded_list = quote(list_name, safe="")
    query_url = f"{site_url}/_vti_bin/owssvr.dll?XMLDATA=1&List={encoded_list}&RowLimit=0&RootFolder="
    return (
        "WEB\n"
        "1\n"
        f"{query_url}\n\n"
        f"Selection={list_name}\n"
        "EditWebPage=\n"
        "Formatting=None\n"
        "PreFormattedTextToColumns=True\n"
        "ConsecutiveDelimitersAsOne=True\n"
        "SingleBlockTextImport=False\n"
        "DisableDateRecognition=False\n"
        "DisableRedirections=False\n"
        f"Local Fixture StoreApplication={site_url}/_vti_bin\n"
        f"Local Fixture StoreListName={list_name}\n"
        "RootFolder=\n"
    )


def _safe_output_path(snapshot_dir: Path, list_name: str) -> Path:
    safe_name = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in list_name)
    return snapshot_dir / f"{safe_name}.xlsx"


def _release_com(obj: Any) -> None:
    try:
        import pythoncom  # type: ignore[import-not-found]  # noqa: PLC0415

        pythoncom.PumpWaitingMessages()
    except Exception:
        return

    try:
        obj = obj
    finally:
        del obj


def _count_rows(path: Path) -> int | None:
    try:
        import pandas as pd  # noqa: PLC0415

        frame = pd.read_excel(path, usecols=[0])
        return int(len(frame.index))
    except Exception:
        return None


def _sync_one_list(excel: Any, site_url: str, list_name: str, snapshot_dir: Path, temp_dir: Path) -> SyncResult:
    iqy_path = temp_dir / f"{list_name}.iqy"
    temp_xlsx = temp_dir / f"{list_name}.xlsx"
    output_path = _safe_output_path(snapshot_dir, list_name)
    iqy_path.write_text(_build_iqy(site_url, list_name), encoding="ascii")

    workbook = None
    try:
        workbook = excel.Workbooks.Open(str(iqy_path))
        workbook.RefreshAll()
        excel.CalculateUntilAsyncQueriesDone()
        workbook.SaveAs(str(temp_xlsx), 51)
        workbook.Close(False)
        workbook = None
        time.sleep(0.5)
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        os.replace(temp_xlsx, output_path)
        rows_hint = _count_rows(output_path)
        return SyncResult(list_name=list_name, output_path=output_path, rows_hint=rows_hint, status="OK")
    except Exception as exc:
        return SyncResult(list_name=list_name, output_path=output_path, rows_hint=None, status="ERROR", error=str(exc))
    finally:
        if workbook is not None:
            try:
                workbook.Close(False)
            except Exception:
                logger.debug("Could not close Excel workbook for %s", list_name, exc_info=True)


def sync_sla_local_lists(
    snapshot_dir: Path | None = None,
    site_url: str | None = None,
    list_names: tuple[str, ...] = DEFAULT_LIST_NAMES,
) -> list[SyncResult]:
    """Refresh Local Fixture Store list snapshots through local Excel authentication."""
    snapshot_dir = snapshot_dir or _default_snapshot_dir()
    site_url = _clean_site_url(site_url) or _site_url_from_env()
    if not site_url:
        raise RuntimeError("SLA Local Fixture Store site URL resolved to an empty value.")

    try:
        import win32com.client  # type: ignore[import-not-found]  # noqa: PLC0415
        import pythoncom  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("pywin32 is required for Excel Local Fixture Store sync") from exc

    temp_root = Path(tempfile.mkdtemp(prefix="invoice_sla_Local Source Adapter_"))
    excel = None
    results: list[SyncResult] = []
    try:
        pythoncom.CoInitialize()
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        for list_name in list_names:
            logger.info("Refreshing SLA Local Fixture Store list: %s", list_name)
            results.append(_sync_one_list(excel, site_url, list_name, snapshot_dir, temp_root))
        return results
    finally:
        if excel is not None:
            try:
                excel.Quit()
            except Exception:
                logger.debug("Could not quit Excel cleanly", exc_info=True)
            _release_com(excel)
        try:
            pythoncom.CoUninitialize()
        except Exception:
            logger.debug("Could not uninitialize COM", exc_info=True)
        shutil.rmtree(temp_root, ignore_errors=True)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync SLA Local Fixture Store lists to local snapshots.")
    parser.add_argument("--snapshot-dir", metavar="PATH", default=None)
    parser.add_argument("--site-url", metavar="URL", default=None)
    parser.add_argument("--list", dest="lists", action="append", default=None)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = _build_arg_parser().parse_args()
    list_names = tuple(args.lists) if args.lists else DEFAULT_LIST_NAMES
    started = datetime.now(timezone.utc)
    results = sync_sla_local_lists(
        snapshot_dir=Path(args.snapshot_dir) if args.snapshot_dir else None,
        site_url=args.site_url,
        list_names=list_names,
    )
    failed = [result for result in results if result.status != "OK"]
    for result in results:
        row_text = "unknown" if result.rows_hint is None else str(result.rows_hint)
        print(
            f"[{result.status}] {result.list_name}: rows={row_text} "
            f"path={result.output_path}"
        )
        if result.error:
            print(f"[WARN] {result.list_name}: {result.error}")
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    if failed:
        raise SystemExit(f"SLA Local Fixture Store sync failed for {len(failed)} list(s) after {elapsed:.1f}s")
    print(f"[OK] SLA Local Fixture Store sync completed in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
