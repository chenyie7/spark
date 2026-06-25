# Reviewer 审查系统重构 — 设计规格

## 概述

将当前"44 条程序检查 + 17 条 AI 检查"的双层审查系统，重构为"fuck-u-code 静态分析 + AI 统一审查"的架构。消除程序检查维护成本，引入代码质量 7 维评分，AI 审查从两次调用合并为一次。

## 动机

1. **程序检查覆盖不全**：44 条规则只能覆盖 coder 12 个规范文件中约 60% 的条目，且每加一条规则都要写 Python 代码
2. **两层 AI 重复**：当前的 AI 语义检查和 fuck-u-code 的 ai-review 审查的是同一批代码
3. **缺少代码质量视角**：当前系统只查"规范合规"，不查复杂度、重复代码、巨函数等质量问题
4. **维护成本高**：程序检查有 scanner/config/models/reporter 四层抽象，约 1500 行 Python + 65 个测试

## 技术选型

| 组件 | 技术 | 原因 |
|------|------|------|
| 静态分析 | fuck-u-code `analyze` (MCP) | 7 维评分、离线免费、支持 Java、结构化 JSON 输出 |
| AI 审查 | pipeline reviewer agent | 一次调用，同时完成规范合规 + 深度质量分析 |
| 报告渲染 | Python CLI（保留 report 子命令） | 模板化输出，格式稳定，可聚合历史数据 |

## 架构对比

### 当前架构（改前）

```
review.skill.md
    │
    ├── Step 1: code_check.cli scan       ← 程序检查 44 条
    │   ├── scanner.py (3 种扫描器)
    │   ├── config.py (YAML 加载)
    │   └── → pre-check-result.json
    │
    ├── Step 2: AI 语义检查               ← AI 调用 #1
    │   └── → review-result.json
    │
    └── Step 3: code_check.cli report     ← 拼接
        └── → final-review-report.md
```

### 目标架构（改后）

```
review.skill.md
    │
    ├── Step 1: fuck-u-code analyze          ← 程序，免费
    │   └── → quality.json
    │
    ├── Step 2: AI 统一审查                   ← AI 调用，唯一一次
    │   输入: ai-checklist.yaml + quality.json + 代码
    │   └── → findings.json
    │
    └── Step 3: cli.py report                ← 程序，模板渲染
        quality.json + findings.json
        └── → final-review-report.md
```

## 文件变更清单

### 删除

```
agents/reviewer/check_system/
├── code_check/scanner.py             # 3 种扫描器（java-ast/package-structure/file-naming/config-check）
├── code_check/config.py              # YAML 配置加载器
├── code_check/models.py              # 旧 dataclasses（PreCheckResult 等）
├── rules/program-checks.yaml         # 44 条程序检查规则
├── code-check-config.yaml            # 阻断策略配置
├── hooks/                            # pre/post hook 脚本
└── tests/                            # 全部 65 个测试
```

### 大改

```
agents/reviewer/check_system/
├── rules/ai-checklist.yaml           # 17 → ~40 条，AI 审查的唯一标准输入
├── code_check/cli.py                 # 只保留 report 子命令，删 scan 子命令
├── code_check/models.py              # 重写为 findings schema（AI 输出的 JSON 结构）
├── code_check/reporter.py            # 重写为 quality.json + findings.json → Markdown 渲染器
└── review.skill.md                   # 流程从 3 步变成 2 步
```

### 小改

```
agents/scheduler/pipeline.yaml        # reviewer 的 prompt_template 更新
agents/reviewer/README.md             # 更新文档
```

### 新增

```
.mcp.json                             # 项目根目录，fuck-u-code MCP 配置
```

### 不改

```
pipeline_engine/                      # DAG 调度、状态管理全部不变
build.skill.md                        # 执行循环逻辑不变
coder/                                # 12 个规范文件不变
benchmarks/                           # 性能数据采集逻辑不变
```

## 组件设计

### 1. ai-checklist.yaml（~40 条）

从 coder 12 个规范文件中提取所有 AI 可判断的检查条目。保留当前 17 条有效条目，新增 ~25 条，删掉程序检查能做得更好的条目。

#### 保留（17 条，来自当前）：

```
分层架构:
  BE-ST-04  Controller 直接注入 Mapper              P0
  BE-ST-05  Service 只有实现类没有接口               P1
  BE-ST-07  Service 方法返回 Entity 给 Controller     P1
  BE-ST-18  Entity 类命名符合规范                    P2

异常处理:
  BE-QL-01  throw new RuntimeException("自由文本")   P1
  BE-QL-02  BusinessException(BusinessErrorEnum)     P1
  BE-QL-04  Controller 方法包裹 try-catch             P1
  BE-QL-05  catch 后只打日志不抛出                    P1
  BE-QL-06  GlobalExceptionHandler 兜底              P2

日志质量:
  BE-QL-11  log.info 包含关键业务信息                 P2
  BE-QL-12  循环内大量 log.info                       P2

代码质量:
  BE-QL-14  返回裸 String/boolean/Map/JSONObject     P1
  BE-QL-35  集合返回值可能为 null                     P1
  BE-QL-39  循环内 + 拼接字符串                       P2
  BE-QL-41  魔法数字                                 P2
  BE-QL-46  循环内逐条查数据库                        P1
  BE-QL-16  分页返回 Result<PageResult<T>>           P2
  BE-QL-17  分页 DTO 继承 PageQueryDTO               P2
  BE-QL-38  常量类 final + 私有构造                   P2

数据库:
  BE-QL-19  业务表必备审计字段                        P1
  BE-QL-20  主键 BIGINT + 雪花ID                     P1

认证:
  BE-AU-07  密码 BCryptPasswordEncoder 加密           P0
  BE-AU-02  多端 StpKit vs StpUtil                   P1
```

