#!/usr/bin/env python3
"""Lightweight public-readiness scanner for examples and source files.

The scanner intentionally has no third-party dependencies. It checks for
committed operational config files, common secret-like literals, internal-style
deployment URLs, and optional user-provided proprietary terms.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_PATHS = [
    ROOT / "config.example.yaml",
    ROOT / ".env.example",
    ROOT / "README.md",
]
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "venv",
    ".venv",
    "node_modules",
}
SKIP_FILES = {
    ".env",
    "config.yaml",
}
SELF_AUDIT_EXEMPT = {
    Path("scripts/audit_public_readiness.py"),
    Path("SECURITY_CHECKLIST.md"),
}

SECRET_PATTERNS = [
    (
        "slack-token-prefix",
        re.compile(r"\bxox[aboprs]-[A-Za-z0-9-]+\b"),
        "Slack token-looking literal",
    ),
    (
        "slack-webhook-url",
        re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+"),
        "Slack webhook URL",
    ),
    (
        "github-token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
        "GitHub token-looking literal",
    ),
    (
        "aws-access-key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "AWS access key-looking literal",
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        "JWT-looking literal",
    ),
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "private key block",
    ),
    (
        "internal-style-url",
        re.compile(r"https?://[^\s\"']*(?:internal|staging|corp)[^\s\"']*", re.IGNORECASE),
        "internal-style deployment URL",
    ),
]
CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)^\s*[A-Z0-9_-]*(api[_-]?key|token|secret|password|signing[_-]?secret|auth[_-]?token|environment[_-]?id)[A-Z0-9_-]*\b"
    r"\s*[:=]\s*['\"]?([^'\"\s#]+)"
)
PLACEHOLDER_MARKERS = (
    "${",
    "<",
    "placeholder",
    "replace",
    "your-",
    "example",
    "owner/repo",
)
CONFIG_LIKE_SUFFIXES = {
    ".env",
    ".example",
    ".json",
    ".md",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class Finding:
    path: Path
    line_number: int
    rule: str
    detail: str

    def format(self) -> str:
        rel_path = self.path.relative_to(ROOT) if self.path.is_relative_to(ROOT) else self.path
        if self.line_number:
            return f"{rel_path}:{self.line_number}: {self.rule}: {self.detail}"
        return f"{rel_path}: {self.rule}: {self.detail}"


@dataclass(frozen=True)
class TermPattern:
    label: str
    pattern: re.Pattern[str]


def is_placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"").lower()
    return any(marker in normalized for marker in PLACEHOLDER_MARKERS)


def is_config_like_file(path: Path) -> bool:
    if path.name.endswith(".example"):
        return True
    return path.suffix.lower() in CONFIG_LIKE_SUFFIXES


def load_terms(path: Path | None) -> list[TermPattern]:
    if path is None:
        return []
    terms: list[TermPattern] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("re:"):
            pattern_text = line[3:].strip()
            terms.append(TermPattern(f"{path.name}:{line_number}", re.compile(pattern_text, re.IGNORECASE)))
        else:
            terms.append(
                TermPattern(
                    f"{path.name}:{line_number}",
                    re.compile(re.escape(line), re.IGNORECASE),
                )
            )
    return terms


def iter_repo_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        rel_path = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel_path.parts):
            continue
        if path.is_dir():
            continue
        if rel_path in SELF_AUDIT_EXEMPT:
            continue
        files.append(path)
    return files


def scan_paths(paths: list[Path], terms: list[TermPattern] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    terms = terms or []

    for path in paths:
        if path.name in SKIP_FILES:
            findings.append(
                Finding(
                    path=path,
                    line_number=0,
                    rule="committed-operational-file",
                    detail=f"{path.name} should not be committed; keep only example files",
                )
            )
            continue
        if not path.exists() or not path.is_file():
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule, pattern, detail in SECRET_PATTERNS:
                if pattern.search(line) and not is_placeholder(line):
                    findings.append(Finding(path, line_number, rule, detail))
            assignment = CREDENTIAL_ASSIGNMENT.search(line) if is_config_like_file(path) else None
            if assignment:
                value = assignment.group(2)
                if not is_placeholder(value):
                    findings.append(
                        Finding(
                            path,
                            line_number,
                            "credential-literal",
                            "credential-like assignment should use a placeholder",
                        )
                    )

            for term in terms:
                if term.pattern.search(line):
                    findings.append(
                        Finding(
                            path,
                            line_number,
                            "proprietary-term",
                            f"matched denylist entry {term.label}",
                        )
                    )

    return findings


def paths_for_scope(scope: str) -> list[Path]:
    if scope == "samples":
        return DEFAULT_SAMPLE_PATHS
    return iter_repo_files(ROOT)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan public examples or the full repository for secret-like/proprietary literals."
    )
    parser.add_argument(
        "--scope",
        choices=["samples", "all"],
        default="samples",
        help="Scan sample/docs files only, or all repository files except generated/tooling exclusions.",
    )
    parser.add_argument(
        "--terms-file",
        type=Path,
        help=(
            "Optional untracked denylist file with one proprietary term per line. "
            "Prefix a line with 're:' to provide a regular expression."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    terms = load_terms(args.terms_file)
    findings = scan_paths(paths_for_scope(args.scope), terms)
    if findings:
        print("Public-readiness audit found issues:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding.format()}", file=sys.stderr)
        return 1

    print(f"Public-readiness audit passed for scope={args.scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
