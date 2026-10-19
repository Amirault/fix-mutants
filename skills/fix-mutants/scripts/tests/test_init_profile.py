import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "init_profile.py"


def load():
    spec = importlib.util.spec_from_file_location("init_profile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InitProfileTests(unittest.TestCase):
    def setUp(self):
        self.init = load()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        subprocess.check_call(["git", "init", "-q"], cwd=self.repo)

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def dotnet_project(self, root=""):
        self.write(f"{root}src/App/App.csproj", "<Project />")
        self.write(
            f"{root}tests/App.Tests/App.Tests.csproj",
            '<Project><ItemGroup><PackageReference Include="Microsoft.NET.Test.Sdk" />'
            '<PackageReference Include="xunit" />'
            '<ProjectReference Include="../../src/App/App.csproj" /></ItemGroup></Project>',
        )

    def run_init(self, *arguments):
        return self.init.main(["--repo", str(self.repo), *arguments])

    def test_given_dotnet_solution_when_initialising_should_pair_production_and_test_projects(self):
        # Given
        self.dotnet_project()

        # When
        code = self.run_init()

        # Then
        profile = json.loads((self.repo / ".fix-mutants/profile.json").read_text())
        self.assertEqual(code, 0)
        self.assertEqual(profile["production_root"], "src/App")
        self.assertEqual(profile["test_roots"], ["tests/App.Tests"])
        self.assertEqual(profile["report_schema_version"], "2")

    def test_given_new_project_when_initialising_should_start_an_empty_ledger(self):
        # Given
        self.dotnet_project()

        # When
        code = self.run_init()

        # Then
        self.assertEqual(code, 0)
        self.assertEqual((self.repo / ".fix-mutants/ledger.jsonl").read_text(), "")

    def test_given_dotnet_project_in_subfolder_when_initialising_should_prefix_paths_with_it(self):
        # Given
        self.dotnet_project("services/shop/")
        self.repo = self.repo / "services" / "shop"

        # When
        self.run_init()

        # Then
        profile = json.loads((self.repo / ".fix-mutants/profile.json").read_text())
        self.assertEqual(profile["production_root"], "services/shop/src/App")
        self.assertEqual(profile["gate_allow"], ["services/shop/.fix-mutants"])

    def test_given_js_project_when_initialising_should_detect_source_and_test_folders(self):
        # Given
        self.write("package.json", json.dumps({"devDependencies": {"jest": "1", "@stryker-mutator/core": "8"}}))
        self.write("src/a.js", "")
        self.write("test/a.test.js", "")

        # When
        self.run_init()

        # Then
        profile = json.loads((self.repo / ".fix-mutants/profile.json").read_text())
        self.assertEqual((profile["production_root"], profile["test_roots"]), ("src", ["test"]))
        self.assertEqual(profile["report_schema_version"], "1.0")
        self.assertIn("ignorePatterns", (self.repo / ".fix-mutants/PROFILE.md").read_text())

    def test_given_unknown_stack_when_initialising_should_fail_and_suggest_generic(self):
        # When / Then
        self.assertEqual(self.run_init(), 2)

    def test_given_existing_profile_when_initialising_without_force_should_not_overwrite(self):
        # Given
        self.dotnet_project()
        self.run_init()
        (self.repo / ".fix-mutants/PROFILE.md").write_text("mine", encoding="utf-8")

        # When
        code = self.run_init()

        # Then
        self.assertEqual(code, 1)
        self.assertEqual((self.repo / ".fix-mutants/PROFILE.md").read_text(), "mine")


if __name__ == "__main__":
    unittest.main()
