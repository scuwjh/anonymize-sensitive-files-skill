import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
RUNNER = SCRIPT_DIR / "run_anonymize.py"


class RunAnonymizeTest(unittest.TestCase):
    def test_dry_run_plans_venv_bootstrap_and_argument_forwarding(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "input.docx",
                "--report",
                "report.json",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
            check=True,
        )

        payload = json.loads(result.stdout)
        self.assertTrue(payload["venv_dir"].endswith("/.venv"))
        self.assertTrue(payload["python"].endswith("/.venv/bin/python"))
        self.assertIn("venv", payload["steps"])
        self.assertIn("install", payload["steps"])
        self.assertTrue(payload["command"][1].endswith("/scripts/anonymize_files.py"))
        self.assertEqual(payload["command"][2:], ["input.docx", "--report", "report.json"])

    def test_no_install_dry_run_skips_dependency_install(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "input.md",
                "--no-install",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
            check=True,
        )

        payload = json.loads(result.stdout)
        self.assertIn("venv", payload["steps"])
        self.assertNotIn("install", payload["steps"])


if __name__ == "__main__":
    unittest.main()
