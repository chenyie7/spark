"""Java file scanner engine for code-check system.

Scans Java source files against program check rules defined in YAML.
Supports three scanner types:
  - text-grep:       line-by-line regex matching
  - java-annotation: context-aware annotation presence checks
  - java-return-type: controller method return-type check (Result<T>)
"""

import fnmatch
import string as _string_
import os
import re
from pathlib import Path
from typing import Any

from agents.reviewer.check_system.code_check.models import (
    BlockingStrategy,
    Finding,
    FileReport,
    HintForAI,
    Level,
    ScanMetadata,
    ScanResult,
    ScanScope,
    ScanSummary,
)


# ── Helpers ────────────────────────────────────────────────────


def _get_class_annotations(content: str) -> list[str]:
    """Return annotation names applied at class level.

    Looks for annotations on lines preceding the ``class`` keyword.
    """
    m = re.search(
        r"(?:public\s+|private\s+|protected\s+)?"
        r"(?:abstract\s+)?(?:static\s+)?class\s+\w+",
        content,
    )
    if not m:
        return []
    preceding = content[: m.start()]
    return re.findall(r"@(\w+)", preceding)


def _get_class_name(content: str) -> str:
    """Extract the simple class name from Java source."""
    m = re.search(
        r"(?:public\s+|private\s+|protected\s+)?"
        r"(?:abstract\s+)?(?:static\s+)?class\s+(\w+)",
        content,
    )
    return m.group(1) if m else ""


def _any_match(annotations: list[str], pattern: str) -> bool:
    """Return True if any annotation name matches the pipe-separated *pattern*."""
    return any(re.search(pattern, a) for a in annotations)


def _has_annotation(content: str, annotation_pattern: str) -> bool:
    """Return True if *annotation_pattern* is found anywhere in *content*."""
    return bool(re.search(rf"\b{annotation_pattern}\b", content))


def _parse_params(params_str: str) -> list[dict]:
    """Parse a Java method's comma-separated parameter text into structured records.

    Each record has keys ``type``, ``name``, and ``annotations`` (list of annotation
    names without the leading ``@``).
    """
    if not params_str.strip():
        return []
    params: list[dict] = []
    for seg in params_str.split(","):
        seg = seg.strip()
        if not seg:
            continue
        annots = re.findall(r"@(\w+)", seg)
        clean = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", seg).strip()
        parts = clean.split()
        param_type = parts[0] if parts else ""
        param_name = parts[1] if len(parts) > 1 else ""
        params.append({"type": param_type, "name": param_name, "annotations": annots})
    return params


def _find_methods(content: str) -> list[dict]:
    """Find all method declarations in Java source with their metadata.

    Returns a list of dicts with keys:
        name, return_type, params (structured), params_str, line_num.
    Block-comments and line-comments are stripped before matching.
    """
    clean = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    clean = re.sub(r"//[^\n]*", "", clean)

    methods: list[dict] = []
    pattern = (
        r"(?:public|private|protected)\s+"
        r"(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?"
        r"([\w<>,?\[\]\s]+?)\s+"
        r"(\w+)\s*"
        r"\(([^()]*)\)"
        r"\s*\{"
    )

    for m in re.finditer(pattern, clean):
        methods.append(
            {
                "return_type": m.group(1).strip(),
                "name": m.group(2),
                "params_str": m.group(3),
                "params": _parse_params(m.group(3)),
                "line_num": content[: m.start()].count("\n") + 1,
            }
        )
    return methods


# ── Base Scanner ───────────────────────────────────────────────

from abc import ABC, abstractmethod


def _safe_format(template: str, replacements: dict[str, str]) -> str:
    """Format *template* with only the keys it actually references.

    Unlike ``str.format(**kwargs)``, this accepts a dict so reserved words
    like ``class`` can be used as template placeholders.
    """
    used = {f[1] for f in _string_.Formatter().parse(template) if f[1]}
    return template.format(**{k: v for k, v in replacements.items() if k in used})


class BaseScanner(ABC):
    """Abstract base scanner.

    Subclasses must set *scanner_name* and implement *scan*.
    """

    scanner_name: str = ""

    @abstractmethod
    def scan(self, file_path: Path, rules: dict) -> list[Finding]:
        """Run this scanner over *file_path* using the given *rules*.

        Args:
            file_path: Path to the Java source file.
            rules: Full rule dict (all check codes -> rule body).

        Returns:
            List of Finding objects, possibly empty.
        """
        ...

    @staticmethod
    def _rules_for_scanner(rules: dict, scanner_name: str) -> dict:
        """Filter *rules* to those whose ``program.scanner`` equals *scanner_name*."""
        return {
            code: rule
            for code, rule in rules.items()
            if rule.get("program", {}).get("scanner") == scanner_name
        }


