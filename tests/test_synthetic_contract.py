import os
import re
import subprocess
import unittest
from pathlib import Path

from scripts.synthetic_e2e import ROOT, run_pipeline, scan_files, scan_text


class SyntheticContractTest(unittest.TestCase):
    def test_encoding_gate_rejects_c0_controls(self):
        coverage = {"text": 0, "json": 0, "workbook": 0, "sqlite": 0, "binary": 0, "screenshots": 0, "unknown": 0}
        for codepoint in (0x00, 0x07, 0x0B, 0x1F):
            findings = []
            scan_text(ROOT / "synthetic-control-fixture.txt", b"clean" + bytes([codepoint]), coverage, findings)
            self.assertTrue(findings, f"C0 U+{codepoint:04X} was accepted")

    def test_encoding_gate_allows_valid_utf8_unicode(self):
        coverage = {"text": 0, "json": 0, "workbook": 0, "sqlite": 0, "binary": 0, "screenshots": 0, "unknown": 0}
        findings = []
        scan_text(ROOT / "synthetic-unicode-fixture.txt", "café — ✅".encode("utf-8"), coverage, findings)
        self.assertEqual(findings, [])

    def test_end_to_end_contract(self):
        result = run_pipeline(write_manifest=False)
        self.assertEqual(result["stages"]["load"], "GREEN", result["errors"])
        self.assertEqual(result["stages"]["etl_transform"], "GREEN", result["errors"])
        self.assertEqual(result["stages"]["query"]["status"], "GREEN", result["errors"])
        self.assertEqual(result["stages"]["filters"]["status"], "GREEN", result["errors"])
        self.assertEqual(result["stages"]["ui_static_smoke"]["status"], "GREEN", result["errors"])
        self.assertEqual(result["stages"]["quality_scan"]["status"], "GREEN", result["errors"])
        self.assertEqual(result["stages"]["browser_smoke"]["status"], "GREEN", result["errors"])
        self.assertEqual(result["status"], "GREEN", result["errors"])
        self.assertGreater(result["evidence"]["normalized_rows"], 0)

    def test_quality_scan_releases_sqlite_files(self):
        result = scan_files()
        self.assertEqual(result["status"], "GREEN", result["findings"])

        database = ROOT / "dashboard" / "data" / "invoices.db"
        probe = database.with_suffix(".release-probe")
        self.assertFalse(probe.exists(), probe)
        try:
            os.replace(database, probe)
            os.replace(probe, database)
        finally:
            if probe.exists():
                os.replace(probe, database)

    def test_run_daily_log_is_sanitized_and_useful(self):
        log_dir = ROOT / "runtime" / "logs"
        before = set(log_dir.glob("run_daily_*.log"))
        completed = subprocess.run(
            ["cmd", "/d", "/c", str(ROOT / "automation" / "RUN_DAILY.bat")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

        created = sorted(set(log_dir.glob("run_daily_*.log")) - before)
        self.assertEqual(len(created), 1, f"expected one new daily log, found: {created}")
        log_path = created[0]
        raw = log_path.read_bytes()
        coverage = {"text": 0, "json": 0, "workbook": 0, "sqlite": 0, "binary": 0, "screenshots": 0, "unknown": 0}
        findings = []
        scan_text(log_path, raw, coverage, findings)
        self.assertEqual(findings, [], findings)

        text = raw.decode("utf-8-sig")
        folded = text.casefold()
        host_values = {
            os.environ.get("USERNAME"),
            os.environ.get("USERDOMAIN"),
            str(Path.home()),
            str(ROOT.resolve()),
        }
        for value in host_values:
            if value:
                self.assertNotIn(value.casefold(), folded)
        self.assertIsNone(re.search(r"(?i)(?<![a-z0-9])[a-z]:[\\/]", text), text)
        for transcript_field in ("Username:", "RunAs User:", "Machine:", "Host Application:"):
            self.assertNotIn(transcript_field, text)

        self.assertIn("[OK] RUN_DAILY lock acquired: runtime\\locks\\run_daily.lock", text)
        self.assertIn("[OK] DB integrity: ok", text)
        self.assertIn("invoice_rows=2", text)
        self.assertIn("[OK] Dashboard exported in pack: dashboard", text)
        self.assertIn("[OK] RUN_DAILY completed: exit_code=0", text)


if __name__ == "__main__":
    unittest.main()
