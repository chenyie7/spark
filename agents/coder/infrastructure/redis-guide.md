# Redis 开发规范

> 适用：Spring Boot + RedisTemplate，单体 + 微服务

---

## 一、序列化配置

所有 Value 统一序列化为 JSON：

```java
package com.chenyi.{project}.config;

import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.impl.LaissezFaireSubTypeValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisConfig {

    @Bean
    public RedisTemplate<String, Object> redisTemplate(RedisConnectionFactory factory) {
        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);

        // Key 用 String
        StringRedisSerializer stringSerializer = new StringRedisSerializer();
        template.setKeySerializer(stringSerializer);
        template.setHashKeySerializer(stringSerializer);

        // Value 用 JSON
        ObjectMapper objectMapper = new ObjectMapper();
        objectMapper.activateDefaultTyping(
            LaissezFaireSubTypeValidator.instance,
            ObjectMapper.DefaultTyping.NON_FINAL,
            JsonTypeInfo.As.PROPERTY
        );
        Jackson2JsonRedisSerializer<Object> jsonSerializer =
            new Jackson2JsonRedisSerializer<>(objectMapper, Object.class);
        template.setValueSerializer(jsonSerializer);
        template.setHashValueSerializer(jsonSerializer);

        template.afterPropertiesSet();
        return template;
    }
}
```

---

## 二、RedisUtil 工具类

`RedisUtil` 封装 `RedisTemplate`，统一序列化和异常处理：

```java
package com.chenyi.{project}.util;

import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.util.*;
import java.util.concurrent.TimeUnit;

@Component
public class RedisUtil {

    private final RedisTemplate<String, Object> redisTemplate;

    public RedisUtil(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    // ==================== Key 操作 ====================

    /** 判断 key 是否存在 */
    public boolean hasKey(String key) {
        return Boolean.TRUE.equals(redisTemplate.hasKey(key));
    }

    /** 删除 key */
    public boolean delete(String key) {
        return Boolean.TRUE.equals(redisTemplate.delete(key));
    }

    /** 批量删除 */
    public long delete(Collection<String> keys) {
        return Optional.ofNullable(redisTemplate.delete(keys)).orElse(0L);
    }

    /** 设置过期时间 */
    public boolean expire(String key, long timeout, TimeUnit unit) {
        return Boolean.TRUE.equals(redisTemplate.expire(key, timeout, unit));
    }

    /** 获取过期时间（秒），-1 永久有效，-2 key 不存在 */
    public long getExpire(String key) {
        return Optional.ofNullable(redisTemplate.getExpire(key, TimeUnit.SECONDS)).orElse(-2L);
    }

    /** 查找匹配的 key，慎用（在线服务避免使用 keys，用 scan 替代） */
    public Set<String> scan(String pattern) {
        return redisTemplate.execute((connection) -> {
            Set<String> keys = new HashSet<>();
            var cursor = connection.scan(0, new org.springframework.data.redis.core.ScanOptions.ScanOptionsBuilder()
                .match(pattern).count(100).build());
            while (cursor.hasNext()) {
                keys.add(new String(cursor.next()));
            }
            return keys;
        });
    }

    // ==================== String 操作（对象存取） ====================

    /** 存入对象 */
    public <T> void set(String key, T value) {
        redisTemplate.opsForValue().set(key, value);
    }

    /** 存入对象并设置过期时间 */
    public <T> void set(String key, T value, long timeout, TimeUnit unit) {
        redisTemplate.opsForValue().set(key, value, timeout, unit);
    }

    /** 获取对象 */
    @SuppressWarnings("unchecked")
    public <T> T get(String key) {
        return (T) redisTemplate.opsForValue().get(key);
    }

    /** 获取字符串（等同于 get，语义更明确） */
    public String getString(String key) {
        Object value = redisTemplate.opsForValue().get(key);
        return value != null ? value.toString() : null;
    }

    /** 存入字符串 */
    public void setString(String key, String value, long timeout, TimeUnit unit) {
        redisTemplate.opsForValue().set(key, value, timeout, unit);
    }

    /** 不存在时设置（简易分布式锁底层） */
    public boolean setIfAbsent(String key, Object value, long timeout, TimeUnit unit) {
        return Boolean.TRUE.equals(redisTemplate.opsForValue().setIfAbsent(key, value, timeout, unit));
    }

    /** 获取并设置新值 */
    @SuppressWarnings("unchecked")
    public <T> T getAndSet(String key, T value) {
        return (T) redisTemplate.opsForValue().getAndSet(key, value);
    }

    // ==================== 计数器 ====================

    /** 自增 1 */
    public long increment(String key) {
        return Optional.ofNullable(redisTemplate.opsForValue().increment(key)).orElse(0L);
    }

    /** 自增指定值 */
    public long increment(String key, long delta) {
        return Optional.ofNullable(redisTemplate.opsForValue().increment(key, delta)).orElse(0L);
    }

    /** 自减 1 */
    public long decrement(String key) {
        return Optional.ofNullable(redisTemplate.opsForValue().decrement(key)).orElse(0L);
    }

    // ==================== Hash 操作 ====================

    /** Hash 存单个字段 */
    public void hSet(String key, String field, Object value) {
        redisTemplate.opsForHash().put(key, field, value);
    }

    /** Hash 存整个 Map */
    public void hSetAll(String key, Map<String, Object> map) {
        redisTemplate.opsForHash().putAll(key, map);
    }

    /** Hash 取单个字段 */
    @SuppressWarnings("unchecked")
    public <T> T hGet(String key, String field) {
        return (T) redisTemplate.opsForHash().get(key, field);
    }

    /** Hash 取所有字段 */
    public Map<Object, Object> hGetAll(String key) {
        return redisTemplate.opsForHash().entries(key);
    }

    /** Hash 删除字段 */
    public long hDelete(String key, Object... fields) {
        return redisTemplate.opsForHash().delete(key, fields);
    }

    /** Hash 判断字段是否存在 */
    public boolean hHasKey(String key, String field) {
        return redisTemplate.opsForHash().hasKey(key, field);
    }

    // ==================== List 操作 ====================

    /** List 右侧推入 */
    public long lPush(String key, Object value) {
        return Optional.ofNullable(redisTemplate.opsForList().rightPush(key, value)).orElse(0L);
    }

    /** List 左侧弹出 */
    @SuppressWarnings("unchecked")
    public <T> T lPop(String key) {
        return (T) redisTemplate.opsForList().leftPop(key);
    }

    /** List 获取全部 */
    public List<Object> lRange(String key, long start, long end) {
        return redisTemplate.opsForList().range(key, start, end);
    }

    /** List 获取长度 */
    public long lSize(String key) {
        return Optional.ofNullable(redisTemplate.opsForList().size(key)).orElse(0L);
    }

    // ==================== Set 操作 ====================

    /** Set 添加 */
    public long sAdd(String key, Object... values) {
        return Optional.ofNullable(redisTemplate.opsForSet().add(key, values)).orElse(0L);
    }

    /** Set 是否存在 */
    public boolean sIsMember(String key, Object value) {
        return Boolean.TRUE.equals(redisTemplate.opsForSet().isMember(key, value));
    }

    /** Set 获取所有成员 */
    public Set<Object> sMembers(String key) {
        return redisTemplate.opsForSet().members(key);
    }

    /** Set 随机弹出 */
    @SuppressWarnings("unchecked")
    public <T> T sPop(String key) {
        return (T) redisTemplate.opsForSet().pop(key);
    }
}
```

