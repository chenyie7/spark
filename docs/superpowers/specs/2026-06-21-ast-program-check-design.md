# AST 程序校验重构设计

## 背景

当前 Python 程序校验系统使用正则表达式（text-grep、java-annotation、java-return-type 扫描器）检查 Java 源码，存在大量误报：

| 误报类型 | 根因 |
|---------|------|
| Interface 被标记为缺少 `@RequiredArgsConstructor` | 正则无法区分 `interface` 和 `class` |
| 配置类被标记为缺少 BCrypt | 正则不理解「这个类是否需要密码处理」的语义 |
| 注释中的代码被匹配 | 正则不认识 Java 注释边界 |
| 常量字段被标记为缺少 `@Schema` | 正则无法判断字段修饰符（static final） |
| 泛型返回类型的括号匹配错误 | 正则处理嵌套括号脆弱 |

**结论：正则引擎的能力上限决定了它无法准确理解 Java 代码结构。需要升级为基于 AST 的检查引擎。**

## 设计方案：全量替换为 tree-sitter-java

### 为什么选 tree-sitter-java

| 对比维度 | Python javalang | tree-sitter-java | JavaParser（JVM 方案） |
|---------|:---:|:---:|:---:|
| 解析准确度 | ⚠️ 仅 Java 8 | ✅ 支持 Java 20+ | ✅ 最准确 |
| class/interface 区分 | ✅ | ✅ | ✅ |
| 注释边界 | ⚠️ | ✅（独立节点） | ✅ |
| 字段修饰符检查 | ❌ | ✅ static/final 是节点属性 | ✅ |
| 依赖 | Python 库 | Python 库 | 需要 JVM |
| 维护状态 | 已停维 5 年 | 活跃维护 | 活跃 |

**选择 tree-sitter-java**：零 JVM 依赖、纯 Python 集成、活跃维护、准确度足够覆盖所有 40 条规则的语法检查需求。

安装方式：
```bash
pip install tree-sitter tree-sitter-java
```

### 架构

```
                        Python（纯 Python，零外部进程）
    
    调度层                      检查层                     输出层
    ┌──────────┐    ┌─────────────────────────────┐    ┌──────────┐
    │ cli.py   │───▶│         scanner.py           │───▶│ reporter │
    │ config   │    │                             │    │   .py    │
    │   .py    │    │ ┌─────────────────────────┐ │    │          │
    └──────────┘    │ │   JavaAstScanner         │ │    └──────────┘
                    │ │   (tree-sitter-java)     │ │
                    │ │   遍历 AST 节点          │ │
                    │ │   匹配规则条件            │ │
                    │ │   收集 Finding[]         │ │
                    │ └─────────────────────────┘ │
                    │ ┌─────────────────────────┐ │
                    │ │   PackageStructureScanner│ │
                    │ │   FileNamingScanner      │ │
                    │ │   ConfigCheckScanner     │ │
                    │ └─────────────────────────┘ │
                    └─────────────────────────────┘

删除的扫描器：TextGrepScanner、JavaAnnotationScanner、JavaReturnTypeScanner
新增的扫描器：JavaAstScanner
保留的扫描器：PackageStructureScanner、FileNamingScanner、ConfigCheckScanner
```

### 新规则 YAML 格式

统一格式，所有需要解析 Java 源文件的规则走 `scanner: java-ast`：

```yaml
<规则ID>:
  description: "规则描述"
  level: P0|P1|P2
  program:
    scanner: java-ast
    target: class | method | field | constructor          # AST 节点类型
    filters:                                              # 过滤条件
      on_dir: "controller"                                # 目录匹配
      on_class_annotation: "RestController|Controller"    # 类上的注解
      on_method_annotation: "PostMapping|PutMapping"      # 方法上的注解
      on_field_type: "DTO"                                # 字段类型匹配
      skip_static_final: true                             # 跳过常量字段
      skip_interface: true                                # 跳过接口
      method_return_type: "void"                          # 返回类型过滤
    require:                                              # 必须具备
      required_class_annotation: "@Slf4j"                 # 类注解
      required_method_annotation: "@Operation"            # 方法注解
      required_return_pattern: "Result<"                  # 返回类型模式
      required_field_annotation: "@Schema"                # 字段注解
      required_class_modifier: "final"                    # 类修饰符
      required_private_constructor: true                  # 私有构造器
      param_has_annotation: "@Valid"                      # 参数注解
    forbid:                                               # 禁止出现
      annotation: "@Autowired"                            # 禁止注解
      pattern: "System\\.(out|err)\\.print"              # 禁止文本
      in_method: true                                     # 限定方法体内
    check:                                                # 特殊检查
      param_count_gte: 4                                  # 参数数量检查
```

