# Mapper 层开发规范

> 适用：Spring Boot + MyBatis-Plus，单体 + 微服务

---

## 一、SQL 写法的选择规则

| 场景 | 方式 | 说明 |
|------|------|------|
| 单表 CRUD | `BaseMapper` 内置方法 | `insert`、`selectById`、`deleteById`、`updateById` |
| 单表条件查询 | `LambdaQueryWrapper` | 编译期安全，字段名不会写错 |
| 多表联查（JOIN） | **XML** | Lambda 无法处理联表 |
| 子查询 | **XML** | 同上 |
| 聚合函数（SUM/COUNT/AVG + GROUP BY） | **XML** | 同上 |
| 超过 5 个条件组合 | **XML** | Wrapper 条件太多可读性差 |

### 1.1 LambdaQueryWrapper 示例

```java
// ✅ 常见单表查询
List<UserEntity> users = lambdaQuery()
    .eq(UserEntity::getUsername, username)
    .ge(UserEntity::getAge, 18)
    .orderByDesc(UserEntity::getCreateTime)
    .list();

// ✅ LambdaUpdateWrapper
lambdaUpdate()
    .set(UserEntity::getStatus, 1)
    .eq(UserEntity::getId, id)
    .update();
```

### 1.2 XML 示例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
    "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="com.chenyi.{project}.mapper.UserMapper">

    <select id="selectDetailById" resultType="com.chenyi.{project}.vo.UserVO">
        SELECT u.id, u.username, u.create_time,
               o.order_count
        FROM sys_user u
        LEFT JOIN (
            SELECT user_id, COUNT(*) order_count
            FROM sys_order
            WHERE deleted = 0
            GROUP BY user_id
        ) o ON u.id = o.user_id
        WHERE u.id = #{id}
          AND u.deleted = 0
    </select>

</mapper>
```

---

## 二、禁止 `@Select` / `@Update` / `@Insert` 注解写 SQL

```java
// ❌ 禁止：注解里写 SQL 串
@Select("SELECT * FROM sys_user WHERE username = #{name}")
User selectByName(String name);

// ❌ 禁止
@Update("UPDATE sys_user SET password = #{pwd} WHERE id = #{id}")
int updatePassword(Long id, String pwd);
```

**原因：** SQL 写在注解字符串中不可格式化、不可高亮、不支持 DTD 校验、不好 Review。

---

## 三、Entity 基础规范

### 3.1 完整示例

```java
package com.chenyi.{project}.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("sys_user")
public class UserEntity {

    @TableId(type = IdType.ASSIGN_ID)           // 雪花ID
    private Long id;

    @TableField(fill = FieldFill.INSERT)         // 新增时自动填充
    private Long createId;

    @TableField(fill = FieldFill.INSERT)         // 新增时自动填充
    private String createName;

    @TableField(fill = FieldFill.INSERT)         // 新增时自动填充 + 数据库 DEFAULT CURRENT_TIMESTAMP 保底
    private LocalDateTime createTime;

    @TableField(fill = FieldFill.INSERT_UPDATE)  // 新增和修改时自动填充
    private Long updateId;

    @TableField(fill = FieldFill.INSERT_UPDATE)  // 新增和修改时自动填充
    private String updateName;

    @TableField(fill = FieldFill.INSERT_UPDATE)  // 新增和修改时自动填充 + 数据库 ON UPDATE CURRENT_TIMESTAMP 保底
    private LocalDateTime updateTime;

    @TableLogic                                  // 逻辑删除
    private Integer deleted;