# ── Text-Grep Scanner ──────────────────────────────────────────


class TextGrepScanner(BaseScanner):
    """Line-by-line regex scanner.

    Reports one ``Finding`` per matching line.  Supports an optional
    ``no_match_in_same_line`` negation pattern (e.g. to exclude lines that
    already use ``LambdaQueryWrapper`` when checking for ``QueryWrapper``).
    """

    scanner_name = "text-grep"

    def scan(self, file_path: Path, rules: dict) -> list[Finding]:
        findings: list[Finding] = []
        my_rules = self._rules_for_scanner(rules, self.scanner_name)
        if not my_rules:
            return findings

        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        for code, rule in my_rules.items():
            program = rule["program"]
            regex = re.compile(program["pattern"])
            neg_regex = (
                re.compile(program["no_match_in_same_line"])
                if "no_match_in_same_line" in program
                else None
            )
            level = Level(rule["level"])
            msg = rule["message"]

            for lineno, line in enumerate(lines, 1):
                match = regex.search(line)
                if match:
                    if neg_regex and neg_regex.search(line):
                        continue
                    findings.append(
                        Finding(
                            code=code,
                            level=level,
                            line=lineno,
                            message=msg,
                            evidence=match.group().strip(),
                        )
                    )
        return findings


# ── Java Annotation Scanner ────────────────────────────────────


class JavaAnnotationScanner(BaseScanner):
    """Context-aware scanner for Java annotations.

    Supports two targets:

    * ``method_param`` — checks that DTO-typed method parameters carry a
      required annotation (e.g. ``@Valid`` / ``@Validated``).
    * ``required_class_annotation`` — checks that classes matching a
      ``on_class`` pattern carry a specific class-level annotation
      (e.g. ``@Slf4j``).
    """

    scanner_name = "java-annotation"

    def scan(self, file_path: Path, rules: dict) -> list[Finding]:
        findings: list[Finding] = []
        my_rules = self._rules_for_scanner(rules, self.scanner_name)
        if not my_rules:
            return findings

        content = file_path.read_text(encoding="utf-8")
        class_anns = _get_class_annotations(content)
        class_name = _get_class_name(content)

        for code, rule in my_rules.items():
            program = rule["program"]
            level = Level(rule["level"])
            msg_template = rule["message"]
            on_class = program["on_class"]

            if not _any_match(class_anns, on_class):
                continue

            # ── method_param: DTO params missing @Validated/@Valid ──
            target = program.get("target", "")
            if target == "method_param":
                findings.extend(
                    self._check_method_param_annotations(
                        content, code, level, msg_template, program, class_name
                    )
                )

            # ── required_class_annotation: class-level annotation missing ──
            if "required_class_annotation" in program:
                needed = program["required_class_annotation"]
                if not _has_annotation(content, needed):
                    findings.append(
                        Finding(
                            code=code,
                            level=level,
                            line=0,
                                                    message=_safe_format(msg_template, {"class": class_name, "class_": class_name, "method": ""}),
                            evidence=f"缺少 {needed} 注解",
                        )
                    )

        return findings

    @staticmethod
    def _check_method_param_annotations(
        content: str,
        code: str,
        level: Level,
        msg_template: str,
        program: dict,
        class_name: str,
    ) -> list[Finding]:
        """Check method parameters for required annotations.

        Iterates over all methods in *content* and checks whether any parameter
        whose type matches *match_param_type* also carries an annotation matching
        *missing_annotation*.  If the annotation is absent a ``Finding`` is
        emitted for that method.
        """
        findings: list[Finding] = []
        match_param_type = program.get("match_param_type", "")
        missing_annotation = program.get("missing_annotation", "")
        type_regex = re.compile(match_param_type) if match_param_type else None
        ann_regex = re.compile(missing_annotation) if missing_annotation else None

        methods = _find_methods(content)
        for method in methods:
            for param in method["params"]:
                if type_regex and not type_regex.search(param["type"]):
                    continue
                has_required_ann = False
                if ann_regex:
                    for ann in param["annotations"]:
                        if ann_regex.search(f"@{ann}"):
                            has_required_ann = True
                            break
                if not has_required_ann:
                    findings.append(
                        Finding(
                            code=code,
                            level=level,
                            line=method["line_num"],
                            message=_safe_format(
                                msg_template,
                                {"method": method["name"], "class": class_name, "class_": class_name},
                            ),
                            evidence=f"参数 {param['type']} {param['name']} 缺少 {missing_annotation}",
                            method=method["name"],
                        )
                    )
        return findings


