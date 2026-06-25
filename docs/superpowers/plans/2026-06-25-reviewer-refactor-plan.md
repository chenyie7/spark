# Reviewer 审查系统重构 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前"44 条程序检查 + 17 条 AI 检查"重构为"fuck-u-code 静态分析 + AI 统一审查"，消除程序检查维护成本，引入 7 维代码质量评分。

**Architecture:** review.skill.md 流程从 3 步简化为：fuck-u-code MCP 静态分析 → AI 统一审查（一次调用，同时覆盖规范合规+质量深度分析）→ cli.py report 模板渲染。删除 scanner/config/program-checks/hooks/tests，扩充 ai-checklist.yaml 为唯一审查标准。

**Tech Stack:** Python 3 (dataclasses, argparse, PyYAML), fuck-u-code MCP Server (Node.js/npx), pipeline_engine (DAG 调度，不改)

---

## 文件结构

```
新增:
  .mcp.json                                               # fuck-u-code MCP 配置
  agents/reviewer/check_system/tests/                      # 新测试目录

大改:
  agents/reviewer/check_system/rules/ai-checklist.yaml     # 17→~40条
  agents/reviewer/check_system/code_check/models.py        # 新 findings schema
  agents/reviewer/check_system/code_check/reporter.py      # 新渲染器
  agents/reviewer/check_system/code_check/cli.py           # 只保留 report
  agents/reviewer/review.skill.md                          # 新 3 步流程

小改:
  agents/scheduler/pipeline.yaml                           # reviewer prompt_template
  agents/reviewer/README.md                                # 更新文档

删除:
  agents/reviewer/check_system/code_check/scanner.py
  agents/reviewer/check_system/code_check/config.py
  agents/reviewer/check_system/rules/program-checks.yaml
  agents/reviewer/check_system/code-check-config.yaml
  agents/reviewer/check_system/hooks/
  agents/reviewer/check_system/tests/                      # 旧 65 个测试

不改:
  agents/scheduler/pipeline_engine/                        # 全部不变
  .claude/skills/build/                                    # build.skill.md 不变
  agents/coder/                                            # 12 个规范文件不变
  benchmarks/                                              # 数据采集不变
```

---

### Task 1: 新增 .mcp.json — fuck-u-code MCP 配置

**Files:**
- Create: `.mcp.json`

- [ ] **Step 1: 创建 MCP 配置文件**

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

- [ ] **Step 2: 验证 MCP 配置语法正确**

```bash
python3 -c "import json; json.load(open('.mcp.json'))" && echo "Valid JSON"
```
Expected: `Valid JSON`

- [ ] **Step 3: 确认 fuck-u-code 可安装（不实际安装，只检查 npm registry）**

```bash
npm view fuck-u-code version 2>/dev/null && echo "Package exists" || echo "Package not found — will need npm registry access"
```

- [ ] **Step 4: Commit**

```bash
git add .mcp.json
git commit -m "feat: add fuck-u-code MCP server configuration"
```

---

### Task 2: 扩充 ai-checklist.yaml — 17 条 → 40 条

**Files:**
- Modify: `agents/reviewer/check_system/rules/ai-checklist.yaml`

- [ ] **Step 1: 备份旧文件**

```bash
cp agents/reviewer/check_system/rules/ai-checklist.yaml agents/reviewer/check_system/rules/ai-checklist.yaml.bak
```

- [ ] **Step 2: 写入完整 ai-checklist.yaml**

文件内容如下（保留原有 17 条 + 新增 27 条，共 44 条，按来源分类）：

