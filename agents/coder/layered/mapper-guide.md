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
List<User> users = lambdaQuery()
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
    private LocalDateTime createTime;

    @TableField(fill = FieldFill.INSERT_UPDATE)  // 新增和修改时自动填充
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
| `createTime` | `LocalDateTime` | `@TableField(fill = FieldFill.INSERT)` |
| `updateTime` | `LocalDateTime` | `@TableField(fill = FieldFill.INSERT_UPDATE)` |
| `deleted` | `Integer` | `@TableLogic`（逻辑删除） |

---

## 四、自动填充配置

```java
package com.chenyi.{project}.config;

import com.baomidou.mybatisplus.core.handlers.MetaObjectHandler;
import org.apache.ibatis.reflection.MetaObject;
import org.springframework.stereotype.Component;
import java.time.LocalDateTime;

@Component
public class MyMetaObjectHandler implements MetaObjectHandler {

    @Override
    public void insertFill(MetaObject metaObject) {
        this.strictInsertFill(metaObject, "createTime", LocalDateTime.class, LocalDateTime.now());
        this.strictInsertFill(metaObject, "updateTime", LocalDateTime.class, LocalDateTime.now());
    }

    @Override
    public void updateFill(MetaObject metaObject) {
        this.strictUpdateFill(metaObject, "updateTime", LocalDateTime.class, LocalDateTime.now());
    }
}
```

---

## 五、分页配置

### 5.1 分页插件

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

### 5.2 分页查询示例

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

## 六、Mapper 接口定义

### 6.1 接口定义

```java
package com.chenyi.{project}.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.chenyi.{project}.entity.User;
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

## 七、禁止事项

| 禁止 | 原因 |
|------|------|
| 用 `@Select` / `@Update` / `@Insert` 注解写 SQL | 不可格式化、不可高亮、不可 DTD 校验 |
| 用 Lambda 写联表/子查询 | Lambda 无法处理 |
| Mapper 方法参数不加 `@Param` | XML 中无法引用参数名 |
| Mapper 直接返回 Entity 给 Controller | Entity 不穿透到 Controller 层，见 `service-guide.md` |
| 字符串字段名构建条件：`new QueryWrapper<User>().eq("username", name)` | 字段名写死字符串，编译期不检查 |
| JPA 双向关联场景下滥用 `@Data` 自带的 `@ToString` / `@EqualsAndHashCode` | 可能导致循环引用 StackOverflow，如有需要手动 `@ToString.Exclude` 排除关联字段 |

---

## 八、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../architecture/package-structure-guide.md` | Mapper 在包结构中的位置 |
| `service-guide.md` | Service 调 Mapper，Service 负责 DTO ↔ Entity 转换 |
| `controller-guide.md` | Controller 禁止直接调 Mapper |
| `../infrastructure/result-guide.md` | 分页返回 `PageResult<T>` |
