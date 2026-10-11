#!/usr/bin/env python3
"""Create the Local Scribe roadmap issues (R01-R18) on GitHub.

Reads docs/roadmap/roadmap-issues.json and uses the GitHub CLI (`gh`) that is
already signed in inside GitHub Codespaces and GitHub Actions. No personal
access token is needed or read by this script.

Safe by default:
  * Without --apply nothing is written: it only reports what it would do.
  * Each issue body carries a hidden marker such as <!-- roadmap-id:R01 -->.
    Reruns find issues by that marker (or by a "[R01]" title prefix) and
    reuse them instead of creating duplicates.
  * Existing issues are never modified unless --update-existing is given.

Usage:
  python scripts/create_roadmap_issues.py                 # dry run
  python scripts/create_roadmap_issues.py --apply         # create issues
  python scripts/create_roadmap_issues.py --validate-only # no GitHub access

Only the Python standard library and the `gh` command are used.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEFINITIONS = ROOT / "docs" / "roadmap" / "roadmap-issues.json"
DEFAULT_INDEX = ROOT / "docs" / "roadmap" / "issue-index.md"

ID_RE = re.compile(r"^R\d{2}$")
MARKER_RE = re.compile(r"<!--\s*roadmap-id:\s*(R\d{2})\s*-->")
TITLE_ID_RE = re.compile(r"^\s*\[(R\d{2})\]")
COLOR_RE = re.compile(r"^[0-9a-fA-F]{6}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ISSUE_URL_RE = re.compile(r"/issues/(\d+)\s*$")

ISSUE_LIST_LIMIT = 1000


class DefinitionError(ValueError):
    """The roadmap definition file is malformed."""


class GhError(RuntimeError):
    """A `gh` command failed."""


# --------------------------------------------------------------------------
# Definitions
# --------------------------------------------------------------------------

def _is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)


def validate_definitions(data) -> List[str]:
    """Return a list of human-readable problems; empty means valid."""
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["definitions must be a JSON object"]

    repo = data.get("repository")
    if not isinstance(repo, str) or not REPO_RE.match(repo):
        errors.append("'repository' must look like 'owner/name'")
    if not isinstance(data.get("governance_notice"), str) or not data["governance_notice"].strip():
        errors.append("'governance_notice' must be a non-empty string")
    if not _is_str_list(data.get("governance_labels", [])):
        errors.append("'governance_labels' must be a list of strings")

    label_names: List[str] = []
    labels = data.get("labels")
    if not isinstance(labels, list) or not labels:
        errors.append("'labels' must be a non-empty list")
        labels = []
    for i, label in enumerate(labels):
        if not isinstance(label, dict) or not isinstance(label.get("name"), str) or not label["name"].strip():
            errors.append(f"labels[{i}] needs a non-empty 'name'")
            continue
        name = label["name"]
        if name in label_names:
            errors.append(f"label '{name}' is defined twice")
        label_names.append(name)
        if not isinstance(label.get("color"), str) or not COLOR_RE.match(label["color"]):
            errors.append(f"label '{name}' needs a 6-digit hex 'color' without '#'")
        if not isinstance(label.get("description", ""), str):
            errors.append(f"label '{name}' description must be a string")

    milestone_keys: List[str] = []
    milestone_titles: List[str] = []
    milestones = data.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        errors.append("'milestones' must be a non-empty list")
        milestones = []
    for i, ms in enumerate(milestones):
        if not isinstance(ms, dict):
            errors.append(f"milestones[{i}] must be an object")
            continue
        key, title = ms.get("key"), ms.get("title")
        if not isinstance(key, str) or not key.strip():
            errors.append(f"milestones[{i}] needs a non-empty 'key'")
            continue
        if key in milestone_keys:
            errors.append(f"milestone key '{key}' is defined twice")
        milestone_keys.append(key)
        if not isinstance(title, str) or not title.strip():
            errors.append(f"milestone '{key}' needs a non-empty 'title'")
        elif title in milestone_titles:
            errors.append(f"milestone title '{title}' is used twice")
        else:
            milestone_titles.append(title)

    for name in data.get("governance_labels", []) or []:
        if isinstance(name, str) and name not in label_names:
            errors.append(f"governance label '{name}' is not defined in 'labels'")

    issues = data.get("issues")
    if not isinstance(issues, list) or not issues:
        errors.append("'issues' must be a non-empty list")
        return errors

    ids: List[str] = []
    for i, issue in enumerate(issues):
        if not isinstance(issue, dict):
            errors.append(f"issues[{i}] must be an object")
            continue
        iid = issue.get("id")
        if not isinstance(iid, str) or not ID_RE.match(iid):
            errors.append(f"issues[{i}] id {iid!r} must look like 'R01'")
            continue
        if iid in ids:
            errors.append(f"issue id {iid} is defined twice")
        ids.append(iid)

    for issue in issues:
        if not isinstance(issue, dict) or not isinstance(issue.get("id"), str):
            continue
        iid = issue["id"]
        title = issue.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{iid}: 'title' must be a non-empty string")
        elif TITLE_ID_RE.match(title):
            errors.append(f"{iid}: 'title' must not include the '[{iid}]' prefix; it is added automatically")
        elif len(issue_title(issue)) > 256:
            errors.append(f"{iid}: title is longer than GitHub's 256 character limit")
        if issue.get("milestone") not in milestone_keys:
            errors.append(f"{iid}: milestone {issue.get('milestone')!r} is not defined")
        if not _is_str_list(issue.get("labels")) or not issue["labels"]:
            errors.append(f"{iid}: 'labels' must be a non-empty list of strings")
        else:
            for name in issue["labels"]:
                if name not in label_names:
                    errors.append(f"{iid}: label '{name}' is not defined in 'labels'")
        if "goal" in issue and (not isinstance(issue["goal"], str) or not issue["goal"].strip()):
            errors.append(f"{iid}: 'goal' must be a non-empty string when present")
        if not _is_str_list(issue.get("acceptance_criteria")) or not issue["acceptance_criteria"]:
            errors.append(f"{iid}: 'acceptance_criteria' must be a non-empty list of strings")
        for note in ("dependency_note", "sequencing_note"):
            if note in issue and (not isinstance(issue[note], str) or not issue[note].strip()):
                errors.append(f"{iid}: '{note}' must be a non-empty string when present")
        for key in ("depends_on", "sequenced_after"):
            refs = issue.get(key, [])
            if not isinstance(refs, list):
                errors.append(f"{iid}: '{key}' must be a list")
                continue
            for ref in refs:
                if ref == iid:
                    errors.append(f"{iid}: '{key}' refers to itself")
                elif ref not in ids:
                    errors.append(f"{iid}: '{key}' refers to unknown issue {ref!r}")

    cycle = _find_cycle(issues)
    if cycle:
        errors.append("dependency cycle: " + " -> ".join(cycle))
    return errors


def _find_cycle(issues) -> Optional[List[str]]:
    graph: Dict[str, List[str]] = {}
    for issue in issues:
        if isinstance(issue, dict) and isinstance(issue.get("id"), str):
            refs = []
            for key in ("depends_on", "sequenced_after"):
                if isinstance(issue.get(key), list):
                    refs.extend(r for r in issue[key] if isinstance(r, str))
            graph[issue["id"]] = refs
    state: Dict[str, int] = {}
    stack: List[str] = []

    def visit(node: str) -> Optional[List[str]]:
        state[node] = 1
        stack.append(node)
        for nxt in graph.get(node, []):
            if nxt not in graph:
                continue
            if state.get(nxt) == 1:
                return stack[stack.index(nxt):] + [nxt]
            if state.get(nxt) is None:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in graph:
        if state.get(node) is None:
            found = visit(node)
            if found:
                return found
    return None


def load_definitions(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DefinitionError(f"cannot read {path}: {exc}") from exc
    errors = validate_definitions(data)
    if errors:
        raise DefinitionError("invalid roadmap definitions:\n  - " + "\n  - ".join(errors))
    return data


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def marker(issue_id: str) -> str:
    return f"<!-- roadmap-id:{issue_id} -->"


def issue_title(issue: dict) -> str:
    return f"[{issue['id']}] {issue['title']}"


def milestone_title(data: dict, key: str) -> str:
    for ms in data["milestones"]:
        if ms["key"] == key:
            return ms["title"]
    raise KeyError(key)


def _ref(data: dict, ref_id: str, numbers: Dict[str, int]) -> str:
    title = next(i["title"] for i in data["issues"] if i["id"] == ref_id)
    if ref_id in numbers:
        return f"#{numbers[ref_id]} ({ref_id} — {title})"
    return f"{ref_id} — {title} (issue not created yet)"


def render_body(data: dict, issue: dict, numbers: Dict[str, int]) -> str:
    """Build the issue body. `numbers` maps roadmap IDs to issue numbers."""
    lines = [
        marker(issue["id"]),
        f"**Roadmap ID:** {issue['id']}  ",
        f"**Milestone:** {milestone_title(data, issue['milestone'])}",
        "",
    ]
    if set(issue["labels"]) & set(data.get("governance_labels", [])):
        lines += [f"> {data['governance_notice']}", ""]
    if issue.get("goal"):
        lines += ["## Goal", "", issue["goal"], ""]
    lines += ["## Acceptance criteria", ""]
    lines += [f"- [ ] {item}" for item in issue["acceptance_criteria"]]
    lines.append("")

    deps = []
    for ref in issue.get("depends_on", []):
        deps.append(f"- Depends on {_ref(data, ref, numbers)}")
    for ref in issue.get("sequenced_after", []):
        deps.append(f"- Suggested to follow {_ref(data, ref, numbers)}")
    if issue.get("dependency_note"):
        deps.append(f"- Also requires: {issue['dependency_note']}")
    if issue.get("sequencing_note"):
        deps.append(f"- Sequencing: {issue['sequencing_note']}")
    if deps:
        lines += ["## Dependencies", ""] + deps + [""]

    lines += [
        "---",
        f"_Source: `{data.get('source', 'docs/roadmap/issue-backlog.md')}`. "
        "Created by `scripts/create_roadmap_issues.py`; keep the hidden roadmap-id "
        "marker so reruns do not create duplicates._",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Existing issues
# --------------------------------------------------------------------------

@dataclass
class ExistingIssue:
    number: int
    title: str
    body: str = ""
    state: str = "OPEN"
    url: str = ""
    labels: List[str] = field(default_factory=list)
    milestone: Optional[str] = None


def match_existing(issues: Sequence[ExistingIssue], ids: Sequence[str]) -> Tuple[Dict[str, ExistingIssue], List[str]]:
    """Map roadmap IDs to existing issues.

    The body marker wins; a "[Rxx]" title prefix is the fallback so issues
    created by hand are reused too. With several candidates the oldest
    (lowest number) is used and a warning is returned.
    """
    wanted = set(ids)
    by_marker: Dict[str, List[ExistingIssue]] = {}
    by_title: Dict[str, List[ExistingIssue]] = {}
    for issue in sorted(issues, key=lambda i: i.number):
        found = set(MARKER_RE.findall(issue.body or "")) & wanted
        for iid in found:
            by_marker.setdefault(iid, []).append(issue)
        m = TITLE_ID_RE.match(issue.title or "")
        if m and m.group(1) in wanted and m.group(1) not in found:
            by_title.setdefault(m.group(1), []).append(issue)

    result: Dict[str, ExistingIssue] = {}
    warnings: List[str] = []
    for iid in ids:
        candidates = by_marker.get(iid) or by_title.get(iid) or []
        if not candidates:
            continue
        result[iid] = candidates[0]
        if iid not in by_marker:
            warnings.append(f"{iid}: reusing #{candidates[0].number} matched by title only (no roadmap-id marker)")
        if len(candidates) > 1:
            others = ", ".join(f"#{c.number}" for c in candidates[1:])
            warnings.append(f"{iid}: possible duplicates {others}; using #{candidates[0].number}")
    return result, warnings


def _issue_from_json(raw: dict) -> ExistingIssue:
    milestone = raw.get("milestone") or None
    return ExistingIssue(
        number=int(raw["number"]),
        title=raw.get("title") or "",
        body=raw.get("body") or "",
        state=raw.get("state") or "",
        url=raw.get("url") or "",
        labels=[label["name"] for label in raw.get("labels") or []],
        milestone=milestone.get("title") if isinstance(milestone, dict) else None,
    )


# --------------------------------------------------------------------------
# GitHub CLI wrapper
# --------------------------------------------------------------------------

Runner = Callable[[List[str], Optional[str]], "subprocess.CompletedProcess"]


def _subprocess_runner(args: List[str], input_text: Optional[str]) -> "subprocess.CompletedProcess":
    return subprocess.run(args, input=input_text, capture_output=True, text=True, encoding="utf-8")


class GhClient:
    """Thin wrapper over the `gh` command; every call targets one repo."""

    def __init__(self, repo: str, runner: Optional[Runner] = None):
        self.repo = repo
        self._runner = runner or _subprocess_runner

    def _gh(self, args: List[str], input_text: Optional[str] = None) -> str:
        proc = self._runner(["gh"] + args, input_text)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise GhError(f"gh {' '.join(args[:2])} failed: {detail}")
        return proc.stdout or ""

    def list_issues(self) -> List[ExistingIssue]:
        out = self._gh([
            "issue", "list", "--repo", self.repo, "--state", "all",
            "--limit", str(ISSUE_LIST_LIMIT),
            "--json", "number,title,body,state,url,labels,milestone",
        ])
        return [_issue_from_json(raw) for raw in json.loads(out or "[]")]

    def list_labels(self) -> List[str]:
        out = self._gh(["label", "list", "--repo", self.repo, "--limit", "1000", "--json", "name"])
        return [label["name"] for label in json.loads(out or "[]")]

    def create_label(self, name: str, color: str, description: str) -> None:
        self._gh(["label", "create", name, "--repo", self.repo, "--color", color,
                  "--description", description])

    def list_milestones(self) -> List[str]:
        out = self._gh(["api", f"repos/{self.repo}/milestones?state=all&per_page=100",
                        "--paginate", "--jq", ".[].title"])
        return [line for line in out.splitlines() if line.strip()]

    def create_milestone(self, title: str, description: str) -> None:
        self._gh(["api", "--method", "POST", f"repos/{self.repo}/milestones",
                  "-f", f"title={title}", "-f", f"description={description}"])

    def create_issue(self, title: str, body: str, labels: List[str], milestone: Optional[str]) -> ExistingIssue:
        args = ["issue", "create", "--repo", self.repo, "--title", title, "--body-file", "-"]
        for label in labels:
            args += ["--label", label]
        if milestone:
            args += ["--milestone", milestone]
        url = self._gh(args, body).strip().splitlines()[-1].strip()
        m = ISSUE_URL_RE.search(url)
        if not m:
            raise GhError(f"could not read the new issue number from gh output: {url!r}")
        return ExistingIssue(number=int(m.group(1)), title=title, body=body, state="OPEN",
                             url=url, labels=list(labels), milestone=milestone)

    def edit_issue(self, number: int, title: str, body: str, add_labels: List[str],
                   milestone: Optional[str]) -> None:
        args = ["issue", "edit", str(number), "--repo", self.repo, "--title", title, "--body-file", "-"]
        for label in add_labels:
            args += ["--add-label", label]
        if milestone:
            args += ["--milestone", milestone]
        self._gh(args, body)


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------

@dataclass
class Result:
    issue_id: str
    action: str  # created | reused | updated | would-create | would-update | failed
    number: Optional[int] = None
    url: str = ""
    detail: str = ""


@dataclass
class Summary:
    applied: bool
    results: List[Result] = field(default_factory=list)
    labels_created: List[str] = field(default_factory=list)
    milestones_created: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    issues: Dict[str, ExistingIssue] = field(default_factory=dict)

    def count(self, *actions: str) -> int:
        return sum(1 for r in self.results if r.action in actions)

    @property
    def failed(self) -> int:
        return self.count("failed")


def run_import(data: dict, client, apply: bool = False, update_existing: bool = False,
               log: Callable[[str], None] = print) -> Summary:
    """Create (or plan) labels, milestones and issues. Safe to rerun."""
    summary = Summary(applied=apply)
    ids = [issue["id"] for issue in data["issues"]]
    verb = "" if apply else "would "

    existing, warnings = match_existing(client.list_issues(), ids)
    summary.warnings.extend(warnings)
    summary.issues = dict(existing)

    have_labels = set(client.list_labels())
    for label in data["labels"]:
        if label["name"] in have_labels:
            continue
        if apply:
            try:
                client.create_label(label["name"], label["color"], label.get("description", ""))
            except GhError as exc:
                summary.warnings.append(f"label '{label['name']}' not created: {exc}")
                continue
        summary.labels_created.append(label["name"])
        log(f"  label     {verb}create '{label['name']}'")

    available_milestones = set()
    try:
        available_milestones = set(client.list_milestones())
    except GhError as exc:
        summary.warnings.append(f"cannot list milestones; issues will be created without them: {exc}")
    else:
        for ms in data["milestones"]:
            if ms["title"] in available_milestones:
                continue
            if apply:
                try:
                    client.create_milestone(ms["title"], ms.get("description", ""))
                except GhError as exc:
                    summary.warnings.append(
                        f"milestone '{ms['title']}' not created (missing permission?); "
                        f"affected issues are created without a milestone: {exc}")
                    continue
            available_milestones.add(ms["title"])
            summary.milestones_created.append(ms["title"])
            log(f"  milestone {verb}create '{ms['title']}'")

    numbers = {iid: issue.number for iid, issue in existing.items()}
    for issue in data["issues"]:
        iid = issue["id"]
        title = issue_title(issue)
        ms_title = milestone_title(data, issue["milestone"])
        milestone = ms_title if ms_title in available_milestones else None
        body = render_body(data, issue, numbers)
        current = existing.get(iid)
        try:
            if current is None:
                if apply:
                    created = client.create_issue(title, body, issue["labels"], milestone)
                    numbers[iid] = created.number
                    summary.issues[iid] = created
                    summary.results.append(Result(iid, "created", created.number, created.url))
                    log(f"  {iid}       created #{created.number} {created.url}")
                else:
                    summary.results.append(Result(iid, "would-create"))
                    log(f"  {iid}       would create '{title}'")
                continue

            missing_labels = [name for name in issue["labels"] if name not in current.labels]
            stale = (current.title != title or current.body.strip() != body.strip() or missing_labels
                     or (milestone is not None and current.milestone != milestone))
            if update_existing and stale:
                if apply:
                    client.edit_issue(current.number, title, body, missing_labels, milestone)
                    summary.issues[iid] = ExistingIssue(
                        current.number, title, body, current.state, current.url,
                        current.labels + missing_labels, milestone or current.milestone)
                    summary.results.append(Result(iid, "updated", current.number, current.url))
                    log(f"  {iid}       updated #{current.number}")
                else:
                    summary.results.append(Result(iid, "would-update", current.number, current.url))
                    log(f"  {iid}       would update #{current.number}")
            else:
                note = "differs from definitions (use --update-existing to sync)" if stale else ""
                summary.results.append(Result(iid, "reused", current.number, current.url, note))
                log(f"  {iid}       exists #{current.number}" + (f" — {note}" if note else ""))
        except GhError as exc:
            summary.results.append(Result(iid, "failed", detail=str(exc)))
            log(f"  {iid}       FAILED: {exc}")
    return summary


def render_index(data: dict, issues: Dict[str, ExistingIssue]) -> str:
    """Markdown index of roadmap IDs, issue links, state and dependencies."""
    blocks: Dict[str, List[str]] = {}
    for issue in data["issues"]:
        for ref in issue.get("depends_on", []):
            blocks.setdefault(ref, []).append(issue["id"])

    def link(iid: str) -> str:
        found = issues.get(iid)
        return f"{iid} (#{found.number})" if found else iid

    def refs(values: List[str]) -> str:
        return ", ".join(link(v) for v in values) or "—"

    lines = [
        "<!-- Generated by scripts/create_roadmap_issues.py --apply. Do not edit by hand. -->",
        "# Roadmap issue index",
        "",
        "Generated from `docs/roadmap/roadmap-issues.json`. Each issue is grouped under "
        "its parent milestone. \"Depends on\" lists hard prerequisites from the backlog; "
        "\"Follows\" lists the suggested sequencing. See `CREATE_ISSUES.md` to regenerate.",
        "",
    ]
    for ms in data["milestones"]:
        members = [i for i in data["issues"] if i["milestone"] == ms["key"]]
        if not members:
            continue
        lines += [f"## {ms['title']}", "",
                  "| ID | Issue | Title | State | Depends on | Follows | Blocks |",
                  "|---|---|---|---|---|---|---|"]
        for issue in members:
            iid = issue["id"]
            found = issues.get(iid)
            cell = f"[#{found.number}]({found.url})" if found and found.url else (
                f"#{found.number}" if found else "not created")
            state = (found.state or "").lower() if found else "—"
            title = issue["title"].replace("|", "\\|")
            lines.append(f"| {iid} | {cell} | {title} | {state or '—'} | "
                         f"{refs(issue.get('depends_on', []))} | "
                         f"{refs(issue.get('sequenced_after', []))} | {refs(blocks.get(iid, []))} |")
        lines.append("")
    return "\n".join(lines)


def print_summary(summary: Summary, out: Callable[[str], None] = print) -> None:
    mode = "APPLY" if summary.applied else "DRY RUN (nothing was changed)"
    out("")
    out(f"Summary — {mode}")
    if summary.applied:
        out(f"  created: {summary.count('created')}   reused: {summary.count('reused')}   "
            f"updated: {summary.count('updated')}   failed: {summary.failed}")
    else:
        out(f"  would create: {summary.count('would-create')}   already exist: {summary.count('reused')}   "
            f"would update: {summary.count('would-update')}   failed: {summary.failed}")
    verb = "created" if summary.applied else "to create"
    out(f"  labels {verb}: {len(summary.labels_created)}   milestones {verb}: {len(summary.milestones_created)}")
    for result in summary.results:
        if result.action == "failed":
            out(f"  FAILED {result.issue_id}: {result.detail}")
    for warning in summary.warnings:
        out(f"  warning: {warning}")


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def _preflight(args, expected_repo: str, runner: Runner = _subprocess_runner) -> str:
    """Check gh is installed and signed in; return the verified target repo."""
    if shutil.which("gh") is None:
        raise SystemExit("error: the GitHub CLI 'gh' is not installed. Open this repository in a "
                         "GitHub Codespace (it includes gh) or install it from https://cli.github.com/.")
    auth = runner(["gh", "auth", "status"], None)
    if auth.returncode != 0:
        raise SystemExit("error: gh is not signed in. Run:  gh auth login --web\n"
                         + (auth.stderr or auth.stdout or "").strip())

    repo = args.repo
    if not repo:
        view = runner(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], None)
        if view.returncode != 0:
            raise SystemExit("error: could not detect the repository; pass --repo OWNER/NAME\n"
                             + (view.stderr or "").strip())
        repo = view.stdout.strip()
    if not REPO_RE.match(repo or ""):
        raise SystemExit(f"error: {repo!r} is not a valid OWNER/NAME repository")
    if repo.lower() != expected_repo.lower() and not args.allow_other_repo:
        raise SystemExit(f"error: target repository is {repo}, expected {expected_repo}. "
                         "Use --allow-other-repo only if you really mean it.")
    return repo


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="actually create labels, milestones and issues (default: dry run)")
    parser.add_argument("--update-existing", action="store_true",
                        help="rewrite title/body and add missing labels/milestone on issues that already exist")
    parser.add_argument("--validate-only", action="store_true",
                        help="only validate the definitions file; does not contact GitHub")
    parser.add_argument("--definitions", type=Path, default=DEFAULT_DEFINITIONS,
                        help="roadmap definitions JSON (default: %(default)s)")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX,
                        help="generated index written after --apply (default: %(default)s)")
    parser.add_argument("--repo", help="target OWNER/NAME (default: the current checkout's repository)")
    parser.add_argument("--allow-other-repo", action="store_true",
                        help="allow a target repository other than the one named in the definitions")
    args = parser.parse_args(argv)

    try:
        data = load_definitions(args.definitions)
    except DefinitionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Definitions OK: {len(data['issues'])} issues, {len(data['labels'])} labels, "
          f"{len(data['milestones'])} milestones.")
    if args.validate_only:
        return 0

    repo = _preflight(args, data["repository"])
    print(f"Target repository: {repo}")
    print("Mode: " + ("APPLY — changes will be made" if args.apply else
                      "dry run — nothing will be changed (add --apply to create issues)"))
    client = GhClient(repo)
    try:
        summary = run_import(data, client, apply=args.apply, update_existing=args.update_existing)
    except GhError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.apply:
        try:
            refreshed, _ = match_existing(client.list_issues(), [i["id"] for i in data["issues"]])
            summary.issues.update(refreshed)
        except GhError as exc:
            summary.warnings.append(f"could not refresh issue states for the index: {exc}")
        args.index.parent.mkdir(parents=True, exist_ok=True)
        args.index.write_text(render_index(data, summary.issues), encoding="utf-8")
        print(f"Wrote {args.index}")

    print_summary(summary)
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