```yaml
# AI 统一审查清单 — 从 coder/ 全部 12 个规范文件中提取
# 这是 AI 审查的唯一标准输入，审查时逐条对代码执行检查
#
# 来源规范文件:
#   architecture/package-structure-guide.md
#   layered/controller-guide.md
#   layered/service-guide.md
#   layered/mapper-guide.md
#   infrastructure/result-guide.md
#   infrastructure/swagger-guide.md
#   quality/code-style-guide.md
#   quality/database-guide.md

# ═══════════════════════════════════════════════════════════════
# 分层架构 (来自 architecture/ layered/)
# ═══════════════════════════════════════════════════════════════

BE-ST-04:
  description: "Controller 是否直接注入 Mapper"
  level: P0
  check: "检查所有 Controller 类中是否直接注入了 Mapper 接口。Controller 应通过 Service 调用，直接注入 Mapper 违反了分层架构"

BE-ST-05:
  description: "Service 是否只有实现类没有接口"
  level: P1
  check: "检查 service/impl/ 下的每个 ServiceImpl 是否有对应的 Service 接口。Spring AOP 代理（事务、缓存）依赖接口，缺少接口会导致代理失效"

BE-ST-07:
  description: "Service 方法是否返回 Entity 给 Controller"
  level: P1
  check: "检查 Service 实现类中所有 public 方法的返回值类型。Entity 是数据库映射对象，不应暴露到 Controller 层，应转换为 VO 后返回"

BE-ST-18:
  description: "Entity 类命名是否符合规范"
  level: P2
  check: "检查 entity/ 目录下的实体类命名。项目规范支持两种风格：*Entity.java（如 UserEntity.java）或 Sys* 前缀（如 SysUser.java）。只要符合其中一种即可"

# ═══════════════════════════════════════════════════════════════
# Controller 层 (来自 layered/controller-guide.md)
# ═══════════════════════════════════════════════════════════════

BE-CT-01:
  description: "GET 请求是否使用了 DTO 参数（禁止）"
  level: P1
  check: "检查 @GetMapping 方法是否将 DTO 作为参数（不含 @RequestParam 平铺）。GET 请求参数应平铺为 @RequestParam（≤3个）或改用 POST + @RequestBody。若参数 >3 个应收敛到 DTO + POST"

BE-CT-02:
  description: "分页查询是否统一使用 POST"
  level: P2
  check: "检查分页查询方法（方法名含 page 或参数含 PageQueryDTO）是否使用了 @PostMapping。分页查询统一用 POST，便于扩展筛选条件"

BE-CT-03:
  description: "Controller 方法参数 >3 个是否收敛到 DTO"
  level: P1
  check: "检查 Controller 方法签名，如果参数超过 3 个且未使用 DTO 封装，违规。参数 >3 个必须收敛到 DTO + @RequestBody"

BE-CT-04:
  description: "CRUD URL 是否使用了动词（禁止）"
  level: P2
  check: "检查 @RequestMapping 路径和 HTTP 方法。CRUD 操作用标准 RESTful 复数名词（GET/POST/PUT/DELETE /api/users），不用动词。非 CRUD 业务动作（login、logout、cancel、reset-password、assign-roles）允许动词"

# ═══════════════════════════════════════════════════════════════
# Service 层 (来自 layered/service-guide.md)
# ═══════════════════════════════════════════════════════════════

BE-SV-01:
  description: "@Transactional 是否配置 rollbackFor = Exception.class"
  level: P1
  check: "检查 Service Impl 中所有 @Transactional 注解是否包含 rollbackFor = Exception.class。Spring 默认只回滚 RuntimeException，受检异常也必须回滚"

BE-SV-02:
  description: "Service 是否直接注入 HttpServletRequest（禁止）"
  level: P1
  check: "检查 Service 类的字段和构造参数是否包含 HttpServletRequest 或 HttpServletResponse。应使用 LoginContextHolder 获取当前用户信息。直接注入 Servlet API 在定时任务/消息队列场景会 NPE"

BE-SV-03:
  description: "Service 方法命名是否符合约定"
  level: P2
  check: "检查 Service 接口的方法命名：查询单个 getById/getByName，查询列表 list，分页 page，新增 create，修改 update，删除 delete/deleteBatch，状态流转用业务动词如 cancel/resetPassword"

# ═══════════════════════════════════════════════════════════════
# Mapper 层 (来自 layered/mapper-guide.md)
# ═══════════════════════════════════════════════════════════════

BE-MP-01:
  description: "是否使用了 @Select/@Update/@Insert 注解写 SQL（禁止）"
  level: P0
  check: "检查 Mapper 接口方法上是否有 @Select、@Update、@Insert、@Delete 注解。SQL 必须写在 XML 文件中，注解里写 SQL 不可格式化、不可 DTD 校验"

BE-MP-02:
  description: "Entity 主键是否使用 @TableId(type = IdType.ASSIGN_ID) 雪花ID"
  level: P1
  check: "检查所有 Entity 类的 id 字段是否标注 @TableId(type = IdType.ASSIGN_ID)。雪花ID 是分布式环境的标准主键策略，禁止使用自增主键"

BE-MP-03:
  description: "审计字段是否配置了 @TableField(fill = ...) 自动填充"
  level: P1
  check: "检查 Entity 中 createId/createName/createTime/updateId/updateName/updateTime 字段是否标注了 @TableField(fill = FieldFill.INSERT) 或 @TableField(fill = FieldFill.INSERT_UPDATE)。审计字段必须由 MetaObjectHandler 自动填充，不应手动赋值"

BE-MP-04:
  description: "Mapper 多参数方法是否缺少 @Param 注解"
  level: P1
  check: "检查 Mapper 接口中参数 ≥2 个的方法，每个参数是否标注了 @Param 注解。MyBatis 在多参数场景下需要 @Param 才能在 XML 中引用参数名"

BE-MP-05:
  description: "是否使用 QueryWrapper 而非 LambdaQueryWrapper（禁止）"
  level: P1
  check: "检查是否使用了 QueryWrapper 或 UpdateWrapper（非 Lambda 版本）。LambdaQueryWrapper/LambdaUpdateWrapper 编译期安全，字段名不会写错。禁止字符串字段名构建条件"

BE-MP-06:
  description: "状态/类型字段是否使用了 MyBatis-Plus 枚举映射"
  level: P2
  check: "检查 Entity 中的状态、类型等有固定值范围的字段（status、type 等）。应使用 @EnumValue 标注的枚举类型替代 Integer/String 裸值。枚举提供类型安全和编译期检查"

# ═══════════════════════════════════════════════════════════════
# 异常处理 (来自 quality/error-code-reference.md)
# ═══════════════════════════════════════════════════════════════

BE-QL-01:
  description: "是否写了 throw new RuntimeException(\"自由文本\")"
  level: P1
  check: "检查代码中是否直接抛出 new RuntimeException() 或 new Exception() 并传入自由文本。应使用 BusinessException(BusinessErrorEnum.XXX) 替代，确保有统一错误码"

BE-QL-02:
  description: "业务异常是否使用 BusinessException(BusinessErrorEnum.XXX)"
  level: P1
  check: "检查抛出的业务异常是否使用了 BusinessException 并传入了 BusinessErrorEnum 枚举值，而非直接 new BusinessException(\"文本\")"

BE-QL-04:
  description: "Controller 方法是否包裹了 try-catch（禁止）"
  level: P1
  check: "检查 Controller 方法中是否手写了 try-catch 块。应由 GlobalExceptionHandler 统一拦截异常并返回 Result<T> 格式"

BE-QL-05:
  description: "Service 中 catch 异常后是否只打日志不抛出"
  level: P1
  check: "检查 Service 层的 catch 块，确认 catch 后是否只记录了日志但没有向上抛出异常。异常被吞掉会导致事务管理器无法感知错误"

BE-QL-06:
  description: "系统异常是否被 GlobalExceptionHandler 兜底处理"
  level: P2
  check: "检查 GlobalExceptionHandler 中是否有 @ExceptionHandler(Exception.class) 兜底方法，确保非业务异常也能返回统一格式的 Result<T> 错误响应"

# ═══════════════════════════════════════════════════════════════
# 日志质量 (来自 infrastructure/logging-guide.md)
# ═══════════════════════════════════════════════════════════════

BE-QL-11:
  description: "log.info 是否包含关键业务信息（如 orderId、userId）"
  level: P2
  check: "检查 log.info/log.warn 语句是否包含了操作的关键业务标识。log.info(\"创建成功\") 不通过；log.info(\"用户创建成功, userId={}\", userId) 通过"

BE-QL-12:
  description: "循环内是否有大量 log.info"
  level: P2
  check: "检查 for/while 循环体内是否调用了 log.info。循环内逐条打印日志严重影响性能，应移出循环或使用批量日志"

# ═══════════════════════════════════════════════════════════════
# 代码质量 (来自 quality/code-style-guide.md)
# ═══════════════════════════════════════════════════════════════

BE-QL-14:
  description: "是否返回了裸的 String、boolean、Map 或 JSONObject"
  level: P1
  check: "检查 Controller 方法的返回值类型。直接返回 String、boolean、Map、JSONObject 等裸类型破坏了统一响应格式，应使用 Result<T> 包裹或定义专门的 VO 返回"

BE-QL-35:
  description: "集合返回值是否可能为 null"
  level: P1
  check: "检查返回 List、Set、Map 等集合类型的方法，确保所有路径上都返回了非 null 值。返回 null 会导致调用方 NPE，应返回空集合（new ArrayList<>() 或 Collections.emptyList()）"

BE-QL-39:
  description: "循环内是否用 + 拼接字符串"
  level: P2
  check: "检查 for/while 循环内是否存在使用 + 或 += 拼接字符串的代码。循环内每次 + 拼接都创建新 String 对象，应使用 StringBuilder"

BE-QL-41:
  description: "是否存在魔法数字"
  level: P2
  check: "检查代码中是否存在未命名的数字字面量（如 if (status == 1)、sleep(5000)）。应使用枚举或常量替代。循环初始值 int i=0、数学常量等不在此列"

BE-QL-46:
  description: "循环内是否逐条查数据库"
  level: P1
  check: "检查 for/while 循环内是否调用了 Mapper 方法逐条查询或插入。应使用批量方法（selectBatchIds、insertBatch）或一次性 IN 查询替代"

BE-QL-16:
  description: "分页查询是否返回 Result<PageResult<T>>"
  level: P2
  check: "检查 Controller 中执行分页查询的方法是否返回了 Result<PageResult<T>> 格式。通过是否使用 MyBatis-Plus Page<T> 或 IPage<T> 判断"

BE-QL-17:
  description: "分页查询 DTO 是否继承 PageQueryDTO"
  level: P2
  check: "检查被 Controller 分页方法用作参数的 DTO 是否继承了 PageQueryDTO。CreateDTO、UpdateDTO、AssignDTO 等非分页 DTO 不在此检查范围"

BE-QL-38:
  description: "常量类是否 final + 私有构造"
  level: P2
  check: "检查名称为 *Constant、*Constants、*Code、*Codes 的常量类是否声明为 final 并包含私有构造方法。PageQueryDTO 等分页 DTO 不是常量类，不应被标记"

BE-CS-01:
  description: "DTO 是否有 @NoArgsConstructor（Jackson 反序列化需要）"
  level: P0
  check: "检查 dto/ 目录下所有 DTO 类是否标注了 @NoArgsConstructor。Jackson 反序列化 @RequestBody 时需要无参构造器，缺少会导致 400 错误。使用 @Data 的类会自动生成 getter/setter 但不会生成无参构造（如果只有 @AllArgsConstructor）"

BE-CS-02:
  description: "常量类是否 final + private 构造"
  level: P2
  check: "同 BE-QL-38，检查常量类是否 final 且构造器私有。常量类禁止实例化"

BE-CS-03:
  description: "是否使用了禁止的 Lombok 注解 @SneakyThrows/@Cleanup/@Synchronized"
  level: P1
  check: "检查代码中是否使用了 @SneakyThrows、@Cleanup、@Synchronized 注解。这些注解隐藏问题或不如标准写法直观"

BE-CS-04:
  description: "工具类是否 final + private 构造 + 全部 static 方法"
  level: P2
  check: "检查命名为 *Utils 或 *Util 的工具类。必须是 final 类、构造器 private、所有方法 static"

# ═══════════════════════════════════════════════════════════════
# Result 返回体 (来自 infrastructure/result-guide.md)
# ═══════════════════════════════════════════════════════════════

BE-RS-01:
  description: "Controller 返回值是否统一用 Result<T> 包裹"
  level: P1
  check: "检查所有 Controller 方法的返回值类型。所有返回值必须用 Result<T> 包裹，禁止直接返回 VO、String、Map 等裸类型"

BE-RS-02:
  description: "新增/修改/删除操作是否用 Result.success() 无 data 返回"
  level: P2
  check: "检查 @PostMapping（新增）、@PutMapping（修改）、@DeleteMapping（删除）方法的返回。应使用 Result.success() 无参数版本，返回 Result<Void>"

BE-RS-03:
  description: "成功消息是否固定为 \"ok\""
  level: P2
  check: "检查 Result.success() 的调用。成功消息固定为 \"ok\"，不返回自定义文本如 \"添加成功\""

# ═══════════════════════════════════════════════════════════════
# Swagger 文档 (来自 infrastructure/swagger-guide.md)
# ═══════════════════════════════════════════════════════════════

BE-SW-01:
  description: "Controller 类是否标注 @Tag(name = \"模块名\")"
  level: P2
  check: "检查所有 Controller 类是否标注了 @Tag 注解并包含 name 属性"

BE-SW-02:
  description: "Controller 方法是否标注 @Operation(summary = \"描述\")"
  level: P2
  check: "检查所有 Controller 方法是否标注了 @Operation 注解并包含 summary 属性"

BE-SW-03:
  description: "DTO/VO 字段是否标注 @Schema(description = \"...\")"
  level: P2
  check: "检查 dto/ 和 vo/ 目录下所有类的字段是否标注了 @Schema 注解并包含 description 属性。排除 static final 常量字段"

# ═══════════════════════════════════════════════════════════════
# 数据库规范 (来自 quality/database-guide.md)
# ═══════════════════════════════════════════════════════════════

BE-QL-19:
  description: "业务表是否包含必备审计字段"
  level: P1
  check: "检查建表 SQL 和 Entity 类，确认业务表是否包含 id、create_id、create_name、create_time、update_id、update_name、update_time、deleted 等必备审计字段。日志表、多对多中间表可以不包含"

BE-QL-20:
  description: "主键是否使用 BIGINT + 雪花ID"
  level: P1
  check: "检查 Entity 类和建表 SQL，主键 id 应为 BIGINT（Java Long），并用雪花ID 策略（@TableId(type = IdType.ASSIGN_ID)），禁止自增主键"

BE-DB-01:
  description: "是否使用了 AUTO_INCREMENT 自增主键（禁止）"
  level: P1
  check: "检查建表 SQL 中是否包含 AUTO_INCREMENT。分布式环境下自增主键会产生冲突，所有表统一使用雪花ID"

BE-DB-02:
  description: "业务表是否有 deleted 逻辑删除字段"
  level: P1
  check: "检查建表 SQL 和 Entity 类，业务表必须包含 deleted 字段（TINYINT DEFAULT 0）。中间表和日志表可以不包含"

BE-DB-03:
  description: "表名是否统一 sys_ 前缀"
  level: P1
  check: "检查建表 SQL 中业务表的命名，是否使用了 sys_ 前缀（如 sys_user、sys_role）。业务表统一前缀便于识别和管理"

BE-DB-04:
  description: "时间字段是否有双层保障（DB DEFAULT + MetaObjectHandler）"
  level: P2
  check: "检查建表 SQL 中 create_time 是否有 DEFAULT CURRENT_TIMESTAMP，update_time 是否有 DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP。同时检查 MetaObjectHandler 是否配置了对应的自动填充"

# ═══════════════════════════════════════════════════════════════
# 认证安全 (来自 auth/)
# ═══════════════════════════════════════════════════════════════

BE-AU-07:
  description: "登录密码是否使用 BCryptPasswordEncoder 加密"
  level: P0
  check: "检查涉及用户密码操作的 Service 类中，密码是否通过 BCryptPasswordEncoder.encode() 加密后再存储。重点关注 AuthService 的登录/注册和 UserService 的创建用户/修改密码方法。不处理密码的 Service 不在此范围"

BE-AU-02:
  description: "多端场景下是否直接使用 StpUtil 而未通过 StpKit 门面"
  level: P1
  check: "先读取 agents/coder/auth/auth-basic.md 确认项目的 Sa-Token 使用策略。纯后台管理项目允许直接使用 StpUtil；多端项目应使用 StpKit 门面隔离不同端的会话。根据项目实际配置判断"
```

