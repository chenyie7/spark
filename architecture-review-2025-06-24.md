# Agent 架构全面审查报告

> 审查日期：2026-06-24
> 审查范围：`agents/` 全量 + `docs/` + 流水线 + Python 源码 + Skill 定义

---

## 一、架构全景图

```
/build <需求>
    │
    ▼
┌──────────────────────────────────────────────────┐
│  scheduler/build.skill.md (主控 Agent)            │
│  pipeline.yaml (DAG 定义，实际只是给人看的文档)      │
│                                                   │
│  Phase 0: 初始化 → Phase 1: coder 生成            │
│  → Phase 2: review 审查 → Phase 3: 判定           │
│  → Phase 4: 修复循环 ↻                            │
└──────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
┌─────────────────┐    ┌──────────────────────────┐
│ coder (Agent)    │    │ reviewer (Agent)          │
│ 读取 20 个规范    │    │ 调用 Skill("review")       │
│ 生成 Java 代码   │    │                           │
│                 │    │ Step 1: pre-hook.sh        │
│                 │    │   └─ Python CLI scan       │
│                 │    │ Step 2: AI 语义检查         │
│                 │    │ Step 3: post-hook.sh        │
│                 │    │   └─ 合并最终报告           │
└─────────────────┘    └──────────────────────────┘
```

---

## 二、优点（保持）

| # | 优点 | 说明 |
|---|------|------|
| 1 | **双层校验设计精巧** | Layer 1 程序预检（46 条规则，零 AI Token）+ Layer 2 AI 语义检查（23 条），分工清晰 |
| 2 | **tree-sitter AST 扫描** | 比正则匹配准确得多，能区分 class/interface/enum、识别注解、解析方法签名 |
| 3 | **YAML 驱动规则** | 规则与扫描引擎解耦，新增规则不需要改 Python 代码 |
| 4 | **P0/P1/P2 分级阻断** | strict/normal/loose 三档策略，灵活适配不同项目阶段 |
| 5 | **coder 规范组织良好** | 6 个子目录，渐进式加载（auth-overview → basic → multi-end/SSO/OAuth2） |
| 6 | **修复循环有边界** | max_retries=3 防止死循环，REVIEW_ERROR 异常终止不进入修复 |

---

## 三、🔴 严重问题

### 3.1 `pipeline.yaml` 是"死配置"——DAG 从未被机器执行

**位置：** `agents/scheduler/pipeline.yaml` + `agents/scheduler/build.skill.md`

`pipeline.yaml` 定义了完整的 DAG（节点、边、条件、触发器），但 `build.skill.md` **完全没有解析这个 DAG**。它用自然语言硬编码了 coder→reviewer→fix 循环。YAML 中的 `edges`、`condition`、`trigger` 字段是给人看的文档，不是可执行配置。

**后果：**
- 修改 YAML 中的 edges 不会改变流水线行为
- 新增节点（如未来加入 analyst/测试节点）需要同时改 YAML 和 build.skill.md
- 两份"真相"必然漂移

**建议：** 要么让 build.skill.md 真正解析 YAML 动态执行，要么删除 YAML 中的 DAG 定义，只保留 defaults 配置。

---

### 3.2 路径引用脆弱，存在三级相对路径

**位置：**
- `build.skill.md` Phase 4 — 告诉 coder 读取 `review-output/pre-check-result.json`
- `review.skill.md` Step 2 — 引用 `../../../review-output/review-result.json`
- `review-pre-hook.sh:16` — `PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"`
- `review-post-hook.sh:10` — 同上

多处使用 `../../../review-output/` 硬编码相对路径。这些路径在不同工作目录下行为不一致。尤其是当 coder Agent 的工作目录和 reviewer Agent 的工作目录不同时，产物路径会断裂。

**建议：** 统一用环境变量 `REVIEW_OUTPUT_DIR` 或始终用项目根目录的绝对路径。

---

### 3.3 修复阶段引用了可能不存在的文件

**位置：** `agents/scheduler/build.skill.md` Phase 4

