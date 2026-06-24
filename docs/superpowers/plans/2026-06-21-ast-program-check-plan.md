# AST Program Check Refactoring Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all regex-based Java source scanners (text-grep, java-annotation, java-return-type) with a single tree-sitter-java AST scanner that eliminates false positives by accurately distinguishing class/interface/field/modifier nodes.

**Architecture:** Python-only. `JavaAstScanner` uses tree-sitter-java to parse each `.java` file into a concrete syntax tree (CST), then traverses nodes matching rule conditions. Remaining scanners (package-structure, file-naming, config-check) stay as-is — they don't parse Java source code. External interface (models.py, cli.py, reporter.py, config.py) unchanged.

**Tech Stack:** Python 3.12+, tree-sitter, tree-sitter-java, PyYAML, pytest

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `rules/program-checks.yaml` | **Rewrite** | All 35 java-source rules converted to `scanner: java-ast` format; 12 non-source rules stay on old scanners |
| `scanner.py` | **Rewrite** | Delete TextGrepScanner, JavaAnnotationScanner, JavaReturnTypeScanner. Add JavaAstScanner with tree-sitter traversal. Keep PackageStructureScanner, FileNamingScanner, ConfigCheckScanner. |
| `tests/test_scanner.py` | **Rewrite** | Test JavaAstScanner against every rule code, verify 0 false positives on class vs interface, static final fields, comments. |
| `tests/conftest.py` | **Modify** | Update sample rule fixture to new java-ast format |
| `requirements.txt` | **Create** | tree-sitter, tree-sitter-java |
| `models.py` | No change | Finding/ScanResult unchanged |
| `config.py` | No change | Rule loading unchanged |
| `reporter.py` | No change | Report generation unchanged |
| `cli.py` | No change | CLI interface unchanged |
| `code-check-config.yaml` | **Modify** | Change strategy from `strict` to `strict` (unchanged), verify output_dir correct |

---

### Task 1: Install dependencies and verify tree-sitter works

