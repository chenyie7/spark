"""Java file scanner engine for code-check system.

Scans Java source files against program check rules defined in YAML.
Supports four scanner types:
  - java-ast:           tree-sitter AST-based scanning (class, method, field checks)
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

import tree_sitter
import tree_sitter_java as tsjava

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




def _safe_fullmatch(pattern: str, text: str) -> bool:
    """Like re.fullmatch, but returns False on invalid regex instead of raising."""
    try:
        return bool(re.fullmatch(pattern, text))
    except re.error:
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
            elif _safe_fullmatch(pat, part):
                return True
    return False












# ── tree-sitter initialization ──────────────────────────────────

_TS_LANGUAGE = tree_sitter.Language(tsjava.language())
_TS_PARSER = tree_sitter.Parser(_TS_LANGUAGE)


def _parse_java_source(source: bytes) -> tree_sitter.Tree:
    """Parse Java source bytes into a tree-sitter concrete syntax tree."""
    return _TS_PARSER.parse(source)


# ── AST Node Helpers ─────────────────────────────────────────────


def _node_text(node, source: bytes) -> str:
    """Return the source text of a tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _child_by_type(node, type_name: str):
    """Return the first immediate child of *node* with the given type name."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _children_by_type(node, type_name: str) -> list:
    """Return all immediate children of *node* with the given type name."""
    return [child for child in node.children if child.type == type_name]


def _descendants_by_type(node, type_name: str) -> list:
    """Return all descendant nodes (recursive) of *node* with the given type name."""
    result = []
    for child in node.children:
        if child.type == type_name:
            result.append(child)
        result.extend(_descendants_by_type(child, type_name))
    return result


def _has_modifier(node, modifier: str) -> bool:
    """Check if *node* has a specific modifier in its modifiers child."""
    mods = _child_by_type(node, "modifiers")
    if mods is None:
        return False
    return any(child.type == modifier for child in mods.children)


def _class_modifiers(class_node) -> set:
    """Return the set of modifier keywords on a class/interface declaration."""
    mods = _child_by_type(class_node, "modifiers")
    if mods is None:
        return set()
    return {child.type for child in mods.children}


def _annotation_names(node) -> list[str]:
    """Return the simple names of all annotations on *node*.

    Handles both marker_annotation (@Override) and annotation (@Schema(...)).
    """
    mods = _child_by_type(node, "modifiers")
    if mods is None:
        return []
    names = []
    for child in mods.children:
        if child.type == "marker_annotation":
            name_node = _child_by_type(child, "identifier")
            if name_node:
                names.append(name_node.text.decode("utf-8", errors="replace"))
        elif child.type == "annotation":
            name_node = _child_by_type(child, "identifier")
            if name_node:
                names.append(name_node.text.decode("utf-8", errors="replace"))
    return names


def _find_class_node(tree: tree_sitter.Tree) -> tuple:
    """Find the primary class or interface declaration node and its name.
    Returns (node, name) or (None, "").
    """
    for child in tree.root_node.children:
        if child.type in ("class_declaration", "interface_declaration"):
            name_node = _child_by_type(child, "identifier")
            name = name_node.text.decode("utf-8", errors="replace") if name_node else ""
            return child, name
    return None, ""


def _get_class_interface_body(node):
    """Get the body node for a class/interface/enum, handling interface_body and enum_body."""
    for body_type in ("class_body", "interface_body", "enum_body"):
        body = _child_by_type(node, body_type)
        if body is not None:
            return body
    return None


def _find_ast_methods(root_node):
    """Yield all method_declaration and constructor_declaration nodes
    with (method_node, containing_class_type, class_modifiers_set).
    """
    for child in root_node.children:
        if child.type in ("class_declaration", "interface_declaration"):
            body = _get_class_interface_body(child)
            if body is None:
                continue
            for member in body.children:
                if member.type in ("method_declaration", "constructor_declaration"):
                    yield member, child.type, _class_modifiers(child)


def _find_ast_fields(root_node):
    """Yield all field_declaration nodes with (field_node, containing_class_type, class_modifiers_set)."""
    for child in root_node.children:
        if child.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            body = _get_class_interface_body(child)
            if body is None:
                continue
            for member in body.children:
                if member.type == "field_declaration":
                    yield member, child.type, _class_modifiers(child)


def _find_formal_parameters(method_node) -> list:
    """Return all formal_parameter nodes for a method, handling nested structure."""
    formal_params = _child_by_type(method_node, "formal_parameters")
    if formal_params:
        return _children_by_type(formal_params, "formal_parameter")
    return []


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
                try:
                    fp_regex = re.compile(program["on_file_pattern"])
                except re.error:
                    continue
                if not fp_regex.search(file_name):
                    continue

            # ── exclude_pattern ──
            if "exclude_pattern" in program:
                if fnmatch.fnmatch(file_name, program["exclude_pattern"]):
                    continue

            # ── must_be_in_root_package ──
            if program.get("must_be_in_root_package"):
                # If pattern is specified, only check files matching the pattern
                if "pattern" in program:
                    if not fnmatch.fnmatch(file_name, program["pattern"]):
                        continue
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

# ── Java AST Scanner ────────────────────────────────────────────


class JavaAstScanner(BaseScanner):
    """AST-based scanner using tree-sitter-java.

    Replaces TextGrepScanner, JavaAnnotationScanner, and JavaReturnTypeScanner.
    Parses Java source into a concrete syntax tree, then matches rules
    against structured AST nodes (class_declaration vs interface_declaration,
    field_declaration modifiers, method_declaration return types, etc.).
    """

    scanner_name = "java-ast"

    def scan(self, file_path: Path, rules: dict) -> list[Finding]:
        findings: list[Finding] = []
        my_rules = self._rules_for_scanner(rules, self.scanner_name)
        if not my_rules:
            return findings

        source_bytes = file_path.read_bytes()
        tree = _parse_java_source(source_bytes)
        class_node, class_name = _find_class_node(tree)
        class_type = class_node.type if class_node else ""
        class_anns = _annotation_names(class_node) if class_node else []

        for code, rule in my_rules.items():
            program = rule["program"]
            level = Level(rule["level"])
            msg = rule["message"]

            # ── Directory filter ──
            if "on_dir" in program:
                if not _matches_on_dir(file_path, program["on_dir"]):
                    continue

            # ── Class annotation filter (also matches class name for backward compat) ──
            if "on_class_annotation" in program:
                on_cls = program["on_class_annotation"]
                # Skip if on_class_annotation is empty (matches all)
                if on_cls and not _any_match(class_anns + [class_name], on_cls):
                    continue

            target = program.get("target", "class")

            if target == "class":
                findings.extend(
                    self._check_class(tree, source_bytes, code, level, msg, program, class_node, class_name, class_type)
                )
            elif target == "method":
                findings.extend(
                    self._check_methods(tree, source_bytes, code, level, msg, program, class_node, class_name, class_type)
                )
            elif target == "field":
                findings.extend(
                    self._check_fields(tree, source_bytes, code, level, msg, program, class_node, class_name, class_type)
                )
            elif target == "all":
                findings.extend(
                    self._check_all(source_bytes, code, level, msg, program, file_path)
                )

        findings.sort(key=lambda f: f.line)
        return findings

    def _check_class(self, tree, source_bytes, code, level, msg, program, class_node, class_name, class_type):
        """Check class-level rules: annotations, modifiers, extends, naming."""
        findings = []

        if program.get("skip_interface") and class_type == "interface_declaration":
            return findings

        line = class_node.start_point[0] + 1 if class_node else 0

        # ── required_class_annotation ──
        if "required_class_annotation" in program:
            needed = program["required_class_annotation"].lstrip("@")
            anns = _annotation_names(class_node) if class_node else []
            if needed not in anns:
                findings.append(Finding(
                    code=code, level=level, line=line,
                    message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": ""}),
                    evidence=f"缺少 @{needed} 注解"
                ))

        # ── required_class_modifier ──
        if "required_class_modifier" in program:
            mod_needed = program["required_class_modifier"]
            mods = _class_modifiers(class_node) if class_node else set()
            if mod_needed not in mods:
                findings.append(Finding(
                    code=code, level=level, line=line,
                    message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": ""}),
                    evidence=f"类缺少 {mod_needed} 修饰符"
                ))

        # ── required_private_constructor ──
        if program.get("required_private_constructor"):
            has_private_ctor = False
            if class_node:
                class_body = _get_class_interface_body(class_node)
                if class_body:
                    for child in class_body.children:
                        if child.type == "constructor_declaration":
                            if _has_modifier(child, "private"):
                                has_private_ctor = True
                                break
            if not has_private_ctor:
                findings.append(Finding(
                    code=code, level=level, line=line,
                    message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": ""}),
                    evidence="类缺少私有构造器"
                ))

        # ── required_field_annotation on class ──
        if "required_field_annotation" in program:
            needed = program["required_field_annotation"].lstrip("@")
            found = False
            for field_node, _, _ in _find_ast_fields(tree.root_node):
                ann_texts = _annotation_names(field_node)
                if needed in ann_texts:
                    found = True
                    break
            if not found:
                findings.append(Finding(
                    code=code, level=level, line=line,
                    message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": ""}),
                    evidence=f"缺少 @{needed} 注解（字段级别）"
                ))

        # ── forbid_pattern on class ──
        if "forbid_pattern" in program:
            pattern = re.compile(program["forbid_pattern"])
            class_text = _node_text(class_node, source_bytes) if class_node else ""
            for lineno_offset, line_text in enumerate(class_text.split("\n")):
                if pattern.search(line_text):
                    findings.append(Finding(
                        code=code, level=level, line=line + lineno_offset,
                        message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": ""}),
                        evidence=line_text.strip()[:120]
                    ))
                    break

        # ── require_pattern on class ──
        if "require_pattern" in program:
            pattern = re.compile(program["require_pattern"])
            class_text = _node_text(class_node, source_bytes) if class_node else ""
            found = any(pattern.search(line) for line in class_text.split("\n"))
            if not found:
                findings.append(Finding(
                    code=code, level=level, line=line,
                    message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": ""}),
                    evidence=f"未找到匹配: {program['require_pattern']}"
                ))

        # ── package_lowercase check ──
        if program.get("check_package_lowercase"):
            for child in tree.root_node.children:
                if child.type == "package_declaration":
                    pkg_text = _node_text(child, source_bytes)
                    if re.search(r'package\s+\S*[A-Z]\S*;', pkg_text):
                        findings.append(Finding(
                            code=code, level=level, line=child.start_point[0] + 1,
                            message=msg,
                            evidence=pkg_text.strip()
                        ))
                    break

        return findings

    def _check_methods(self, tree, source_bytes, code, level, msg, program, class_node, class_name, class_type):
        """Check method-level rules: annotations, return type, parameter count, body patterns."""
        findings = []

        on_method_ann = program.get("on_method_annotation", "")
        match_method_name = program.get("match_method_name", "")

        for method_node, containing_type, _ in _find_ast_methods(tree.root_node):
            method_name_node = _child_by_type(method_node, "identifier")
            method_name = _node_text(method_name_node, source_bytes) if method_name_node else ""
            method_line = method_node.start_point[0] + 1
            method_anns = _annotation_names(method_node)

            # ── Filter by method annotation ──
            if on_method_ann:
                patterns = on_method_ann.split("|")
                if not any(any(pat.strip() in a for a in method_anns) for pat in patterns if pat.strip()):
                    continue

            # ── Filter by method name ──
            if match_method_name:
                patterns = match_method_name.split("|")
                if not any(re.search(pat.strip(), method_name) for pat in patterns if pat.strip()):
                    continue

            # ── required_method_annotation ──
            if "required_method_annotation" in program:
                needed = program["required_method_annotation"].lstrip("@")
                if needed not in method_anns:
                    findings.append(Finding(
                        code=code, level=level, line=method_line,
                        method=method_name,
                        message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": method_name}),
                        evidence=f"方法 {method_name} 缺少 @{needed}"
                    ))

            # ── required_return_pattern ──
            if "required_return_pattern" in program:
                ret_type_node = None
                for child in method_node.children:
                    # Skip modifiers, annotations, type_parameters — look for type_identifier or generic_type
                    if child.type in ("type_identifier", "generic_type", "void_type", "integral_type",
                                       "floating_point_type", "boolean_type", "array_type", "scoped_type_identifier"):
                        ret_type_node = child
                        break
                if ret_type_node:
                    ret_text = _node_text(ret_type_node, source_bytes)
                    pattern = program["required_return_pattern"]
                    # Use regex with negative lookbehind to avoid substring false positives
                    # e.g. "NonResult<Void>" should NOT match pattern "Result<"
                    if not re.search(r'(?<![a-zA-Z])' + re.escape(pattern), ret_text):
                        findings.append(Finding(
                            code=code, level=level, line=method_line,
                            method=method_name,
                            message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": method_name}),
                            evidence=f"返回类型: {ret_text}"
                        ))
                else:
                    findings.append(Finding(
                        code=code, level=level, line=method_line,
                        method=method_name,
                        message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": method_name}),
                        evidence="返回类型: void"
                    ))

            # ── param_count_gte filter ──
            if "param_count_gte" in program:
                param_nodes = _find_formal_parameters(method_node)
                if len(param_nodes) < program["param_count_gte"]:
                    continue

            # ── Check parameters for missing annotation ──
            if "param_missing_annotation" in program:
                needed_anns = program["param_missing_annotation"].lstrip("@").split("|")
                needed_anns = [a.strip() for a in needed_anns]
                match_param_type = program.get("match_param_type", "")
                param_has_ann = program.get("param_has_annotation", "")

                param_nodes = _find_formal_parameters(method_node)
                for pn in param_nodes:
                    param_anns = _annotation_names(pn)

                    # Check if param already has the needed annotation
                    has_needed = any(na in param_anns for na in needed_anns)
                    if has_needed:
                        continue

                    # Filter by param annotation (e.g., only check params with @PathVariable/@RequestParam)
                    if param_has_ann:
                        req_anns = param_has_ann.split("|")
                        if not any(any(ra.strip() in a for a in param_anns) for ra in req_anns if ra.strip()):
                            continue

                    # Filter by param type
                    type_node = None
                    for child in pn.children:
                        if child.type in ("type_identifier", "generic_type", "scoped_type_identifier",
                                           "integral_type", "floating_point_type", "boolean_type", "array_type"):
                            type_node = child
                            break
                    param_type = _node_text(type_node, source_bytes) if type_node else ""

                    if match_param_type and not re.search(match_param_type, param_type):
                        continue

                    param_name_node = _child_by_type(pn, "identifier")
                    param_name = _node_text(param_name_node, source_bytes) if param_name_node else "?"

                    findings.append(Finding(
                        code=code, level=level, line=method_line,
                        method=method_name,
                        message=_safe_format(msg, {
                            "class": class_name, "class_": class_name,
                            "method": method_name, "param": f"{param_type} {param_name}"
                        }),
                        evidence=f"参数缺少注解: {param_type} {param_name}"
                    ))

            # ── Check method body for patterns ──
            body_node = None
            for child in method_node.children:
                if child.type == "block":
                    body_node = child
                    break

            if body_node is None:
                continue

            body_text = _node_text(body_node, source_bytes)

            # forbid_pattern_in_body
            if "forbid_pattern_in_body" in program:
                regex = re.compile(program["forbid_pattern_in_body"])
                for lineno_offset, line_text in enumerate(body_text.split("\n")):
                    if regex.search(line_text):
                        findings.append(Finding(
                            code=code, level=level, line=body_node.start_point[0] + 1 + lineno_offset,
                            method=method_name,
                            message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": method_name}),
                            evidence=line_text.strip()[:120]
                        ))

            # require_pattern_in_body
            if "require_pattern_in_body" in program:
                pattern = re.compile(program["require_pattern_in_body"])
                found = any(pattern.search(line) for line in body_text.split("\n"))
                if not found:
                    findings.append(Finding(
                        code=code, level=level, line=method_line,
                        method=method_name,
                        message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": method_name}),
                        evidence=f"方法体中未找到: {program['require_pattern_in_body']}"
                    ))

            # check @Validated group presence
            if program.get("check_validated_group"):
                for pn in _find_formal_parameters(method_node):
                    param_type_text = ""
                    for child in pn.children:
                        if child.type in ("type_identifier", "generic_type", "scoped_type_identifier",
                                           "array_type", "integral_type", "floating_point_type", "boolean_type"):
                            param_type_text = _node_text(child, source_bytes)
                            break
                    # Only check DTO-type params
                    if not re.search(program.get("match_param_type", "DTO|Request|Command"), param_type_text):
                        continue
                    for child in pn.children:
                        if child.type == "annotation":
                            ann_text = _node_text(child, source_bytes)
                            if "Validated" in ann_text and "(" not in ann_text:
                                findings.append(Finding(
                                    code=code, level=level, line=method_line,
                                    method=method_name,
                                    message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": method_name}),
                                    evidence=f"@Validated 未指定分组: {ann_text}"
                                ))

        return findings

    def _check_fields(self, tree, source_bytes, code, level, msg, program, class_node, class_name, class_type):
        """Check field-level rules: annotations, naming, types."""
        findings = []

        for field_node, containing_type, _ in _find_ast_fields(tree.root_node):
            # identifier may be nested inside variable_declarator
            field_name_node = _child_by_type(field_node, "identifier")
            if not field_name_node:
                var_decl = _child_by_type(field_node, "variable_declarator")
                if var_decl:
                    field_name_node = _child_by_type(var_decl, "identifier")
            if not field_name_node:
                continue
            field_name = _node_text(field_name_node, source_bytes)
            field_line = field_node.start_point[0] + 1
            field_anns = _annotation_names(field_node)
            is_static = _has_modifier(field_node, "static")
            is_final = _has_modifier(field_node, "final")

            # ── Skip static final fields ──
            if program.get("skip_static_final") and is_static and is_final:
                continue

            type_node = None
            for child in field_node.children:
                if child.type in ("type_identifier", "generic_type", "scoped_type_identifier",
                                   "array_type", "integral_type", "floating_point_type", "boolean_type"):
                    type_node = child
                    break
            field_type = _node_text(type_node, source_bytes) if type_node else ""

            # ── Filter by field type ──
            if "on_field_type" in program:
                if not re.search(program["on_field_type"], field_type):
                    continue

            # ── required_field_annotation ──
            if "required_field_annotation" in program:
                needed = program["required_field_annotation"].lstrip("@")
                if needed not in field_anns:
                    findings.append(Finding(
                        code=code, level=level, line=field_line,
                        message=_safe_format(msg, {
                            "class": class_name, "class_": class_name,
                            "field": field_name, "method": ""
                        }),
                        evidence=f"字段 {field_type} {field_name} 缺少 @{needed} 注解"
                    ))

            # ── forbid_field_annotation ──
            if "forbid_field_annotation" in program:
                forbidden = program["forbid_field_annotation"].lstrip("@")
                if forbidden in field_anns:
                    findings.append(Finding(
                        code=code, level=level, line=field_line,
                        message=_safe_format(msg, {
                            "class": class_name, "class_": class_name,
                            "field": field_name, "method": ""
                        }),
                        evidence=f"字段 {field_type} {field_name} 存在禁止的注解 @{forbidden}"
                    ))

            # ── forbid_field_type ──
            if "forbid_field_type" in program:
                if re.search(program["forbid_field_type"], field_type):
                    findings.append(Finding(
                        code=code, level=level, line=field_line,
                        message=_safe_format(msg, {
                            "class": class_name, "class_": class_name,
                            "field": field_name, "method": ""
                        }),
                        evidence=f"字段 {field_type} {field_name}"
                    ))

            # ── Constant naming check ──
            if program.get("check_constant_naming") and is_static and is_final:
                if field_name and re.search(r'^[a-z]', field_name):
                    findings.append(Finding(
                        code=code, level=level, line=field_line,
                        message=_safe_format(msg, {
                            "class": class_name, "class_": class_name,
                            "field": field_name, "method": ""
                        }),
                        evidence=f"常量命名应使用 UPPER_SNAKE: {field_name}"
                    ))

        return findings

    def _check_all(self, source_bytes, code, level, msg, program, file_path):
        """Check across the entire file: text patterns in source lines."""
        findings = []
        full_text = source_bytes.decode("utf-8", errors="replace")
        lines = full_text.split("\n")

        # ── forbid_pattern (whole file) ──
        if "forbid_pattern" in program:
            pattern = re.compile(program["forbid_pattern"])
            for lineno, line_text in enumerate(lines, 1):
                if pattern.search(line_text):
                    findings.append(Finding(
                        code=code, level=level, line=lineno,
                        message=msg,
                        evidence=line_text.strip()[:120]
                    ))

        # ── require_pattern (whole file) ──
        if "require_pattern" in program:
            pattern = re.compile(program["require_pattern"])
            found = any(pattern.search(line) for line in lines)
            if not found:
                findings.append(Finding(
                    code=code, level=level, line=1,
                    message=msg,
                    evidence=f"未找到匹配: {program['require_pattern']}"
                ))

        return findings


SCANNERS: dict[str, BaseScanner] = {
    "java-ast": JavaAstScanner(),
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
