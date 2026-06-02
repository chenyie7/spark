# 数据库建表规范

> 适用：所有数据库（MySQL、PostgreSQL 等），不限于特定数据库

---

## 一、必备审计字段

### 1.1 业务表完整示例

```sql
CREATE TABLE sys_user (
    id              BIGINT       NOT NULL COMMENT '主键ID',
    username        VARCHAR(64)  NOT NULL COMMENT '用户名',
    password        VARCHAR(256) NOT NULL COMMENT '密码',
    email           VARCHAR(128) DEFAULT NULL COMMENT '邮箱',
    -- 审计字段
    create_id       BIGINT       NOT NULL COMMENT '创建人ID',
    create_name     VARCHAR(64)  NOT NULL COMMENT '创建人姓名',
    create_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_id       BIGINT       NOT NULL COMMENT '最后更新人ID',
    update_name     VARCHAR(64)  NOT NULL COMMENT '最后更新人姓名',
    update_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    deleted         TINYINT      NOT NULL DEFAULT 0 COMMENT '逻辑删除：0未删除，1已删除',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用户表';
```

### 1.2 审计字段清单

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `id` | `BIGINT` | 无 | 主键，雪花ID，由 MyBatis-Plus `IdType.ASSIGN_ID` 生成 |
| `create_id` | `BIGINT` | 无 | 创建人ID（雪花ID） |
| `create_name` | `VARCHAR(64)` | 无 | 创建人姓名 |
| `create_time` | `DATETIME` | `CURRENT_TIMESTAMP` | 创建时间，数据库自动填充 |
| `update_id` | `BIGINT` | 无 | 最后更新人ID（雪花ID） |
| `update_name` | `VARCHAR(64)` | 无 | 最后更新人姓名 |
| `update_time` | `DATETIME` | `CURRENT_TIMESTAMP ON UPDATE` | 最后更新时间，数据库自动更新 |
| `deleted` | `TINYINT` | `0` | 逻辑删除：0未删除，1已删除 |

### 1.3 Entity 对应审计字段

```java
@TableId(type = IdType.ASSIGN_ID)
private Long id;

@TableField(fill = FieldFill.INSERT)
private Long createId;

@TableField(fill = FieldFill.INSERT)
private String createName;

@TableField(fill = FieldFill.INSERT)
private LocalDateTime createTime;

@TableField(fill = FieldFill.INSERT_UPDATE)
private Long updateId;

@TableField(fill = FieldFill.INSERT_UPDATE)
private String updateName;

@TableField(fill = FieldFill.INSERT_UPDATE)
private LocalDateTime updateTime;

@TableLogic
private Integer deleted;
```

### 1.4 时间字段填充策略

`create_time` 和 `update_time` 采用**双层保障** — 数据库默认值保底 + 代码 MetaObjectHandler 主控：

```sql
create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
```

| 层级 | 负责内容 | 说明 |
|------|---------|------|
| 数据库 | `create_time`、`update_time` 默认值 | 安全网，万一代码没设也不会空 |
| 代码 `MetaObjectHandler` | 全部审计字段（id + name + time） | 主渠道，统一填充，姓名从 SaToken 获取 |

`MetaObjectHandler` 完整实现见 `../layered/mapper-guide.md` 第四节。

---

## 二、不需要审计字段的表

以下类型的表**不需要** `create_id`、`create_name`、`update_id`、`update_name` 和 `deleted`：

### 2.1 多对多中间表

```sql
CREATE TABLE sys_user_role (
    id       BIGINT  NOT NULL COMMENT '主键ID',
    user_id  BIGINT  NOT NULL COMMENT '用户ID',
    role_id  BIGINT  NOT NULL COMMENT '角色ID',
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_role (user_id, role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户角色关联表';
```

只有外键和关联关系，无独立业务含义，不需要审计和逻辑删除。

### 2.2 仅 DBA 直连维护的表

只有 DBA 在数据库层面直接操作的表才可以省略审计字段，例如 Flyway/Liquibase 的 migration 记录表。这类表没有对应的 Java 业务代码。

**字典表通过后台管理界面维护，必须包含审计字段和逻辑删除。**

### 2.3 日志表

```sql
CREATE TABLE sys_operation_log (
    id           BIGINT       NOT NULL COMMENT '主键ID',
    user_id      BIGINT       NOT NULL COMMENT '操作人ID',
    module       VARCHAR(64)  NOT NULL COMMENT '操作模块',
    content      TEXT         NOT NULL COMMENT '操作内容',
    create_time  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    PRIMARY KEY (id),
    KEY idx_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作日志表';
```

只追加不修改，只需 `create_time`，不需要 `update_*` 和 `deleted`。

---

## 三、主键策略

| 规则 | 说明 |
|------|------|
| 所有表主键使用 `BIGINT` | 对应雪花ID |
| **禁止** `AUTO_INCREMENT` 自增 | 分布式环境下自增会冲突 |
| MyBatis-Plus 配置 `IdType.ASSIGN_ID` | 自动生成雪花ID |
| 中间表、字典表也使用雪花ID | 保持统一 |

---

## 四、逻辑删除

| 规则 | 说明 |
|------|------|
| 业务表必须加 `deleted` | `TINYINT NOT NULL DEFAULT 0` |
| 0 未删除，1 已删除 | 不搞反直觉的旧式定义 |
| 中间表不需要 | 外键关联直接物理删除 |
| 日志表不需要 | 只追加不删除 |
| Entity 加 `@TableLogic` | 查询自动过滤已删除数据 |

---

## 五、命名约定

| 元素 | 风格 | 示例 |
|------|------|------|
| 表名 | 小写 + 下划线 | `sys_user`、`order_item` |
| 字段名 | 小写 + 下划线 | `create_time`、`user_id` |
| 主键 | `id` | 所有表统一 `id` |
| 唯一索引 | `uk_字段名` | `uk_username`、`uk_user_role` |
| 普通索引 | `idx_字段名` | `idx_create_time`、`idx_user_id` |
| 外键字段 | `关联表名_id` | `user_id`、`parent_id` |

---

## 六、字符集与引擎

| 规则 | 说明 |
|------|------|
| 引擎 | `ENGINE=InnoDB` |
| 字符集 | `DEFAULT CHARSET=utf8mb4` |
| 排序规则 | `COLLATE=utf8mb4_general_ci` |
| 每张表必须加 `COMMENT` | 说明表用途 |

---

## 七、禁止事项

| 禁止 | 原因 |
|------|------|
| 使用 `AUTO_INCREMENT` 自增主键 | 分布式环境冲突 |
| 表名/字段名用驼峰 | 数据库规范用小写+下划线 |
| 表不加 `COMMENT` | 无法从数据库直接理解表用途 |
| 业务表缺少审计字段 | 无法追溯数据变更责任人 |
| 业务表不用逻辑删除 | 数据丢失风险 |
| 用 `utf8` 字符集（MySQL 的 fake utf8） | 必须用 `utf8mb4` 支持 emoji 和生僻字 |
| 数据库字段用 `NULL` 不加 `NOT NULL` | 查询时需额外判空，能用 `DEFAULT` 就用 |

---

## 八、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../layered/mapper-guide.md` | Entity 定义，`@TableLogic`、`@TableField`、`MetaObjectHandler` |