- [ ] **Step 3: 验证 YAML 语法正确**

```bash
python3 -c "import yaml; yaml.safe_load(open('agents/reviewer/check_system/rules/ai-checklist.yaml')); print('YAML valid')"
```
Expected: `YAML valid`

- [ ] **Step 4: 统计条目数确认覆盖完整**

```bash
python3 -c "
import yaml
with open('agents/reviewer/check_system/rules/ai-checklist.yaml') as f:
    data = yaml.safe_load(f)
p0 = sum(1 for v in data.values() if v['level'] == 'P0')
p1 = sum(1 for v in data.values() if v['level'] == 'P1')
p2 = sum(1 for v in data.values() if v['level'] == 'P2')
print(f'Total: {len(data)} rules (P0={p0}, P1={p1}, P2={p2})')
"
```
Expected: `Total: 44 rules (P0=4, P1=22, P2=18)`

- [ ] **Step 5: Commit**

```bash
git add agents/reviewer/check_system/rules/ai-checklist.yaml
git commit -m "feat: expand ai-checklist.yaml from 17 to 44 rules covering all 12 coder spec files"
```

---

### Task 3: 重写 models.py — 新 findings schema

**Files:**
- Modify: `agents/reviewer/check_system/code_check/models.py`

- [ ] **Step 1: 写入新 models.py**