**Files:**
- Create: `agents/reviewer/check_system/requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```
tree-sitter>=0.23.0
tree-sitter-java>=0.23.0
```

- [ ] **Step 2: Install dependencies**

```bash
cd agents/reviewer/check_system && pip install tree-sitter tree-sitter-java
```

Expected: install succeeds without errors.

- [ ] **Step 3: Verify tree-sitter-java parses Java correctly**

```bash
python3 -c "
import tree_sitter_java as tsjava
import tree_sitter
lang = tree_sitter.Language(tsjava.language())
parser = tree_sitter.Parser(lang)
tree = parser.parse(b'class Foo {}')
print(tree.root_node.sexp()[:200])
"
```

Expected: prints AST sexp starting with `(program (class_declaration ...`

- [ ] **Step 4: Commit**

```bash
git add agents/reviewer/check_system/requirements.txt
git commit -m "chore: add tree-sitter + tree-sitter-java dependencies"
```

---

### Task 2: Write the JavaAstScanner core engine

**Files:**
- Modify: `agents/reviewer/check_system/code_check/scanner.py` (add JavaAstScanner, keep existing scanners)

- [ ] **Step 1: Add imports at top of scanner.py**

After the existing imports, add:

```python
import tree_sitter
import tree_sitter_java as tsjava
```

- [ ] **Step 2: Add tree-sitter Language/Parser initialization**

```python
# ── tree-sitter initialization ──────────────────────────────────

_TS_LANGUAGE = tree_sitter.Language(tsjava.language())
_TS_PARSER = tree_sitter.Parser(_TS_LANGUAGE)


def _parse_java_source(source: bytes) -> tree_sitter.Tree:
    """Parse Java source bytes into a tree-sitter concrete syntax tree."""
    return _TS_PARSER.parse(source)
```

- [ ] **Step 3: Add AST node type helpers**

```python
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
    
    Handles both marker_annotation (@Override) and normal_annotation (@Schema(...)).
    """
    mods = _child_by_type(node, "modifiers")
    if mods is None:
        return []
    names = []
    for child in mods.children:
        if child.type == "marker_annotation":
            name_node = _child_by_type(child, "identifier")
            if name_node:
                names.append(_node_text(name_node, b""))
        elif child.type == "annotation":
            # tree-sitter-java uses 'annotation' for @Xxx(...) style
            name_node = _child_by_type(child, "identifier")
            if name_node:
                names.append(_node_text(name_node, b""))
    return names


def _find_class_node(tree: tree_sitter.Tree) -> tuple:
    """Find the primary class or interface declaration node and its name."""
    for child in tree.root_node.children:
        if child.type in ("class_declaration", "interface_declaration"):
            name_node = _child_by_type(child, "identifier")
            name = _node_text(name_node, b"") if name_node else ""
            return child, name
    return None, ""


def _find_methods(root_node):
    """Yield all method_declaration and constructor_declaration nodes."""
    for child in root_node.children:
        if child.type in ("class_declaration", "interface_declaration"):
            for member in child.children:
                if member.type in ("method_declaration", "constructor_declaration"):
                    yield member, child.type, _class_modifiers(child)


def _find_fields(root_node):
    """Yield all field_declaration nodes with their containing class info."""
    for child in root_node.children:
        if child.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            for member in child.children:
                if member.type == "field_declaration":
                    yield member, child.type, _class_modifiers(child)
```

- [ ] **Step 4: Commit**

```bash
git add agents/reviewer/check_system/code_check/scanner.py
git commit -m "feat: add tree-sitter AST helpers to scanner.py"
```

---

### Task 3: Write the JavaAstScanner rule matching engine

**Files:**
- Modify: `agents/reviewer/check_system/code_check/scanner.py` (add JavaAstScanner class)

- [ ] **Step 1: Add JavaAstScanner class skeleton**

```python
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

        # Determine file-level context
        for code, rule in my_rules.items():
            program = rule["program"]
            level = Level(rule["level"])
            msg = rule["message"]

            # ── Directory filter ──
            if "on_dir" in program:
                if not _matches_on_dir(file_path, program["on_dir"]):
                    continue

            # ── Class annotation filter ──
            if "on_class_annotation" in program:
                if not _any_match(class_anns, program["on_class_annotation"]):
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
                    self._check_all(tree, source_bytes, code, level, msg, program, file_path)
                )

        findings.sort(key=lambda f: f.line)
        return findings
```

- [ ] **Step 2: Implement `_check_class` — class-level checks**

```python
    def _check_class(self, tree, source_bytes, code, level, msg, program, class_node, class_name, class_type):
        """Check class-level rules: annotations, modifiers, extends, naming."""
        findings = []
        
        # ── skip_interface: skip interface_declaration nodes ──
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
                for child in class_node.children:
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
            for field_node, _, _ in _find_fields(tree.root_node):
                for ann_name in _annotation_names(field_node):
                    if ann_name == needed:
                        found = True
                        break
                if found:
                    break
            if not found:
                findings.append(Finding(
                    code=code, level=level, line=line,
                    message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": ""}),
                    evidence=f"缺少 @{needed} 注解（字段级别）"
                ))

        # ── forbid annotation on class ──
        if "forbid_annotation" in program:
            forbidden = program["forbid_annotation"].lstrip("@")
            anns = _annotation_names(class_node) if class_node else []
            if forbidden in anns:
                findings.append(Finding(
                    code=code, level=level, line=line,
                    message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": ""}),
                    evidence=f"存在禁止的注解 @{forbidden}"
                ))

        # ── forbid pattern on class level (e.g. package lowercase) ──
        if "forbid_pattern" in program:
            pattern = re.compile(program["forbid_pattern"])
            # Search in the class text
            class_text = _node_text(class_node, source_bytes) if class_node else ""
            for line_text in class_text.split("\n"):
                if pattern.search(line_text):
                    findings.append(Finding(
                        code=code, level=level, line=line,
                        message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": ""}),
                        evidence=line_text.strip()[:120]
                    ))
                    break

        # ── require pattern on class ──
        if "require_pattern" in program:
            pattern = re.compile(program["require_pattern"])
            class_text = _node_text(class_node, source_bytes) if class_node else ""
            found = False
            for line_text in class_text.split("\n"):
                if pattern.search(line_text):
                    found = True
                    break
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
```

- [ ] **Step 3: Implement `_check_methods` — method-level checks**

```python
    def _check_methods(self, tree, source_bytes, code, level, msg, program, class_node, class_name, class_type):
        """Check method-level rules: annotations, return type, parameter count, body patterns."""
        findings = []

        on_method_ann = program.get("on_method_annotation", "")
        skip_method_ann = program.get("skip_method_annotation", "")
        match_method_name = program.get("match_method_name", "")

        for method_node, containing_type, _ in _find_methods(tree.root_node):
            method_name_node = _child_by_type(method_node, "identifier")
            method_name = _node_text(method_name_node, source_bytes) if method_name_node else ""
            method_line = method_node.start_point[0] + 1
            method_anns = _annotation_names(method_node)

            # ── Filter by method annotation ──
            if on_method_ann:
                patterns = on_method_ann.split("|")
                if not any(any(pat.strip() == a for a in method_anns) for pat in patterns):
                    continue

            # ── Skip by method annotation ──
            if skip_method_ann:
                patterns = skip_method_ann.split("|")
                if any(any(pat.strip() == a for a in method_anns) for pat in patterns):
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
                ret_type_node = _child_by_type(method_node, "type")
                if ret_type_node:
                    ret_text = _node_text(ret_type_node, source_bytes)
                    if program["required_return_pattern"] not in ret_text:
                        findings.append(Finding(
                            code=code, level=level, line=method_line,
                            method=method_name,
                            message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": method_name}),
                            evidence=f"返回类型: {ret_text}"
                        ))
                else:
                    # void methods have no type child
                    if program["required_return_pattern"] != "void":
                        findings.append(Finding(
                            code=code, level=level, line=method_line,
                            method=method_name,
                            message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": method_name}),
                            evidence="返回类型: void"
                        ))

            # ── param_count_gte ──
            if "param_count_gte" in program:
                param_nodes = _children_by_type(method_node, "formal_parameter")
                if len(param_nodes) >= program["param_count_gte"]:
                    min_count = program["param_count_gte"]
                    findings.append(Finding(
                        code=code, level=level, line=method_line,
                        method=method_name,
                        message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": method_name}),
                        evidence=f"参数数量 {len(param_nodes)} >= {min_count}"
                    ))

            # ── Check parameters for missing annotation ──
            if "param_missing_annotation" in program:
                needed = program["param_missing_annotation"].lstrip("@")
                match_param_type = program.get("match_param_type", "")
                param_nodes = _children_by_type(method_node, "formal_parameter")
                for pn in param_nodes:
                    param_anns = _annotation_names(pn)
                    if needed in [a.lstrip("@") for a in param_anns]:
                        continue
                    # Check if param type matches
                    type_node = _child_by_type(pn, "type")
                    if type_node and match_param_type:
                        type_text = _node_text(type_node, source_bytes)
                        if not re.search(match_param_type, type_text):
                            continue
                    # Also check for @Param on Mapper methods
                    param_name_node = _child_by_type(pn, "identifier")
                    param_name = _node_text(param_name_node, source_bytes) if param_name_node else "?"
                    findings.append(Finding(
                        code=code, level=level, line=method_line,
                        method=method_name,
                        message=_safe_format(msg, {
                            "class": class_name, "class_": class_name,
                            "method": method_name, "param": f"type {param_name}"
                        }),
                        evidence=f"参数缺少 @{needed}: {_node_text(pn, source_bytes)[:80]}"
                    ))

            # ── Check method body for patterns ──
            body_node = _child_by_type(method_node, "block")
            if body_node is None:
                continue

            body_text = _node_text(body_node, source_bytes)

            # forbid_pattern_in_body
            if "forbid_pattern_in_body" in program:
                patterns = program["forbid_pattern_in_body"].split("|")
                for pat in patterns:
                    pat = pat.strip()
                    if not pat:
                        continue
                    regex = re.compile(pat)
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
                for pn in _children_by_type(method_node, "formal_parameter"):
                    for ann_child in pn.children:
                        if ann_child.type in ("annotation", "marker_annotation"):
                            ann_text = _node_text(ann_child, source_bytes)
                            if "Validated" in ann_text:
                                if "(" not in ann_text:
                                    findings.append(Finding(
                                        code=code, level=level, line=method_line,
                                        method=method_name,
                                        message=_safe_format(msg, {"class": class_name, "class_": class_name, "method": method_name}),
                                        evidence=f"@Validated 未指定分组: {ann_text}"
                                    ))

        return findings
```

- [ ] **Step 4: Implement `_check_fields` and `_check_all`**

```python
    def _check_fields(self, tree, source_bytes, code, level, msg, program, class_node, class_name, class_type):
        """Check field-level rules: annotations, naming, types."""
        findings = []

        for field_node, containing_type, _ in _find_fields(tree.root_node):
            field_name_node = _child_by_type(field_node, "identifier")
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

            type_node = _child_by_type(field_node, "type")
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
                if re.search(r'[a-z]', field_name[0]) if field_name else False:
                    findings.append(Finding(
                        code=code, level=level, line=field_line,
                        message=_safe_format(msg, {
                            "class": class_name, "class_": class_name,
                            "field": field_name, "method": ""
                        }),
                        evidence=f"常量命名应使用 UPPER_SNAKE: {field_name}"
                    ))

        return findings

    def _check_all(self, tree, source_bytes, code, level, msg, program, file_path):
        """Check across the entire file: text patterns, method calls, object creations."""
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
```

- [ ] **Step 5: Commit**

```bash
git add agents/reviewer/check_system/code_check/scanner.py
git commit -m "feat: add JavaAstScanner with tree-sitter AST matching engine"
```

---

### Task 4: Rewrite program-checks.yaml to java-ast format

**Files:**
- Rewrite: `agents/reviewer/check_system/rules/program-checks.yaml`

This is the core migration: all 35 java-source rules converted from text-grep/java-annotation/java-return-type to java-ast format.

The 12 non-java-source rules (package-structure, file-naming, config-check) remain unchanged.

- [ ] **Step 1: Write the full new program-checks.yaml**

```yaml
# 程序检查规则 —— 基于 tree-sitter-java AST 解析
# scanner: java-ast 的规则通过结构化 AST 节点匹配，消除正则误报
# scanner: package-structure / file-naming / config-check 保持不变

# ═══════════════════════════════════════════════════════════════
# Structure Review / 结构审查
# ═══════════════════════════════════════════════════════════════

BE-ST-01:
  description: "包结构是否含 controller/service/impl/mapper/entity/dto/vo 标准子包"
  level: P1
  program:
    scanner: package-structure
    required_dirs: "controller|service|mapper|entity|dto|vo"
    required_service_impl: true
  message: "包结构不符合规范，缺少标准子包"

BE-ST-02:
  description: "service/ 下是否有 impl/ 子包"
  level: P1
  program:
    scanner: package-structure
    check_impl_subdir: true
  message: "缺少 service/impl 子包"

BE-ST-03:
  description: "启动类是否放在根包下"
  level: P2
  program:
    scanner: file-naming
    pattern: "*Application.java"
    must_be_in_root_package: true
  message: "启动类应放在根包下"

BE-ST-14:
  description: "Controller 类名是否以 Controller 结尾"
  level: P2
  program:
    scanner: file-naming
    on_dir: "controller"
    pattern: "*Controller.java"
  message: "不符合 Controller 命名规范"

BE-ST-15:
  description: "Service 接口是否以 Service 结尾"
  level: P2
  program:
    scanner: file-naming
    on_dir: "service"
    pattern: "*Service.java"
    exclude_pattern: "*Impl.java"
  message: "不符合 Service 接口命名规范"

BE-ST-16:
  description: "ServiceImpl 类名是否以 ServiceImpl 结尾"
  level: P2
  program:
    scanner: file-naming
    on_dir: "impl"
    pattern: "*ServiceImpl.java"
  message: "不符合 ServiceImpl 命名规范"

BE-ST-17:
  description: "Mapper 类名是否以 Mapper 结尾"
  level: P2
  program:
    scanner: file-naming
    on_dir: "mapper"
    pattern: "*Mapper.java"
  message: "不符合 Mapper 命名规范"

BE-ST-18:
  description: "Entity 类名是否以 Entity 结尾"
  level: P2
  program:
    scanner: file-naming
    on_dir: "entity"
    pattern: "*Entity.java"
  message: "不符合 Entity 命名规范"

BE-ST-19:
  description: "DTO 命名是否为 {业务名}{动作}DTO"
  level: P2
  program:
    scanner: file-naming
    on_dir: "dto"
    pattern: "*DTO.java"
  message: "不符合 DTO 命名规范"

BE-ST-20:
  description: "包名是否全部小写"
  level: P2
  program:
    scanner: java-ast
    target: class
    check_package_lowercase: true
  message: "包名应全部小写"

BE-ST-21:
  description: "常量命名是否用 UPPER_SNAKE 风格"
  level: P2
  program:
    scanner: java-ast
    target: field
    check_constant_naming: true
  message: "常量命名应使用 UPPER_SNAKE 风格"

BE-ST-22:
  description: "是否使用 @Autowired 字段注入"
  level: P1
  program:
    scanner: java-ast
    target: field
    forbid_field_annotation: "@Autowired"
  message: "{class} 使用了 @Autowired 字段注入，应改用构造注入"

BE-ST-23:
  description: "是否使用 @RequiredArgsConstructor + private final 构造注入"
  level: P1
  program:
    scanner: java-ast
    target: class
    on_class_annotation: "Service|ServiceImpl|Controller|RestController|Component"
    skip_interface: true
    required_class_annotation: "@RequiredArgsConstructor"
  message: "{class} 应使用 @RequiredArgsConstructor + private final 构造注入"

# ═══════════════════════════════════════════════════════════════
# Quality Review / 质量审查
# ═══════════════════════════════════════════════════════════════

# ── JSR 303 参数校验 ──

BE-QL-29:
  description: "Controller 方法的 DTO 参数是否加了 @Validated 或 @Valid"
  level: P1
  program:
    scanner: java-ast
    target: method
    on_class_annotation: "RestController|Controller"
    match_param_type: "DTO|Request|Command|Form"
    param_missing_annotation: "@Valid|@Validated"
  message: "{method} 缺少 @Validated/@Valid 注解 DTO 参数"

BE-QL-30:
  description: "@Validated 是否指定了分组（Create/Update）"
  level: P2
  program:
    scanner: java-ast
    target: method
    on_class_annotation: "RestController|Controller"
    match_param_type: "DTO|Request|Command"
    check_validated_group: true
  message: "{method} 的 @Validated 未指定分组"

# ── Result 返回体 ──

BE-QL-13:
  description: "Controller 返回值是否用 Result<T> 包裹"
  level: P1
  program:
    scanner: java-ast
    target: method
    on_class_annotation: "RestController|Controller"
    required_return_pattern: "Result<"
  message: "{method} 返回值未使用 Result<T> 包裹"

BE-QL-15:
  description: "新增/修改/删除是否用 Result.success() 无 data 返回"
  level: P2
  program:
    scanner: java-ast
    target: method
    on_class_annotation: "RestController|Controller"
    on_method_annotation: "PostMapping|PutMapping|DeleteMapping"
    require_pattern_in_body: "Result\\.success\\(\\s*\\)"
  message: "{method} 应使用 Result.success() 无 data 返回"

BE-QL-16:
  description: "分页查询是否返回 Result<PageResult<T>>"
  level: P2
  program:
    scanner: java-ast
    target: method
    on_class_annotation: "RestController|Controller"
    match_method_name: "page|list"
    required_return_pattern: "PageResult<"
  message: "{method} 分页查询应返回 Result<PageResult<T>>"

BE-QL-17:
  description: "分页 DTO 是否继承 PageQueryDTO"
  level: P2
  program:
    scanner: java-ast
    target: class
    on_dir: "dto"
    on_class_annotation: ""  # match all in dto dir
    require_pattern: "extends\\s+\\w*PageQueryDTO|extends\\s+\\w*PageRequest"
  message: "分页 DTO 应继承 PageQueryDTO"

BE-QL-18:
  description: "成功消息是否固定为 ok"
  level: P2
  program:
    scanner: java-ast
    target: all
    forbid_pattern: 'Result\\.success\\(\\s*"(?!ok")[^"]*"'
  message: "成功消息应为 'ok'，不应返回自定义文本"

# ── 日志规范 ──

BE-QL-07:
  description: "是否使用 System.out.println 或 System.err.println"
  level: P1
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "System\\.(out|err)\\.print"
  message: "使用 System.out/err，应使用 @Slf4j log"

BE-QL-08:
  description: "业务类是否加了 @Slf4j"
  level: P2
  program:
    scanner: java-ast
    target: class
    on_class_annotation: "Service|ServiceImpl|Controller|RestController|Component"
    skip_interface: true
    required_class_annotation: "@Slf4j"
  message: "{class} 缺少 @Slf4j 注解"

BE-QL-09:
  description: "日志中是否打印了密码、手机号、Token、身份证等敏感信息"
  level: P0
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "log\\.(info|warn|debug|error|trace)\\s*\\(.*(password|passwd|token|phone|mobile|idCard|idNumber|secret|apiKey)"
  message: "日志中包含敏感信息"

BE-QL-10:
  description: "Controller 方法内是否手写了请求日志"
  level: P2
  program:
    scanner: java-ast
    target: method
    on_class_annotation: "RestController|Controller"
    forbid_pattern_in_body: "log\\.info.*(request|请求)"
  message: "手写了请求日志，应使用 Filter 统一拦截"

# ── 代码风格 ──

BE-QL-33:
  description: "是否使用了禁止的 Lombok 注解"
  level: P1
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "@SneakyThrows|@Cleanup|@Synchronized"
  message: "使用了禁止的 Lombok 注解"

BE-QL-38:
  description: "常量类是否 final + 私有构造"
  level: P2
  program:
    scanner: java-ast
    target: class
    on_class_annotation: ".*(Constant|Constants|Code|Codes)"
    required_class_modifier: "final"
    required_private_constructor: true
  message: "常量类应声明为 final + 私有构造"

BE-QL-40:
  description: "是否手动声明 Logger 字段而未用 @Slf4j"
  level: P2
  program:
    scanner: java-ast
    target: field
    forbid_field_type: "Logger"
  message: "手动声明 Logger，应使用 @Slf4j"

BE-QL-42:
  description: "是否调用了 System.gc() / Runtime.gc()"
  level: P2
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "(System|Runtime)\\.gc\\(\\)"
  message: "调用了 System.gc()，不应手动触发 GC"

BE-QL-43:
  description: "是否使用了 finalize() 方法"
  level: P2
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "protected\\s+void\\s+finalize\\(\\)"
  message: "使用了 finalize()，JDK 已废弃"

# ── 数据库规范 ──

BE-QL-27:
  description: "Entity 是否加了 @TableLogic 注解"
  level: P1
  program:
    scanner: java-ast
    target: class
    on_class_annotation: "*Entity"
    required_field_annotation: "@TableLogic"
  message: "{class} 缺少 @TableLogic 注解"

# ── Mapper 专项 ──

BE-QL-44:
  description: "Mapper 方法参数是否缺 @Param 注解"
  level: P1
  program:
    scanner: java-ast
    target: method
    on_class_annotation: "*Mapper"
    param_missing_annotation: "@Param"
    param_count_gte: 2
  message: "{method} 缺少 @Param 注解（多参数 Mapper 方法）"

BE-QL-45:
  description: "是否用字符串字段名构建 MyBatis-Plus 条件"
  level: P1
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "new\\s+QueryWrapper|new\\s+UpdateWrapper"
  message: "使用字符串字段名构建条件，应使用 LambdaQueryWrapper/LambdaUpdateWrapper"

# ═══════════════════════════════════════════════════════════════
# Infrastructure Review / 基础设施审查
# ═══════════════════════════════════════════════════════════════

# ── Swagger ──

BE-IN-01:
  description: "Controller 类是否加了 @Tag(name = 模块名)"
  level: P2
  program:
    scanner: java-ast
    target: class
    on_class_annotation: "RestController|Controller"
    required_class_annotation: "@Tag"
  message: "{class} 缺少 @Tag 注解"

BE-IN-02:
  description: "Controller 方法是否加了 @Operation(summary = 描述)"
  level: P2
  program:
    scanner: java-ast
    target: method
    on_class_annotation: "RestController|Controller"
    required_method_annotation: "@Operation"
  message: "{method} 缺少 @Operation 注解"

BE-IN-03:
  description: "GET 的 @PathVariable/@RequestParam 是否加了 @Parameter"
  level: P2
  program:
    scanner: java-ast
    target: method
    on_method_annotation: "GetMapping"
    match_param_type: ".*"
    param_missing_annotation: "@Parameter"
    param_has_annotation: "PathVariable|RequestParam"
  message: "{method} 的 {param} 缺少 @Parameter 注解"

BE-IN-04:
  description: "DTO 字段是否加了 @Schema(description = ...)"
  level: P2
  program:
    scanner: java-ast
    target: field
    on_dir: "dto"
    skip_static_final: true
    required_field_annotation: "@Schema"
  message: "{class}.{field} 缺少 @Schema 注解"

BE-IN-05:
  description: "VO 字段是否加了 @Schema(description = ...)"
  level: P2
  program:
    scanner: java-ast
    target: field
    on_dir: "vo"
    skip_static_final: true
    required_field_annotation: "@Schema"
  message: "{class}.{field} 缺少 @Schema 注解"

BE-IN-07:
  description: "生产环境 knife4j.enable 是否为 false"
  level: P1
  program:
    scanner: config-check
    file_pattern: "application-prod*.yml|application-prod*.yaml"
    pattern: "knife4j\\.enable\\s*:\\s*true"
    must_not_match: true
  message: "生产环境 knife4j.enable 应为 false"

# ── 配置管理 ──

BE-IN-08:
  description: "yml 文件中是否包含明文密码/密钥"
  level: P0
  program:
    scanner: config-check
    file_pattern: "*.yml|*.yaml|*.properties"
    pattern: "(password|passwd|secret|api-key|apikey)\\s*[:=]\\s*(?!\\$\\{)[^\\s]+"
    exclude_file: "code-check-config.yaml"
  message: "配置文件包含明文敏感信息"

BE-IN-09:
  description: "数据库密码/Redis 密码是否通过环境变量 ${VAR:} 占位"
  level: P1
  program:
    scanner: config-check
    file_pattern: "application*.yml|application*.yaml"
    pattern: "(password|passwd)\\s*:\\s*(?!\\$\\{)[^\\s#]+"
    must_not_match: true
  message: "密码应通过环境变量占位符注入 ${VAR:}"

BE-IN-10:
  description: "是否用 @Value 散落配置（应使用 @ConfigurationProperties）"
  level: P1
  program:
    scanner: java-ast
    target: all
    forbid_pattern: '@Value\\(\\"\\$\\{'
  message: "应使用 @ConfigurationProperties 替代 @Value 散落"

BE-IN-15:
  description: "是否直接使用 RedisTemplate（应使用 RedisUtil 封装）"
  level: P1
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "RedisTemplate"
  message: "应使用 RedisUtil 封装，不直接使用 RedisTemplate"

# ── 文件上传安全 ──

BE-IN-30:
  description: "文件名是否由服务端生成（未使用用户原始文件名）"
  level: P0
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "(getOriginalFilename|originalFilename|fileName\\.getName)"
  message: "使用了用户原始文件名做存储路径，存在路径遍历风险"

BE-IN-31:
  description: "上传文件是否存放到 static/ 或 resources/ 目录"
  level: P1
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "(static/|resources/).*upload|upload.*(static/|resources/)"
  message: "文件存储路径不应在 static/resources 下，可被直接 URL 访问"

# ═══════════════════════════════════════════════════════════════
# Auth Review / 认证审查
# ═══════════════════════════════════════════════════════════════

BE-AU-02:
  description: "多端场景下是否直接使用 StpUtil 而未通过 StpKit 门面"
  level: P1
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "import\\s+cn\\.dev33\\.satoken\\.StpUtil|StpUtil\\."
  message: "直接使用了 StpUtil，多端场景应使用 StpKit 门面"

BE-AU-05:
  description: "Sa-Token 配置类是否命名为 SaTokenCustomConfig"
  level: P0
  program:
    scanner: file-naming
    pattern: "*SaToken*Config*.java"
    exclude_pattern: "SaTokenCustomConfig.java"
    must_not_match: true
  message: "配置类应命名为 SaTokenCustomConfig，避免与库类 SaTokenConfig 冲突"

BE-AU-07:
  description: "登录密码是否使用 BCryptPasswordEncoder 加密"
  level: P0
  program:
    scanner: java-ast
    target: class
    on_class_annotation: "Service|ServiceImpl"
    require_pattern: "BCryptPasswordEncoder"
  message: "密码未使用 BCryptPasswordEncoder 加密"

BE-AU-15:
  description: "权限注解是否放在 Controller 层而非 Service 层"
  level: P1
  program:
    scanner: java-ast
    target: class
    on_dir: "service"
    forbid_pattern: "@SaCheck(Permission|Role|Login)"
  message: "权限注解应放在 Controller 层，Service 层不应有权限注解"

BE-AU-18:
  description: "权限码是否定义在常量类中，未硬编码字符串"
  level: P1
  program:
    scanner: java-ast
    target: all
    forbid_pattern: '@SaCheckPermission\\("'
  message: "硬编码权限码字符串，应使用 PermissionCodes 常量"

BE-AU-21:
  description: "Service 是否直接注入 HttpServletRequest"
  level: P0
  program:
    scanner: java-ast
    target: all
    on_dir: "service"
    forbid_pattern: "HttpServletRequest"
  message: "Service 直接注入了 HttpServletRequest"

BE-AU-31:
  description: "密码是否明文存储"
  level: P0
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "setPassword\\(\"(?!.*encode|.*BCrypt|.*\\$2a\\$)[^\"]+\"\\)|password\\s*=\\s*\"(?!.*encode|.*BCrypt|.*\\$2a\\$)[^\"]+\""
  message: "密码明文存储"

BE-AU-32:
  description: "Token/密钥是否硬编码在代码中"
  level: P0
  program:
    scanner: java-ast
    target: all
    forbid_pattern: "(secret|apiKey|api-key|accessKey)\\s*=\\s*\"[^\"]{8,}\""
  message: "Token/密钥硬编码在代码中"
```

- [ ] **Step 2: Commit**

```bash
git add agents/reviewer/check_system/rules/program-checks.yaml
git commit -m "feat: rewrite program-checks.yaml to java-ast scanner format"
```

---

### Task 5: Remove old scanners from scanner.py

**Files:**
- Modify: `agents/reviewer/check_system/code_check/scanner.py`

- [ ] **Step 1: Delete TextGrepScanner, JavaAnnotationScanner, JavaReturnTypeScanner classes**

Delete the entire class definitions and their helper methods (_scan_methods_by_annotation, etc.).

- [ ] **Step 2: Update SCANNERS registry**

```python
SCANNERS: dict[str, BaseScanner] = {
    "java-ast": JavaAstScanner(),
    "package-structure": PackageStructureScanner(),
    "file-naming": FileNamingScanner(),
    "config-check": ConfigCheckScanner(),
}
```

- [ ] **Step 3: Verify no broken imports in `scan_single_file`**

The `scan_single_file` function currently calls `scanner.scan(file_path, rules)` for each scanner in SCANNERS — this should work without changes since `BaseScanner.scan()` signature is identical.

- [ ] **Step 4: Run quick smoke test**

```bash
cd agents/reviewer/check_system && python3 -c "
from code_check.scanner import JavaAstScanner
print('JavaAstScanner imported successfully')
"
```

Expected: prints success message.

- [ ] **Step 5: Commit**

```bash
git add agents/reviewer/check_system/code_check/scanner.py
git commit -m "refactor: remove old regex scanners, keep only AST + structure scanners"
```

---

### Task 6: Update conftest.py with new rule format

**Files:**
- Modify: `agents/reviewer/check_system/tests/conftest.py`

- [ ] **Step 1: Update sample rule in tmp_project fixture**

Replace the old java-annotation rule with a java-ast rule:

```python
(rules_dir / "program-checks.yaml").write_text("""
BE-QL-29:
  description: "Controller DTO 参数缺少 @Validated"
  level: P1
  program:
    scanner: java-ast
    target: method
    on_class_annotation: "RestController|Controller"
    match_param_type: "DTO|Request|Command"
    param_missing_annotation: "@Valid|@Validated"
  message: "{method} 缺少 @Validated/@Valid 注解 DTO 参数"
""")
```

- [ ] **Step 2: Commit**

```bash
git add agents/reviewer/check_system/tests/conftest.py
git commit -m "test: update conftest rule format to java-ast"
```

---

### Task 7: Rewrite test_scanner.py for JavaAstScanner

**Files:**
- Rewrite: `agents/reviewer/check_system/tests/test_scanner.py`

Write tests verifying JavaAstScanner correctly handles each rule type and eliminates the key false positives.

- [ ] **Step 1: Write test structure with key Java source samples**

```python
"""Tests for JavaAstScanner and retained scanners."""

import pytest
from pathlib import Path
from code_check.scanner import (
    scan_files,
    scan_single_file,
    JavaAstScanner,
    PackageStructureScanner,
    FileNamingScanner,
    ConfigCheckScanner,
    classify_files,
    should_exclude,
    is_blocked,
)
from code_check.models import Level, BlockingStrategy, Finding, ScanResult


# ── Test Java Sources ──

JAVA_CONTROLLER_WITH_VALID = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import com.example.common.Result;
import jakarta.validation.Valid;
import com.example.dto.CreateUserDTO;

@RestController
@RequestMapping("/users")
@Tag(name = "用户管理")
@Slf4j
@RequiredArgsConstructor
public class UserController {

    @PostMapping
    @Operation(summary = "创建用户")
    public Result<Void> createUser(@Valid CreateUserDTO dto) {
        return Result.success();
    }
}
"""

JAVA_CONTROLLER_WITH_AUTOWIRED = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import org.springframework.beans.factory.annotation.Autowired;
import com.example.service.UserService;

@RestController
@RequestMapping("/users")
public class UserController {

    @Autowired
    private UserService userService;
}
"""

JAVA_INTERFACE_SERVICE = """
package com.example.service;

public interface UserService {
    UserVO getUser(Long id);
}
"""

JAVA_SERVICE_WITH_SLF4J = """
package com.example.service.impl;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

@Slf4j
@Service
@RequiredArgsConstructor
public class UserServiceImpl {
    public void doSomething() {
        log.info("processing");
    }
}
"""

JAVA_DTO_WITH_SCHEMA = """
package com.example.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;

public class RegisterDTO {

    @Schema(description = "用户名")
    @NotBlank
    private String username;

    @Schema(description = "密码")
    @NotBlank
    private String password;

    private static final int USERNAME_MIN_LENGTH = 3;
}
"""

JAVA_WITH_SYSOUT = """
package com.example;

public class DebugService {
    public void debug() {
        System.out.println("debug info");
        System.err.println("error info");
    }
}
"""

JAVA_NO_RESULT_RETURN = """
package com.example.controller;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/users")
public class UserController {

    @GetMapping("/{id}")
    public UserVO getUser(@PathVariable Long id) {
        return new UserVO();
    }
}
"""

JAVA_ENTITY_WITH_TABLE_LOGIC = """
package com.example.entity;

import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

@Data
@TableName("user")
public class UserEntity {
    private Long id;
    private String username;

    @TableLogic
    private Integer deleted;
}
"""

JAVA_MAPPER_MULTI_PARAM = """
package com.example.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.entity.UserEntity;
import org.apache.ibatis.annotations.Param;

public interface UserMapper extends BaseMapper<UserEntity> {
    UserEntity selectByUsernameAndStatus(
        @Param("username") String username,
        @Param("status") Integer status
    );
}
```

- [ ] **Step 2: Write test class for class-level checks**

```python
class TestJavaAstClassChecks:

    def test_autowired_field_detected(self, tmp_path):
        """BE-ST-22: @Autowired field injection should be detected."""
        rules = {
            "BE-ST-22": {
                "level": "P1",
                "message": "{class} 使用了 @Autowired",
                "program": {
                    "scanner": "java-ast",
                    "target": "field",
                    "forbid_field_annotation": "@Autowired"
                }
            }
        }
        file_path = tmp_path / "UserController.java"
        file_path.write_text(JAVA_CONTROLLER_WITH_AUTOWIRED)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 1
        assert findings[0].code == "BE-ST-22"

    def test_required_args_constructor_on_class_not_interface(self, tmp_path):
        """BE-ST-23: @RequiredArgsConstructor check skips interface."""
        rules = {
            "BE-ST-23": {
                "level": "P1",
                "message": "{class} 应使用 @RequiredArgsConstructor",
                "program": {
                    "scanner": "java-ast",
                    "target": "class",
                    "on_class_annotation": "Service|ServiceImpl",
                    "skip_interface": True,
                    "required_class_annotation": "@RequiredArgsConstructor"
                }
            }
        }
        # Interface should NOT be flagged
        iface_path = tmp_path / "UserService.java"
        iface_path.write_text(JAVA_INTERFACE_SERVICE)
        scanner = JavaAstScanner()
        findings = scanner.scan(iface_path, rules)
        assert len(findings) == 0, f"Interface should not be flagged, got {findings}"

    def test_slf4j_on_business_class(self, tmp_path):
        """BE-QL-08: @Slf4j should be present on Service class."""
        rules = {
            "BE-QL-08": {
                "level": "P2",
                "message": "{class} 缺少 @Slf4j",
                "program": {
                    "scanner": "java-ast",
                    "target": "class",
                    "on_class_annotation": "Service|ServiceImpl",
                    "skip_interface": True,
                    "required_class_annotation": "@Slf4j"
                }
            }
        }
        file_path = tmp_path / "UserServiceImpl.java"
        file_path.write_text(JAVA_SERVICE_WITH_SLF4J)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 0
```

- [ ] **Step 3: Write test class for field-level checks**

```python
class TestJavaAstFieldChecks:

    def test_schema_on_dto_fields_skips_static_final(self, tmp_path):
        """BE-IN-04: @Schema check on DTO fields skips static final constants."""
        rules = {
            "BE-IN-04": {
                "level": "P2",
                "message": "{class}.{field} 缺少 @Schema",
                "program": {
                    "scanner": "java-ast",
                    "target": "field",
                    "on_dir": "dto",
                    "skip_static_final": True,
                    "required_field_annotation": "@Schema"
                }
            }
        }
        dto_dir = tmp_path / "dto"
        dto_dir.mkdir()
        file_path = dto_dir / "RegisterDTO.java"
        file_path.write_text(JAVA_DTO_WITH_SCHEMA)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        # RegisterDTO has @Schema on username & password, but USERNAME_MIN_LENGTH is static final
        # and should be skipped
        assert len(findings) == 0, f"Expected 0 findings (all fields have @Schema or are static final), got {findings}"

    def test_constant_naming_upper_snake(self, tmp_path):
        """BE-ST-21: Constant naming should use UPPER_SNAKE."""
        rules = {
            "BE-ST-21": {
                "level": "P2",
                "message": "常量命名应使用 UPPER_SNAKE 风格",
                "program": {
                    "scanner": "java-ast",
                    "target": "field",
                    "check_constant_naming": True
                }
            }
        }
        java_with_bad_constant = """
        public class Config {
            private static final int minValue = 10;
        }
        """
        file_path = tmp_path / "Config.java"
        file_path.write_text(java_with_bad_constant)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 1
        assert "minValue" in findings[0].evidence

    def test_manual_logger_field_forbidden(self, tmp_path):
        """BE-QL-40: Manual Logger field declaration should be flagged."""
        rules = {
            "BE-QL-40": {
                "level": "P2",
                "message": "手动声明 Logger",
                "program": {
                    "scanner": "java-ast",
                    "target": "field",
                    "forbid_field_type": "Logger"
                }
            }
        }
        java_with_logger = """
        import org.slf4j.Logger;
        import org.slf4j.LoggerFactory;
        public class OldService {
            private static final Logger log = LoggerFactory.getLogger(OldService.class);
        }
        """
        file_path = tmp_path / "OldService.java"
        file_path.write_text(java_with_logger)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 1
```

- [ ] **Step 4: Write test class for method-level checks**

```python
class TestJavaAstMethodChecks:

    def test_system_out_detected(self, tmp_path):
        """BE-QL-07: System.out.println should be detected."""
        rules = {
            "BE-QL-07": {
                "level": "P1",
                "message": "使用 System.out/err",
                "program": {
                    "scanner": "java-ast",
                    "target": "all",
                    "forbid_pattern": "System\\.(out|err)\\.print"
                }
            }
        }
        file_path = tmp_path / "DebugService.java"
        file_path.write_text(JAVA_WITH_SYSOUT)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) >= 1

    def test_result_return_type_required(self, tmp_path):
        """BE-QL-13: Controller methods must return Result<T>."""
        rules = {
            "BE-QL-13": {
                "level": "P1",
                "message": "{method} 返回值未使用 Result<T> 包裹",
                "program": {
                    "scanner": "java-ast",
                    "target": "method",
                    "on_class_annotation": "RestController|Controller",
                    "required_return_pattern": "Result<"
                }
            }
        }
        file_path = tmp_path / "UserController.java"
        file_path.write_text(JAVA_NO_RESULT_RETURN)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 1
        assert findings[0].method == "getUser"

    def test_result_success_no_data_for_post(self, tmp_path):
        """BE-QL-15: PostMapping should use Result.success() with no data."""
        rules = {
            "BE-QL-15": {
                "level": "P2",
                "message": "{method} 应使用 Result.success() 无 data",
                "program": {
                    "scanner": "java-ast",
                    "target": "method",
                    "on_class_annotation": "RestController|Controller",
                    "on_method_annotation": "PostMapping|PutMapping|DeleteMapping",
                    "require_pattern_in_body": "Result\\.success\\(\\s*\\)"
                }
            }
        }
        # Controller with correct usage
        file_path = tmp_path / "GoodController.java"
        file_path.write_text(JAVA_CONTROLLER_WITH_VALID)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 0, f"Expected 0 findings for correct usage, got {findings}"

    def test_mapper_multi_param_needs_param_annotation(self, tmp_path):
        """BE-QL-44: Mapper method with 2+ params needs @Param."""
        rules = {
            "BE-QL-44": {
                "level": "P1",
                "message": "{method} 缺少 @Param 注解",
                "program": {
                    "scanner": "java-ast",
                    "target": "method",
                    "on_class_annotation": "*Mapper",
                    "param_missing_annotation": "@Param",
                    "param_count_gte": 2
                }
            }
        }
        file_path = tmp_path / "UserMapper.java"
        file_path.write_text(JAVA_MAPPER_MULTI_PARAM)
        scanner = JavaAstScanner()
        findings = scanner.scan(file_path, rules)
        assert len(findings) == 0, "Multi-param mapper method with @Param should pass"
```

- [ ] **Step 5: Write test class for retained scanners**

```python
class TestRetainedScanners:

    def test_package_structure_scanner_still_works(self, tmp_path):
        """Verify PackageStructureScanner is still in SCANNERS registry."""
        from code_check.scanner import SCANNERS
        assert "package-structure" in SCANNERS
        assert "file-naming" in SCANNERS
        assert "config-check" in SCANNERS

    def test_old_scanners_removed(self):
        """Verify old scanners are gone."""
        from code_check.scanner import SCANNERS
        assert "text-grep" not in SCANNERS
        assert "java-annotation" not in SCANNERS
        assert "java-return-type" not in SCANNERS

    def test_classify_files(self):
        """verify classify_files still works."""
        files = ["UserController.java", "UserService.java", "UserServiceImpl.java",
                  "UserMapper.java", "UserEntity.java", "CreateUserDTO.java", "UserVO.java"]
        counts = classify_files(files)
        assert counts["controller"] == 1
        assert counts["service"] == 2
        assert counts["mapper"] == 1
        assert counts["entity"] == 1
        assert counts["dto"] == 2

    def test_is_blocked_strict(self):
        f1 = Finding(code="X", level=Level.P1, line=1, message="test", evidence="test")
        f2 = Finding(code="Y", level=Level.P0, line=1, message="test", evidence="test")
        assert is_blocked([f1], BlockingStrategy.STRICT)
        assert is_blocked([f2], BlockingStrategy.STRICT)
        assert not is_blocked([], BlockingStrategy.STRICT)
```

- [ ] **Step 6: Run all scanner tests**

```bash
cd agents/reviewer/check_system && python3 -m pytest tests/test_scanner.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add agents/reviewer/check_system/tests/test_scanner.py
git commit -m "test: rewrite scanner tests for JavaAstScanner"
```

---

### Task 8: End-to-end smoke test with real Java source

**Files:** (none — verification only)

- [ ] **Step 1: Run full scan against the project src/main/java**

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli scan ../../../src/main/java
```

Expected: scan completes, outputs `review-output/pre-check-result.json` and `review-output/pre-check-report.md`.

- [ ] **Step 2: Verify the old false positives are gone**

Check the output for:
- BE-ST-23 should NOT flag `UserService.java` (interface)
- BE-IN-04 should NOT flag `USERNAME_MIN_LENGTH` (static final constant field)
- BE-AU-07 should NOT flag `JwtProperties.java` (not a business Service class)

- [ ] **Step 3: Verify valid issues still detected**

Check that legit issues like missing `@Slf4j`, `@Schema` on non-static fields, etc. are still caught.

- [ ] **Step 4: Run all existing tests**

```bash
cd agents/reviewer/check_system && python3 -m pytest tests/ -v
```

Expected: all tests pass (test_cli.py, test_config.py, test_models.py, test_reporter.py should be unaffected).

- [ ] **Step 5: Commit if any fixes needed, otherwise done**

---

### Task 9: Final cleanup — update code-check-config.yaml

**Files:**
- Modify: `agents/reviewer/check_system/code-check-config.yaml`

- [ ] **Step 1: Verify config is correct**

Ensure the diff shows only the strategy setting (keep strict, which was already the setting):

No changes needed — verify the file is correct as-is.

- [ ] **Step 2: Final commit if needed**

```bash
git status
```

---

## Summary

| Task | Files Changed | What |
|------|:---:|------|
| 1 | `requirements.txt` (new) | tree-sitter + tree-sitter-java deps |
| 2 | `scanner.py` | Add AST helpers, tree-sitter init |
| 3 | `scanner.py` | Add JavaAstScanner class |
| 4 | `program-checks.yaml` | Rewrite 35 rules to java-ast format |
| 5 | `scanner.py` | Delete old scanners |
| 6 | `conftest.py` | Update sample rule format |
| 7 | `test_scanner.py` | Rewrite tests for JavaAstScanner |
| 8 | (smoke test) | E2E verification |
| 9 | (cleanup) | Final checks |
