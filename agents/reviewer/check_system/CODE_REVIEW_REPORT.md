# check_system/ 代码审查报告

**审查日期**: 2026-06-21  
**修复日期**: 2026-06-23 (commit `6aa08fd`)  
**审查范围**: `agents/reviewer/check_system/` 下所有 Python 源码、YAML 配置、测试文件  
**审查方法**: 逐文件静态分析 + AST 逻辑走查  
**测试状态**: 现有 99 个测试全部通过

---

## 修复状态总览

| 编号 | 级别 | 描述 | 状态 |
|------|------|------|------|
| BUG-1 | P0 | `_find_formal_parameters` 无限递归 | ✅ 发现时已修复 |
| BUG-2 | P0 | `required_return_pattern` 子串匹配 | ✅ 发现时已修复 |
| BUG-3 | P0 | `_check_fields` 类型检测不完整 | ✅ 发现时已修复 |
| BUG-4 | P0 | `check_validated_group` 参数类型检测 | ✅ 发现时已修复 |
| BUG-5 | P1 | `_matches_on_dir` 正则错误处理 | ✅ 发现时已修复（`_safe_fullmatch`） |
| BUG-6 | P1 | `on_file_pattern` 正则编译 | ✅ 发现时已修复 |
| BUG-7 | P1 | CLI `output_format` None | ✅ 发现时已修复 |
| BUG-8 | P1 | JSON 反序列化错误处理 | ✅ 发现时已修复 |
| BUG-9 | P1 | `cmd_report` 死代码 | ✅ 已修复 |
| BUG-10 | P1 | Windows 路径兼容 | ✅ 已修复（`os.sep` → `/`） |
| BUG-11 | P1 | `_find_java_package_dirs` 深度遍历 | ✅ 已修复（max_depth=5） |
| BUG-12 | P2 | 标准目录名重复 | ✅ 已修复（`STANDARD_PACKAGE_DIRS`） |
| BUG-13 | P2 | 辅助函数类型标注 | ✅ 已修复 |
| BUG-14 | P2 | 文件分类器 DTO 变体 | ✅ 已修复（+Request/Command/Form） |

---

## 总览

| 类别 | 数量 | 说明 |
|------|------|------|
| P0（关键 Bug） | 4 | 潜在崩溃 / 静默漏报 |
| P1（鲁棒性） | 7 | 错误处理缺失、跨平台兼容、死代码 |
| P2（代码质量） | 3 | 重复常量、类型标注、分类器覆盖不全 |
| 测试覆盖缺口 | 9 | 边界情况、集成测试、P0 回归覆盖缺失 |

---

## P0 — 关键 Bug

### BUG-1: `_find_formal_parameters` 潜在无限递归

- **文件**: `code_check/scanner.py`，第 228-233 行
- **严重性**: P0（潜伏崩溃）

```python
def _find_formal_parameters(method_node) -> list:
    formal_params = _child_by_type(method_node, "formal_parameters")
    if formal_params:
        return _children_by_type(formal_params, "formal_parameter")
    return _find_formal_parameters(method_node)  # BUG: 传入相同参数递归调用自身
```

**问题**: 当 `_child_by_type` 返回 `None`（没有 `formal_parameters` 子节点）时，函数用完全相同的参数调用自身，最终导致栈溢出。当前 tree-sitter-java 对方法/构造器声明总是生成 `formal_parameters` 子节点（即使是空 `()`），所以此 Bug 处于潜伏状态。

**修复**: 将回退逻辑改为 `return []`。

---

### BUG-2: `required_return_pattern` 子串匹配导致假阴性

- **文件**: `code_check/scanner.py`，第 924 行
- **严重性**: P0（静默漏报）

```python
if program["required_return_pattern"] not in ret_text:
```

**问题**: 使用 `in` 做子串匹配。如果规则要求 `Result<`，方法返回 `NonResult<Void>` 会通过检测，因为 `"Result<"` 出现在了 `"NonResult<Void>"` 中。

**修复**: 使用词边界感知的检查或正则，例如 `re.match(r'(?:.*\.)?Result<', ret_text)`。

---

### BUG-3: `_check_fields` 字段类型检测不完整

- **文件**: `code_check/scanner.py`，第 1075-1076 行
- **严重性**: P0（静默漏报）

```python
type_node = _child_by_type(field_node, "type_identifier")
field_type = _node_text(type_node, source_bytes) if type_node else ""
```

**问题**: 只识别 `type_identifier` 作为字段声明的直接子节点。tree-sitter-java 中：
- 泛型类型 `List<String>` → AST 节点类型: `generic_type`
- 全限定类型 `com.example.Foo` → AST 节点类型: `scoped_type_identifier`
- 数组类型 `int[]` → AST 节点类型: `array_type`

