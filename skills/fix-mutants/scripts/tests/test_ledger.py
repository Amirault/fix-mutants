import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "ledger.py"


def row(**fields):
    base = {
        "file": "src/Shop/LoyaltyDiscount.cs",
        "lines": "12",
        "mutator": "Boolean mutation",
        "status": "fixed",
        "pr": 3787,
        "note": "killed in place",
    }
    base.update(fields)
    return base


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "ledger.jsonl"
        spec = importlib.util.spec_from_file_location("ledger", SCRIPT)
        self.ledger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ledger)

    def write(self, *rows):
        self.path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def run_cli(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.ledger.main(["--ledger", str(self.path), *arguments])
        return code, out.getvalue(), err.getvalue()

    def test_given_valid_rows_when_validating_should_succeed(self):
        # Given
        self.write(row(), row(status="skipped", category="equivalent", pr=3681), row(status="queued", pr=None))

        # When
        code, _, err = self.run_cli("validate")

        # Then
        self.assertEqual((code, err), (0, ""))

    def test_given_unknown_status_when_validating_should_name_the_row(self):
        # Given
        self.write(row(), row(status="🟢 Fixed"))

        # When
        code, _, err = self.run_cli("validate")

        # Then
        self.assertEqual(code, 1)
        self.assertIn("row 2: status", err)

    def test_given_skip_without_category_when_validating_should_fail(self):
        # Given
        self.write(row(status="skipped"))

        # When
        code, _, err = self.run_cli("validate")

        # Then
        self.assertEqual(code, 1)
        self.assertIn("row 1: category", err)

    def test_given_category_on_a_fixed_row_when_validating_should_fail(self):
        # Given
        self.write(row(category="equivalent"))

        # When
        code, _, err = self.run_cli("validate")

        # Then
        self.assertEqual(code, 1)
        self.assertIn("row 1: category", err)

    def test_given_pr_as_a_link_when_validating_should_fail(self):
        # Given
        self.write(row(pr="[#3787](https://github.com/example/repo/pull/3787)"))

        # When
        code, _, err = self.run_cli("validate")

        # Then
        self.assertEqual(code, 1)
        self.assertIn("row 1: pr", err)

    def test_given_commit_that_is_not_a_sha_when_validating_should_fail(self):
        # Given
        self.write(row(commit="#3787"))

        # When
        code, _, err = self.run_cli("validate")

        # Then
        self.assertEqual(code, 1)
        self.assertIn("row 1: commit", err)

    def test_given_unknown_field_when_validating_should_fail(self):
        # Given
        self.write(row(status_note="typo"))

        # When
        code, _, err = self.run_cli("validate")

        # Then
        self.assertEqual(code, 1)
        self.assertIn("row 1: unknown field status_note", err)

    def test_given_broken_json_line_when_validating_should_name_the_row(self):
        # Given
        self.path.write_text(json.dumps(row()) + "\n{not json\n", encoding="utf-8")

        # When
        code, _, err = self.run_cli("validate")

        # Then
        self.assertEqual(code, 1)
        self.assertIn("row 2", err)

    def test_given_rows_when_finding_by_file_and_status_should_print_only_matches_with_their_row_number(self):
        # Given
        self.write(
            row(),
            row(file="src/Shop/Text/StringExtensions.cs", status="queued", pr=None),
            row(status="queued", pr=None),
        )

        # When
        code, out, _ = self.run_cli("find", "--file", "LoyaltyDiscount", "--status", "queued")

        # Then
        self.assertEqual(code, 0)
        self.assertEqual([json.loads(line)["row"] for line in out.splitlines()], [3])

    def test_given_a_file_name_inside_a_longer_name_when_finding_should_not_match_it(self):
        # Given
        self.write(
            row(file="src/Shop/Text/JsonStringExtensions.cs"),
            row(file="src/Shop/Text/StringExtensions.cs"),
            row(file="src/{Cart,Checkout}/Text/StringExtensions.cs, src/Shop/Conversion.cs"),
        )

        # When
        code, out, _ = self.run_cli("find", "--file", "StringExtensions.cs")

        # Then
        self.assertEqual(code, 0)
        self.assertEqual([json.loads(line)["row"] for line in out.splitlines()], [2, 3])

    def test_given_a_valid_row_when_adding_should_append_it(self):
        # Given
        self.write(row())

        # When
        code, _, _ = self.run_cli("add", json.dumps(row(lines="22", pr="pending")))

        # Then
        self.assertEqual(code, 0)
        self.assertEqual([r["lines"] for r in self.ledger.load(self.path)], ["12", "22"])

    def test_given_an_invalid_row_when_adding_should_leave_the_ledger_unchanged(self):
        # Given
        self.write(row())
        before = self.path.read_text(encoding="utf-8")

        # When
        code, _, err = self.run_cli("add", json.dumps(row(status="skipped")))

        # Then
        self.assertEqual(code, 1)
        self.assertIn("category", err)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_given_a_queued_row_when_updating_it_should_merge_the_fields_in_place(self):
        # Given
        self.write(row(), row(status="queued", pr=None, note="dead but tested"))

        # When
        code, _, _ = self.run_cli("update", "2", json.dumps({"status": "fixed", "pr": "pending", "note": "deleted"}))

        # Then
        self.assertEqual(code, 0)
        self.assertEqual(self.ledger.load(self.path)[1], row(pr="pending", note="deleted"))

    def test_given_an_update_removing_a_field_when_updating_should_drop_it(self):
        # Given
        self.write(row(status="skipped", category="equivalent"))

        # When
        code, _, _ = self.run_cli("update", "1", json.dumps({"status": "queued", "category": None}))

        # Then
        self.assertEqual(code, 0)
        self.assertNotIn("category", self.ledger.load(self.path)[0])

    def test_given_an_unknown_row_when_updating_should_fail(self):
        # Given
        self.write(row())

        # When
        code, _, err = self.run_cli("update", "5", json.dumps({"status": "queued"}))

        # Then
        self.assertEqual(code, 1)
        self.assertIn("row 5", err)

    def test_given_pending_rows_when_filling_the_pr_should_replace_only_pending(self):
        # Given
        self.write(row(pr=3681), row(pr="pending"), row(status="queued", pr="pending"))

        # When
        code, _, _ = self.run_cli("fill-pr", "3800")

        # Then
        self.assertEqual(code, 0)
        self.assertEqual([r["pr"] for r in self.ledger.load(self.path)], [3681, 3800, 3800])

    def test_given_no_pending_row_when_filling_the_pr_should_fail(self):
        # Given
        self.write(row())

        # When
        code, _, err = self.run_cli("fill-pr", "3800")

        # Then
        self.assertEqual(code, 1)
        self.assertIn("pending", err)

    def test_given_no_ledger_file_yet_when_adding_should_create_it(self):
        # Given
        self.assertFalse(self.path.exists())

        # When
        code, _, err = self.run_cli("add", json.dumps(row(status="queued", pr=None)))

        # Then
        self.assertEqual(code, 0, err)
        self.assertEqual(self.ledger.load(self.path), [row(status="queued", pr=None)])

    def test_given_a_nested_working_directory_when_finding_the_ledger_should_use_the_nearest_profile_folder(self):
        # Given
        project = Path(self.temporary.name) / "project"
        (project / ".fix-mutants").mkdir(parents=True)
        nested = project / "src" / "Shop"
        nested.mkdir(parents=True)

        # When
        found = self.ledger.find_ledger(nested)

        # Then
        self.assertEqual(found, (project / ".fix-mutants" / "ledger.jsonl").resolve())

    def test_given_no_profile_folder_when_finding_the_ledger_should_fail(self):
        # Given
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()

        # When / Then
        with self.assertRaisesRegex(ValueError, "init_profile"):
            self.ledger.find_ledger(outside)


if __name__ == "__main__":
    unittest.main()