    private String username;
    private String password;
    private String email;
}
```

### 3.2 必备字段

每个数据表 Entity 必须包含：

| 字段 | 类型 | 注解 |
|------|------|------|
| `id` | `Long` | `@TableId(type = IdType.ASSIGN_ID)` |
| `createId` | `Long` | `@TableField(fill = FieldFill.INSERT)` |
| `createName` | `String` | `@TableField(fill = FieldFill.INSERT)` |
| `createTime` | `LocalDateTime` | `@TableField(fill = FieldFill.INSERT)` |
| `updateId` | `Long` | `@TableField(fill = FieldFill.INSERT_UPDATE)` |
| `updateName` | `String` | `@TableField(fill = FieldFill.INSERT_UPDATE)` |
| `updateTime` | `LocalDateTime` | `@TableField(fill = FieldFill.INSERT_UPDATE)` |
| `deleted` | `Integer` | `@TableLogic`（逻辑删除） |

---

## 四、自动填充配置

审计字段（`create_id`、`create_name`、`create_time`、`update_id`、`update_name`、`update_time`）通过 `MetaObjectHandler` 统一填充，不手动赋值。

```java
package com.chenyi.{project}.config;

import com.chenyi.{project}.context.LoginContextHolder;
import com.baomidou.mybatisplus.core.handlers.MetaObjectHandler;
import org.apache.ibatis.reflection.MetaObject;
import org.springframework.stereotype.Component;
import java.time.LocalDateTime;

@Component
public class MyMetaObjectHandler implements MetaObjectHandler {

    @Override
    public void insertFill(MetaObject metaObject) {
        Long userId = getCurrentUserId();
        String userName = getCurrentUserName();
        LocalDateTime now = LocalDateTime.now();

        this.strictInsertFill(metaObject, "createId", Long.class, userId);
        this.strictInsertFill(metaObject, "createName", String.class, userName);
        this.strictInsertFill(metaObject, "createTime", LocalDateTime.class, now);
        this.strictInsertFill(metaObject, "updateId", Long.class, userId);
        this.strictInsertFill(metaObject, "updateName", String.class, userName);
        this.strictInsertFill(metaObject, "updateTime", LocalDateTime.class, now);
    }

    @Override
    public void updateFill(MetaObject metaObject) {
        this.strictUpdateFill(metaObject, "updateId", Long.class, getCurrentUserId());
        this.strictUpdateFill(metaObject, "updateName", String.class, getCurrentUserName());
        this.strictUpdateFill(metaObject, "updateTime", LocalDateTime.class, LocalDateTime.now());
    }

    private Long getCurrentUserId() {
        Long userId = LoginContextHolder.getUserId();
        return userId != null ? userId : 0L;
    }

    private String getCurrentUserName() {
        String userName = LoginContextHolder.getUserName();
        return userName != null ? userName : "system";
    }
}
```

> `LoginContextHolder` 在拦截器/网关中被设置为当前的 `StpLogic`，MetaObjectHandler 不需要知道当前是哪个系统/哪个端。
> 非 HTTP 场景中 `LoginContextHolder.getUserId()` 返回 null，兜底为 `0L` / `"system"`。

**说明：**

- `LoginContextHolder` 在拦截器/网关中被设置为当前的 `StpLogic`，通用组件不需要硬编码 `StpKit` 实例
- 非 HTTP 场景中 `LoginContextHolder.getUserId()` 返回 null，兜底为 `0L` / `"system"`
- 数据库 `DEFAULT CURRENT_TIMESTAMP` 作为二层保底，代码没设也不会空（见 `../quality/database-guide.md`）
- `@TableField(fill = ...)` 注解只在字段不手动赋值时才生效，显式 set 过的字段不会覆盖

---

## 五、枚举字段映射

### 5.1 枚举定义

状态、类型等有固定值范围的字段，使用 MyBatis-Plus 枚举映射替代 `Integer`/`String` 裸值。

```java
package com.chenyi.{project}.enums;

import com.baomidou.mybatisplus.annotation.EnumValue;
import lombok.Getter;

@Getter
public enum StatusEnum {
    ENABLED(1, "启用"),
    DISABLED(0, "禁用");

    @EnumValue                          // 存入数据库的值
    private final int code;
    private final String desc;

    StatusEnum(int code, String desc) {
        this.code = code;
        this.desc = desc;
    }
}
```

### 5.2 Entity 使用

```java
@Data
@TableName("sys_user")
public class UserEntity {

    // 直接用枚举类型，不用 Integer
    private StatusEnum status;
}
```

### 5.3 配置启用

```java
@Configuration
public class MybatisPlusConfig {