当这些类型出现时，`field_type` 为空字符串，`on_field_type` 和 `forbid_field_type` 检查被静默跳过。

**影响范围**:
- `BE-QL-40` (`forbid_field_type: "Logger"`) — 无法标记 `private List<Logger> loggers;` 或 `private com.foo.Logger logger;`
- `BE-QL-27` (`required_field_annotation: "@TableLogic"`) — 不受影响（仅检查注解）
- `BE-ST-22` (`forbid_field_annotation: "@Autowired"`) — 不受影响（仅检查注解）

**修复**: 添加 `generic_type`、`scoped_type_identifier`、`array_type`、`integral_type`、`floating_point_type`、`boolean_type` 到类型检测逻辑中，与 `_check_methods`（第 918-919 行）保持一致。

---

### BUG-4: `check_validated_group` 参数类型检测不完整

- **文件**: `code_check/scanner.py`，第 1029-1035 行
- **严重性**: P0（静默漏报）

```python
for child in pn.children:
    if child.type in ("type_identifier", "generic_type"):
        param_type_text = _node_text(child, source_bytes)
        break
```

**问题**: 只处理 `type_identifier` 和 `generic_type`，遗漏 `scoped_type_identifier`、`array_type`、`integral_type`、`floating_point_type`、`boolean_type`。对于全限定类型参数 `@Validated com.example.dto.CreateUserDTO dto`，`param_type_text` 保持为空，后续正则不匹配，`@Validated` 分组检查被静默跳过。

**影响范围**: `BE-QL-30` 规则

**修复**: 添加缺失的类型节点类型，与 `_check_methods` 保持一致。

---

## P1 — 鲁棒性问题

### BUG-5: `_matches_on_dir` 缺少正则错误处理

- **文件**: `code_check/scanner.py`，第 87-88 行
- **严重性**: P1（潜在崩溃）

```python
elif re.fullmatch(pat, part):
    return True
```

**问题**: `_any_match` 使用了 `try/except re.error` 包裹（第 35-36 行），但 `re.fullmatch` 没有。如果规则中 `on_dir` 包含非法正则，整个扫描崩溃。

**修复**: 包裹 `try/except re.error`，与 `_any_match` 保持一致。

---

### BUG-6: `FileNamingScanner.on_file_pattern` 正则编译无错误处理

- **文件**: `code_check/scanner.py`，第 475-477 行
- **严重性**: P1（潜在崩溃）

```python
if "on_file_pattern" in program:
    fp_regex = re.compile(program["on_file_pattern"])
```

**问题**: `re.compile` 对非法模式抛出 `re.error`。当前无规则使用 `on_file_pattern`，但它是 YAML 可配置项。

**修复**: 包裹 `try/except re.error`。

---

### BUG-7: CLI `cmd_scan` — `output_format` 为 `None` 时静默不输出

- **文件**: `code_check/cli.py`，第 99、122-130 行
- **严重性**: P1（静默数据丢失）

```python
output_format = args.format or config["format"]
...
if output_format == "json":      # None → False
    ...
if output_format == "md" or ...  # None 且 passed=True → False
    ...
```

**问题**: 如果配置文件 `format: null`（YAML null），两个分支都不命中。扫描通过时，无任何输出文件生成，也无错误提示。

**修复**: `output_format = args.format or config["format"] or "json"`。

---

### BUG-8: JSON 反序列化缺少错误处理

- **文件**: `code_check/cli.py`，`_parse_scan_result`（第 33-65 行）和 `_parse_review_result`（第 68-87 行）
- **严重性**: P1（糟糕的 UX）

**问题**: 两函数直接访问字典键 `data["metadata"]`、`meta["scan_scope"]` 等。如果 JSON 文件格式错误或来自旧版本，`KeyError`/`TypeError`/`json.JSONDecodeError` 会以原始 Traceback 终止进程。

**修复**: 包裹 `try/except (KeyError, TypeError, json.JSONDecodeError)`，输出友好错误信息并干净退出。

---

### BUG-9: `cmd_report` 加载配置但未使用

- **文件**: `code_check/cli.py`，第 142-143 行
- **严重性**: P1（死代码）

```python
if args.config:
    config = load_cli_config(Path(args.config))
```

**问题**: `config` 变量赋值后从未被引用。

**修复**: 移除未使用的配置加载，或将其用于报表生成选项（如输出格式偏好）。

---

### BUG-10: Windows 路径兼容性

- **文件**: `code_check/scanner.py`，`_path_matches_glob`（第 1208-1232 行）
- **严重性**: P1（平台 Bug）

