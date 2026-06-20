# 检查规则补全方案

> 将 reviewer 规范文件中的全部 132 项检查（含 BE-AU-05 P0 纠偏）映射到程序检查/AI 检查两个 YAML 文件中，通过 `level` + `strategy` 实现分级控制。

---

## 一、strategy 三档差异

| 策略 | 执行范围 | 阻断条件 | 场景 |
|------|---------|---------|------|
| strict | P0 + P1 + P2 全部 | P0 + P1 阻断 | 核心业务 |
| normal | P0 + P1 + P2 全部 | 仅 P0 阻断 | 一般开发 |
| loose | 仅 P0 + P1（跳过 P2） | 仅 P0 阻断 | 快速迭代 |

**设计原则：** strategy 控制两件事——① 执行哪些级别的规则，② 遇到问题时哪些级别阻断。P2 为风格/文档类，loose 模式下不执行。

---

## 二、分类规则

判断一个检查项属于 `program` 还是 `ai` 的标准：

| 类型 | 标准 | 示例 |
|------|------|------|
| program | 正则/模式匹配能做到确定性判断，无误报风险 | `@Autowired` 检测、命名后缀、包结构 |
| ai | 需要语义理解、上下文判断、或可能误报 | "业务逻辑应下沉到 Service"、"应使用常量替代" |

---

## 三、补全映射表

### structure-check.md → 程序检查（13 项）

| 编码 | 级别 | 扫描方式 | 说明 |
|------|:--:|------|------|
| BE-ST-01 | P1 | text-grep | 包结构缺失检测（扫描目录是否存在 controller/service/impl/mapper/entity/dto/vo） |
| BE-ST-02 | P1 | text-grep | service/impl 子包检测 |
| BE-ST-03 | P2 | text-grep | 启动类是否在根包（类名含 Application，包路径检测） |
| BE-ST-14 | P2 | text-grep | Controller 类名以 Controller 结尾 |
| BE-ST-15 | P2 | text-grep | Service 接口以 Service 结尾 |
| BE-ST-16 | P2 | text-grep | ServiceImpl 以 ServiceImpl 结尾 |
| BE-ST-17 | P2 | text-grep | Mapper 以 Mapper 结尾 |
| BE-ST-18 | P2 | text-grep | Entity 以 Entity 结尾 |
| BE-ST-19 | P2 | text-grep | DTO 命名规范 `{业务}{动作}DTO` |
| BE-ST-20 | P2 | text-grep | 包名全部小写 |
| BE-ST-21 | P2 | text-grep | 常量 UPPER_SNAKE |
| BE-ST-22 | P1 | text-grep | @Autowired 字段注入 |
| BE-ST-23 | P1 | java-annotation | @RequiredArgsConstructor + private final 构造注入 |

### structure-check.md → AI 检查（2 项）

| 编码 | 级别 | 说明 |
|------|:--:|------|
| BE-ST-06 | P2 | 业务逻辑是否在 Controller 层（应下沉到 Service） |
| BE-ST-24 | P2 | 构造注入参数 > 7 个（应拆分 Service） |

### quality-check.md → 程序检查（补 9 项，累计 18 项）

已有 9 项：BE-QL-07/08/13/29/33/40/42/43/45。

新增：

| 编码 | 级别 | 扫描方式 | 说明 |
|------|:--:|------|------|
| BE-QL-09 | P0 | text-grep | 日志中打印敏感信息（password/phone/token/idCard/secret 正则） |
| BE-QL-10 | P2 | text-grep | Controller 手写请求日志（检测 log.info 在 Controller 类中） |
| BE-QL-15 | P2 | java-return-type | 增删改返回 Result.success() 无 data |
| BE-QL-16 | P2 | java-return-type | 分页返回 Result<PageResult<T>> |
| BE-QL-17 | P2 | text-grep | 分页 DTO 继承 PageQueryDTO |
| BE-QL-18 | P2 | text-grep | 成功消息固定 "ok" |
| BE-QL-27 | P1 | java-annotation | Entity 是否加 @TableLogic |
| BE-QL-38 | P2 | java-annotation | 常量类 final + 私有构造 |
| BE-QL-44 | P1 | text-grep | Mapper 参数缺 @Param |

### quality-check.md → AI 检查（补 7 项，累计 19 项）

已有 13 项：BE-QL-01/02/04/05/11/12/14/34/35/36/37/41/46。

新增：

| 编码 | 级别 | 说明 |
|------|:--:|------|
| BE-QL-03 | P1 | 新增 BusinessErrorEnum 后同步 i18n |
| BE-QL-06 | P2 | 系统异常被 GlobalExceptionHandler 兜底 |
| BE-QL-19 | P1 | 业务表含必备审计字段 |
| BE-QL-20 | P1 | 主键 BIGINT + 雪花ID |
| BE-QL-21 | P1 | 业务表含 deleted 逻辑删除 |
| BE-QL-31 | P1 | DTO 校验消息用 {key} 占位符 |
| BE-QL-32 | P2 | @Schema.requiredMode 与校验注解一致 |

### infra-check.md → 程序检查（12 项）

