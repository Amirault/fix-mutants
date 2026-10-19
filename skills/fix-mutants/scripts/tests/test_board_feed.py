import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "board_feed.py"
spec = importlib.util.spec_from_file_location("board_feed", SCRIPT)
board_feed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board_feed)

TS = "2026-10-12T00:39:37.000Z"
TEST_FILE = "/repo/tests/Shop.Tests/Quotation/QuoteTests.cs"
PRODUCTION_FILE = "/repo/src/Shop/Quotation/Quote.cs"
INFRASTRUCTURE_FILE = "/repo/src/Shop.Storage/BlobClient.cs"
TRACKER = "/repo/.fix-mutants/MUTATION-TRACKING.md"
LEDGER = "/repo/.fix-mutants/ledger.jsonl"
LAYOUT = board_feed.Layout("src/Shop", ["tests/Shop.Tests"])


def user(text, ts=TS):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": text}}


def say(text):
    return {"type": "assistant", "timestamp": TS, "message": {"content": [{"type": "text", "text": text}]}}


def tool(name, **tool_input):
    return {"type": "assistant", "timestamp": TS, "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]}}


def bash(command):
    return tool("Bash", command=command)


def caller_search():
    return bash("rg -n -g '*.cs' -w 'Quote' . | rg -v '\\.Tests/'")


def verify():
    return bash("python3 scripts/mutant_checks.py verify --report r.json --target t.json")


def one_fixed_mutant():
    return [caller_search(), verify(), bash("git add -A src tests")]


def events_of(entries):
    feed = board_feed.Feed(LAYOUT)
    return [event for entry in entries for event in feed.push(entry)]


def steps_of(entries):
    return [event["step"] for event in events_of(entries)]


def steps_after_start(entries):
    return steps_of([user("/fix-mutants"), *entries])[1:]


class StartTests(unittest.TestCase):
    def test_given_no_invocation_when_tools_run_then_nothing_is_emitted(self):
        # Given
        entries = [bash("git add . && git commit -m x"), say("hello")]

        # When
        emitted = steps_of(entries)

        # Then
        self.assertEqual(emitted, [])

    def test_given_the_slash_command_when_pushed_then_the_run_starts_at_its_timestamp(self):
        # Given
        invocation = user("/fix-mutants 3 targets", ts="2026-10-12T00:39:37Z")

        # When
        emitted = events_of([invocation])

        # Then
        self.assertEqual([(e["step"], e["t"]) for e in emitted], [("start", 1791765577.0)])

    def test_given_the_skill_tool_when_pushed_then_the_run_starts(self):
        # Given
        invocation = tool("Skill", skill="fix-mutants")

        # When
        emitted = steps_of([invocation])

        # Then
        self.assertEqual(emitted, ["start"])

    def test_given_a_command_tag_when_pushed_then_the_run_starts(self):
        # Given
        invocation = user("<command-name>/fix-mutants</command-name>")

        # When
        emitted = steps_of([invocation])

        # Then
        self.assertEqual(emitted, ["start"])

    def test_given_a_second_invocation_when_pushed_then_the_run_does_not_restart(self):
        # Given
        entries = [user("/fix-mutants"), user("/fix-mutants")]

        # When
        emitted = steps_of(entries)

        # Then
        self.assertEqual(emitted, ["start"])


class SetupTests(unittest.TestCase):
    def test_given_the_baseline_fetch_when_run_then_the_report_step_is_emitted(self):
        # Given
        fetch = bash("python3 scripts/mutant_checks.py --profile .fix-mutants/profile.json baseline --repo . --report r.json --out b.json")

        # When
        emitted = steps_after_start([fetch])

        # Then
        self.assertEqual(emitted, ["report"])

    def test_given_a_survey_agent_when_launched_then_the_report_step_carries_the_survey_actor(self):
        # Given
        entries = [user("/fix-mutants"), tool("Agent", description="Survey mutants idx 364-395", prompt="...")]

        # When
        emitted = events_of(entries)[1:]

        # Then
        self.assertEqual([(e["step"], e.get("actor")) for e in emitted], [("report", "survey")])

    def test_given_the_tracker_read_during_setup_when_run_then_the_sync_step_is_emitted(self):
        # Given
        read = tool("Read", file_path=TRACKER)

        # When
        emitted = steps_after_start([read])

        # Then
        self.assertEqual(emitted, ["sync"])

    def test_given_a_clock_reading_after_the_sync_when_run_then_a_mutant_is_picked(self):
        # Given
        entries = [tool("Read", file_path=TRACKER), bash("date -u +%Y-%m-%dT%H:%M:%SZ")]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["sync", "pick"])

    def test_given_the_request_clock_reading_when_nothing_is_synced_then_no_mutant_is_picked(self):
        # Given
        clock = bash("date -u +%Y-%m-%dT%H:%M:%SZ")

        # When
        emitted = steps_after_start([clock])

        # Then
        self.assertEqual(emitted, [])