**问题**: 函数硬编码 `"/"` 分割路径。Windows 上 `str(Path(...))` 使用 `\`，导致路径分割失败，所有 `**` 通配符匹配静默失效。

**修复**: 使用 `path.split(os.sep)` 或先转换为 POSIX 路径 `path.replace(os.sep, "/").split("/")`。

---

### BUG-11: `_find_java_package_dirs` 深度遍历边界情况

- **文件**: `code_check/scanner.py`，第 389-435 行
- **严重性**: P1（特定项目结构中的假阳性）

**问题**: 函数在完整目录树上 `os.walk`。当子目录有标准同级目录但没有自己的 Java 文件时，由于 `os.walk` 深层遍历，分类逻辑可能错误地将子目录识别为包根目录。可能导致 `PackageStructureScanner` 对 `required_dirs` 报告错误发现。

**修复**: 添加深度限制，或仅考虑直接包含 Java 文件的目录。

---

## P2 — 代码质量

### BUG-12: 标准目录名重复定义

- **文件**: `code_check/scanner.py`，第 401 行和第 497 行
- **严重性**: P2（维护风险）

集合 `{"controller", "service", "mapper", "entity", "dto", "vo"}` 在 `_find_java_package_dirs` 和 `FileNamingScanner.scan` 中重复出现。变更需同步两处。

**修复**: 提取为模块级常量 `STANDARD_PACKAGE_DIRS`。

---

### BUG-13: 辅助函数缺少泛型类型标注

- **文件**: `code_check/scanner.py`
- **严重性**: P2（代码质量）

`_find_formal_parameters`（`-> list` 无元素类型）、`_find_ast_methods`（无返回标注）、`_find_ast_fields`（无返回标注）等函数缺少泛型类型提示。

**修复**: 添加 `-> list[tree_sitter.Node]`、`-> Iterator[tuple[tree_sitter.Node, str, set[str]]]` 等。

---

### BUG-14: 文件分类器不支持完整 DTO 命名变体

- **文件**: `code_check/scanner.py`，第 1238-1257 行
- **严重性**: P2（轻微报告不准确）

函数按 `DTO.java`/`VO.java` 后缀分类，但 `program-checks.yaml` 中 `match_param_type: "DTO|Request|Command|Form"` 还包含 `Request.java`、`Command.java`、`Form.java` 等变体，这些文件在报告中被忽略。

**修复**: 添加 `Request.java`、`Command.java`、`Form.java` 到分类逻辑。

---

## 测试覆盖缺口

| 编号 | 缺口描述 | 缺失测试 |
|------|----------|----------|
| G1 | `_find_formal_parameters` 递归回退路径 | 无测试验证回退的安全性 |
| G2 | `_matches_on_dir` 非法正则输入 | 无测试验证错误处理 |
| G3 | `on_file_pattern` 非法正则 | 无测试 |
| G4 | 空 `.java` 文件扫描 | 无测试覆盖任何扫描器的空文件输入 |
| G5 | `scan_files` 完整集成 | `scan_files` 被导入但从未直接测试；无端到端测试覆盖目录扫描、提示生成、阻断逻辑 |
| G6 | `_check_fields` 泛型/数组/全限定字段类型 | 无测试使用 `List<T>`、`com.foo.Bar`、`int[]` 字段配合 `on_field_type`/`forbid_field_type` 规则 |
| G7 | `check_validated_group` 全限定参数类型 | 无测试使用 `@Validated com.example.dto.CreateUserDTO dto` |
| G8 | `required_return_pattern` 假阴性 | 无测试验证 `NonResult<Void>` 被正确标记 |
| G9 | CLI 配置 `output_format: None` | 无测试覆盖静默无输出场景 |

---

## 规则 / 配置一致性

| 编号 | 检查项 | 结论 |
|------|--------|------|
| R1 | `on_class_annotation` 类名匹配 (`Service\|ServiceImpl\|...`) | 正常 — `_any_match` 同时匹配注解和类名，符合预期 |
| R2 | `BE-ST-03` 缺少 `on_dir` 过滤 | 正常 — 全局搜索 `*Application.java` 是正确行为 |
| R3 | `BE-IN-08` 密码检测负向前瞻 `(?!\${)` | 正常 — 正确跳过 `${ENV_VAR}` 占位符，有对应测试 |
| R4 | `BE-AU-31` 明文密码检测 | 基本正常 — 负向前瞻正确跳过 bcrypt，但某些边界情况可能产生假阴性 |

---

## 修复优先级建议

1. **立即修复**（P0）: BUG-2、BUG-3、BUG-4 — 导致生产环境静默漏报
2. **尽快修复**（P0 + P1）: BUG-1 — 潜在崩溃；BUG-5~BUG-8 — 提升健壮性
3. **计划修复**（P1 + P2 + 测试）: BUG-9~BUG-14 + G1~G9 — 代码质量和测试完善
