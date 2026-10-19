import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "mutant_checks.py"


class MutantChecksTests(unittest.TestCase):
    def setUp(self):
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for name in [name for name in os.environ if name.startswith("GIT_")]:
            del os.environ[name]
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.target = "src/App/Example.cs"
        self.source = self.repo / self.target
        self.source.parent.mkdir(parents=True)
        self.source.write_text("class Example { }\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        spec = importlib.util.spec_from_file_location("mutant_checks", SCRIPT)
        self.checks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.checks)
        self.profile = Path(self.temporary.name) / ".fix-mutants" / "profile.json"
        self.profile.parent.mkdir()
        self.profile.write_text(json.dumps({
            "production_root": "src/App",
            "test_roots": ["tests/App.Tests"],
            "report_schema_version": "2",
            "declaration_pattern": r"\b(?:record(?:\s+(?:class|struct))?|class|struct|interface|enum)\s+(\w+)",
        }), encoding="utf-8")
        self.checks.use_profile(self.profile)
        self.mutant = {
            "id": "0",
            "path": self.target,
            "mutator": "Block removal mutation",
            "location": {
                "start": {"line": 1, "column": 1},
                "end": {"line": 1, "column": 18},
            },
            "status": "NoCoverage",
        }

    def git(self, *arguments):
        return subprocess.check_output(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *arguments],
            cwd=self.repo,
            text=True,
            stderr=subprocess.PIPE,
        ).strip()

    def test_given_another_profile_when_checking_change_should_use_its_production_root(self):
        # Given
        profile = self.repo / "profile.json"
        profile.write_text(
            json.dumps({
                "production_root": "src/app",
                "test_roots": ["src/app.tests"],
                "declaration_pattern": r"\bclass\s+(\w+)",
            }),
            encoding="utf-8",
        )
        self.addCleanup(self.checks.use_profile, self.profile)
        self.checks.use_profile(profile)

        # When / Then
        with self.assertRaisesRegex(ValueError, "inside the production scope"):
            self.checks.check_change(self.repo, "HEAD", self.target, "test")

    def test_given_raw_report_when_building_baseline_should_keep_only_alive_mutants_with_repo_paths(self):
        # Given
        report = self.report()
        report["files"]["Example.cs"]["mutants"].append({
            "id": "1", "mutatorName": "x", "location": self.mutant["location"], "status": "Survived",
        })
        report["files"]["Example.cs"]["mutants"][0]["status"] = "Killed"
        raw = self.repo / "raw.json"
        raw.write_text(json.dumps(report), encoding="utf-8")

        # When
        baseline = self.checks.make_baseline(self.repo, raw)

        # Then
        self.assertEqual([m["id"] for m in baseline["mutants"]], ["1"])
        self.assertEqual(baseline["mutants"][0]["path"], self.target)
        self.assertEqual(baseline["counts"], {"Killed": 1, "Survived": 1, "remaining": 1})
        self.assertEqual(len(baseline["report_sha256"]), 64)

    def test_given_baseline_when_describing_mutants_should_show_original_code(self):
        # Given
        baseline = {"mutants": [self.mutant]}

        # When
        rows = self.checks.describe_mutants(self.repo, baseline)

        # Then
        self.assertEqual(rows[0]["original"], "class Example { }")

    def test_given_profile_below_repo_root_when_finding_it_should_locate_it(self):
        # Given
        nested = self.repo / "tools" / "app" / ".fix-mutants"
        nested.mkdir(parents=True)
        (nested / "profile.json").write_text("{}", encoding="utf-8")
        self.profile.unlink()

        # When
        with tempfile.TemporaryDirectory() as elsewhere:
            found = self.checks.find_profile(elsewhere, repo=self.repo)

        # Then
        self.assertEqual(found, (nested / "profile.json").resolve())

    def test_given_no_profile_when_finding_it_should_explain_how_to_create_one(self):
        # When / Then
        with tempfile.TemporaryDirectory() as empty, self.assertRaisesRegex(ValueError, "init_profile"):
            self.checks.find_profile(empty)

    def test_given_siblings_sharing_location_and_mutator_when_verifying_should_match_by_replacement(self):
        # Given
        report = self.report()
        killed = report["files"]["Example.cs"]["mutants"][0]
        killed.update(replacement="x > 5")
        sibling = {**killed, "id": "1", "replacement": "x < 5", "status": "Survived", "killedBy": []}
        report["files"]["Example.cs"]["mutants"].append(sibling)
        target = {**self.mutant, "replacement": "x > 5"}

        # When
        result = self.checks.verify_report(
            report, self.repo, target, "test", new_test="GivenInput_WhenAction_ShouldResult"
        )

        # Then
        self.assertEqual(result["alive_in_scope"], 1)

    def test_given_qualified_test_name_in_report_when_verifying_should_accept_the_short_name(self):
        # Given
        report = self.report()
        report["testFiles"][next(iter(report["testFiles"]))]["tests"][0]["name"] = "Ns.Class.GivenInput_WhenAction_ShouldResult"

        # When / Then
        self.checks.verify_report(
            report, self.repo, self.mutant, "test", new_test="GivenInput_WhenAction_ShouldResult"
        )

    def test_given_staged_test_and_production_files_when_gating_should_reject_production(self):
        # Given
        test_file = self.repo / "tests/App.Tests/ExampleTests.cs"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("// test\n", encoding="utf-8")
        self.git("add", "tests")

        # When / Then
        self.assertEqual(self.checks.check_test_only(self.repo), ["tests/App.Tests/ExampleTests.cs"])
        self.source.write_text("class Changed { }\n", encoding="utf-8")
        self.git("add", self.target)
        with self.assertRaisesRegex(ValueError, "not test-only"):
            self.checks.check_test_only(self.repo)

    def test_given_empty_tracked_file_when_checking_removal_should_reject_it(self):
        # Given
        self.source.write_text("", encoding="utf-8")
        self.git("add", self.target)

        # When / Then
        with self.assertRaisesRegex(ValueError, "still exists"):
            self.checks.check_change(self.repo, "HEAD", self.target, "removed")

    def test_given_unstaged_deletion_when_checking_removal_should_reject_it(self):
        # Given
        self.source.unlink()

        # When / Then
        with self.assertRaisesRegex(ValueError, "staged"):
            self.checks.check_change(self.repo, "HEAD", self.target, "removed")

    def test_given_staged_deletion_when_checking_removal_should_accept_it(self):
        # Given
        self.git("rm", self.target)

        # When / Then
        self.checks.check_change(self.repo, "HEAD", self.target, "removed")

    def test_given_partial_removal_when_checking_change_should_require_original_code_absent(self):
        # Given
        self.source.write_text("class Remaining { }\n", encoding="utf-8")
        self.git("add", self.target)

        # When / Then
        self.checks.check_change(
            self.repo, "HEAD", self.target, "removed", removed_code="class Example { }"
        )
        with self.assertRaisesRegex(ValueError, "base"):
            self.checks.check_change(
                self.repo, "HEAD", self.target, "removed", removed_code="invented code"
            )

    def test_given_crlf_bom_file_when_checking_partial_removal_should_accept_it(self):
        # Given
        self.source.write_bytes(b"\xef\xbb\xbfclass Example { }\r\nclass Other { }\r\n")
        self.git("add", self.target)
        self.git("commit", "-qm", "crlf source")
        self.source.write_bytes(b"\xef\xbb\xbfclass Other { }\r\n")
        self.git("add", self.target)

        # When / Then
        self.checks.check_change(
            self.repo, "HEAD", self.target, "removed", removed_code="class Example { }\r\n"
        )

    def test_given_move_when_checking_change_should_require_staged_destination_outside_production_scope(self):
        # Given
        destination = self.target.replace("src/App", "src/Infra")
        moved = self.repo / destination
        moved.parent.mkdir(parents=True)
        self.git("mv", self.target, destination)

        # When / Then
        self.checks.check_change(self.repo, "HEAD", self.target, "moved", destination=destination)
        with self.assertRaisesRegex(ValueError, "outside the production scope"):
            self.checks.check_change(self.repo, "HEAD", self.target, "moved", destination=self.target)

    def report(self, status="Killed", killed_by=None):
        return {
            "schemaVersion": "2",
            "projectRoot": str(self.source.parent),
            "files": {
                "Example.cs": {
                    "source": self.source.read_text(encoding="utf-8") if self.source.exists() else "",
                    "mutants": [{
                        "id": "999",
                        "mutatorName": self.mutant["mutator"],
                        "location": self.mutant["location"],
                        "status": status,
                        "killedBy": ["new-test"] if killed_by is None else killed_by,
                    }],
                }
            },
            "testFiles": {
                str(self.repo / "tests/App.Tests/ExampleTests.cs"): {
                    "tests": [{"id": "new-test", "name": "GivenInput_WhenAction_ShouldResult"}]
                }
            },
        }

    def verify(self, report, outcome="test"):
        return self.checks.verify_report(
            report, self.repo, self.mutant, outcome,
            new_test="GivenInput_WhenAction_ShouldResult",
        )

    def test_given_kill_by_new_test_when_verifying_should_match_location_not_mutant_id(self):
        # Given
        report = self.report()

        # When
        result = self.verify(report)

        # Then
        self.assertEqual(result["alive_in_scope"], 0)

    def test_given_unkilled_or_wrong_killer_when_verifying_should_reject_it(self):
        # Given
        reports = [self.report("Survived"), self.report(killed_by=["old-test"])]

        # When / Then
        for report in reports:
            with self.subTest(report=report), self.assertRaises(ValueError):
                self.verify(report)

    def test_given_active_mutant_outside_scope_when_verifying_should_reject_it(self):
        # Given
        report = self.report()
        report["files"]["Other.cs"] = report["files"]["Example.cs"]

        # When / Then
        with self.assertRaisesRegex(ValueError, "outside scope"):
            self.verify(report)

    def test_given_foreign_or_empty_test_inventory_when_verifying_should_reject_it(self):
        # Given
        report = self.report()
        inventories = [{}, {"../Other.Tests/Other.cs": {"tests": []}}]

        # When / Then
        for inventory in inventories:
            report["testFiles"] = inventory
            with self.subTest(inventory=inventory), self.assertRaisesRegex(ValueError, "test inventory"):
                self.verify(report)

    def test_given_deleted_file_when_verifying_should_reject_empty_report_entry(self):
        # Given
        self.git("rm", self.target)
        report = self.report()
        report["files"]["Example.cs"] = {"source": "", "mutants": []}

        # When / Then
        with self.assertRaisesRegex(ValueError, "deleted source"):
            self.verify(report, "removed")
        report["files"] = {}
        self.assertEqual(self.verify(report, "removed")["outcome"], "removed")

    def test_given_stale_source_when_verifying_should_reject_report(self):
        # Given
        report = self.report()
        report["files"]["Example.cs"]["source"] = "old source"

        # When / Then
        with self.assertRaisesRegex(ValueError, "source differs"):
            self.verify(report)

    def cli(self, action, *arguments):
        baseline = self.repo / "baseline.json"
        baseline.write_text(json.dumps({"mutants": [self.mutant]}), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable, str(SCRIPT), action,
                "--repo", str(self.repo), "--base", "HEAD",
                "--baseline", str(baseline), "--mutant-id", "0",
                *map(str, arguments),
            ],
            cwd=self.repo, capture_output=True, text=True,
        )

    def test_given_invalid_deletion_when_checking_cli_should_exit_nonzero(self):
        # When
        result = self.cli("check", "--outcome", "removed")

        # Then
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("still exists", result.stderr)

    def test_given_broad_excerpt_with_unchanged_target_when_checking_should_reject_it(self):
        # Given
        original = "class Example { }\nclass Unrelated { }\n"
        self.source.write_text(original)
        self.git("add", self.target)
        self.git("commit", "-qm", "add unrelated class")
        self.source.write_text("class Example { }\n")
        self.git("add", self.target)

        # When
        result = self.cli("check", "--outcome", "removed", "--removed-code", original)

        # Then
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target span still exists", result.stderr)

    def test_given_remaining_target_in_partial_removal_report_when_verifying_should_reject_it(self):
        # Given
        report = self.report("NoCoverage")

        # When / Then
        with self.assertRaisesRegex(ValueError, "target mutation still exists"):
            self.checks.verify_report(
                report, self.repo, self.mutant, "removed", removed_code="class Unrelated { }"
            )

    def test_given_unchanged_move_destination_when_checking_should_reject_it(self):
        # Given
        destination = self.target.replace("src/App", "src/Infra")
        moved = self.repo / destination
        moved.parent.mkdir(parents=True)
        moved.write_text(self.source.read_text())
        self.git("add", destination)
        self.git("commit", "-qm", "add existing destination")
        self.git("rm", self.target)

        # When / Then
        with self.assertRaisesRegex(ValueError, "destination must be changed"):
            self.checks.check_change(self.repo, "HEAD", self.target, "moved", destination=destination)

    def test_given_unrelated_staged_move_destination_when_checking_should_reject_it(self):
        # Given
        destination = self.target.replace("src/App", "src/Infra")
        moved = self.repo / destination
        moved.parent.mkdir(parents=True)
        moved.write_text("class Unrelated { }\n")
        self.git("add", destination)
        self.git("rm", self.target)

        # When / Then
        with self.assertRaisesRegex(ValueError, "original declarations"):
            self.checks.check_change(self.repo, "HEAD", self.target, "moved", destination=destination)

    def test_given_unrelated_removed_excerpt_when_checking_should_reject_it(self):
        # Given
        self.source.write_text("class Example { }\nclass Unrelated { }\n")
        self.git("add", self.target)
        self.git("commit", "-qm", "add unrelated class")
        self.source.write_text("class Example { }\n")
        self.git("add", self.target)

        # When
        result = self.cli("check", "--outcome", "removed", "--removed-code", "class Unrelated { }\n")

        # Then
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target span", result.stderr)

    def test_given_reformatted_not_removed_code_when_checking_should_reject_it(self):
        # Given
        self.source.write_text("class Example {\n}\n")
        self.git("add", self.target)

        # When
        result = self.cli("check", "--outcome", "removed", "--removed-code", "class Example { }")

        # Then
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("still exists", result.stderr)

    def test_given_current_removal_report_when_verifying_should_not_create_files(self):
        # Given
        self.git("rm", self.target)
        report = self.report()
        report["files"] = {}
        report_path = self.repo / "mutation-report.json"
        report_path.write_text(json.dumps(report))
        (self.repo / "baseline.json").write_text(json.dumps({"mutants": [self.mutant]}))
        before = set(self.repo.rglob("*"))

        # When
        result = self.cli("verify", "--outcome", "removed", "--report", report_path)

        # Then
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["alive_in_scope"], 0)
        self.assertEqual(set(self.repo.rglob("*")), before)

    def test_given_current_kill_report_when_verifying_cli_should_accept_new_test(self):
        # Given
        report_path = self.repo / "mutation-report.json"
        report_path.write_text(json.dumps(self.report()))

        # When
        result = self.cli(
            "verify", "--outcome", "test", "--report", report_path,
            "--new-test", "GivenInput_WhenAction_ShouldResult",
        )

        # Then
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "test")

    def test_given_two_utc_timestamps_when_computing_duration_should_be_human_readable(self):
        # Given
        cases = {
            ("2026-09-30T08:00:00Z", "2026-09-30T08:00:45Z"): (45, "45s"),
            ("2026-09-30T08:00:00Z", "2026-09-30T08:38:29Z"): (2309, "38m 29s"),
            ("2026-09-30T08:00:00Z", "2026-09-30T09:00:05Z"): (3605, "1h 0m 5s"),
            ("2026-09-30T08:00:00Z", "2026-10-01T10:03:04Z"): (93784, "1d 2h 3m 4s"),
            ("2026-09-30T08:00:00Z", "2026-09-30T08:00:00Z"): (0, "0s"),
        }

        for (start, end), (seconds, human) in cases.items():
            with self.subTest(start=start, end=end):
                # When
                result = self.checks.duration(start, end)

                # Then
                self.assertEqual(result, {"seconds": seconds, "human": human})

    def test_given_end_before_start_when_computing_duration_cli_should_exit_nonzero(self):
        # When
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT), "duration",
                "--start", "2026-09-30T08:00:01Z", "--end", "2026-09-30T08:00:00Z",
            ],
            capture_output=True, text=True,
        )

        # Then
        self.assertEqual(result.returncode, 1)

    def test_given_timestamps_when_computing_duration_cli_should_print_json(self):
        # When
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT), "duration",
                "--start", "2026-09-30T08:00:00Z", "--end", "2026-09-30T08:38:29Z",
            ],
            capture_output=True, text=True,
        )

        # Then
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"seconds": 2309, "human": "38m 29s"})


if __name__ == "__main__":
    unittest.main()