class LedgerTests(unittest.TestCase):
    def test_given_the_ledger_queue_read_during_setup_when_run_then_the_sync_step_is_emitted(self):
        # Given
        find = bash("python3 .claude/skills/fix-mutants/scripts/ledger.py find --status queued")

        # When
        emitted = steps_after_start([find])

        # Then
        self.assertEqual(emitted, ["sync"])

    def test_given_a_skipped_ledger_row_added_for_the_open_mutant_when_run_then_the_skip_path_is_taken(self):
        # Given
        add = bash('python3 $L add \'{"file": "Quote.cs", "status": "skipped", "category": "real-defect"}\'')

        # When
        emitted = steps_after_start([caller_search(), add])

        # Then
        self.assertEqual(emitted, ["pick", "trace", "skip"])

    def test_given_a_fixed_ledger_row_added_for_the_open_mutant_when_run_then_no_step_is_emitted(self):
        # Given
        add = bash('python3 $L add \'{"file": "Quote.cs", "status": "fixed", "pr": "pending"}\'')

        # When
        emitted = steps_after_start([caller_search(), add])

        # Then
        self.assertEqual(emitted, ["pick", "trace"])

    def test_given_the_pr_link_filled_in_the_ledger_after_the_pr_when_run_then_the_ledger_step_is_emitted(self):
        # Given
        entries = [*one_fixed_mutant(), bash("git commit -m x"), bash("gh pr create"), bash("python3 $L fill-pr 3813")]

        # When
        emitted = steps_after_start(entries)[6:]

        # Then
        self.assertEqual(emitted, ["commit", "pr", "ledger"])


class MutantTests(unittest.TestCase):
    def test_given_a_caller_search_without_a_mutant_when_run_then_a_mutant_is_picked_and_traced(self):
        # Given
        search = caller_search()

        # When
        emitted = steps_after_start([search])

        # Then
        self.assertEqual(emitted, ["pick", "trace"])

    def test_given_a_new_test_when_edited_then_the_test_path_is_taken(self):
        # Given
        entries = [caller_search(), tool("Edit", file_path=TEST_FILE, old_string="a", new_string="b")]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test"])

    def test_given_stryker_and_verify_when_run_then_the_mutant_is_verified_and_killed(self):
        # Given
        entries = [
            caller_search(),
            tool("Write", file_path=TEST_FILE, content="class QuoteTests {}"),
            bash('cd tests/Shop.Tests && dotnet stryker --mutate "**/Quote.cs" --reporter json'),
            verify(),
        ]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test", "verify", "kill"])

    def test_given_a_verify_without_any_edit_when_run_then_the_test_path_is_inferred(self):
        # Given
        entries = [caller_search(), verify()]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test", "verify", "kill"])

    def test_given_a_production_removal_when_verified_then_the_dead_code_path_is_taken(self):
        # Given
        entries = [caller_search(), bash(f"git rm -q {PRODUCTION_FILE}"), bash("python3 mutant_checks.py check"), verify()]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "dead", "verify", "kill"])

    def test_given_code_written_in_another_layer_when_verified_then_the_move_path_is_taken(self):
        # Given
        entries = [caller_search(), tool("Write", file_path=INFRASTRUCTURE_FILE, content="x"), bash("python3 mutant_checks.py check"), verify()]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "move", "verify", "kill"])

    def test_given_a_skipped_ledger_row_for_the_open_mutant_when_written_then_the_skip_path_is_taken(self):
        # Given
        entries = [caller_search(), tool("Write", file_path=LEDGER, content='{"file": "Quote.cs", "status": "skipped", "category": "real-defect"}\n')]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "skip"])

    def test_given_a_verify_called_through_a_variable_when_run_then_the_mutant_is_killed(self):
        # Given
        entries = [caller_search(), bash("TOOL=$REPO/.claude/skills/fix-mutants/scripts/mutant_checks.py; python3 $TOOL verify --mutant-id 120 --outcome test")]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test", "verify", "kill"])

    def test_given_a_verify_called_through_a_quoted_variable_when_run_then_the_mutant_is_killed(self):
        # Given
        entries = [caller_search(), bash('mise x -- python3 "$TOOL" verify --mutant-id 42 --outcome test --new-test "$TN"')]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test", "verify", "kill"])

    def test_given_verify_named_in_a_heredoc_text_when_run_then_no_mutant_is_verified(self):
        # Given
        entries = [*one_fixed_mutant(), bash("python3 - <<'E'\nentry = 'mutant_checks.py verify exit 0'\nE")]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test", "verify", "kill", "stage"])

    def test_given_a_verify_of_a_removal_when_run_then_the_dead_code_path_is_taken(self):
        # Given
        entries = [caller_search(), bash('python3 $TOOL verify --mutant-id 120 --outcome removed --removed-code "$(cat removed.txt)"')]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "dead", "verify", "kill"])

    def test_given_tests_deleted_with_dead_code_when_verified_then_the_dead_code_path_is_taken(self):
        # Given
        removal = tool("Edit", file_path=TEST_FILE, old_string="[Test]\npublic void Old() { }\n", new_string="")
        entries = [caller_search(), removal, bash("python3 $TOOL verify --outcome removed")]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "dead", "verify", "kill"])

    def test_given_a_staged_mutant_when_verified_again_then_no_other_mutant_is_picked(self):
        # Given
        entries = [*one_fixed_mutant(), bash('npx stryker run --mutate src/quote.js'), verify()]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test", "verify", "kill", "stage"])

    def test_given_a_staged_mutant_when_the_clock_is_read_then_another_mutant_is_picked(self):
        # Given
        entries = [*one_fixed_mutant(), bash("date -u +%Y-%m-%dT%H:%M:%SZ")]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test", "verify", "kill", "stage", "pick"])

    def test_given_a_killed_mutant_when_the_fix_clock_is_read_then_no_mutant_is_picked(self):
        # Given
        entries = [caller_search(), verify(), bash("date -u +%Y-%m-%dT%H:%M:%SZ")]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test", "verify", "kill"])

    def test_given_an_unstaged_killed_mutant_when_another_is_searched_then_the_first_is_staged(self):
        # Given
        entries = [caller_search(), verify(), caller_search()]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test", "verify", "kill", "stage", "pick", "trace"])