```
请先读取以下文件，了解上一轮审查发现的问题：
1. review-output/pre-check-result.json — 程序预检结果
2. review-output/review-result.json — AI 语义检查结果（如存在）   ← 标了"如存在"但不明确
3. review-output/pre-check-report.md — 预检报告
```

当 review 因预检阻断返回 `REVIEW_FAILED` 时，Step 2（AI 检查）被跳过，`review-result.json` **不会生成**。coder 修复时尝试读取这个不存在的文件会出错或读到空。虽然 Phase 4 标注了"如存在"，但没有区分"预检阻断"和"AI 检查失败"两种情况。

**建议：** 修复 prompt 中区分两种情况，只引用实际存在的产物文件。或在 Phase 3 判定时传递具体的失败原因和产物清单。

---

## 四、🟡 中等问题

### 4.1 `_any_match` 函数的正则拆分 Bug

**位置：** `agents/reviewer/check_system/code_check/scanner.py:43-66`

```python
def _any_match(items: list[str], pattern: str) -> bool:
    for pat in pattern.split("|"):   # ← 按 | 拆分
        pat = pat.strip()
        if not pat:
            continue
        for item in items:
            if "*" in pat or "?" in pat:
                if fnmatch.fnmatch(item, pat):
                    return True
            else:
                try:
                    if re.search(pat, item):   # ← 用拆分后的片段做正则
                        return True
                except re.error:
                    pass   # ← 静默吞掉错误
```

当模式本身包含正则的 `|`（或操作符）时：
```python
# 输入: ".*(Constant|Constants|Code|Codes)"
# 拆分结果: [".*(Constant", "Constants", "Code", "Codes)"]  
# 前两个是无效正则 → 被 except re.error pass 吞掉
# 后两个能匹配但丢失了上下文约束
```

代码用 `try/except re.error: pass` 吞掉了错误，但导致**某些规则静默失效**——即不报错，也不匹配。

**建议：** 对不含 `*` `?` 的模式，使用 `re.search(pat, item)` 时传入原始完整模式，不要拆分。拆分仅用于 fnmatch 路径。

---

### 4.2 tree-sitter Parser 全局单例，不可并行

**位置：** `agents/reviewer/check_system/code_check/scanner.py:115-116`

```python
_TS_LANGUAGE = tree_sitter.Language(tsjava.language())
_TS_PARSER = tree_sitter.Parser(_TS_LANGUAGE)
```

`tree_sitter.Parser` 不是线程安全的。如果未来想并行扫描多个文件（多线程/多进程），这个全局单例会出问题。当前虽然是单线程扫描，但限制了未来的性能优化空间。

**建议：** 每次扫描创建新的 Parser 实例，或使用 `threading.local()` 做线程局部存储。

---

### 4.3 `ConfigCheckScanner.scan_directory` 签名不一致

**位置：** `scanner.py:262-296` (BaseScanner) vs `scanner.py:590` (ConfigCheckScanner)

```python
# 基类
class BaseScanner(ABC):
    def scan_directory(self, base_path: Path, rules: dict) -> list[Finding]: ...

# 子类多了一个参数
class ConfigCheckScanner(BaseScanner):
    def scan_directory(self, base_path: Path, rules: dict, 
                       exclude_patterns: list[str] | None = None) -> list[Finding]:
```

`_run_directory_scanners` 通过硬编码 scanner 名字来特殊处理：
```python
if scanner_name == "config-check":
    findings.extend(scanner.scan_directory(base_path, rules, excludes))
else:
    findings.extend(scanner.scan_directory(base_path, rules))
```

**建议：** 统一接口，把 `exclude_patterns` 放进 `rules` 或作为所有 scanner 的通用参数。

---

### 4.4 每个文件被读取两次

**位置：** `scanner.py:1396-1453` scan_files()

```python
for java_file in java_files:
    content = java_file.read_text(encoding="utf-8")    # 第一次：文本模式
    all_hints.extend(_scan_for_hints(java_file, content))
    findings = scan_single_file(java_file, active_rules) # 内部 read_bytes() 第二次
```

第一次用文本模式读完整文件做敏感信息检测（`_scan_for_hints`），第二次用字节模式读完整文件做 AST 解析（`scan_single_file` → `file_path.read_bytes()`）。