#### 新增（~25 条，来自 coder 规范）：

```
来自 controller-guide.md:
  BE-CT-01  GET 请求禁用 DTO 参数                     P1
  BE-CT-02  分页查询统一 POST                          P2
  BE-CT-03  Controller 参数 >3 个收敛到 DTO            P1
  BE-CT-04  CRUD 操作不用动词（业务动作除外）            P2

来自 service-guide.md:
  BE-SV-01  @Transactional(rollbackFor=Exception.class)  P1
  BE-SV-02  使用 LoginContextHolder 而非直接注入 HttpServletRequest  P1
  BE-SV-03  方法命名符合约定（getById/list/page/create/update/delete）P2

来自 mapper-guide.md:
  BE-MP-01  禁止 @Select/@Update/@Insert 注解写 SQL    P0
  BE-MP-02  Entity 主键 @TableId(type=IdType.ASSIGN_ID)  P1
  BE-MP-03  审计字段 @TableField(fill=...) 必须配置      P1
  BE-MP-04  Mapper 多参数方法必须 @Param                P1
  BE-MP-05  使用 LambdaQueryWrapper 而非 QueryWrapper   P1
  BE-MP-06  状态/类型字段使用 MyBatis-Plus 枚举映射      P2

来自 code-style-guide.md:
  BE-CS-01  DTO 必须有 @NoArgsConstructor              P0
  BE-CS-02  常量类 final + private 构造                 P2
  BE-CS-03  禁止 Lombok @SneakyThrows/@Cleanup         P1
  BE-CS-04  工具类 final + private 构造 + 全 static     P2

来自 database-guide.md:
  BE-DB-01  禁止 AUTO_INCREMENT 自增主键                P1
  BE-DB-02  业务表必须有 deleted 逻辑删除字段            P1
  BE-DB-03  表名统一 sys_ 前缀                          P1
  BE-DB-04  时间字段双层保障（DB default + MetaObjectHandler）P2

来自 result-guide.md:
  BE-RS-01  Controller 返回值统一 Result<T> 包裹        P1
  BE-RS-02  新增/修改/删除用 Result.success() 无 data    P2
  BE-RS-03  成功消息固定 "ok"                           P2

来自 swagger-guide.md:
  BE-SW-01  Controller 类必须有 @Tag                    P2
  BE-SW-02  Controller 方法必须有 @Operation            P2
  BE-SW-03  DTO/VO 字段必须有 @Schema                   P2
```

最终 ai-checklist.yaml 约 40-45 条，覆盖 coder 全部 12 个规范文件。

### 2. review.skill.md（新流程）

不再调用 `code_check.cli scan`（删除），改为 3 步：

**Step 1**: 调用 MCP tool `fuck-u-code analyze` 扫描目标目录，产出 quality.json，写入 `review-output/{run_id}/quality.json`。

**Step 2**: AI 统一审查。输入 ai-checklist.yaml + quality.json + 待审查代码，按固定 schema 输出 findings.json，写入 `review-output/{run_id}/findings.json`。返回 REVIEW_PASSED / REVIEW_FAILED / REVIEW_ERROR。

**Step 3**: 调用 `python3 -m code_check.cli report` 合并 quality.json + findings.json → final-review-report.md。

### 3. models.py（findings 的 JSON Schema）

```python
@dataclass
class SpecViolation:
    rule_id: str        # BE-QL-14
    level: str          # P0 | P1 | P2
    file: str           # auth/controller/AuthController.java
    line: int           # 42
    method: str         # login
    description: str    # 返回裸 Map<String, Object>
    suggestion: str     # 应定义 LoginResultVO，用 Result<LoginResultVO> 包裹

@dataclass
class QualityIssue:
    file: str           # system/service/impl/UserServiceImpl.java
    line: int           # 38
    dimension: str      # N+1查询 | 复杂度 | 重复代码 | 异常处理 | ...
    severity: str       # high | medium | low
    detail: str         # page 方法在 for 循环内逐条调用 userRoleMapper.selectRoleCodesByUserId
    suggestion: str     # 应先收集所有 userId，使用 selectBatchIds 批量查询

@dataclass
class FindingsResult:
    review_status: str          # PASSED | FAILED
    spec_violations: list[SpecViolation]
    quality_issues: list[QualityIssue]
    summary: str                # AI 给出的总结摘要
```