**使用方式：**

```java
// Service 中注入 RedisUtil
private final RedisUtil redisUtil;

// 存入并设置过期
redisUtil.set("app:user:token:12345", token, 30, TimeUnit.DAYS);

// 取出
UserVO user = redisUtil.get("app:cache:user:12345");

// 自增计数
redisUtil.increment("app:counter:order:today");

// Hash 存用户信息
redisUtil.hSet("app:user:info:12345", "username", "zhang");
redisUtil.hGet("app:user:info:12345", "username");
```

---

## 三、Key 命名规范

```
{项目}:{模块}:{类型}:{标识}

示例：
app:user:token:{userId}          # 用户 Token
app:user:info:{userId}           # 用户信息缓存
app:order:lock:{orderId}         # 订单分布式锁
app:sys:dict:{dictKey}           # 字典缓存
app:api:rate:{userId}:{api}      # API 限流
app:counter:order:today          # 今日订单计数器
```

| 规则 | 说明 |
|------|------|
| 分隔符 | 用 `:` 不用 `_` 或 `-`（Redis 自带分组） |
| 全部小写 | 不混用大小写 |
| 动态值用 `{}` 占位 | `{userId}` 而非硬编码具体值 |

---

## 四、过期时间

| 类型 | 默认过期 | 说明 |
|------|---------|------|
| Token | 30 天 | 对应 SaToken 配置 |
| 业务缓存 | 1 小时 | 用户信息、字典数据等短期不变的数据 |
| 验证码 | 5 分钟 | 短信/邮件验证码 |
| 简易分布式锁 | 30 秒 | 基于 `setIfAbsent`，防止死锁 |
| 计数器/限流 | 不超时 | 计数器一般不做全局过期 |

**禁止不设过期时间长期缓存数据**（计数器除外），避免 Redis 内存膨胀。

---

## 五、分布式锁

一般业务不需要分布式锁，仅高并发关键场景（如库存扣减、订单状态流转）按需使用。

```java
// 简易实现（基于 setIfAbsent + expire）
public boolean tryLock(String key, long timeout, TimeUnit unit) {
    return redisUtil.setIfAbsent("app:order:lock:" + key, "1", timeout, unit);
}

public void unlock(String key) {
    redisUtil.delete("app:order:lock:" + key);
}
```

如果业务强依赖分布式锁（锁续期、可重入等），再引入 Redisson。

---

## 六、禁止事项

| 禁止 | 原因 |
|------|------|
| 直接使用 `redisTemplate` 存取 | 用 `RedisUtil` 统一封装 |
| Key 硬编码散落各处 | 定义常量：`RedisKeys.USER_TOKEN` |
| 不设过期时间 | 内存膨胀，极端情况 OOM |
| 存储大对象（>10KB） | 换用对象存储（MinIO/OSS） |
| `keys *` 在线环境使用 | 阻塞 Redis，用 `scan` 替代 |
| 敏感信息明文存 Redis | 必要时脱敏后存储 |

---

## 七、相关文件

| 文件 | 关联内容 |
|------|---------|
| `../quality/code-style-guide.md` | Key 常量定义（`CacheConstants` / `RedisKeys`） |
| `../auth/auth-basic.md` | SaToken 共享 Redis Session |