| 编码 | 级别 | 扫描方式 | 说明 |
|------|:--:|------|------|
| BE-IN-01 | P2 | java-annotation | Controller 类缺 @Tag |
| BE-IN-02 | P2 | text-grep | Controller 方法缺 @Operation |
| BE-IN-03 | P2 | text-grep | @PathVariable/@RequestParam 缺 @Parameter |
| BE-IN-04 | P2 | text-grep | DTO 字段缺 @Schema |
| BE-IN-05 | P2 | text-grep | VO 字段缺 @Schema |
| BE-IN-07 | P1 | text-grep | 生产环境 knife4j.enable=false |
| BE-IN-08 | P0 | text-grep | yml 明文敏感信息 |
| BE-IN-09 | P1 | text-grep | 数据库/Redis 密码未用环境变量 |
| BE-IN-10 | P1 | text-grep | 未用 @ConfigurationProperties（检测 @Value 散落） |
| BE-IN-15 | P1 | text-grep | 直用 RedisTemplate |
| BE-IN-30 | P0 | text-grep | 文件名未由服务端生成（检测用户原始文件名风险） |
| BE-IN-31 | P1 | text-grep | 上传文件放在 static/resources 下 |

### infra-check.md → AI 检查（13 项）

| 编码 | 级别 | 说明 |
|------|:--:|------|
| BE-IN-06 | P2 | @Schema.requiredMode 与校验注解一致 |
| BE-IN-11 | P2 | 配置文件按环境拆分 |
| BE-IN-12 | P1 | Nacos 地址通过环境变量注入 |
| BE-IN-13 | P1 | 中间件连接配 @RefreshScope |
| BE-IN-14 | P2 | Nacos 用 Namespace 区分环境 |
| BE-IN-16 | P2 | Redis Key 命名格式 {项目}:{模块}:{类型}:{标识} |
| BE-IN-17 | P1 | 不设过期时间 |
| BE-IN-18 | P2 | 存储 > 10KB 大对象 |
| BE-IN-19 | P1 | 生产环境用 keys * |
| BE-IN-20 | P1 | 敏感信息明文存 Redis |
| BE-IN-27 | P1 | 缺文件大小限制 |
| BE-IN-28 | P1 | 文件类型白名单校验 |
| BE-IN-29 | P1 | 文件魔数校验 |

### auth-check.md → 程序检查（8 项）

| 编码 | 级别 | 扫描方式 | 说明 |
|------|:--:|------|------|
| BE-AU-02 | P1 | text-grep | 多端场景直用 StpUtil（检测 import 和调用） |
| BE-AU-05 | P0 | text-grep | 配置类名 SaTokenCustomConfig（检测类名） |
| BE-AU-07 | P0 | text-grep | 密码未用 BCryptPasswordEncoder |
| BE-AU-15 | P1 | text-grep | 权限注解放在 Controller（检测 Service 上的权限注解） |
| BE-AU-18 | P1 | text-grep | 权限码硬编码字符串 |
| BE-AU-21 | P0 | text-grep | Service 注入 HttpServletRequest |
| BE-AU-31 | P0 | text-grep | 密码明文存储 |
| BE-AU-32 | P0 | text-grep | Token/密钥硬编码 |

### auth-check.md → AI 检查（13 项）

| 编码 | 级别 | 说明 |
|------|:--:|------|
| BE-AU-03 | P1 | StpKit 门面类定义 |
| BE-AU-04 | P1 | StpKit 含匹配场景的 StpLogic |
| BE-AU-06 | P1 | 多端登录分独立 Controller |
| BE-AU-08 | P1 | 多端登录用 StpKit.USER.login() |
| BE-AU-09 | P1 | 登出用 LoginContextHolder.get() |
| BE-AU-10 | P1 | 登录时用户名存 Session |
| BE-AU-11 | P1 | 多端独立拦截器 |
| BE-AU-12 | P0 | 用户端拦截器排除 /api/admin/**
| BE-AU-13 | P1 | checkLogin 后 LoginContextHolder.set() |
| BE-AU-14 | P1 | 拦截器排除白名单 |
| BE-AU-20 | P1 | Service 用 LoginContextHolder.getUserId() |
| BE-AU-24 | P1 | Gateway 遍历 StpKit 匹配 Token |
| BE-AU-25 | P1 | Gateway 透传 X-User-Id/X-User-Name |

---

## 四、汇总

| 维度 | 程序检查 | AI 检查 | 合计 |
|------|:--:|:--:|:--:|
| quality-check.md | 18（已有9，新增9） | 20（已有13，新增7） | 38 |
| structure-check.md | 13 | 2 | 15 |
| infra-check.md | 12 | 13 | 25 |
| auth-check.md | 8 | 13 | 21 |
| **合计** | **51** | **48** | **99** |

> 注：部分检查项（BE-ST-04/05/07/08/09/10/11/12/13, BE-QL-22~28 等数据库相关, BE-IN-21/22/23~26/32, BE-AU-16/17/19/22/23/26~29/33~35）在程序侧暂时无法做到可靠的确定性检测，归入 AI 检查或推迟到 v2。

---

## 五、strategy 行为定义

```python
# 程序预检脚本中的 strategy 控制逻辑

if strategy == "loose":
    # 只执行 P0 + P1 规则，跳过 P2
    active_rules = {k: v for k, v in rules.items() if v["level"] in ("P0", "P1")}
else:
    # strict / normal: 执行全部规则
    active_rules = rules

# 阻断判断（对所有策略一致）
blocking_levels = {"P0"}  # P0 永远阻断
if strategy == "strict":
    blocking_levels.add("P1")  # strict 额外阻断 P1

blocked = any(f.level in blocking_levels for f in findings)
```