### 4. reporter.py（新渲染器）

```python
def render(quality: dict, findings: dict) -> str:
    """合并两份 JSON 为 Markdown 报告"""
    sections = []
    
    # 块1：静态质量概览
    sections.append(_render_quality_overview(quality))
    # 总分、7 维指标表格、最差文件 Top 10
    
    # 块2：规范合规检查（来自 findings.spec_violations）
    sections.append(_render_spec_compliance(findings["spec_violations"]))
    # 按 P0/P1/P2 分组，每项：文件、行号、方法、规则、问题、建议
    
    # 块3：代码深度问题（来自 findings.quality_issues）
    sections.append(_render_quality_issues(findings["quality_issues"]))
    # 按严重程度分组，每项：文件、维度、详情、建议
    
    # 块4：汇总表
    sections.append(_render_summary(quality, findings))
    # P0/P1/P2 计数、质量评分、是否通过
    
    return "\n\n".join(sections)
```

### 5. cli.py（只保留 report 命令）

```bash
python3 -m code_check.cli report \
  --quality review-output/{run_id}/quality.json \
  --findings review-output/{run_id}/findings.json \
  --output review-output/{run_id}/final-review-report.md
```

删 `scan` 子命令，保留 `report` 子命令，参数从 `--pre` `--ai` 改为 `--quality` `--findings`。

### 6. .mcp.json（新增）

```json
{
  "mcpServers": {
    "fuck-u-code": {
      "command": "npx",
      "args": ["fuck-u-code-mcp"]
    }
  }
}
```

## 数据流

```
[admin-test-XX/src/main/java]
         │
         ├──→ fuck-u-code analyze (MCP)
         │        │
         │        └──→ quality.json
         │              ├─ overall_score: 72
         │              ├─ metrics: {complexity, duplication, size, structure, ...}
         │              └─ worst_files: [{file, score, shit_gas_index}]
         │
         └──→ AI 统一审查
                  │
                  ├─ 读取 ai-checklist.yaml (~40条)
                  ├─ 读取 quality.json（定位最差文件）
                  ├─ 逐个文件检查
                  │   ├─ 规范合规 → spec_violations[]
                  │   └─ 质量问题 → quality_issues[]
                  │
                  └──→ findings.json
                        ├─ review_status: PASSED | FAILED
                        ├─ spec_violations: [...]
                        └─ quality_issues: [...]
                                   │
         ┌─────────────────────────┘
         ↓
    cli.py report
         │
         └──→ final-review-report.md
               ├─ 第1块：静态质量概览
               ├─ 第2块：规范合规检查（P0/P1/P2）
               ├─ 第3块：代码深度问题
               └─ 第4块：汇总表
```

## 错误处理

| 场景 | 策略 |
|------|------|
| fuck-u-code 未安装 | reviewer prompt 提示安装 `npm i -g fuck-u-code`，返回 REVIEW_ERROR |
| MCP 调用超时 | 重试 1 次，仍失败 → quality.json 为空，AI 审查仍继续执行（只做规范合规检查） |
| quality.json 格式不兼容 | reporter 跳过静态质量概览块，其余正常渲染 |
| findings.json 不符合 schema | reporter 报错退出，reviewer 需重新执行 |
| AI 调用失败 | 返回 REVIEW_ERROR，pipeline engine 进入 error 分支 |
| AI 返回格式不合法 | retry 1 次（在 prompt 中强调 schema），仍不合法 → REVIEW_ERROR |

## 验证策略

### 改前验证（不改代码，纯对照）

1. 将 coder 12 个规范文件的每一条规则，对照 ai-checklist.yaml 条目，逐一确认覆盖
2. 验收标准：每个 coder 规范文件中的每一条必须/禁止规则，都能在 ai-checklist.yaml 中找到对应条目

### 改后验证（代码改完后）

1. 对 admin-test-02 的代码跑新流程，产出一份 final-review-report.md
2. 对比 admin-test-02 上一次 REVIEW_PASSED 报告，确认新流程不会漏掉之前发现的 P0/P1 问题
3. 用 review-output 历史数据中的 pre-check-result.json + review-result.json，喂给新 reporter，确认输出格式正确

## 测试策略

| 层级 | 测什么 | 方式 |
|------|------|------|
| ai-checklist.yaml | 每条规则语法正确、有 description 和 level | 简单 Python 脚本校验 YAML 结构 |
| models.py | findings 的 dataclass 序列化/反序列化正常 | 3-5 个单元测试 |
| reporter.py | 给定 quality.json + findings.json，输出正确 Markdown | 5-8 个快照测试（fixture + 期望输出） |
| cli.py | report 命令参数校验、文件不存在报错 | 3-4 个集成测试 |
| 端到端 | 对 admin-test-02 跑完整流程，产出报告 | 手动 + pipeline 执行 |

## 不做

- 不改 pipeline_engine（DAG 调度逻辑不变）
- 不改 build.skill.md（执行循环不变）
- 不改 coder 规范文件
- 不碰 benchmarks 数据采集
- 不做 fuck-u-code 的 MCP server 开发（直接用现成的）
