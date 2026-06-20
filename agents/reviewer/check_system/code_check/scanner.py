"""Java file scanner engine for code-check system.

Scans Java source files against program check rules defined in YAML.
Supports six scanner types:
  - text-grep:          line-by-line regex matching
  - java-annotation:    context-aware annotation presence checks
  - java-return-type:   controller method return-type check (Result<T>)
  - package-structure:  directory structure verification
  - file-naming:        file naming convention checks
  - config-check:       YAML/properties config file checks
"""

import fnmatch
import string as _string_
import os
import re
from pathlib import Path
from typing import Any

from code_check.models import (
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
    """Return annotation names applied at class/interface level.

    Looks for annotations on lines preceding the ``class`` or ``interface`` keyword.
    """
    m = re.search(
        r"(?:public\s+|private\s+|protected\s+)?"
        r"(?:abstract\s+)?(?:static\s+)?(?:class|@interface|interface)\s+\w+",
        content,
    )
    if not m:
        return []
    preceding = content[: m.start()]
    return re.findall(r"@(\w+)", preceding)


def _get_class_name(content: str) -> str:
    """Extract the simple class/interface name from Java source."""
    m = re.search(
        r"(?:public\s+|private\s+|protected\s+)?"
        r"(?:abstract\s+)?(?:static\s+)?(?:class|@interface|interface)\s+(\w+)",
        content,
    )
    return m.group(1) if m else ""


def _any_match(items: list[str], pattern: str) -> bool:
    """Return True if any *item* matches the pipe-separated *pattern*.

    Supports both glob patterns (``*Entity``) and regex/substring patterns.
    Invalid regex patterns (e.g. unbalanced parentheses) are silently skipped
    to prevent crashing the entire scan.
    """
    for pat in pattern.split("|"):
        pat = pat.strip()
        if not pat:
            continue
        for item in items:
            if "*" in pat or "?" in pat:
                if fnmatch.fnmatch(item, pat):
                    return True
            else:
                try:
                    if re.search(pat, item):
                        return True
                except re.error:
                    # Skip invalid regex fragments (e.g. from patterns like
                    # ".*(Constant|Constants|Code|Codes)" split on |)
                    pass
    return False


def _class_name_matches(class_name: str, on_class: str) -> bool:
    """Check if *class_name* matches any pattern in pipe-separated *on_class*.

    Supports both glob patterns (e.g. ``*Entity``) and regex/substring
    patterns (e.g. ``RestController``).

    Invalid regex patterns are silently skipped.
    """
    if not class_name:
        return False
    for pat in on_class.split("|"):
        pat = pat.strip()
        if not pat:
            continue
        # Glob-style patterns (contain * or ?) → fnmatch
        if "*" in pat or "?" in pat:
            if fnmatch.fnmatch(class_name, pat):
                return True
        # Regex/substring patterns → re.search
        else:
            try:
                if re.search(pat, class_name):
                    return True
            except re.error:
                # Skip invalid regex fragments (e.g. "Codes)" from
                # ".*(Constant|Constants|Code|Codes)" split on |)
                pass
    return False


def _on_class_matches(
    class_annotations: list[str], class_name: str, on_class: str
) -> bool:
    """Return True if *on_class* matches either annotations or class name.

    This unifies the two semantics of ``on_class``:
    1. Annotation name patterns: ``RestController|Controller`` matches ``@RestController``
    2. Class name patterns: ``*Entity`` matches class ``UserEntity``
    """
    if _any_match(class_annotations, on_class):
        return True
    if _class_name_matches(class_name, on_class):
        return True
    return False


def _matches_on_dir(file_path: Path, on_dir: str) -> bool:
    """Check if *file_path*'s parent directory components match *on_dir*.

    *on_dir* is a pipe-separated list of directory name patterns.
    Example: ``"controller"`` matches ``.../controller/UserController.java``.
    Example: ``"config|security"`` matches files in either directory.
    """
    if not on_dir:
        return True
    parts = [p for p in file_path.parent.parts]
    patterns = on_dir.split("|")
    for pat in patterns:
        pat = pat.strip()
        if not pat:
            continue
        for part in parts:
            # Exact match: use fnmatch for glob patterns, fullmatch for regex
            if "*" in pat or "?" in pat:
                if fnmatch.fnmatch(part, pat):
                    return True
            elif re.fullmatch(pat, part):
                return True
    return False


def _has_annotation(content: str, annotation_pattern: str) -> bool:
    """Return True if *annotation_pattern* is found anywhere in *content*."""
    return bool(re.search(rf"\b{annotation_pattern}\b", content))


def _glob_to_regex(pattern: str) -> str:
    """Convert a shell glob pattern to a regex pattern.

    Handles ``*`` (any sequence of non-separator chars) and ``?`` (any single
    character).  If the pattern already looks like a regex (contains ``\\\\``
    or ``.*`` or ``[``), return it unchanged.

    Examples:
        ``*VO.java`` → ``^.*VO\\.java$``
        ``*Controller.java`` → ``^.*Controller\\.java$``
    """
    # If it already looks like a regex, return as-is
    if any(token in pattern for token in ("\\\\", ".*", "(", ")", "[", "]", "+", "{", "}", "|")):
        return pattern
    # Convert glob to regex
    result = "^" + fnmatch.translate(pattern) + "$"
    return result


def _has_class_modifier(content: str, modifier: str) -> bool:
    """Check if the class/interface declaration includes *modifier* (e.g. ``final``).

    Example: ``public final class FooConstants`` → True for ``final``.
    """
    m = re.search(
        r"(?:public\s+|private\s+|protected\s+)?"
        r"(?:abstract\s+)?(?:static\s+)?"
        rf"(?:{modifier}\s+)?"
        r"(?:class|@interface|interface)\s+\w+",
        content,
    )
    if not m:
        return False
    # Check that *modifier* actually appears before the class keyword
    return bool(re.search(rf"\b{modifier}\b", content[: m.end()]))


def _has_private_constructor(content: str) -> bool:
    """Check if the Java source contains a private constructor.

    Matches constructors with optional ``throws`` clause, e.g.:
    ``private Foo() throws Exception {``.
    """
    clean = _strip_comments_preserve_lines(content)
    return bool(re.search(
        r"private\s+\w+\s*\([^)]*\)\s*(?:throws\s+[\w\s,]+)?\s*\{",
        clean,
    ))


def _param_has_validated_with_group(params_str: str, param_name: str) -> bool:
    """Check if a parameter named *param_name* has ``@Validated(SomeGroup.class)``.

    Returns True if the ``@Validated`` annotation on the parameter includes
    a group argument (e.g. ``@Validated(Create.class)``).  A bare
    ``@Validated`` without a group is ignored by Spring validation, so this
    check helps catch misconfigured validation annotations.
    """
    # Find the parameter segment in params_str
    for seg in params_str.split(","):
        seg = seg.strip()
        if param_name in seg:
            # Check if @Validated has a parenthesized group argument
            if re.search(r"@Validated\s*\([^)]+\)", seg):
                return True
            break
    return False


def _find_method_body_range(
    lines: list[str], method_line: int
) -> tuple[int | None, int | None]:
    """Find the body range (start, end) of a method starting near *method_line*.

    Searches for the opening ``{`` after the method signature (looking for
    ``) {`` or ``){`` to avoid matching braces inside annotation strings like
    ``@GetMapping("/{id}")``) and tracks brace depth to find the matching
    closing ``}``.  Returns ``(None, None)`` if the body cannot be determined.
    """
    # Find the method signature's closing paren and opening brace.
    # Look for ") {" or "){ " pattern to avoid false matches inside strings.
    brace_line = None
    for i in range(method_line - 1, len(lines)):
        line = lines[i]
        if re.search(r"\)\s*\{", line):
            brace_line = i + 1  # 1-based line number
            break

    if brace_line is None:
        # Fallback: search more loosely
        for i in range(method_line - 1, len(lines)):
            if "{" in lines[i]:
                brace_line = i + 1
                break

    if brace_line is None:
        return None, None

    # Track brace depth from the position of the opening brace.
    # Start counting from the brace itself, ignoring characters before it.
    start_line = lines[brace_line - 1]
    brace_pos = start_line.index("{")
    depth = 0

    for i in range(brace_line - 1, len(lines)):
        line = lines[i]
        start_idx = brace_pos if i == brace_line - 1 else 0
        for j, ch in enumerate(line):
            if j < start_idx:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return brace_line, i + 1  # 1-based end line

    return brace_line, len(lines)  # fallback to end of file


def _parse_params(params_str: str) -> list[dict]:
    """Parse a Java method's comma-separated parameter text into structured records.

    Each record has keys ``type``, ``name``, and ``annotations`` (list of annotation
    names without the leading ``@``).

    Generic type parameters (e.g. ``List<Map<String, Integer>>``) are handled by
    tracking angle-bracket depth so that commas inside generics are not treated
    as parameter separators.
    """
    if not params_str.strip():
        return []
    params: list[dict] = []

    # Split by comma, respecting angle brackets
    segments: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in params_str:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "," and depth == 0:
            segments.append("".join(current))
            current = []
            continue
        current.append(ch)
    if current:
        segments.append("".join(current))

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        annots = re.findall(r"@(\w+)", seg)
        clean = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", seg).strip()
        # The last word is the parameter name, everything before is the type.
        # This handles generic types like "Map<String, Integer> map".
        parts = clean.rsplit(maxsplit=1)
        if len(parts) == 2:
            param_type, param_name = parts[0], parts[1]
        elif len(parts) == 1:
            param_type, param_name = parts[0], ""
        else:
            param_type, param_name = "", ""
        params.append({"type": param_type, "name": param_name, "annotations": annots})
    return params


def _strip_comments_preserve_lines(text: str) -> str:
    """Replace comments with newlines so that line numbering stays accurate.

    Block comments (``/* ... */``) are replaced with the same number of
    newlines they contain.  Line comments (``// ...``) are replaced with
    empty strings (they don't change line count).

    Uses a negative lookbehind to avoid stripping ``://`` inside URL strings
    (e.g. ``"http://example.com"``).  This is not a full Java parser — edge
    cases with ``//`` inside string literals without a preceding ``:`` remain
    as a known limitation.
    """
    # Block comments: replace with newlines to preserve line count
    result = re.sub(
        r"/\*.*?\*/",
        lambda m: "\n" * m.group(0).count("\n"),
        text,
        flags=re.DOTALL,
    )
    # Line comments: skip "://" (URLs in strings), remove everything else
    result = re.sub(r"(?<!:)//[^\n]*", "", result)
    return result


def _find_methods(content: str) -> list[dict]:
    """Find all method declarations in Java source with their metadata.

    Returns a list of dicts with keys:
        name, return_type, params (structured), params_str, line_num, annotations.
    Comments are replaced with newlines to preserve accurate line numbering.
    Handles both regular methods (ending with ``{``) and interface/abstract
    methods (ending with ``;``).
    """
    clean = _strip_comments_preserve_lines(content)

    methods: list[dict] = []
    # Match both regular methods ({) and abstract/interface methods (;)
    # Access modifier is optional to support interface methods.
    # Post-filter removes false matches on Java keywords inside method bodies
    # (e.g. "return new UserVO();" would otherwise match as a method).
    pattern = (
        r"((?:@\w+(?:\([^)]*\))?\s*)*)"  # method annotations
        r"\s*"                             # consume leading whitespace
        r"(?:(?:public|private|protected)\s+)?"
        r"(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?(?:abstract\s+)?(?:default\s+)?"
        r"([\w<>,?\[\]\s]+?)\s+"
        r"(\w+)\s*"  # method name
        r"\(([^()]*)\)"
        r"\s*(?:\{|;)"  # body or semicolon
    )

    _JAVA_KEYWORDS = frozenset({
        "return", "new", "if", "else", "for", "while", "do", "switch", "case",
        "try", "catch", "finally", "throw", "throws", "class", "interface",
        "enum", "package", "import", "synchronized", "static", "abstract",
        "default", "private", "protected", "public", "assert", "break",
        "continue", "instanceof", "super", "this", "void", "goto", "const",
    })

    for m in re.finditer(pattern, clean):
        method_name = m.group(3)
        # Skip false matches on Java keywords (e.g. "new Foo()" in method bodies)
        if method_name in _JAVA_KEYWORDS:
            continue
        return_type = m.group(2).strip()
        # Skip if return type contains statement keywords
        # (e.g. "return new UserVO()" would parse as method with return type "return new")
        _STMT_KW = {"return", "throw", "new", "if", "else", "for", "while", "do", "switch", "case", "try", "catch", "finally"}
        if any(token in _STMT_KW for token in return_type.split()):
            continue
        ann_line = m.group(1)
        method_annotations = re.findall(r"@(\w+(?:\([^)]*\))?)", ann_line)
        methods.append(
            {
                "return_type": return_type,
                "name": method_name,
                "params_str": m.group(4),
                "params": _parse_params(m.group(4)),
                "line_num": clean[: m.start()].count("\n") + 1,  # use clean for accurate line numbers
                "annotations": method_annotations,
            }
        )
    return methods


def _get_fields(content: str) -> list[dict]:
    """Extract field declarations from Java source.

    Returns a list of dicts with keys:
        name, type, annotations, line_num.
    Comments are replaced with newlines to preserve accurate line numbering.
    """
    clean = _strip_comments_preserve_lines(content)

    fields: list[dict] = []
    # Match: [annotations] [modifiers] Type name [= value];
    pattern = (
        r"((?:@\w+(?:\([^)]*\))?\s*)*)"  # field annotations
        r"(?:private|protected|public)\s+"
        r"(?:static\s+)?(?:final\s+)?"
        r"([\w<>,?\[\]\s]+?)\s+"          # type
        r"(\w+)"                            # name
        r"\s*(?:=|;)"
    )

    for m in re.finditer(pattern, clean):
        ann_line = m.group(1)
        field_annotations = re.findall(r"@(\w+(?:\([^)]*\))?)", ann_line)
        fields.append(
            {
                "type": m.group(2).strip(),
                "name": m.group(3),
                "annotations": field_annotations,
                "line_num": clean[: m.start()].count("\n") + 1,  # use clean for accurate line numbers
            }
        )
    return fields


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

    def scan_directory(self, base_path: Path, rules: dict) -> list[Finding]:
        """Run directory-level scan over *base_path*.

        Override in scanners that need directory-level access
        (e.g. package-structure, config-check).

        Args:
            base_path: Root directory to scan.
            rules: Full rule dict.

        Returns:
            List of Finding objects, possibly empty.
        """
        return []

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

    Also supports:
    - ``on_dir``: restrict to files in specific directories
    - ``on_class``: restrict to files whose class annotation matches
    - ``on_file_pattern``: restrict to files matching a filename regex
    - ``on_method_annotation``: restrict scan to methods with this annotation
    - ``must_match``: report when pattern is NOT found (inverse logic)
    """

    scanner_name = "text-grep"

    def scan(self, file_path: Path, rules: dict) -> list[Finding]:
        findings: list[Finding] = []
        my_rules = self._rules_for_scanner(rules, self.scanner_name)
        if not my_rules:
            return findings

        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        file_name = file_path.name
        class_anns = _get_class_annotations(content)
        class_name = _get_class_name(content)

        for code, rule in my_rules.items():
            program = rule["program"]

            # ── on_dir filtering ──
            if "on_dir" in program:
                if not _matches_on_dir(file_path, program["on_dir"]):
                    continue

            # ── on_class filtering ──
            if "on_class" in program:
                if not _on_class_matches(class_anns, class_name, program["on_class"]):
                    continue

            # ── on_file_pattern filtering ──
            if "on_file_pattern" in program:
                fp_regex = re.compile(_glob_to_regex(program["on_file_pattern"]))
                if not fp_regex.search(file_name):
                    continue

            regex = re.compile(program["pattern"])
            neg_regex = (
                re.compile(program["no_match_in_same_line"])
                if "no_match_in_same_line" in program
                else None
            )
            level = Level(rule["level"])
            msg = rule["message"]
            must_match = program.get("must_match", False)
            on_method_annotation = program.get("on_method_annotation", "")

            if on_method_annotation:
                # ── Per-method scanning with annotation filter ──
                findings.extend(
                    self._scan_methods_by_annotation(
                        content, lines, code, level, msg, program, on_method_annotation
                    )
                )
            elif must_match:
                # Inverse logic: report if pattern is NOT found anywhere in file
                found = False
                for lineno, line in enumerate(lines, 1):
                    if regex.search(line):
                        found = True
                        break
                if not found:
                    findings.append(
                        Finding(
                            code=code,
                            level=level,
                            line=1,
                            message=msg,
                            evidence=f"未找到匹配: {program['pattern']}",
                        )
                    )
            else:
                # Default: report each matching line
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

    @staticmethod
    def _scan_methods_by_annotation(
        content: str,
        lines: list[str],
        code: str,
        level: Level,
        msg: str,
        program: dict,
        on_method_annotation: str,
    ) -> list[Finding]:
        """Scan only methods annotated with *on_method_annotation*.

        For each matching method, checks whether the pattern (with optional
        ``must_match`` semantics) applies within the method body.
        """
        findings: list[Finding] = []
        method_ann_regex = re.compile(on_method_annotation)
        regex = re.compile(program["pattern"])
        must_match = program.get("must_match", False)

        methods = _find_methods(content)
        for method in methods:
            # Check if method has the required annotation
            has_ann = any(
                method_ann_regex.search(a) for a in method["annotations"]
            )
            if not has_ann:
                continue

            # Find method body range (from opening { to matching })
            body_start, body_end = _find_method_body_range(
                lines, method["line_num"]
            )
            if body_start is None:
                continue

            body_lines = lines[body_start - 1 : body_end]

            if must_match:
                # Pattern MUST exist in the method body
                found = any(regex.search(line) for line in body_lines)
                if not found:
                    findings.append(
                        Finding(
                            code=code,
                            level=level,
                            line=method["line_num"],
                            message=_safe_format(
                                msg,
                                {
                                    "method": method["name"],
                                    "class": "",
                                    "class_": "",
                                },
                            ),
                            evidence=f"方法 {method['name']} 缺少: {program['pattern']}",
                            method=method["name"],
                        )
                    )
            else:
                # Report each matching line in the method body
                for i, line in enumerate(body_lines):
                    match = regex.search(line)
                    if match:
                        findings.append(
                            Finding(
                                code=code,
                                level=level,
                                line=body_start + i,
                                message=msg,
                                evidence=match.group().strip(),
                                method=method["name"],
                            )
                        )
        return findings


# ── Java Annotation Scanner ────────────────────────────────────


class JavaAnnotationScanner(BaseScanner):
    """Context-aware scanner for Java annotations.

    Supports multiple targets:

    * ``method_param`` — checks that DTO-typed method parameters carry a
      required annotation (e.g. ``@Valid`` / ``@Validated``).
    * ``field`` — checks that fields carry a required annotation
      (e.g. ``@Schema`` on DTO fields).
    * ``required_class_annotation`` — checks that classes carry a specific
      class-level annotation (e.g. ``@Slf4j``).
    * ``required_field_annotation`` — checks that classes have a field with
      a specific annotation (e.g. ``@TableLogic`` on Entity).
    * ``on_public_method`` + ``missing_annotation`` — checks that public methods
      carry a required annotation (e.g. ``@Operation`` on Controller methods).
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

            # ── on_dir filtering ──
            if "on_dir" in program:
                if not _matches_on_dir(file_path, program["on_dir"]):
                    continue

            # ── on_file_pattern filtering ──
            if "on_file_pattern" in program:
                fp_regex = re.compile(_glob_to_regex(program["on_file_pattern"]))
                if not fp_regex.search(file_path.name):
                    continue

            # ── on_class: match against both annotations AND class name ──
            if "on_class" in program:
                if not _on_class_matches(class_anns, class_name, program["on_class"]):
                    continue

            target = program.get("target", "")

            # ── target: field ──
            if target == "field":
                findings.extend(
                    self._check_field_annotations(
                        content, code, level, msg_template, program, class_name
                    )
                )

            # ── target: method_param ──
            elif target == "method_param":
                findings.extend(
                    self._check_method_param_annotations(
                        content, code, level, msg_template, program, class_name
                    )
                )

            # ── required_class_annotation ──
            if "required_class_annotation" in program:
                needed = program["required_class_annotation"]
                if not _has_annotation(content, needed):
                    findings.append(
                        Finding(
                            code=code,
                            level=level,
                            line=0,
                            message=_safe_format(
                                msg_template,
                                {"class": class_name, "class_": class_name, "method": ""},
                            ),
                            evidence=f"缺少 {needed} 注解",
                        )
                    )

            # ── required_class_modifier ── (BE-QL-38: final class)
            if "required_class_modifier" in program:
                modifier = program["required_class_modifier"]
                # Check class declaration has the modifier
                if not _has_class_modifier(content, modifier):
                    findings.append(
                        Finding(
                            code=code,
                            level=level,
                            line=0,
                            message=_safe_format(
                                msg_template,
                                {"class": class_name, "class_": class_name, "method": ""},
                            ),
                            evidence=f"类缺少 {modifier} 修饰符",
                        )
                    )

            # ── required_private_constructor ── (BE-QL-38: private constructor)
            if program.get("required_private_constructor"):
                if not _has_private_constructor(content):
                    findings.append(
                        Finding(
                            code=code,
                            level=level,
                            line=0,
                            message=_safe_format(
                                msg_template,
                                {"class": class_name, "class_": class_name, "method": ""},
                            ),
                            evidence="类缺少私有构造器",
                        )
                    )

            # ── required_field_annotation ──
            if "required_field_annotation" in program:
                needed = program["required_field_annotation"]
                fields = _get_fields(content)
                has_annotation = any(
                    _has_annotation(f["type"] + " " + f["name"], needed)
                    or any(
                        re.search(needed.replace("@", ""), a)
                        for a in f["annotations"]
                    )
                    for f in fields
                )
                if not has_annotation:
                    findings.append(
                        Finding(
                            code=code,
                            level=level,
                            line=0,
                            message=_safe_format(
                                msg_template,
                                {"class": class_name, "class_": class_name, "method": ""},
                            ),
                            evidence=f"缺少 {needed} 注解",
                        )
                    )

            # ── on_public_method: check public methods for missing annotation ──
            if program.get("on_public_method") and "missing_annotation" in program:
                findings.extend(
                    self._check_method_level_annotations(
                        content, code, level, msg_template, program, class_name
                    )
                )

        return findings

    @staticmethod
    def _check_field_annotations(
        content: str,
        code: str,
        level: Level,
        msg_template: str,
        program: dict,
        class_name: str,
    ) -> list[Finding]:
        """Check fields for missing annotations (e.g. @Schema on DTO fields)."""
        findings: list[Finding] = []
        missing_annotation = program.get("missing_annotation", "")
        if not missing_annotation:
            return findings

        ann_regex = re.compile(missing_annotation.replace("@", ""))
        fields = _get_fields(content)

        for field in fields:
            has_ann = any(ann_regex.search(a) for a in field["annotations"])
            if not has_ann:
                findings.append(
                    Finding(
                        code=code,
                        level=level,
                        line=field["line_num"],
                        message=_safe_format(
                            msg_template,
                            {
                                "class": class_name,
                                "class_": class_name,
                                "field": field["name"],
                                "method": "",
                            },
                        ),
                        evidence=f"字段 {field['type']} {field['name']} 缺少 {missing_annotation}",
                    )
                )
        return findings

    @staticmethod
    def _check_method_level_annotations(
        content: str,
        code: str,
        level: Level,
        msg_template: str,
        program: dict,
        class_name: str,
    ) -> list[Finding]:
        """Check that methods carry required annotations (e.g. @Operation on public methods)."""
        findings: list[Finding] = []
        missing_annotation = program.get("missing_annotation", "")
        if not missing_annotation:
            return findings

        ann_regex = re.compile(missing_annotation.replace("@", ""))
        methods = _find_methods(content)

        for method in methods:
            has_ann = any(ann_regex.search(a) for a in method["annotations"])
            if not has_ann:
                findings.append(
                    Finding(
                        code=code,
                        level=level,
                        line=method["line_num"],
                        message=_safe_format(
                            msg_template,
                            {
                                "method": method["name"],
                                "class": class_name,
                                "class_": class_name,
                            },
                        ),
                        evidence=f"方法 {method['name']} 缺少 {missing_annotation}",
                        method=method["name"],
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
        whose type matches *match_param_type* (or whose annotations match
        *match_annotation*) also carries an annotation matching
        *missing_annotation*.  If the annotation is absent a ``Finding`` is
        emitted for that method.

        Also supports:
        - ``on_method_annotation``: restrict to methods with this annotation
        - ``match_annotation``: filter params by their existing annotations
        - ``param_count_gte``: only check methods with >= N parameters
        """
        findings: list[Finding] = []
        match_param_type = program.get("match_param_type", "")
        match_annotation = program.get("match_annotation", "")
        missing_annotation = program.get("missing_annotation", "")
        on_method_annotation = program.get("on_method_annotation", "")
        param_count_gte = program.get("param_count_gte", 0)

        type_regex = re.compile(match_param_type) if match_param_type else None
        match_ann_regex = re.compile(match_annotation) if match_annotation else None
        ann_regex = re.compile(missing_annotation) if missing_annotation else None
        method_ann_regex = (
            re.compile(on_method_annotation) if on_method_annotation else None
        )

        methods = _find_methods(content)
        for method in methods:
            # Filter by method annotation
            if method_ann_regex:
                if not any(
                    method_ann_regex.search(a) for a in method["annotations"]
                ):
                    continue

            # Filter by param count
            if param_count_gte and len(method["params"]) < param_count_gte:
                continue

            for param in method["params"]:
                # Filter by parameter type
                if type_regex and not type_regex.search(param["type"]):
                    continue
                # Filter by parameter annotation (e.g. @PathVariable/@RequestParam)
                if match_ann_regex:
                    param_anns = [f"@{a}" for a in param["annotations"]]
                    if not any(match_ann_regex.search(a) for a in param_anns):
                        continue

                # ── check_group_present: @Validated should have group ──
                if program.get("check_group_present"):
                    # Re-extract annotations from the original params_str to get
                    # full annotation text including group params
                    has_validated_with_group = _param_has_validated_with_group(
                        method["params_str"], param["name"]
                    )
                    if has_validated_with_group:
                        continue  # OK, has group

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
                                {
                                    "method": method["name"],
                                    "class": class_name,
                                    "class_": class_name,
                                    "param": f"{param['type']} {param['name']}",
                                },
                            ),
                            evidence=f"参数 {param['type']} {param['name']} 的 @Validated 未指定分组",
                            method=method["name"],
                        )
                    )
        return findings


# ── Java Return-Type Scanner ───────────────────────────────────


class JavaReturnTypeScanner(BaseScanner):
    """Checks that controller methods return ``Result<T>``.

    Rule must specify an ``on_class`` pattern (e.g. ``RestController|Controller``)
    and a ``required_return_pattern`` (e.g. ``Result<``).

    Also supports:
    - ``on_method_name``: restrict to methods whose name matches a pipe-separated
      pattern (e.g. ``page|list`` for pagination methods).
    """

    scanner_name = "java-return-type"

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
            required_return = program["required_return_pattern"]
            return_regex = re.compile(required_return)

            if not _on_class_matches(class_anns, class_name, on_class):
                continue

            on_method_name = program.get("on_method_name", "")

            methods = _find_methods(content)
            for method in methods:
                # Filter by method name
                if on_method_name:
                    name_patterns = on_method_name.split("|")
                    if not any(
                        re.search(p.strip(), method["name"])
                        for p in name_patterns
                        if p.strip()
                    ):
                        continue

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


# ── Package Structure Scanner ──────────────────────────────────


class PackageStructureScanner(BaseScanner):
    """Checks that the Java package directory structure follows conventions.

    Operates at the directory level — scans subdirectories under *base_path*
    to verify required directories exist.

    Supports:
    - ``required_dirs``: pipe-separated list of required subdirectory names
    - ``required_service_impl``: require ``service/impl/`` subdirectory
    - ``check_impl_subdir``: check that ``service/`` has ``impl/`` child
    """

    scanner_name = "package-structure"

    def scan(self, file_path: Path, rules: dict) -> list[Finding]:
        # package-structure is directory-level; handled in scan_directory()
        return []

    def scan_directory(self, base_path: Path, rules: dict) -> list[Finding]:
        findings: list[Finding] = []
        my_rules = self._rules_for_scanner(rules, self.scanner_name)
        if not my_rules:
            return findings

        # Find the deepest package directory under base_path
        java_dirs = self._find_java_package_dirs(base_path)
        if not java_dirs:
            return findings

        # Check each Java package directory
        for pkg_dir in java_dirs:
            for code, rule in my_rules.items():
                program = rule["program"]
                level = Level(rule["level"])
                msg = rule["message"]

                subdirs = {
                    d.name: d
                    for d in pkg_dir.iterdir()
                    if d.is_dir() and not d.name.startswith(".")
                }

                # Check required_dirs
                if "required_dirs" in program:
                    required = program["required_dirs"].split("|")
                    missing = [d for d in required if d not in subdirs]
                    if missing:
                        findings.append(
                            Finding(
                                code=code,
                                level=level,
                                line=0,
                                message=msg,
                                evidence=f"缺少子包: {', '.join(missing)} (路径: {pkg_dir})",
                            )
                        )

                # Check service/impl (required_service_impl or check_impl_subdir)
                if program.get("required_service_impl") or program.get("check_impl_subdir"):
                    if "service" in subdirs:
                        service_sub = {
                            d.name: d
                            for d in subdirs["service"].iterdir()
                            if d.is_dir()
                        }
                        if "impl" not in service_sub:
                            findings.append(
                                Finding(
                                    code=code,
                                    level=level,
                                    line=0,
                                    message=msg,
                                    evidence=f"缺少 service/impl 子包 (路径: {subdirs['service']})",
                                )
                            )
                    elif program.get("required_service_impl"):
                        # Only report missing service/ if impl was explicitly required
                        findings.append(
                            Finding(
                                code=code,
                                level=level,
                                line=0,
                                message=msg,
                                evidence=f"缺少 service/ 子包 (路径: {pkg_dir})",
                            )
                        )

        return findings

    @staticmethod
    def _find_java_package_dirs(base_path: Path) -> list[Path]:
        """Find Java package root directories under *base_path*.

        Walks down from base_path looking for directories that contain
        standard package subdirectories (controller, service, etc.).

        Returns only the topmost package roots — subdirectories that are
        themselves inside a standard package dir (e.g. ``controller/``)
        are excluded.
        """
        candidates: list[Path] = []
        std_names = {"controller", "service", "mapper", "entity", "dto", "vo"}

        for root, dirs, files in os.walk(base_path):
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d not in ("test", "target", "node_modules")
            ]
            root_path = Path(root)
            child_dir_names = set(dirs)
            has_java = any(f.endswith(".java") for f in files)

            # A package root has standard subdirs, OR has Java files
            # but is NOT inside a standard subdir itself
            if child_dir_names & std_names:
                candidates.append(root_path)
            elif has_java:
                # Only include if the parent directory is not a standard
                # package subdir (e.g. don't include controller/ itself)
                parent_name = root_path.parent.name
                if parent_name not in std_names:
                    candidates.append(root_path)

        # Deduplicate: keep only topmost directories (remove children)
        result: list[Path] = []
        for c in sorted(candidates):
            # Keep c if no other candidate is a parent of c
            if not any(c != other and c.is_relative_to(other) for other in candidates):
                result.append(c)

        # Fallback: if no structured package found, use base_path itself
        if not result:
            result.append(base_path)
        return result


# ── File Naming Scanner ────────────────────────────────────────


class FileNamingScanner(BaseScanner):
    """Checks Java file naming conventions.

    Supports:
    - ``on_dir``: restrict to files in specific directories
    - ``pattern``: glob pattern the filename must match
    - ``exclude_pattern``: glob pattern to exclude from check
    - ``must_be_in_root_package``: file must be directly in the root package
    - ``must_not_match``: report if pattern IS matched (inverse)
    - ``on_file_pattern``: restrict to files matching a filename regex
    """

    scanner_name = "file-naming"

    def scan(self, file_path: Path, rules: dict) -> list[Finding]:
        findings: list[Finding] = []
        my_rules = self._rules_for_scanner(rules, self.scanner_name)
        if not my_rules:
            return findings

        file_name = file_path.name

        for code, rule in my_rules.items():
            program = rule["program"]
            level = Level(rule["level"])
            msg = rule["message"]

            # ── on_dir filtering ──
            if "on_dir" in program:
                if not _matches_on_dir(file_path, program["on_dir"]):
                    continue

            # ── on_file_pattern filtering ──
            if "on_file_pattern" in program:
                fp_regex = re.compile(program["on_file_pattern"])
                if not fp_regex.search(file_name):
                    continue

            # ── exclude_pattern ──
            if "exclude_pattern" in program:
                if fnmatch.fnmatch(file_name, program["exclude_pattern"]):
                    continue

            # ── must_be_in_root_package ──
            if program.get("must_be_in_root_package"):
                # Check if file is directly in one of the top-level package dirs
                parent = file_path.parent
                sibling_dirs = [
                    d
                    for d in parent.iterdir()
                    if d.is_dir() and not d.name.startswith(".")
                ]
                std_names = {"controller", "service", "mapper", "entity", "dto", "vo"}
                has_std_siblings = any(d.name in std_names for d in sibling_dirs)

                if not has_std_siblings:
                    # Check if parent itself IS a standard subdir (e.g. controller/)
                    # — then the file is in a sub-package, not root
                    if parent.name in std_names:
                        findings.append(
                            Finding(
                                code=code,
                                level=level,
                                line=0,
                                message=msg,
                                evidence=f"{file_name} 不在根包下 (当前路径: {file_path.parent})",
                            )
                        )
                    # else: project may be new (no subdirs created yet),
                    # don't report false positive
                continue

            # ── must_not_match: inverse logic ──
            if program.get("must_not_match"):
                pattern = program["pattern"]
                if fnmatch.fnmatch(file_name, pattern):
                    findings.append(
                        Finding(
                            code=code,
                            level=level,
                            line=0,
                            message=msg,
                            evidence=f"文件名匹配禁止模式: {pattern}: {file_name}",
                        )
                    )
                continue

            # ── Default: check that filename matches pattern ──
            pattern = program["pattern"]
            if not fnmatch.fnmatch(file_name, pattern):
                findings.append(
                    Finding(
                        code=code,
                        level=level,
                        line=0,
                        message=msg,
                        evidence=f"文件名不符合命名规范: {file_name} (期望: {pattern})",
                    )
                )

        return findings


# ── Config Check Scanner ───────────────────────────────────────


class ConfigCheckScanner(BaseScanner):
    """Scans YAML/properties config files for patterns.

    Operates at the directory level — finds config files by glob pattern
    and checks their contents.

    Supports:
    - ``file_pattern``: glob to find config files (e.g. ``*.yml|*.yaml``)
    - ``pattern``: regex to search for in file contents
    - ``must_not_match``: report if pattern IS found (security anti-pattern)
    - ``exclude_file``: glob to exclude specific files
    """

    scanner_name = "config-check"

    def scan(self, file_path: Path, rules: dict) -> list[Finding]:
        # config-check is directory-level; handled in scan_directory()
        return []

    def scan_directory(self, base_path: Path, rules: dict, exclude_patterns: list[str] | None = None) -> list[Finding]:
        findings: list[Finding] = []
        my_rules = self._rules_for_scanner(rules, self.scanner_name)
        if not my_rules:
            return findings

        excludes = exclude_patterns or []

        for code, rule in my_rules.items():
            program = rule["program"]
            level = Level(rule["level"])
            msg = rule["message"]
            file_pattern = program.get("file_pattern", "*.yml|*.yaml|*.properties")
            must_not_match = program.get("must_not_match", False)
            exclude_file = program.get("exclude_file", "")

            # Find matching config files
            patterns = file_pattern.split("|")
            for pat in patterns:
                pat = pat.strip()
                if not pat:
                    continue
                for match in base_path.rglob(pat):
                    if not match.is_file():
                        continue

                    # Apply exclude patterns (same as Java files)
                    if should_exclude(str(match), excludes):
                        continue

                    # Skip hidden dirs and node_modules
                    if any(p.startswith(".") or p == "node_modules" for p in match.parts):
                        continue

                    # Exclude specific files
                    if exclude_file and fnmatch.fnmatch(match.name, exclude_file):
                        continue

                    try:
                        content = match.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        continue

                    regex = re.compile(program["pattern"])
                    lines = content.split("\n")

                    if must_not_match:
                        # Report if pattern IS found (e.g. plaintext password)
                        for lineno, line in enumerate(lines, 1):
                            if regex.search(line):
                                findings.append(
                                    Finding(
                                        code=code,
                                        level=level,
                                        line=lineno,
                                        message=msg,
                                        evidence=f"{match.name}:{lineno}: {line.strip()[:120]}",
                                    )
                                )

                        # Also check multi-line for nested YAML patterns
                        # (e.g. "knife4j:\n  enable: true" vs "knife4j.enable: true")
                        nested_lineno = _find_nested_yaml(content, program["pattern"])
                        if nested_lineno:
                            findings.append(
                                Finding(
                                    code=code,
                                    level=level,
                                    line=nested_lineno,
                                    message=msg,
                                    evidence=f"{match.name}:{nested_lineno}: nested YAML match for {program['pattern']}",
                                )
                            )
                    else:
                        # Report if pattern is NOT found
                        found = any(regex.search(line) for line in lines)
                        # Also check nested YAML
                        if not found:
                            found = _find_nested_yaml(content, program["pattern"]) is not None
                        if not found:
                            findings.append(
                                Finding(
                                    code=code,
                                    level=level,
                                    line=0,
                                    message=msg,
                                    evidence=f"{match.name}: 未找到匹配: {program['pattern']}",
                                )
                            )

        return findings


def _find_nested_yaml(content: str, flat_pattern: str) -> int | None:
    """Check content for a nested YAML equivalent of *flat_pattern*.

    For example, ``knife4j\\.enable\\s*:\\s*true`` also matches::

        knife4j:
          enable: true

    Returns the line number (1-based) of the first nested match, or None.
    """
    # Only handle "parent.child: value" style patterns
    m = re.match(r"(.+?)\\\.(.+?)\\s\*:\\s\*(.+)", flat_pattern)
    if not m:
        return None

    parent = m.group(1)
    child = m.group(2)
    value = m.group(3)

    lines = content.split("\n")
    in_parent = False
    parent_indent = 0

    for lineno, line in enumerate(lines, 1):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Detect parent key at any indentation level
        if re.match(rf"{parent}\s*:\s*$", stripped):
            in_parent = True
            parent_indent = indent
            continue

        # Detect child key inside parent block
        if in_parent and indent > parent_indent:
            if re.match(rf"{child}\s*:\s*{value}", stripped):
                return lineno

        # Reset if we're back to the parent's indent level or lower
        if in_parent and indent <= parent_indent and stripped:
            in_parent = False

    return None

SCANNERS: dict[str, BaseScanner] = {
    "text-grep": TextGrepScanner(),
    "java-annotation": JavaAnnotationScanner(),
    "java-return-type": JavaReturnTypeScanner(),
    "package-structure": PackageStructureScanner(),
    "file-naming": FileNamingScanner(),
    "config-check": ConfigCheckScanner(),
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


# ── Directory-level Scan ───────────────────────────────────────


def _run_directory_scanners(base_path: Path, rules: dict, excludes: list[str] | None = None) -> list[Finding]:
    """Run directory-level scanners (package-structure, config-check)."""
    findings: list[Finding] = []
    for scanner_name in ("package-structure", "config-check"):
        scanner = SCANNERS.get(scanner_name)
        if scanner:
            # ConfigCheckScanner accepts exclude patterns
            if scanner_name == "config-check":
                findings.extend(scanner.scan_directory(base_path, rules, excludes))
            else:
                findings.extend(scanner.scan_directory(base_path, rules))
    return findings


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

    # Filter rules by strategy: loose skips P2 (style/docs), strict/normal run all
    if strategy == BlockingStrategy.LOOSE:
        active_rules = {
            code: rule
            for code, rule in rules.items()
            if rule.get("level") in ("P0", "P1")
        }
    else:
        active_rules = rules

    # ── Phase 1: Directory-level scanners ──
    dir_findings = _run_directory_scanners(base_path, active_rules, excludes)

    # ── Phase 2: Per-file scanners ──
    java_files = find_java_files(base_path, excludes)
    file_names = [f.name for f in java_files]
    breakdown = classify_files(file_names)
    file_reports: list[FileReport] = []
    all_hints: list[HintForAI] = []
    all_findings: list[Finding] = list(dir_findings)

    for java_file in java_files:
        try:
            content = java_file.read_text(encoding="utf-8")
            all_hints.extend(_scan_for_hints(java_file, content))
            findings = scan_single_file(java_file, active_rules)
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

    # Add directory-level findings as a synthetic file report
    if dir_findings:
        file_reports.insert(
            0,
            FileReport(file="[directory-structure]", findings=dir_findings),
        )

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