**建议：** 读一次 bytes，既可以传进 tree-sitter，也可以 `.decode()` 后用于 hint 扫描。

---

### 4.5 `review.skill.md` 的阻断描述有歧义

**位置：** `agents/reviewer/review.skill.md` Step 1

```markdown
- exit 1：预检未通过 → 停止。返回 REVIEW_FAILED，不执行后续步骤
```

实际上 `exit 1` 的触发条件取决于 `code-check-config.yaml` 中的 `strategy`：
- `strict`：P0 或 P1 → exit 1
- `normal`：仅 P0 → exit 1
- `loose`：仅 P0 → exit 1

但 `review.skill.md` 没有提到阻断策略的影响，让执行者以为"exit 1 = 有问题"，但实际上"exit 0"也可能有 P1/P2 问题残留。

**建议：** 在 Step 1 的说明中注明当前策略及对应的阻断条件。

---

### 4.6 缺少编译验证

**位置：** 整个流水线

流水线全程检查代码风格、规范、注解、命名——但**从不运行 `mvn compile`**。可能出现的情况：
- 所有规范检查通过（REVIEW_PASSED）
- 代码实际上有编译错误（类型不匹配、缺少 import 等）

tree-sitter 是语法解析器，不是 Java 编译器，它不检查类型正确性。

**建议：** 在 pre-check 后增加一步 `mvn compile -q` 编译验证，编译失败直接阻断。

---

### 4.7 修复循环中 P0 不降反增无保护

**位置：** `agents/scheduler/build.skill.md` Phase 4 异常处理

> coder 修复后 P0 数量不降反增 → 不自动终止，让循环继续。

这意味着如果 coder 的修复引入了新的 P0，流水线会在无进展的情况下继续消耗 Token 直到 max_retries 耗尽。

**建议：** P0 数量增加时应立即告警并让用户介入，而非盲目重试。

---

## 五、🟢 轻微问题

### 5.1 无流水线中断恢复机制

**位置：** `agents/scheduler/build.skill.md`

如果 `/build` 在 Phase 2 被 Ctrl+C 中断：
- `review-output/` 下的产物保留一半
- 重新运行 `/build` 会从头开始，无法续接

**建议：** 在 Phase 0 检查是否存在上一次的产物，如果有则询问是否续接。

---

### 5.2 规则 ID 编号不连续

**位置：** `agents/reviewer/check_system/rules/program-checks.yaml`

规则编号跳号严重：BE-AU-05, BE-AU-21, BE-AU-31, BE-AU-32。说明规则是 ad-hoc 添加的，没有统一的编号计划。

**建议：** 按维度重新编号，或使用语义化 ID（如 `BE-AU-PASSWORD-PLAINTEXT`）。

---

### 5.3 无跳过预检的开发模式

**位置：** `agents/reviewer/hooks/review-pre-hook.sh`

开发过程中如果遇到预检误报（false positive），无法跳过 Layer 1 直接跑 Layer 2。

**建议：** `review-pre-hook.sh` 支持 `--skip-pre-check` 或环境变量 `SKIP_PRE_CHECK=1`。

---

### 5.4 `.DS_Store` 仍在 Git 追踪中

**位置：** 仓库根目录 + 多个子目录

`.gitignore` 已修改但 macOS 系统文件仍出现在 `git status` 中（`agents/.DS_Store`、`agents/coder/.DS_Store` 等）。需要 `git rm --cached` 清除已追踪的 `.DS_Store` 文件。

---

## 六、已有审查报告的遗留问题

上次审查（2026-06-04，`docs/agents-architecture-review.md`）识别了以下问题**仍未修复**：