# ── Java Return-Type Scanner ───────────────────────────────────


class JavaReturnTypeScanner(BaseScanner):
    """Checks that controller methods return ``Result<T>``.

    Rule must specify an ``on_class`` pattern (e.g. ``RestController|Controller``)
    and a ``required_return_pattern`` (e.g. ``Result<``).
    """

    scanner_name = "java-return-type"

    def scan(self, file_path: Path, rules: dict) -> list[Finding]:
        findings: list[Finding] = []
        my_rules = self._rules_for_scanner(rules, self.scanner_name)
        if not my_rules:
            return findings

        content = file_path.read_text(encoding="utf-8")
        class_anns = _get_class_annotations(content)

        for code, rule in my_rules.items():
            program = rule["program"]
            level = Level(rule["level"])
            msg_template = rule["message"]
            on_class = program["on_class"]
            required_return = program["required_return_pattern"]
            return_regex = re.compile(required_return)

            if not _any_match(class_anns, on_class):
                continue

            methods = _find_methods(content)
            for method in methods:
                if not return_regex.search(method["return_type"]):
                    findings.append(
                        Finding(
                            code=code,
                            level=level,
                            line=method["line_num"],
                            message=msg_template.format(method=method["name"]),
                            evidence=f"返回类型: {method['return_type']}",
                            method=method["name"],
                        )
                    )
        return findings


# ── Scanner Registry ───────────────────────────────────────────

SCANNERS: dict[str, BaseScanner] = {
    "text-grep": TextGrepScanner(),
    "java-annotation": JavaAnnotationScanner(),
    "java-return-type": JavaReturnTypeScanner(),
}


# ── File Discovery ─────────────────────────────────────────────


def find_java_files(
    base_path: Path, exclude_patterns: list[str] | None = None
) -> list[Path]:
    """Recursively walk *base_path* and return all ``.java`` files.

    Files whose path matches any *exclude_patterns* (via ``fnmatch``) are
    skipped.
    """
    excludes = exclude_patterns or []
    java_files: list[Path] = []
    for root, _dirs, files in os.walk(base_path):
        for f in files:
            if f.endswith(".java"):
                full = Path(root) / f
                if not should_exclude(str(full), excludes):
                    java_files.append(full)
    return sorted(java_files)


def should_exclude(path_str: str, exclude_patterns: list[str]) -> bool:
    """Return ``True`` if *path_str* matches any of the *exclude_patterns*.

    Supports ``**`` for recursive directory matching (e.g. ``**/test/**``
    matches any path containing a ``test`` directory component at any depth).
    """
    for pat in exclude_patterns:
        if _path_matches_glob(path_str, pat):
            return True
    return False


def _path_matches_glob(path: str, pattern: str) -> bool:
    """Match a filesystem path against a glob pattern with ``**`` support.

    Falls back to ``fnmatch.fnmatch`` when the pattern contains no ``**``
    since that handles simple wildcards efficiently.
    """
    if "**" not in pattern:
        return fnmatch.fnmatch(path, pattern)

    path_parts = path.split("/")
    pat_parts = pattern.split("/")

    def _match(pp: list[str], pat: list[str]) -> bool:
        if not pat:
            return not pp
        if not pp:
            return all(p == "**" for p in pat)
        if pat[0] == "**":
            for i in range(len(pp) + 1):
                if _match(pp[i:], pat[1:]):
                    return True
            return False
        return fnmatch.fnmatch(pp[0], pat[0]) and _match(pp[1:], pat[1:])

    return _match(path_parts, pat_parts)


# ── File Classification ────────────────────────────────────────


def classify_files(file_names: list[str]) -> dict[str, int]:
    """Categorise Java file names into standard layers.

    Returns a dict whose keys are layer names (``controller``, ``service``,
    ``mapper``, ``entity``, ``dto``) and values are counts.  Only layers
    with at least one file appear.
    """
    counts: dict[str, int] = {}
    for name in file_names:
        if name.endswith("Controller.java"):
            counts["controller"] = counts.get("controller", 0) + 1
        elif name.endswith("ServiceImpl.java") or name.endswith("Service.java"):
            counts["service"] = counts.get("service", 0) + 1
        elif name.endswith("Mapper.java"):
            counts["mapper"] = counts.get("mapper", 0) + 1
        elif name.endswith("Entity.java"):
            counts["entity"] = counts.get("entity", 0) + 1
        elif name.endswith("DTO.java") or name.endswith("VO.java"):
            counts["dto"] = counts.get("dto", 0) + 1
    return counts


# ── Blocking Logic ─────────────────────────────────────────────