```python
"""Data models for the review system — findings schema only.

After the refactor, this module only defines the structured output
that the AI reviewer must produce (findings.json).  Quality data
from fuck-u-code is passed through as a raw dict — no model needed.
"""

from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class SpecViolation:
    """A single spec-compliance violation found by the AI reviewer."""

    rule_id: str          # e.g. "BE-QL-14"
    level: str            # "P0" | "P1" | "P2"
    file: str             # relative path, e.g. "auth/controller/AuthController.java"
    line: int             # line number where the violation occurs
    method: str           # method name, e.g. "login"
    description: str      # what the violation is
    suggestion: str       # how to fix it

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "level": self.level,
            "file": self.file,
            "line": self.line,
            "method": self.method,
            "description": self.description,
            "suggestion": self.suggestion,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpecViolation":
        return cls(
            rule_id=d["rule_id"],
            level=d["level"],
            file=d["file"],
            line=d["line"],
            method=d.get("method", "-"),
            description=d["description"],
            suggestion=d.get("suggestion", ""),
        )


@dataclass
class QualityIssue:
    """A code-quality issue found by the AI reviewer (often guided by fuck-u-code scores)."""

    file: str             # relative path
    line: int             # line number
    dimension: str        # "N+1查询" | "复杂度" | "重复代码" | "异常处理" | "命名" | ...
    severity: str         # "high" | "medium" | "low"
    detail: str           # description of the issue
    suggestion: str       # how to fix it

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "dimension": self.dimension,
            "severity": self.severity,
            "detail": self.detail,
            "suggestion": self.suggestion,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QualityIssue":
        return cls(
            file=d["file"],
            line=d["line"],
            dimension=d["dimension"],
            severity=d["severity"],
            detail=d["detail"],
            suggestion=d.get("suggestion", ""),
        )


@dataclass
class FindingsResult:
    """Top-level result produced by the AI unified review."""

    review_status: str   # "PASSED" | "FAILED"
    spec_violations: list[dict] = field(default_factory=list)
    quality_issues: list[dict] = field(default_factory=list)
    summary: str = ""

    def has_p0(self) -> bool:
        return any(v.get("level") == "P0" for v in self.spec_violations)

    def has_p1(self) -> bool:
        return any(v.get("level") == "P1" for v in self.spec_violations)

    def p0_count(self) -> int:
        return sum(1 for v in self.spec_violations if v.get("level") == "P0")

    def p1_count(self) -> int:
        return sum(1 for v in self.spec_violations if v.get("level") == "P1")

    def p2_count(self) -> int:
        return sum(1 for v in self.spec_violations if v.get("level") == "P2")

    def quality_high_count(self) -> int:
        return sum(1 for q in self.quality_issues if q.get("severity") == "high")

    def quality_medium_count(self) -> int:
        return sum(1 for q in self.quality_issues if q.get("severity") == "medium")

    def quality_low_count(self) -> int:
        return sum(1 for q in self.quality_issues if q.get("severity") == "low")

    def to_dict(self) -> dict:
        return {
            "review_status": self.review_status,
            "spec_violations": self.spec_violations,
            "quality_issues": self.quality_issues,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FindingsResult":
        return cls(
            review_status=d["review_status"],
            spec_violations=d.get("spec_violations", []),
            quality_issues=d.get("quality_issues", []),
            summary=d.get("summary", ""),
        )
```

- [ ] **Step 2: 验证模块可导入**

```bash
cd agents/reviewer/check_system && python3 -c "from code_check.models import FindingsResult, SpecViolation, QualityIssue; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agents/reviewer/check_system/code_check/models.py
git commit -m "feat: rewrite models.py to FindingsResult schema for unified AI review"
```

---

### Task 4: 重写 reporter.py — quality.json + findings.json → Markdown

**Files:**
- Modify: `agents/reviewer/check_system/code_check/reporter.py`

- [ ] **Step 1: 写入新 reporter.py**