### AST 节点类型映射

| tree-sitter-java 节点 | 用途 |
|----------------------|------|
| `class_declaration` | 类声明（不含接口） |
| `interface_declaration` | 接口声明 |
| `method_declaration` | 方法声明 |
| `field_declaration` | 字段声明 |
| `constructor_declaration` | 构造器 |
| `formal_parameter` | 方法参数 |
| `marker_annotation` | 标记注解（如 @Override） |
| `normal_annotation` | 属性注解（如 @Schema(...)） |
| `modifiers` | 修饰符（public/private/static/final） |
| `line_comment` / `block_comment` | 注释 |
| `string_literal` | 字符串字面量 |

### 规则迁移清单

所有 40 条文本/注解检查规则全部迁移到 `java-ast`：

#### 结构审查（ST）— 4 条迁移

| 规则 | 原扫描器 | target | 检查逻辑 |
|------|---------|--------|---------|
| BE-ST-20 包名小写 | text-grep | class/interface | package 小写检查 |
| BE-ST-21 常量命名 | text-grep | field | static final + 大写检查 |
| BE-ST-22 @Autowired | text-grep | class | forbid @Autowired 注解 |
| BE-ST-23 @RequiredArgs | java-annotation | class | require @RequiredArgsConstructor（跳过 interface） |

#### 质量审查（QL）— 15 条迁移

| 规则 | 原扫描器 | target | 检查逻辑 |
|------|---------|--------|---------|
| BE-QL-07 System.out | text-grep | class+method body | forbid System.out/err |
| BE-QL-08 @Slf4j | java-annotation | class | require @Slf4j |
| BE-QL-09 敏感日志 | text-grep | method body | forbid 敏感词在 log 行 |
| BE-QL-10 请求日志 | text-grep | method | forbid 手写请求日志 |
| BE-QL-13 Result<T> | java-return-type | method | require `Result<` 返回类型 |
| BE-QL-15 Result.success() | text-grep | method | require `Result.success()` |
| BE-QL-16 PageResult<T> | java-return-type | method | require `PageResult<` |
| BE-QL-17 PageQueryDTO | text-grep | class | extend PageQueryDTO |
| BE-QL-18 ok 消息 | text-grep | all | forbid 自定义成功消息 |
| BE-QL-27 @TableLogic | java-annotation | class | require @TableLogic |
| BE-QL-29 @Valid/@Validated | java-annotation | method | require @Valid 在 DTO 参数 |
| BE-QL-30 @Validated 分组 | java-annotation | method | require 分组参数 |
| BE-QL-33 禁止 Lombok | text-grep | all | forbid @SneakyThrows 等 |
| BE-QL-38 常量类 final | java-annotation | class | require final + 私有构造 |
| BE-QL-40 手动 Logger | text-grep | class | forbid 手动声明 Logger |
| BE-QL-42 System.gc | text-grep | all | forbid System.gc() |
| BE-QL-43 finalize() | text-grep | class | forbid finalize() |
| BE-QL-44 @Param | java-annotation | method | require @Param 多参数 |
| BE-QL-45 LambdaWrapper | text-grep | all | forbid 非 Lambda QueryWrapper |

#### 基础设施（IN）— 7 条迁移

