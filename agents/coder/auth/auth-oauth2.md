# OAuth2 第三方登录规范

> 适用：接入微信、GitHub、企业微信等第三方 OAuth2 登录
> 依赖：先读 `auth-sso.md`，OAuth2 作为 SSO 的登录方式之一

---

## 一、架构

```
用户 → Gateway → project-auth → [第三方OAuth2]
                       │
              微信 / GitHub / 企业微信
                       │
              获取 openId → 映射本地用户
                       │
              签发 StpKit Token → 返回用户
```

OAuth2 是 SSO 认证中心的**一种登录方式**，最终都落到统一的 `StpKit` Token 体系。

---

## 二、OAuth2 接入流程

```
1. 用户在前端点击"微信登录"
2. 前端重定向到微信授权页
3. 用户授权通过
4. 微信回调 project-auth 的 /api/auth/oauth/wechat/callback?code=xxx
5. project-auth 用 code 换 access_token
6. 用 access_token 获取 openId/unionId
7. 通过 openId 查 sys_user_oauth 表，关联本地用户
8. 签发 StpKit.USER Token，返回给前端
```

---

## 三、第三方配置

```yaml
# application.yml（project-auth）
oauth2:
  wechat:
    app-id: ${WECHAT_APP_ID:}
    app-secret: ${WECHAT_APP_SECRET:}
    redirect-uri: https://auth.example.com/api/auth/oauth/wechat/callback
  github:
    client-id: ${GITHUB_CLIENT_ID:}
    client-secret: ${GITHUB_CLIENT_SECRET:}
    redirect-uri: https://auth.example.com/api/auth/oauth/github/callback
```

敏感信息通过环境变量注入，不写死在配置文件。

---

## 四、用户映射表

```sql
CREATE TABLE sys_user_oauth (
    id          BIGINT       NOT NULL COMMENT '主键ID',
    user_id     BIGINT       NOT NULL COMMENT '本地用户ID',
    provider    VARCHAR(32)  NOT NULL COMMENT '平台：wechat/github',
    open_id     VARCHAR(128) NOT NULL COMMENT '第三方唯一标识',
    create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '绑定时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_provider_openid (provider, open_id),
    KEY idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='OAuth关联表';
```

---

## 五、微信登录示例

```java
@Tag(name = "OAuth认证")
@RestController
@RequestMapping("/api/auth/oauth")
public class OAuthController {

    /** 微信回调 */
    @GetMapping("/wechat/callback")
    public Result<LoginVO> wechatCallback(@RequestParam String code) {
        // 1. code 换 access_token
        WechatToken token = wechatOAuthService.getAccessToken(code);
        // 2. 获取 openId
        WechatUserInfo wechatUser = wechatOAuthService.getUserInfo(token);
        // 3. 查本地映射，没有则创建本地用户
        UserEntity user = userService.getOrCreateByOauth("wechat",
            wechatUser.getOpenId(), wechatUser.getNickname());
        // 4. 签发 StpKit Token
        StpKit.USER.login(user.getId());
        return Result.success(new LoginVO(user.getId(), StpKit.USER.getTokenValue()));
    }
}
```

---

## 六、日志记录

OAuth 登录是跨系统的关键链路，必须记录日志：

```java
log.info("OAuth登录 provider={}, openId={}, userId={}, result=success",
    provider, openId, userId);
```

不打印 accessToken、code 等敏感信息。