class DeliveryTests(unittest.TestCase):
    def test_given_a_review_agent_after_a_fix_when_launched_then_the_review_step_is_emitted(self):
        # Given
        entries = [*one_fixed_mutant(), tool("Agent", description="Fresh independent review of mutant fix", prompt="...")]

        # When
        emitted = steps_after_start(entries)[6:]

        # Then
        self.assertEqual(emitted, ["review"])

    def test_given_a_plan_review_before_any_mutant_when_launched_then_only_a_line_is_said(self):
        # Given
        review = tool("Agent", description="Independent plan review", prompt="...")

        # When
        emitted = steps_after_start([review])

        # Then
        self.assertEqual(emitted, ["say"])

    def test_given_a_review_agent_during_an_open_fix_when_launched_then_only_a_line_is_said(self):
        # Given
        entries = [caller_search(), tool("Agent", description="Review the B3 test", prompt="...")]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "say"])

    def test_given_the_commit_and_the_pr_when_run_then_commit_pr_and_ledger_follow(self):
        # Given
        entries = [
            *one_fixed_mutant(),
            bash("git commit -F - <<'EOF'\ntest(shop): kill it\nEOF"),
            bash("GH_HOST=wakam.ghe.com gh pr create --title t --body-file b"),
            bash("gh pr edit 3681 --body-file b"),
        ]

        # When
        emitted = steps_after_start(entries)[6:]

        # Then
        self.assertEqual(emitted, ["commit", "pr", "ledger"])

    def test_given_a_commit_after_the_pr_when_run_then_it_is_the_ledger_follow_up(self):
        # Given
        entries = [*one_fixed_mutant(), bash("git commit -m x"), bash("gh pr create"), bash("git add t && git commit -m docs")]

        # When
        emitted = steps_after_start(entries)[6:]

        # Then
        self.assertEqual(emitted, ["commit", "pr", "ledger"])

    def test_given_one_command_with_several_signals_when_run_then_steps_follow_the_command_order(self):
        # Given
        entries = [caller_search(), bash("python3 mutant_checks.py verify && git add . && git commit -m x")]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test", "verify", "kill", "stage", "commit"])

    def test_given_a_verify_called_from_a_python_heredoc_when_run_then_the_mutant_is_killed(self):
        # Given
        script = 'python3 - <<\'EOF\'\nimport subprocess\nsubprocess.run(["python3", "scripts/mutant_checks.py", "verify", "--repo", "."])\nEOF'
        entries = [caller_search(), bash(script)]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test", "verify", "kill"])

    def test_given_a_user_prompt_after_the_pr_when_pushed_then_the_human_ends_the_run(self):
        # Given
        entries = [*one_fixed_mutant(), bash("git commit -m x"), bash("gh pr create"), user("review this session"), bash("gh pr create"), say("Next task.")]

        # When
        emitted = steps_after_start(entries)[6:]

        # Then
        self.assertEqual(emitted, ["commit", "pr", "human"])

    def test_given_a_task_notification_after_the_pr_when_pushed_then_the_run_goes_on(self):
        # Given
        entries = [*one_fixed_mutant(), bash("git commit -m x"), bash("gh pr create"), user("<task-notification> done </task-notification>"), bash("gh pr edit 1")]

        # When
        emitted = steps_after_start(entries)[6:]

        # Then
        self.assertEqual(emitted, ["commit", "pr", "ledger"])

    def test_given_signals_inside_a_heredoc_or_quotes_when_run_then_they_are_ignored(self):
        # Given
        entries = [bash("cat > body.md <<'EOF'\nthen gh pr create and git commit\nEOF"), bash("echo 'git commit'")]

        # When
        emitted = steps_after_start(entries)

        # Then
        self.assertEqual(emitted, [])


