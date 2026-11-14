import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = HERE / "check_pins.py"
SHA = "11d5960a326750d5838078e36cf38b85af677262"


def run(*paths):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, paths)],
        capture_output=True,
        text=True,
    )


class CheckPinsOnTemporaryFiles(unittest.TestCase):
    def check(self, line):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "w.yml"
            path.write_text("jobs:\n  a:\n    steps:\n" + line + "\n", encoding="utf-8")
            return run(path), path

    def test_pinned_line_passes(self):
        result, _ = self.check(f"      - uses: actions/checkout@{SHA} # v4.4.0")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")

    def test_tag_ref_fails(self):
        result, path = self.check("      - uses: actions/checkout@v4")
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{path}:4: not pinned: actions/checkout@v4", result.stdout)

    def test_branch_ref_fails(self):
        result, _ = self.check("      - uses: actions/checkout@main")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not pinned: actions/checkout@main", result.stdout)

    def test_short_id_fails(self):
        result, _ = self.check("      - uses: actions/checkout@11d5960 # v4.4.0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not pinned: actions/checkout@11d5960", result.stdout)

    def test_pinned_without_version_comment_fails(self):
        result, _ = self.check(f"      - uses: actions/checkout@{SHA}")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not pinned", result.stdout)

    def test_local_ref_passes(self):
        result, _ = self.check("      - uses: ./.github/workflows/security-scan.yml")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_pin_exempt_example_passes(self):
        result, _ = self.check(
            "      - uses: owner/repo/.github/workflows/x.yml@v1 # pin-exempt: example"
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_exemption_needs_the_exact_comment(self):
        result, _ = self.check("      - uses: owner/repo/.github/workflows/x.yml@v1 # example")
        self.assertEqual(result.returncode, 1)

    def test_exemption_must_name_example(self):
        result, _ = self.check(
            "      - uses: owner/repo/.github/workflows/x.yml@v1 # pin-exempt: later"
        )
        self.assertEqual(result.returncode, 1)

    def test_commented_out_uses_is_ignored(self):
        result, _ = self.check("      # - uses: actions/checkout@v4")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_folder_is_searched(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "bad.yml").write_text("      - uses: a/b@v1\n", encoding="utf-8")
            result = run(folder)
        self.assertEqual(result.returncode, 1)
        self.assertIn("bad.yml:1: not pinned: a/b@v1", result.stdout)

    def test_no_arguments_is_bad_usage(self):
        self.assertEqual(run().returncode, 2)

    def test_missing_path_is_bad_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(run(Path(folder) / "absent.yml").returncode, 2)


class CheckPinsOnThisRepository(unittest.TestCase):
    def test_workflows_folder_is_pinned(self):
        result = run(ROOT / ".github" / "workflows")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_example_caller_passes_only_through_its_exemption(self):
        caller = ROOT / "examples" / "caller.yml"
        self.assertEqual(run(caller).returncode, 0)
        text = caller.read_text(encoding="utf-8").replace("# pin-exempt: example", "")
        with tempfile.TemporaryDirectory() as folder:
            stripped = Path(folder) / "caller.yml"
            stripped.write_text(text, encoding="utf-8")
            result = run(stripped)
        self.assertEqual(result.returncode, 1)
        self.assertIn("security-scan.yml@v1", result.stdout)


if __name__ == "__main__":
    unittest.main()