| 问题 | 严重度 | 状态 |
|------|--------|------|
| 30% coder 禁止事项无 reviewer 检查 | 🔴 P0 | ❌ 未修复 |
| 微服务 70% 规范无审查覆盖 | 🔴 P0 | ❌ 未修复 |
| 缺少文件上传安全规范 | 🔴 P0 | ❌ 未修复（但有 file-upload-guide.md 了） |
| 缺失 @Async / @Scheduled / @Cacheable 规范 | 🟡 P1 | ❌ 未修复 |
| 缺失 XSS / SQL注入 / SSRF 安全规范 | 🟡 P1 | ❌ 未修复 |
| coder 交叉引用维护成本高 | 🟡 P1 | ❌ 未修复 |
| reviewer 串行审查模式效率低 | 🟢 P2 | ❌ 未修复（但双层校验系统已替代原有串行模式） |
| auth-basic.md 分岔逻辑复杂 | 🟢 P2 | ❌ 未修复 |
| 无参考实现项目 | 🟢 P2 | ❌ 未修复 |
| 规范文件无版本标识 | 🟢 P2 | ❌ 未修复 |

> 上次审查侧重于**规范覆盖度**（coder vs reviewer 的内容对比），本次审查侧重于**运行时架构问题**（流水线、Skill 嵌套、路径、扫描引擎 Bug），两者互补。

---

## 七、改进优先级汇总

### P0 — 必须修复（运行时阻断）

| # | 问题 | 影响 | 涉及文件 |
|---|------|------|------|
| 1 | pipeline.yaml 是死配置，DAG 不执行 | 配置与行为漂移 | `pipeline.yaml`, `build.skill.md` |
| 2 | 修复阶段引用可能不存在的 review-result.json | coder 读不到文件或出错 | `build.skill.md` Phase 4 |

### P1 — 强烈建议修复

| # | 问题 | 影响 | 涉及文件 |
|---|------|------|------|
| 4 | `_any_match` 正则拆分导致规则静默失效 | 某些检查不生效 | `scanner.py:43-66` |
| 5 | 路径引用脆弱（`../../..`） | 不同工作目录下产物路径断裂 | `build.skill.md`, `review.skill.md`, `*.sh` |
| 6 | 缺少编译验证 (mvn compile) | 规范通过但代码编译失败 | 流水线新增步骤 |
| 7 | P0 不降反增无保护 | 浪费 Token 到 max_retries | `build.skill.md` Phase 4 |
| 8 | Parser 全局单例不可并行 | 限制未来性能优化 | `scanner.py:115-116` |
| 9 | `ConfigCheckScanner` 签名不一致 | 维护风险 | `scanner.py:590` vs `scanner.py:262` |

### P2 — 改善性修复

| # | 问题 | 影响 | 涉及文件 |
|---|------|------|------|
| 10 | 每个文件读取两次 | 性能浪费 | `scanner.py:1439-1440` |
| 11 | review.skill.md 阻断描述有歧义 | 执行者理解偏差 | `review.skill.md` Step 1 |
| 12 | 无中断恢复机制 | 中断后需重跑 | `build.skill.md` Phase 0 |
| 13 | .DS_Store 污染仓库 | 整洁度 | 仓库根目录 |
| 14 | 规则 ID 编号不连续 | 可读性 | `program-checks.yaml` |
| 15 | 无跳过预检的开发模式 | 开发效率 | `review-pre-hook.sh` |

---

## 八、总结矩阵

| 维度 | 评分 | 关键问题 |
|------|:--:|------|
| 架构设计理念 | ⭐⭐⭐⭐ | 双层校验 + 修复循环 + 上下文隔离设计合理 |
| 流水线执行可靠性 | ⭐⭐⭐ | DAG 不执行、路径脆弱 |
| 扫描引擎实现质量 | ⭐⭐⭐ | AST 方案好，但有静默 Bug、单例问题 |
| 规范覆盖度（coder→reviewer） | ⭐⭐ | 30% 禁止项无审查、微服务 70% 无覆盖 |
| 运维可用性 | ⭐⭐ | 无编译验证、无中断恢复、无跳过模式 |
| 代码工程质量 | ⭐⭐⭐ | 有测试但不覆盖流水线集成 |

---

**总体评价：** 这套架构的设计思路清晰，双层校验 + 上下文隔离的设计在同类工具中是比较先进的。主要问题集中在**运行时实现细节**（DAG 不执行、路径脆弱、Parser Bug）和**覆盖度不足**。建议优先修复 P0 的 2 个运行时问题，然后系统性补齐 P1 问题。
