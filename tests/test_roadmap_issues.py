"""Tests for the roadmap issue importer (scripts/create_roadmap_issues.py).

Nothing here contacts GitHub: a fake client stands in for the `gh` CLI. Covers
the definitions file (complete, valid, and faithful to issue-backlog.md),
validation of broken definitions, and that reruns never create duplicates.

Run with:  python -m tests.test_roadmap_issues
"""

from __future__ import annotations

import copy
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import create_roadmap_issues as R  # noqa: E402

BACKLOG = ROOT / "docs" / "roadmap" / "issue-backlog.md"

FAILURES: list = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


def definitions() -> dict:
    return R.load_definitions(R.DEFAULT_DEFINITIONS)


class FakeGh:
    """In-memory stand-in for GhClient."""

    def __init__(self, issues=None, labels=None, milestones=None, milestone_error=False, fail_ids=()):
        self.issues = list(issues or [])
        self.labels = list(labels or [])
        self.milestones = list(milestones or [])
        self.milestone_error = milestone_error
        self.fail_ids = set(fail_ids)
        self.writes: list = []

    def list_issues(self):
        return [copy.deepcopy(i) for i in self.issues]

    def list_labels(self):
        return list(self.labels)

    def create_label(self, name, color, description):
        self.writes.append(("label", name))
        self.labels.append(name)

    def list_milestones(self):
        return list(self.milestones)

    def create_milestone(self, title, description):
        if self.milestone_error:
            raise R.GhError("HTTP 403: Resource not accessible by integration")
        self.writes.append(("milestone", title))
        self.milestones.append(title)

    def create_issue(self, title, body, labels, milestone):
        if any(title.startswith(f"[{i}]") for i in self.fail_ids):
            raise R.GhError("HTTP 502")
        number = len(self.issues) + 1
        url = f"https://github.com/Andrew-Copilot/localscribe/issues/{number}"
        issue = R.ExistingIssue(number, title, body, "OPEN", url, list(labels), milestone)
        self.issues.append(issue)
        self.writes.append(("issue", title))
        return issue

    def edit_issue(self, number, title, body, add_labels, milestone):
        self.writes.append(("edit", number))
        for issue in self.issues:
            if issue.number == number:
                issue.title, issue.body = title, body
                issue.labels += add_labels
                issue.milestone = milestone or issue.milestone


def quiet(_msg: str) -> None:
    pass


# --- definitions ---------------------------------------------------------

def test_definitions_cover_r01_to_r18() -> None:
    data = definitions()
    ids = [i["id"] for i in data["issues"]]
    check("exactly R01..R18 in order", ids == [f"R{n:02d}" for n in range(1, 19)], str(ids))
    check("target repository", data["repository"] == "Andrew-Copilot/localscribe")
    check("validation reports no errors", R.validate_definitions(data) == [])


def parse_backlog() -> dict:
    entries: dict = {}
    current = None
    in_criteria = False
    for line in BACKLOG.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^### (R\d\d) — (.*)$", line)
        if m:
            current = {"title": m.group(2), "labels": [], "goal": None, "criteria": [], "deps": None}
            entries[m.group(1)] = current
            in_criteria = False
        elif line.startswith("## "):
            current = None
        elif current is None:
            continue
        elif line.startswith("**Labels:**"):
            current["labels"] = re.findall(r"`([^`]+)`", line)
        elif line.startswith("**Goal:**"):
            current["goal"] = line[len("**Goal:**"):].strip()
        elif line.startswith("**Acceptance criteria**"):
            in_criteria = True
        elif line.startswith("**Dependencies:**"):
            in_criteria = False
            current["deps"] = re.findall(r"R\d\d", line)
        elif in_criteria and line.startswith("- "):
            current["criteria"].append(line[2:])
    return entries


def test_definitions_match_backlog() -> None:
    data = definitions()
    backlog = parse_backlog()
    check("backlog has 18 entries", sorted(backlog) == [f"R{n:02d}" for n in range(1, 19)])
    for issue in data["issues"]:
        entry = backlog.get(issue["id"], {})
        same = (entry.get("title") == issue["title"]
                and entry.get("labels") == issue["labels"]
                and entry.get("goal") == issue.get("goal")
                and entry.get("criteria") == issue["acceptance_criteria"])
        check(f"{issue['id']} title/labels/goal/criteria match backlog", same)
        for ref in entry.get("deps") or []:
            check(f"{issue['id']} depends on {ref} as in backlog", ref in issue["depends_on"])