| 规则 | 原扫描器 | target | 检查逻辑 |
|------|---------|--------|---------|
| BE-IN-01 @Tag | java-annotation | class | require @Tag |
| BE-IN-02 @Operation | java-annotation | method | require @Operation |
| BE-IN-03 @Parameter | java-annotation | method | require @Parameter on GET params |
| BE-IN-04 @Schema on DTO | java-annotation | field | require @Schema（跳过 static final） |
| BE-IN-05 @Schema on VO | java-annotation | field | require @Schema（跳过 static final） |
| BE-IN-10 @Value | text-grep | class/field | forbid @Value |
| BE-IN-15 RedisTemplate | text-grep | all | forbid RedisTemplate |
| BE-IN-30 文件名风险 | text-grep | all | forbid getOriginalFilename |
| BE-IN-31 上传路径 | text-grep | all | forbid static/resources 上传 |

#### 认证审查（AU）— 7 条迁移

| 规则 | 原扫描器 | target | 检查逻辑 |
|------|---------|--------|---------|
| BE-AU-02 StpUtil | text-grep | all | forbid StpUtil |
| BE-AU-07 BCrypt | text-grep | class | require BCryptPasswordEncoder 使用 |
| BE-AU-15 权限注解位置 | text-grep | class | forbid @SaCheck 在 service 目录 |
| BE-AU-18 权限码硬编码 | text-grep | all | forbid 硬编码权限码字符串 |
| BE-AU-21 HttpServletRequest | text-grep | class | forbid HttpServletRequest 在 service |
| BE-AU-31 密码明文 | text-grep | all | forbid 密码明文 |
| BE-AU-32 Token 硬编码 | text-grep | all | forbid Token/secret 硬编码 |

#### 结构审查（命名规范性）— 4 条保留 file-naming

| 规则 | 扫描器 | 说明 |
|------|--------|------|
| BE-ST-03 启动类根包 | file-naming | 无需改 |
| BE-ST-14~19 类名后缀 | file-naming | 无需改 |

#### 基础设施（配置文件）— 2 条保留 config-check

| 规则 | 扫描器 | 说明 |
|------|--------|------|
| BE-IN-07 knife4j | config-check | 无需改 |
| BE-IN-08 明文密码 | config-check | 无需改 |
| BE-IN-09 环境变量 | config-check | 无需改 |

### 文件变更范围

| 文件 | 动作 | 说明 |
|------|------|------|
| `rules/program-checks.yaml` | 重写 | 所有 text-grep/java-annotation/java-return-type 规则改为 java-ast |
| `scanner.py` | 重写 | 删除 TextGrepScanner、JavaAnnotationScanner、JavaReturnTypeScanner，新增 JavaAstScanner |
| `tests/` | 重写 | 65 个旧测试全部替换为新规则测试 |
| `models.py` | 不变 | Finding/ScanResult 数据模型无需改动 |
| `config.py` | 不变 | 配置加载无需改动 |
| `reporter.py` | 不变 | 报告生成无需改动 |
| `cli.py` | 不变 | CLI 入口无需改动 |
| `requirements.txt` | 新增 | 添加 tree-sitter + tree-sitter-java |

### 误报消除对照

| 误报 | 如何消除 |
|------|---------|
| Interface 被标缺 @RequiredArgsConstructor | `target: class` + `skip_interface: true`，interface_declaration 是不同节点类型 |
| 配置类被标缺 BCrypt | BE-AU-07 改为 `target: class` + `on_class_annotation: Service|ServiceImpl`，只检查业务类 |
| 注释中代码被误报 | tree-sitter 将注释作为独立节点，扫描时跳过 |
| 常量字段被标缺 @Schema | `skip_static_final: true`，检查字段修饰符 |
| 泛型返回类型解析错误 | AST 提供结构化的 `return_type` 节点，不支持正则匹配 |
| Application.java 不在根包 | BE-ST-03 保留 file-naming，已有逻辑修正 |

### CI 集成影响

- `pip install tree-sitter tree-sitter-java` 添加到环境初始化
- 其他调用方式不变：`python3 -m code_check.cli scan <path>`
- 输出格式不变：预检 JSON + Markdown 报告