```python
"""Report renderer — merges quality.json (fuck-u-code) and findings.json (AI review)
into a single Markdown report with four sections."""

from pathlib import Path
from typing import Any


def _file_short(full_path: str) -> str:
    """Strip the common prefix to get a short relative path."""
    return Path(full_path).name if "/" in full_path else full_path


def render(quality: dict | None, findings: dict) -> str:
    """Merge quality and findings into a complete Markdown report.

    Args:
        quality: Raw quality.json from fuck-u-code (can be None if analysis failed).
        findings: Raw findings.json from the AI unified review.

    Returns:
        Complete Markdown string with four sections.
    """
    sections: list[str] = []

    # -- Header --
    sections.append(_render_header(quality, findings))

    # -- Section 1: Quality overview (from fuck-u-code) --
    if quality:
        sections.append(_render_quality_overview(quality))

    # -- Section 2: Spec compliance (from findings.spec_violations) --
    sections.append(_render_spec_compliance(findings.get("spec_violations", [])))

    # -- Section 3: Quality issues (from findings.quality_issues) --
    sections.append(_render_quality_issues(findings.get("quality_issues", [])))

    # -- Section 4: Summary table --
    sections.append(_render_summary(quality, findings))

    # -- Conclusion --
    sections.append(_render_conclusion(findings))

    return "\n\n".join(sections)


# ── Header ──────────────────────────────────────────────────────

def _render_header(quality: dict | None, findings: dict) -> str:
    status = findings.get("review_status", "UNKNOWN")
    icon = "✅" if status == "PASSED" else ("❌" if status == "FAILED" else "⚠️")

    lines = [
        "# 代码审查报告",
        "",
        f"**状态**: {icon} {status}",
    ]

    if quality:
        scan_path = quality.get("scan_path", "-")
        file_count = quality.get("file_count", 0)
        overall = quality.get("overall_score", "-")
        lines.append(f"**扫描路径**: {scan_path}")
        lines.append(f"**文件数量**: {file_count} 个")
        lines.append(f"**质量评分**: {overall}/100")

    return "\n".join(lines)


# ── Section 1: Quality Overview ─────────────────────────────────

def _render_quality_overview(quality: dict) -> str:
    lines = ["## 静态质量概览", ""]

    overall = quality.get("overall_score", "-")
    lines.append(f"**总体评分**: {overall}/100")
    lines.append("")

    # Metrics table
    metrics = quality.get("metrics", {})
    if metrics:
        lines.append("| 维度 | 得分 |")
        lines.append("|------|------|")
        for dim, score in metrics.items():
            lines.append(f"| {dim} | {score} |")
        lines.append("")

    # Worst files
    worst = quality.get("worst_files", [])
    if worst:
        lines.append("### 最差文件 Top 10")
        lines.append("")
        lines.append("| 文件 | 评分 | Shit-Gas |")
        lines.append("|------|------|------|")
        for w in worst[:10]:
            name = _file_short(w.get("file", ""))
            score = w.get("score", "-")
            sgi = w.get("shit_gas_index", "-")
            lines.append(f"| {name} | {score} | {sgi} |")
        lines.append("")

    return "\n".join(lines)


# ── Section 2: Spec Compliance ──────────────────────────────────

def _render_spec_compliance(violations: list[dict]) -> str:
    lines = ["## 规范合规检查", ""]

    if not violations:
        lines.append("✅ 所有规范合规检查通过，未发现违规。")
        return "\n".join(lines)

    # Group by level
    by_level: dict[str, list[dict]] = {"P0": [], "P1": [], "P2": []}
    for v in violations:
        level = v.get("level", "P2")
        by_level.setdefault(level, []).append(v)

    level_labels = {"P0": "\U0001f534 P0 (阻断级)", "P1": "\U0001f7e1 P1", "P2": "\U0001f7e2 P2"}
    for level in ("P0", "P1", "P2"):
        items = by_level.get(level, [])
        if not items:
            lines.append(f"### {level_labels[level]} (0项)")
            lines.append("_ _")
            lines.append("")
            continue

        lines.append(f"### {level_labels[level]} ({len(items)}项)")
        lines.append("")
        lines.append("| 文件 | 行号 | 方法 | 规则 | 问题 | 建议 |")
        lines.append("|------|------|------|------|------|------|")
        for v in items:
            fname = _file_short(v.get("file", "-"))
            line = v.get("line", 0)
            method = v.get("method", "-")
            rule = v.get("rule_id", "-")
            desc = v.get("description", "")
            sug = v.get("suggestion", "-")
            lines.append(f"| {fname} | {line} | {method} | {rule} | {desc} | {sug} |")
        lines.append("")

    return "\n".join(lines)


# ── Section 3: Quality Issues ───────────────────────────────────

def _render_quality_issues(issues: list[dict]) -> str:
    lines = ["## 代码深度问题", ""]

    if not issues:
        lines.append("✅ 未发现深度质量问题。")
        return "\n".join(lines)

    # Group by severity
    by_sev: dict[str, list[dict]] = {"high": [], "medium": [], "low": []}
    for q in issues:
        sev = q.get("severity", "low")
        by_sev.setdefault(sev, []).append(q)

    sev_labels = {"high": "\U0001f534 高", "medium": "\U0001f7e1 中", "low": "\U0001f7e2 低"}
    for sev in ("high", "medium", "low"):
        items = by_sev.get(sev, [])
        if not items:
            continue
        lines.append(f"### {sev_labels[sev]} ({len(items)}项)")
        lines.append("")
        lines.append("| 文件 | 行号 | 维度 | 详情 | 建议 |")
        lines.append("|------|------|------|------|------|")
        for q in items:
            fname = _file_short(q.get("file", "-"))
            line = q.get("line", 0)
            dim = q.get("dimension", "-")
            detail = q.get("detail", "")
            sug = q.get("suggestion", "-")
            lines.append(f"| {fname} | {line} | {dim} | {detail} | {sug} |")
        lines.append("")

    return "\n".join(lines)


# ── Section 4: Summary ──────────────────────────────────────────

def _render_summary(quality: dict | None, findings: dict) -> str:
    lines = ["## 汇总", ""]

    violations = findings.get("spec_violations", [])
    issues = findings.get("quality_issues", [])

    p0 = sum(1 for v in violations if v.get("level") == "P0")
    p1 = sum(1 for v in violations if v.get("level") == "P1")
    p2 = sum(1 for v in violations if v.get("level") == "P2")
    q_high = sum(1 for q in issues if q.get("severity") == "high")
    q_med = sum(1 for q in issues if q.get("severity") == "medium")
    q_low = sum(1 for q in issues if q.get("severity") == "low")

    lines.append("| 来源 | P0 | P1 | P2 | 高 | 中 | 低 |")
    lines.append("|------|----|----|----|----|----|----|")
    lines.append(f"| 规范合规 | {p0} | {p1} | {p2} | — | — | — |")
    lines.append(f"| 代码质量 | — | — | — | {q_high} | {q_med} | {q_low} |")

    if quality:
        overall = quality.get("overall_score", "-")
        lines.append(f"\n**代码质量评分**: {overall}/100")

    return "\n".join(lines)


# ── Conclusion ──────────────────────────────────────────────────

def _render_conclusion(findings: dict) -> str:
    status = findings.get("review_status", "UNKNOWN")
    violations = findings.get("spec_violations", [])
    summary = findings.get("summary", "")

    lines = ["## 结论", ""]

    p0 = sum(1 for v in violations if v.get("level") == "P0")
    p1 = sum(1 for v in violations if v.get("level") == "P1")

    if status == "PASSED":
        lines.append(f"✅ 通过 — 规范合规检查和代码质量分析均通过。")
    elif status == "FAILED":
        lines.append(f"❌ 未通过 — 存在 P0={p0}, P1={p1} 级问题，需修复后重新提交审查。")
    else:
        lines.append(f"⚠️ {status}")

    if summary:
        lines.append(f"\n{summary}")

    return "\n".join(lines)


# ── Top-level file writer ───────────────────────────────────────

def generate_report(
    quality: dict | None,
    findings: dict,
    output_path: Path,
) -> None:
    """Write the combined Markdown report to *output_path*."""
    md = render(quality, findings)
    output_path.write_text(md, encoding="utf-8")
```

- [ ] **Step 2: 验证模块可导入**

```bash
cd agents/reviewer/check_system && python3 -c "from code_check.reporter import render, generate_report; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: 用 fixture 数据验证渲染输出**

```bash
cd agents/reviewer/check_system && python3 -c "
import json
from pathlib import Path
from code_check.reporter import render

# Minimal fixture
quality = {
    'overall_score': 72,
    'scan_path': 'admin-test-02/src/main/java',
    'file_count': 99,
    'metrics': {'complexity': 8.2, 'duplication': 6.5, 'size': 7.0, 'naming': 8.5},
    'worst_files': [{'file': 'UserServiceImpl.java', 'score': 45, 'shit_gas_index': 82}]
}
findings = {
    'review_status': 'FAILED',
    'spec_violations': [
        {'rule_id': 'BE-QL-14', 'level': 'P1', 'file': 'auth/controller/AuthController.java', 'line': 42, 'method': 'login', 'description': '返回裸Map', 'suggestion': '使用LoginResultVO'}
    ],
    'quality_issues': [
        {'file': 'system/service/impl/UserServiceImpl.java', 'line': 38, 'dimension': 'N+1查询', 'severity': 'high', 'detail': '循环内逐条查数据库', 'suggestion': '使用selectBatchIds'}
    ],
    'summary': 'P1=1, 质量高=1'
}
md = render(quality, findings)
print(md[:500])
print('...')
print(f'Total Markdown length: {len(md)} chars')
"
```
Expected: Markdown output with header, quality overview, spec compliance table, quality issues table, summary table, and conclusion.

- [ ] **Step 4: Commit**

```bash
git add agents/reviewer/check_system/code_check/reporter.py
git commit -m "feat: rewrite reporter.py to merge quality.json + findings.json into unified report"
```

---

### Task 5: 重写 cli.py — 只保留 report 命令

**Files:**
- Modify: `agents/reviewer/check_system/code_check/cli.py`

- [ ] **Step 1: 写入新 cli.py**

```python
#!/usr/bin/env python3
"""code-check CLI — report-only entry point after reviewer refactor."""

import argparse
import json
import sys
from pathlib import Path

from code_check.reporter import generate_report