def test_governance_wording_preserved() -> None:
    data = definitions()
    backlog_text = BACKLOG.read_text(encoding="utf-8")
    check("governance notice copied verbatim from backlog", data["governance_notice"] in backlog_text)
    r01 = next(i for i in data["issues"] if i["id"] == "R01")
    check("R01 stays labelled blocked", "blocked" in r01["labels"])
    for issue in data["issues"]:
        body = R.render_body(data, issue, {})
        if {"phi", "box"} & set(issue["labels"]):
            check(f"{issue['id']} body carries the PHI governance rule", data["governance_notice"] in body)
        lowered = body.lower()
        check(f"{issue['id']} body makes no approval claim",
              "has been approved" not in lowered and "is approved" not in lowered
              and "hipaa compliant" not in lowered)


def test_validation_catches_errors() -> None:
    base = definitions()

    def errors_after(mutate) -> list:
        data = copy.deepcopy(base)
        mutate(data)
        return R.validate_definitions(data)

    check("duplicate id", any("defined twice" in e for e in errors_after(
        lambda d: d["issues"].append(copy.deepcopy(d["issues"][0])))))
    check("bad id format", any("must look like" in e for e in errors_after(
        lambda d: d["issues"][0].update(id="X1"))))
    check("unknown dependency", any("unknown issue" in e for e in errors_after(
        lambda d: d["issues"][0].update(depends_on=["R99"]))))
    check("self dependency", any("itself" in e for e in errors_after(
        lambda d: d["issues"][0].update(depends_on=["R01"]))))
    check("dependency cycle", any("cycle" in e for e in errors_after(
        lambda d: d["issues"][0].update(depends_on=["R04"]))))
    check("undefined label", any("not defined" in e for e in errors_after(
        lambda d: d["issues"][0]["labels"].append("nope"))))
    check("undefined milestone", any("milestone" in e for e in errors_after(
        lambda d: d["issues"][0].update(milestone="m999"))))
    check("empty acceptance criteria", any("acceptance_criteria" in e for e in errors_after(
        lambda d: d["issues"][0].update(acceptance_criteria=[]))))
    check("title must not repeat the prefix", any("prefix" in e for e in errors_after(
        lambda d: d["issues"][0].update(title="[R01] x"))))
    check("bad label colour", any("color" in e for e in errors_after(
        lambda d: d["labels"][0].update(color="#fff"))))

    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        try:
            R.load_definitions(bad)
            check("malformed JSON raises DefinitionError", False)
        except R.DefinitionError:
            check("malformed JSON raises DefinitionError", True)


def test_title_and_marker() -> None:
    data = definitions()
    r01 = data["issues"][0]
    check("title prefix", R.issue_title(r01).startswith("[R01] "))
    body = R.render_body(data, r01, {})
    check("body starts with marker", body.startswith("<!-- roadmap-id:R01 -->"))
    r12 = next(i for i in data["issues"] if i["id"] == "R12")
    check("dependency rendered as issue link", "#7 (R11" in R.render_body(data, r12, {"R11": 7}))


# --- idempotency ---------------------------------------------------------

def test_match_existing() -> None:
    issues = [
        R.ExistingIssue(5, "Something else", "<!-- roadmap-id:R02 -->"),
        R.ExistingIssue(3, "[R01] Hand made", "no marker"),
        R.ExistingIssue(9, "dup", "<!--roadmap-id: R02-->"),
        R.ExistingIssue(4, "[R03] title", "<!-- roadmap-id:R99 -->"),
    ]
    found, warnings = R.match_existing(issues, ["R01", "R02", "R03", "R04"])
    check("marker match, lowest number wins", found.get("R02") and found["R02"].number == 5)
    check("title fallback", found.get("R01") and found["R01"].number == 3)
    check("unknown marker ignored, title still matches", found.get("R03") and found["R03"].number == 4)
    check("missing id not matched", "R04" not in found)
    check("duplicate warned", any("possible duplicates #9" in w for w in warnings), str(warnings))
    check("title-only match warned", any("R01" in w and "title only" in w for w in warnings))


def test_dry_run_writes_nothing() -> None:
    data = definitions()
    fake = FakeGh()
    summary = R.run_import(data, fake, apply=False, log=quiet)
    check("no writes in dry run", fake.writes == [], str(fake.writes))
    check("plans 18 creations", summary.count("would-create") == 18)
    check("plans every label", len(summary.labels_created) == len(data["labels"]))
    check("plans every milestone", len(summary.milestones_created) == len(data["milestones"]))