class SayTests(unittest.TestCase):
    def test_given_agent_text_when_pushed_then_its_first_sentence_is_said(self):
        # Given
        entries = [user("/fix-mutants"), say("I've fetched the new baseline. Now syncing the tracker.")]

        # When
        emitted = events_of(entries)[1:]

        # Then
        self.assertEqual([(e["step"], e["say"]) for e in emitted], [("say", "I've fetched the new baseline.")])

    def test_given_a_long_line_when_said_then_it_is_cut_to_the_bubble_width(self):
        # Given
        entries = [user("/fix-mutants"), say("x" * 300)]

        # When
        line = events_of(entries)[1]["say"]

        # Then
        self.assertEqual((len(line), line[-1]), (board_feed.MAX_SAY, "…"))

    def test_given_an_alive_count_when_said_then_the_count_is_emitted(self):
        # Given
        entries = [user("/fix-mutants"), say("Baseline 10-11 checked: 630 alive.")]

        # When
        emitted = events_of(entries)[1:]

        # Then
        self.assertEqual([(e["step"], e.get("alive")) for e in emitted], [("say", None), ("alive", 630)])

    def test_given_a_later_alive_count_when_said_then_the_baseline_count_is_kept(self):
        # Given
        entries = [user("/fix-mutants"), say("Baseline checked: 630 alive."), say("Only 20 alive in that file.")]

        # When
        emitted = events_of(entries)[1:]

        # Then
        self.assertEqual([e["alive"] for e in emitted if e["step"] == "alive"], [630])


class TranscriptTests(unittest.TestCase):
    def test_given_a_partial_last_line_when_read_twice_then_the_line_is_read_once_complete(self):
        # Given
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "t.jsonl"
        path.write_text(json.dumps(user("/fix-mutants")) + "\n" + '{"type": "us', encoding="utf-8")
        first, offset = board_feed.read_new_entries(path, 0)
        with path.open("a", encoding="utf-8") as stream:
            stream.write('er", "message": {"content": "hi"}}\n')

        # When
        second, _ = board_feed.read_new_entries(path, offset)

        # Then
        self.assertEqual((len(first), second[0]["message"]["content"]), (1, "hi"))

    def test_given_several_transcripts_when_the_newest_run_is_searched_then_the_latest_invocation_wins(self):
        # Given
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        old, other, new = root / "a" / "old.jsonl", root / "b" / "other.jsonl", root / "b" / "subagents" / "new.jsonl"
        for path, text in ((old, "/fix-mutants"), (other, "unrelated"), (new, "/fix-mutants 3")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(user(text)) + "\n", encoding="utf-8")
        os.utime(old, (1, 1))

        # When
        found = board_feed.newest_run(root)

        # Then
        self.assertEqual(found, new)



class LayoutTests(unittest.TestCase):
    def test_given_no_profile_when_a_js_test_file_is_edited_then_the_test_path_is_taken(self):
        # Given
        feed = board_feed.Feed()
        entries = [user("/fix-mutants"), caller_search(), tool("Write", file_path="/repo/test/shipping.test.js", content="x")]

        # When
        emitted = [event["step"] for entry in entries for event in feed.push(entry)][1:]

        # Then
        self.assertEqual(emitted, ["pick", "trace", "test"])

    def test_given_no_profile_when_classifying_then_no_file_is_another_layer(self):
        # Given
        layout = board_feed.Layout()

        # When / Then
        self.assertFalse(layout.is_other_layer(INFRASTRUCTURE_FILE))

    def test_given_a_profile_when_classifying_then_its_roots_decide(self):
        # Given
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / "profile.json"
            profile.write_text(json.dumps({"production_root": "src/Shop", "test_roots": ["tests/Shop.Tests"]}))

            # When
            layout = board_feed.Layout.from_profile(profile)

        # Then
        self.assertTrue(layout.is_test(TEST_FILE))
        self.assertFalse(layout.is_test(PRODUCTION_FILE))
        self.assertTrue(layout.is_other_layer(INFRASTRUCTURE_FILE))
        self.assertFalse(layout.is_other_layer(PRODUCTION_FILE))


if __name__ == "__main__":
    unittest.main()