    @Bean
    public MybatisPlusInterceptor mybatisPlusInterceptor() {
        MybatisPlusInterceptor interceptor = new MybatisPlusInterceptor();
        interceptor.addInnerInterceptor(new PaginationInnerInterceptor(DbType.MYSQL));
        return interceptor;
    }

    @Bean
    public ConfigurationCustomizer configurationCustomizer() {
        return configuration -> configuration.setDefaultEnumTypeHandler(
            MybatisEnumTypeHandler.class
        );
    }
}
```

```yaml
# application.yml
mybatis-plus:
  type-enums-package: com.chenyi.{project}.enums
```

### 5.4 LambdaQueryWrapper 中使用

```java
// ✅ 枚举类型安全，不会写错状态值
lambdaQuery()
    .eq(UserEntity::getStatus, StatusEnum.ENABLED)
    .list();
```

---

## 六、分页配置

### 6.1 分页插件

```java
package com.chenyi.{project}.config;

import com.baomidou.mybatisplus.annotation.DbType;
import com.baomidou.mybatisplus.extension.plugins.MybatisPlusInterceptor;
import com.baomidou.mybatisplus.extension.plugins.inner.PaginationInnerInterceptor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MybatisPlusConfig {

    @Bean
    public MybatisPlusInterceptor mybatisPlusInterceptor() {
        MybatisPlusInterceptor interceptor = new MybatisPlusInterceptor();
        interceptor.addInnerInterceptor(new PaginationInnerInterceptor(DbType.MYSQL));
        return interceptor;
    }
}
```

### 6.2 分页查询示例

```java
// Mapper 接口
public interface UserMapper extends BaseMapper<UserEntity> {
    Page<UserVO> selectPage(@Param("dto") UserPageQueryDTO dto, Page<UserVO> page);
}

// Service
public PageResult<UserVO> page(UserPageQueryDTO dto) {
    Page<UserVO> page = new Page<>(dto.getPage(), dto.getSize());
    Page<UserVO> result = userMapper.selectPage(dto, page);
    return PageResult.of(result.getTotal(), (int) result.getCurrent(),
                         (int) result.getSize(), result.getRecords());
}
```

---

## 七、Mapper 接口定义

### 7.1 接口定义

```java
package com.chenyi.{project}.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.chenyi.{project}.entity.UserEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import java.util.List;

@Mapper
public interface UserMapper extends BaseMapper<UserEntity> {

    // 超出 BaseMapper 的方法才手动定义，封装到 XML 中
    List<UserVO> selectPage(@Param("dto") UserPageQueryDTO dto, Page<UserVO> page);

    UserVO selectDetailById(@Param("id") Long id);
}
```

**命名约定：**

| 操作 | 前缀 |
|------|------|
| 查询 | `select` |
| 新增 | `insert` |
| 修改 | `update` |
| 删除 | `delete` |

---

## 八、禁止事项

| 禁止 | 原因 |
|------|------|
| 用 `@Select` / `@Update` / `@Insert` 注解写 SQL | 不可格式化、不可高亮、不可 DTD 校验 |
| 用 Lambda 写联表/子查询 | Lambda 无法处理 |
| Mapper 方法参数不加 `@Param` | XML 中无法引用参数名 |
| Mapper 直接返回 Entity 给 Controller | Entity 不穿透到 Controller 层，见 `service-guide.md` |
| 字符串字段名构建条件：`new QueryWrapper<UserEntity>().eq("username", name)` | 字段名写死字符串，编译期不检查 |
| JPA 双向关联场景下滥用 `@Data` 自带的 `@ToString` / `@EqualsAndHashCode` | 可能导致循环引用 StackOverflow，如有需要手动 `@ToString.Exclude` 排除关联字段 |

---

## 九、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../architecture/package-structure-guide.md` | Mapper 在包结构中的位置 |
| `service-guide.md` | Service 调 Mapper，Service 负责 DTO ↔ Entity 转换 |
| `controller-guide.md` | Controller 禁止直接调 Mapper |
| `../infrastructure/result-guide.md` | 分页返回 `PageResult<T>` |