def test_apply_is_idempotent() -> None:
    data = definitions()
    fake = FakeGh()
    first = R.run_import(data, fake, apply=True, log=quiet)
    check("first apply creates 18", first.count("created") == 18 and first.failed == 0)
    check("issues carry milestone", all(i.milestone for i in fake.issues))
    r05 = next(i for i in fake.issues if i.title.startswith("[R05]"))
    check("later issues link earlier ones by number", "Depends on #1 (R01" in r05.body)

    writes_before = len(fake.writes)
    second = R.run_import(data, fake, apply=True, log=quiet)
    check("second apply reuses 18", second.count("reused") == 18)
    check("second apply writes nothing", len(fake.writes) == writes_before)
    check("still 18 issues", len(fake.issues) == 18)

    fake.issues[0].body = fake.issues[0].body.replace("- [ ]", "- [x]", 1)
    third = R.run_import(data, fake, apply=True, log=quiet)
    check("user edits are left alone by default",
          "- [x]" in fake.issues[0].body and third.count("updated") == 0)
    fourth = R.run_import(data, fake, apply=True, update_existing=True, log=quiet)
    check("--update-existing syncs the edited issue only", fourth.count("updated") == 1)


def test_partial_failure_and_milestone_permission() -> None:
    data = definitions()
    fake = FakeGh(milestone_error=True, fail_ids={"R03"})
    summary = R.run_import(data, fake, apply=True, log=quiet)
    check("one failure recorded", summary.failed == 1)
    check("others still created", summary.count("created") == 17)
    check("milestone warning", any("milestone" in w for w in summary.warnings))
    check("issues created without milestone", all(i.milestone is None for i in fake.issues))
    retry = R.run_import(data, FakeGh(issues=fake.issues, labels=fake.labels), apply=True, log=quiet)
    check("rerun only creates the missing one", retry.count("created") == 1 and retry.count("reused") == 17)


def test_index_rendering() -> None:
    data = definitions()
    fake = FakeGh()
    summary = R.run_import(data, fake, apply=True, log=quiet)
    index = R.render_index(data, summary.issues)
    check("index lists every id", all(f"| R{n:02d} |" in index for n in range(1, 19)))
    check("index links issue URL",
          "[#1](https://github.com/Andrew-Copilot/localscribe/issues/1)" in index)
    check("index shows reverse dependency (R01 blocks R02, R05)", "| R02 (#2), R05 (#5) |" in index)
    check("index groups by milestone", "## 1.02 — Safe storage and recovery" in index)
    check("index is deterministic", index == R.render_index(data, summary.issues))
    empty = R.render_index(data, {})
    check("index tolerates missing issues", "not created" in empty)


def test_gh_client_commands() -> None:
    calls: list = []

    def runner(args, input_text):
        calls.append((args, input_text))
        out = "https://github.com/Andrew-Copilot/localscribe/issues/42\n" if args[1:3] == ["issue", "create"] else "[]"
        return subprocess.CompletedProcess(args, 0, out, "")

    client = R.GhClient("Andrew-Copilot/localscribe", runner)
    created = client.create_issue("[R01] T", "body", ["roadmap", "phi"], "1.02 — Safe storage and recovery")
    args, stdin = calls[-1]
    check("issue number parsed from URL", created.number == 42)
    check("body sent on stdin", stdin == "body" and "--body-file" in args)
    check("repo always explicit", args[args.index("--repo") + 1] == "Andrew-Copilot/localscribe")
    check("labels passed", args.count("--label") == 2)

    def failing(args, input_text):
        return subprocess.CompletedProcess(args, 1, "", "HTTP 403")

    try:
        R.GhClient("a/b", failing).list_labels()
        check("gh failure raises GhError", False)
    except R.GhError as exc:
        check("gh failure raises GhError", "HTTP 403" in str(exc))


def main() -> int:
    tests = [
        test_definitions_cover_r01_to_r18,
        test_definitions_match_backlog,
        test_governance_wording_preserved,
        test_validation_catches_errors,
        test_title_and_marker,
        test_match_existing,
        test_dry_run_writes_nothing,
        test_apply_is_idempotent,
        test_partial_failure_and_milestone_permission,
        test_index_rendering,
        test_gh_client_commands,
    ]
    for test in tests:
        print(f"\n{test.__name__}")
        test()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