def is_blocked(findings: list[Finding], strategy: BlockingStrategy) -> bool:
    """Determine whether the given *findings* should block the build.

    * ``STRICT`` — blocked by P0 **or** P1 findings.
    * ``NORMAL`` — blocked by P0 findings **only**.
    * ``LOOSE``  — blocked by P0 findings **only**.

    Returns ``False`` when *findings* is empty.
    """
    if not findings:
        return False
    if strategy == BlockingStrategy.STRICT:
        return any(f.level in (Level.P0, Level.P1) for f in findings)
    if strategy in (BlockingStrategy.NORMAL, BlockingStrategy.LOOSE):
        return any(f.level == Level.P0 for f in findings)
    return False


# ── Single-file Scan ───────────────────────────────────────────


def scan_single_file(file_path: Path, rules: dict) -> list[Finding]:
    """Run all applicable scanners against a single Java file.

    Args:
        file_path: Path to the Java source file.
        rules: Dict of check rules keyed by check code.

    Returns:
        Combined, line-sorted list of ``Finding`` objects from all scanners.
    """
    all_findings: list[Finding] = []
    for scanner in SCANNERS.values():
        all_findings.extend(scanner.scan(file_path, rules))
    all_findings.sort(key=lambda f: f.line)
    return all_findings


# ── Sensitive-Keyword Hints ────────────────────────────────────

_SENSITIVE_KEYWORDS = [
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "apikey",
    "api_key",
    "access_key",
    "private_key",
    "credential",
    "jwt",
    "auth",
]


def _scan_for_hints(file_path: Path, content: str) -> list[HintForAI]:
    """Scan *content* for sensitive keywords in ``log.*`` / ``System.*.print*`` statements.

    Returns a list of ``HintForAI`` objects, one per matching line.
    """
    hints: list[HintForAI] = []
    lines = content.split("\n")
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.search(
            r"(log\.|System\.(?:out|err)\.print|logger\.)", stripped, re.IGNORECASE
        ):
            for kw in _SENSITIVE_KEYWORDS:
                if kw in stripped.lower():
                    hints.append(
                        HintForAI(
                            file=str(file_path),
                            line=lineno,
                            code="SENSITIVE_LOG",
                            snippet=stripped,
                        )
                    )
                    break
    return hints


# ── Full Directory Scan ────────────────────────────────────────


def scan_files(
    base_path: Path, rules: dict, config: dict[str, Any]
) -> ScanResult:
    """Scan all Java files under *base_path* using the given *rules* and *config*.

    Args:
        base_path: Root directory to scan.
        rules: Rule dict keyed by check code (from ``load_program_checks``).
        config: CLI / YAML config dict (from ``load_cli_config`` or defaults).

    Returns:
        A complete ``ScanResult`` with metadata, per-file reports, summary
        statistics, and AI attention hints.
    """
    excludes: list[str] = config.get("exclude", [])
    strategy = config.get("strategy", BlockingStrategy.STRICT)
    if isinstance(strategy, str):
        strategy = BlockingStrategy(strategy)

    java_files = find_java_files(base_path, excludes)
    file_names = [f.name for f in java_files]
    breakdown = classify_files(file_names)
    file_reports: list[FileReport] = []
    all_hints: list[HintForAI] = []
    all_findings: list[Finding] = []

    for java_file in java_files:
        try:
            content = java_file.read_text(encoding="utf-8")
            all_hints.extend(_scan_for_hints(java_file, content))
            findings = scan_single_file(java_file, rules)
        except (OSError, UnicodeDecodeError) as exc:
            findings = [
                Finding(
                    code="IO_ERROR",
                    level=Level.P0,
                    line=0,
                    method=None,
                    message=f"Failed to read file: {exc}",
                    evidence=str(java_file),
                )
            ]
        all_findings.extend(findings)
        file_reports.append(FileReport(file=str(java_file), findings=findings))

    file_count = len(java_files)
    passed_count = sum(1 for r in file_reports if not r.findings)
    failed_dicts = [f.to_dict() for f in all_findings]
    blocked = is_blocked(all_findings, strategy)

    scope = ScanScope(
        base_path=str(base_path),
        file_count=file_count,
        breakdown=breakdown,
    )
    metadata = ScanMetadata(
        module="code-check",
        scan_scope=scope,
        blocking_strategy=strategy,
        passed=not blocked,
    )
    summary = ScanSummary(
        total_checks=file_count,
        passed=passed_count,
        failed=failed_dicts,
    )

    return ScanResult(
        metadata=metadata,
        file_reports=file_reports,
        summary=summary,
        hints_for_ai=all_hints,
    )