def load_json(path: Path) -> dict:
    """Load a JSON file, returning {} if missing or malformed."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: Failed to parse '{path}': {e}", file=sys.stderr)
        sys.exit(1)


def cmd_report(args):
    """Merge quality.json + findings.json → final-report.md."""
    quality_path = Path(args.quality)
    findings_path = Path(args.findings)
    output_path = Path(args.output)

    if not findings_path.exists():
        print(f"Error: findings.json not found: {findings_path}", file=sys.stderr)
        sys.exit(1)

    if not quality_path.exists():
        print(f"Warning: quality.json not found: {quality_path} — quality overview will be skipped", file=sys.stderr)

    quality = load_json(quality_path) if quality_path.exists() else None
    findings = load_json(findings_path)

    if not findings:
        print("Error: findings.json is empty or invalid", file=sys.stderr)
        sys.exit(1)

    generate_report(quality, findings, output_path)
    print(f"Final report -> {output_path}")


def main():
    parser = argparse.ArgumentParser(prog="code-check", description="Review report generator")
    sub = parser.add_subparsers(dest="command")

    # report — the only command after refactor
    p_report = sub.add_parser("report", help="Generate final Markdown report")
    p_report.add_argument("--quality", required=True, help="quality.json from fuck-u-code analyze")
    p_report.add_argument("--findings", required=True, help="findings.json from AI unified review")
    p_report.add_argument("--output", required=True, help="Output Markdown path")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "report":
        cmd_report(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证 CLI --help**

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli --help
```
Expected: usage with `report` subcommand, no `scan`

- [ ] **Step 3: 验证 report --help**

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli report --help
```
Expected: `--quality`, `--findings`, `--output` arguments

- [ ] **Step 4: 用 fixture 数据跑通 report 命令**

```bash
cd agents/reviewer/check_system && \
TMPDIR=$(mktemp -d) && \
echo '{"overall_score":72,"metrics":{},"worst_files":[]}' > "$TMPDIR/quality.json" && \
echo '{"review_status":"PASSED","spec_violations":[],"quality_issues":[],"summary":""}' > "$TMPDIR/findings.json" && \
python3 -m code_check.cli report --quality "$TMPDIR/quality.json" --findings "$TMPDIR/findings.json" --output "$TMPDIR/final-report.md" && \
echo "--- Report content ---" && cat "$TMPDIR/final-report.md" && \
rm -rf "$TMPDIR"
```
Expected: Final report -> .../final-report.md with PASSED status

- [ ] **Step 5: 验证 findings.json 缺失时报错**

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli report --quality /dev/null --findings /nonexistent/findings.json --output /tmp/out.md 2>&1; echo "Exit: $?"
```
Expected: `Error: findings.json not found` and non-zero exit

- [ ] **Step 6: Commit**

```bash
git add agents/reviewer/check_system/code_check/cli.py
git commit -m "feat: rewrite cli.py to report-only, removing scan subcommand"
```

---

### Task 6: 更新 review.skill.md — 新 3 步流程

**Files:**
- Modify: `agents/reviewer/review.skill.md`

- [ ] **Step 1: 写入新 review.skill.md**

```markdown
---
name: review
description: 代码审查 —— fuck-u-code 静态分析 + AI 统一审查，输出完整审查报告
---

# /review — 代码审查

用法：`/review <path>`，`path` 是要扫描的 Java 代码路径，默认 `src/main/java`。

---

## 执行流程

### Step 1: fuck-u-code 静态分析

调用 MCP tool `fuck-u-code analyze` 扫描目标目录。

- 产出 `quality.json`：总体评分、7 维指标、最差文件排行
- 耗时 ~5s，零 Token
- 保存到 `review-output/{run_id}/quality.json`

如果 MCP 调用失败（fuck-u-code 未安装或超时），记录警告，跳过本步，继续 Step 2。
不阻断流程。

### Step 2: AI 统一审查

读取以下输入，执行一次 AI 审查，同时完成规范合规检查和代码深度分析：

**输入：**
- `agents/reviewer/check_system/rules/ai-checklist.yaml` — 审查清单（44 条）
- `review-output/{run_id}/quality.json` — 静态分析结果（如存在）
- `{path}` 下的 Java 源文件

**输出：** `review-output/{run_id}/findings.json`，按以下 schema：

```json
{
  "review_status": "PASSED | FAILED",
  "spec_violations": [
    {
      "rule_id": "BE-QL-14",
      "level": "P0 | P1 | P2",
      "file": "相对路径",
      "line": 42,
      "method": "方法名",
      "description": "问题描述",
      "suggestion": "修复建议"
    }
  ],
  "quality_issues": [
    {
      "file": "相对路径",
      "line": 38,
      "dimension": "N+1查询 | 复杂度 | 重复代码 | ...",
      "severity": "high | medium | low",
      "detail": "问题详情",
      "suggestion": "修复建议"
    }
  ],
  "summary": "AI 给出的总结摘要"
}
```

**判定逻辑：**
- P0 > 0 → `REVIEW_FAILED`
- P1 > 0 且阻断策略 strict → `REVIEW_FAILED`
- 其他 → `REVIEW_PASSED`

### Step 3: 合并最终报告

```bash
cd agents/reviewer/check_system && python3 -m code_check.cli report \
  --quality ../../../review-output/{run_id}/quality.json \
  --findings ../../../review-output/{run_id}/findings.json \
  --output ../../../review-output/{run_id}/final-review-report.md
```

将生成的 `review-output/{run_id}/final-review-report.md` 内容展示给用户。

---

## 返回协议

| 返回值 | 含义 |
|--------|------|
| `REVIEW_PASSED` | 静态分析完成，AI 审查通过，产物完整 |
| `REVIEW_FAILED` | AI 审查发现 P0 问题，或 P1 触发阻断 |
| `REVIEW_ERROR` | 环境/工具异常（python3 不可用、fuck-u-code 未安装且无法继续等） |
```

- [ ] **Step 2: Commit**

```bash
git add agents/reviewer/review.skill.md
git commit -m "feat: rewrite review.skill.md for unified AI review + fuck-u-code flow"
```

---

### Task 7: 更新 pipeline.yaml — reviewer prompt_template

**Files:**
- Modify: `agents/scheduler/pipeline.yaml`

- [ ] **Step 1: 定位 reviewer 的 prompt_template 并替换**

找到 `agents/scheduler/pipeline.yaml` 中 `id: reviewer` 节点下的 `prompt_template` 字段，替换为：

```yaml
    prompt_template: |
      你是 review agent。请严格按以下步骤执行，不可跳过任何步骤。

      1. 调用 MCP tool `fuck-u-code analyze` 扫描 {target_dir}/src/main/java
         产出 quality.json，保存到 review-output/{run_id}/quality.json
         （如 MCP 调用失败，记录警告后继续第 2 步）

      2. 读取 agents/reviewer/check_system/rules/ai-checklist.yaml（44条审查清单）
         读取 review-output/{run_id}/quality.json（如存在）
         对 {target_dir}/src/main/java 下所有 Java 文件执行统一审查：
         - 逐条对照 ai-checklist 检查规范合规 → spec_violations[]
         - 对 quality.json 标红的高分文件做深度分析 → quality_issues[]

      3. 按固定 JSON schema 输出 findings.json，写入 review-output/{run_id}/findings.json
         判定 review_status: P0>0 → FAILED, 否则 PASSED

      4. 调用 python3 -m code_check.cli report 合并 quality.json + findings.json → final-review-report.md

      返回: REVIEW_PASSED / REVIEW_FAILED / REVIEW_ERROR
```

- [ ] **Step 2: Commit**

```bash
git add agents/scheduler/pipeline.yaml
git commit -m "feat: update reviewer prompt_template for unified AI review flow"
```

---

### Task 8: 删除旧文件

**Files:**
- Delete: `agents/reviewer/check_system/code_check/scanner.py`
- Delete: `agents/reviewer/check_system/code_check/config.py`
- Delete: `agents/reviewer/check_system/rules/program-checks.yaml`
- Delete: `agents/reviewer/check_system/code-check-config.yaml`
- Delete: `agents/reviewer/check_system/hooks/` (整个目录)
- Delete: `agents/reviewer/check_system/tests/` (整个目录)

- [ ] **Step 1: 删除旧文件**

```bash
rm agents/reviewer/check_system/code_check/scanner.py
rm agents/reviewer/check_system/code_check/config.py
rm agents/reviewer/check_system/rules/program-checks.yaml
rm agents/reviewer/check_system/code-check-config.yaml
rm -rf agents/reviewer/check_system/hooks
rm -rf agents/reviewer/check_system/tests
```

- [ ] **Step 2: 验证删除后 code_check 包仍可导入**

```bash
cd agents/reviewer/check_system && python3 -c "from code_check.models import FindingsResult; from code_check.reporter import render; from code_check.cli import main; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add -A agents/reviewer/check_system/
git commit -m "feat: remove scanner, config, program-checks, hooks, and old tests — replaced by fuck-u-code + unified AI review"
```

---

### Task 9: 编写新测试

**Files:**
- Create: `agents/reviewer/check_system/tests/__init__.py`
- Create: `agents/reviewer/check_system/tests/conftest.py`
- Create: `agents/reviewer/check_system/tests/test_models.py`
- Create: `agents/reviewer/check_system/tests/test_reporter.py`
- Create: `agents/reviewer/check_system/tests/test_cli.py`

- [ ] **Step 1: 创建 tests/__init__.py**

```python
# Test package for code-check
```

- [ ] **Step 2: 创建 conftest.py — 共享 fixture**

```python
import json
import pytest
from pathlib import Path


@pytest.fixture
def sample_quality() -> dict:
    return {
        "overall_score": 72,
        "scan_path": "admin-test-02/src/main/java",
        "file_count": 99,
        "metrics": {
            "complexity": 8.2,
            "duplication": 6.5,
            "size": 7.0,
            "structure": 7.8,
            "error_handling": 6.0,
            "naming": 8.5,
            "comments": 5.5,
        },
        "worst_files": [
            {"file": "UserServiceImpl.java", "score": 45, "shit_gas_index": 82},
            {"file": "AuthController.java", "score": 52, "shit_gas_index": 70},
        ],
    }


@pytest.fixture
def sample_findings_passed() -> dict:
    return {
        "review_status": "PASSED",
        "spec_violations": [],
        "quality_issues": [],
        "summary": "All checks passed.",
    }


@pytest.fixture
def sample_findings_failed() -> dict:
    return {
        "review_status": "FAILED",
        "spec_violations": [
            {
                "rule_id": "BE-QL-14",
                "level": "P1",
                "file": "auth/controller/AuthController.java",
                "line": 42,
                "method": "login",
                "description": "返回裸 Map<String, Object>",
                "suggestion": "使用 LoginResultVO",
            },
            {
                "rule_id": "BE-AU-07",
                "level": "P0",
                "file": "auth/service/impl/AuthServiceImpl.java",
                "line": 56,
                "method": "login",
                "description": "密码使用 MD5 而非 BCrypt",
                "suggestion": "使用 passwordEncoder.matches()",
            },
        ],
        "quality_issues": [
            {
                "file": "system/service/impl/UserServiceImpl.java",
                "line": 38,
                "dimension": "N+1查询",
                "severity": "high",
                "detail": "在 stream.map() 内逐条查数据库",
                "suggestion": "先收集所有 ID，使用 selectBatchIds 批量查询",
            },
        ],
        "summary": "P0=1, P1=1, 质量高=1",
    }


@pytest.fixture
def sample_findings_empty_quality() -> dict:
    return {
        "review_status": "PASSED",
        "spec_violations": [],
        "quality_issues": [],
        "summary": "",
    }
```

- [ ] **Step 3: 创建 test_models.py**

```python
from code_check.models import (
    FindingsResult,
    SpecViolation,
    QualityIssue,
)


class TestSpecViolation:
    def test_to_dict(self):
        v = SpecViolation(
            rule_id="BE-QL-14", level="P1",
            file="AuthController.java", line=42, method="login",
            description="裸Map", suggestion="用VO",
        )
        d = v.to_dict()
        assert d["rule_id"] == "BE-QL-14"
        assert d["level"] == "P1"
        assert d["file"] == "AuthController.java"
        assert d["line"] == 42

    def test_from_dict(self):
        d = {
            "rule_id": "BE-QL-14", "level": "P1",
            "file": "AuthController.java", "line": 42, "method": "login",
            "description": "裸Map", "suggestion": "用VO",
        }
        v = SpecViolation.from_dict(d)
        assert v.rule_id == "BE-QL-14"
        assert v.line == 42


class TestQualityIssue:
    def test_to_dict(self):
        q = QualityIssue(
            file="UserServiceImpl.java", line=38,
            dimension="N+1查询", severity="high",
            detail="逐条查库", suggestion="批量查询",
        )
        d = q.to_dict()
        assert d["dimension"] == "N+1查询"
        assert d["severity"] == "high"

    def test_from_dict(self):
        d = {
            "file": "UserServiceImpl.java", "line": 38,
            "dimension": "N+1查询", "severity": "high",
            "detail": "逐条查库", "suggestion": "批量查询",
        }
        q = QualityIssue.from_dict(d)
        assert q.file == "UserServiceImpl.java"
        assert q.severity == "high"


class TestFindingsResult:
    def test_passed(self, sample_findings_passed):
        r = FindingsResult.from_dict(sample_findings_passed)
        assert r.review_status == "PASSED"
        assert r.p0_count() == 0
        assert not r.has_p0()

    def test_failed(self, sample_findings_failed):
        r = FindingsResult.from_dict(sample_findings_failed)
        assert r.review_status == "FAILED"
        assert r.p0_count() == 1
        assert r.p1_count() == 1
        assert r.p2_count() == 0
        assert r.has_p0()
        assert r.quality_high_count() == 1

    def test_to_dict_roundtrip(self, sample_findings_failed):
        r = FindingsResult.from_dict(sample_findings_failed)
        d = r.to_dict()
        assert d["review_status"] == "FAILED"
        assert len(d["spec_violations"]) == 2
        assert len(d["quality_issues"]) == 1
```

- [ ] **Step 4: 创建 test_reporter.py**

```python
from code_check.reporter import render


class TestRender:
    def test_passed_report(self, sample_quality, sample_findings_passed):
        md = render(sample_quality, sample_findings_passed)
        assert "PASSED" in md
        assert "静态质量概览" in md
        assert "规范合规检查" in md
        assert "代码深度问题" in md
        assert "汇总" in md

    def test_failed_report(self, sample_quality, sample_findings_failed):
        md = render(sample_quality, sample_findings_failed)
        assert "FAILED" in md
        assert "BE-QL-14" in md
        assert "BE-AU-07" in md
        assert "N+1查询" in md
        assert "P0" in md

    def test_no_quality(self, sample_findings_passed):
        md = render(None, sample_findings_passed)
        assert "PASSED" in md
        assert "静态质量概览" not in md

    def test_empty_violations_shows_pass_banner(self, sample_quality, sample_findings_passed):
        md = render(sample_quality, sample_findings_passed)
        assert "所有规范合规检查通过" in md

    def test_empty_issues_shows_pass_banner(self, sample_quality, sample_findings_passed):
        md = render(sample_quality, sample_findings_passed)
        assert "未发现深度质量问题" in md
```

- [ ] **Step 5: 创建 test_cli.py**

```python
import json
import subprocess
import sys
from pathlib import Path


def _run_report(quality_path: str, findings_path: str, output_path: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "code_check.cli", "report",
         "--quality", quality_path, "--findings", findings_path, "--output", output_path],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent,
    )


class TestCliReport:
    def test_report_generates_file(self, tmp_path, sample_quality, sample_findings_passed):
        quality_file = tmp_path / "quality.json"
        findings_file = tmp_path / "findings.json"
        output_file = tmp_path / "report.md"

        quality_file.write_text(json.dumps(sample_quality))
        findings_file.write_text(json.dumps(sample_findings_passed))

        result = _run_report(str(quality_file), str(findings_file), str(output_file))
        assert result.returncode is None or result.returncode == 0

        assert output_file.exists()
        content = output_file.read_text()
        assert "PASSED" in content

    def test_report_missing_findings_exits_error(self, tmp_path):
        result = _run_report("/dev/null", "/nonexistent/f.json", str(tmp_path / "out.md"))
        assert result.returncode is None or result.returncode != 0

    def test_report_missing_quality_warns(self, tmp_path, sample_findings_passed):
        findings_file = tmp_path / "findings.json"
        output_file = tmp_path / "report.md"

        findings_file.write_text(json.dumps(sample_findings_passed))

        result = _run_report("/nonexistent/q.json", str(findings_file), str(output_file))
        # Should still succeed — quality.json is optional
        assert output_file.exists()
```

- [ ] **Step 6: 运行测试确认全部通过**

```bash
cd agents/reviewer/check_system && python3 -m pip install pytest -q 2>/dev/null; python3 -m pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add agents/reviewer/check_system/tests/
git commit -m "feat: add tests for models, reporter, and CLI (report command)"
```

---

### Task 10: 端到端验证

**Files:**
- 无新建，在 admin-test-02 上跑完整新流程

- [ ] **Step 1: 测试 findings.json → report 渲染**

用 admin-test-02 上一次审查的 review-result.json 的数据结构，手动构造一份符合新 schema 的 findings.json，验证 reporter 输出。

```bash
cd agents/reviewer/check_system && \
TMPDIR=$(mktemp -d) && \
python3 -c "
import json
findings = {
    'review_status': 'FAILED',
    'spec_violations': [
        {'rule_id': 'BE-MP-01', 'level': 'P0', 'file': 'system/mapper/UserMapper.java', 'line': 15, 'method': 'selectByName', 'description': '使用了@Select注解写SQL', 'suggestion': '将SQL移到UserMapper.xml'},
        {'rule_id': 'BE-QL-14', 'level': 'P1', 'file': 'auth/controller/AuthController.java', 'line': 42, 'method': 'login', 'description': '返回裸Map', 'suggestion': '使用LoginResultVO'},
    ],
    'quality_issues': [
        {'file': 'system/service/impl/UserServiceImpl.java', 'line': 38, 'dimension': 'N+1查询', 'severity': 'high', 'detail': '循环内逐条查库', 'suggestion': '批量查询'},
    ],
    'summary': '发现P0=1(@Select), P1=1(裸Map), 质量高=1(N+1)'
}
quality = {
    'overall_score': 72, 'scan_path': 'admin-test-02/src/main/java', 'file_count': 99,
    'metrics': {'complexity': 8.2, 'duplication': 6.5, 'size': 7.0, 'structure': 7.8, 'error_handling': 6.0, 'naming': 8.5, 'comments': 5.5},
    'worst_files': [{'file': 'UserServiceImpl.java', 'score': 45, 'shit_gas_index': 82}, {'file': 'AuthController.java', 'score': 52, 'shit_gas_index': 70}]
}
with open('$TMPDIR/quality.json', 'w') as f: json.dump(quality, f)
with open('$TMPDIR/findings.json', 'w') as f: json.dump(findings, f)
"
python3 -m code_check.cli report --quality "$TMPDIR/quality.json" --findings "$TMPDIR/findings.json" --output "$TMPDIR/final-report.md" && \
echo "=== Report ===" && cat "$TMPDIR/final-report.md" && \
rm -rf "$TMPDIR"
```
Expected: Report with quality overview table, spec compliance table with P0/P1 rows, quality issues table, summary table.

- [ ] **Step 2: 确认 ai-checklist.yaml 覆盖所有 coder 规范文件**

```bash
echo "=== 规范文件列表 ===" && ls agents/coder/*/*.md agents/coder/*.md 2>/dev/null | grep -v README && echo "" && echo "=== ai-checklist.yaml 中的来源引用 ===" && grep -c "来自" agents/reviewer/check_system/rules/ai-checklist.yaml
```
Expected: 12 个规范文件全部在 ai-checklist.yaml 中有对应条目

- [ ] **Step 3: 确认删除清单完成**

```bash
echo "=== 已删除的文件检查 ===" && \
for f in \
  agents/reviewer/check_system/code_check/scanner.py \
  agents/reviewer/check_system/code_check/config.py \
  agents/reviewer/check_system/rules/program-checks.yaml \
  agents/reviewer/check_system/code-check-config.yaml \
  ; do
  [ -f "$f" ] && echo "❌ STILL EXISTS: $f" || echo "✅ Deleted: $f"
done && \
[ -d agents/reviewer/check_system/hooks ] && echo "❌ STILL EXISTS: hooks/" || echo "✅ Deleted: hooks/"
```
Expected: all ✅ Deleted

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: final verification of reviewer refactor — all tests pass, old files removed"
```

---

## 验证清单

- [ ] `.mcp.json` 配置有效
- [ ] ai-checklist.yaml 44 条，YAML 语法正确，覆盖全部 12 个 coder 规范文件
- [ ] models.py 可导入，dataclass 序列化/反序列化正确
- [ ] reporter.py 渲染 PASSED 和 FAILED 报告均输出正确 Markdown
- [ ] cli.py `report --help` 显示新参数
- [ ] cli.py 缺失 findings.json 时报错
- [ ] cli.py 缺失 quality.json 时警告但继续
- [ ] review.skill.md 流程清晰可执行
- [ ] pipeline.yaml reviewer prompt 指向新流程
- [ ] 旧文件全部删除（scanner/config/program-checks/hooks）
- [ ] `python3 -m pytest tests/ -v` 全部通过
