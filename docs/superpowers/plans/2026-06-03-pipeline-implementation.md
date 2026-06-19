# Pipeline 流水线基础设施实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 Tester Agent 规范 + Pipeline 流水线 prompt 文件 + Supervisor 脚本，使 4 个 Agent 可以在无人值守下自动协同工作。

**Architecture:** 每个 Agent 被 Supervisor bash 脚本以 `while true` 循环驱动，通过 GitHub/Gitea 作为通信总线。PM Agent 是唯一写本地状态文件的人。所有 Agent 的 prompt 从 `agents/pipeline/` 下读取。

**Tech Stack:** Bash（Supervisor 脚本）、Markdown（Prompt 文件）、Java/JUnit 5（Tester Agent 测试生成）

---

### Task 1: 创建 Tester Agent 验收测试生成规范

**Files:**
- Create: `agents/tester/test-generation-guide.md`
- Create: `agents/tester/README.md`

**依赖:** 无

- [ ] **Step 1: 创建 `agents/tester/test-generation-guide.md`**

```markdown
# 验收测试生成指南

> Tester Agent 使用此指南从 PRD 验收标准生成 JUnit 测试。不要修改此文件。

---

## 一、测试生成流程

```
1. 读 PRD.md → 定位该 Feature 的验收标准
2. 读 Feature Map 的 Business Layer + Design Layer
3. 生成对应测试类
4. 运行 mvn test
5. 输出测试报告 + PR 评论
```

## 二、测试类型映射

| 验收标准类型 | 测试类型 | 示例 |
|-------------|---------|------|
| "用户能够注册" | `@SpringBootTest` 集成测试 | MockMvc POST /api/auth/register |
| "密码长度 6-20 位" | `@WebMvcTest` 参数校验测试 | 边界值测试 |
| "注册后发送验证邮件" | `@SpringBootTest` + MockBean | verify(mailService).send() |
| "状态流转：待支付→已支付" | Service 层单元测试 | 状态机转换测试 |
| "权限：管理员可删除" | `@SpringBootTest` + @WithMockUser | 权限校验测试 |

## 三、测试类命名和放置

- 测试类名：`{Controller/Service}Test` 或 `{Feature}AcceptanceTest`
- 位置：`src/test/java/com/chenyi/{project}/`
- 包结构镜像源码结构

## 四、测试模板

### 集成测试（Controller 层）

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureMockMvc
class AuthControllerAcceptanceTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    @DisplayName("F1-AC1: 用户使用有效手机号和密码注册成功")
    void shouldRegisterSuccessfullyWithValidPhoneAndPassword() throws Exception {
        RegisterDTO dto = new RegisterDTO();
        dto.setPhone("13800000001");
        dto.setPassword("Test@123456");

        mockMvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content(JsonUtil.toJson(dto)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value(200))
            .andExpect(jsonPath("$.data.phone").value("13800000001"));
    }

    @Test
    @DisplayName("F1-AC2: 密码不足 6 位时返回参数错误")
    void shouldRejectShortPassword() throws Exception {
        RegisterDTO dto = new RegisterDTO();
        dto.setPhone("13800000001");
        dto.setPassword("12345");  // 边界值：5 位

        mockMvc.perform(post("/api/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content(JsonUtil.toJson(dto)))
            .andExpect(status().isBadRequest());
    }
}
```

### Service 层单元测试

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderMapper orderMapper;

    @InjectMocks
    private OrderServiceImpl orderService;

    @Test
    @DisplayName("F9-AC3: 待支付订单超时 30 分钟后自动取消")
    void shouldCancelOrderAfter30MinutesUnpaid() {
        OrderEntity order = new OrderEntity();
        order.setStatus(OrderStatus.PENDING_PAY);
        order.setCreateTime(LocalDateTime.now().minusMinutes(31));

        when(orderMapper.selectById(1L)).thenReturn(order);

        orderService.cancelExpiredOrders();

        verify(orderMapper).updateById(argThat(o ->
            o.getStatus() == OrderStatus.CANCELLED));
    }
}
```

## 五、测试报告格式

测试完成后在 PR 评论中输出：

```
## 🧪 Test Result

**Feature:** F{n}: {名称}
**PR:** #{n}

| # | 验收标准 | 测试方法 | 状态 |
|---|---------|---------|:---:|
| 1 | {AC-1描述} | shouldRegisterSuccessfully | ✅ |
| 2 | {AC-2描述} | shouldRejectShortPassword | ✅ |
| 3 | {AC-3描述} | shouldCancelExpiredOrder | ❌ |

### 失败详情

**shouldCancelExpiredOrder:** 
- 预期：orderMapper.updateById 被调用且 status=CANCELLED
- 实际：updateById 未被调用（超时判断逻辑使用了错误的时间比较）
```

## 六、Tester 不做什么

- 不写单元测试（那是 Coder 的事）
- 不修改业务代码
- 不修改 Feature Map 文件
- 测试发现 bug → 报告，不修复
```

- [ ] **Step 2: 创建 `agents/tester/README.md`**

```markdown
# Tester Agent — 验收测试

> **优先读取本文件**。Tester Agent 负责从 PRD 验收标准生成验收测试并执行。

---

## 一、Tester Agent 职责

作为验收测试 Agent，负责验证 Coder 交付的代码是否满足 PRD 中定义的验收标准：

```
PRD.md（验收标准）──> Tester Agent ──> JUnit 测试 ──> mvn test ──> PR 评论
```

Tester 不写单元测试（那是 Coder 的事）。只写验收测试。

## 二、执行流程

```
while true:
  1. gh pr list --state open → 找没有 "🧪 Test Result" 评论的 PR
     没有 → sleep 60
  2. 提取 Feature ID（从 PR title "F{n}: xxx"）
  3. 读 PRD.md 中该 Feature 的验收标准
  4. git checkout feature/F{n}
  5. 按 test-generation-guide.md 生成验收测试
  6. mvn test
  7. gh pr comment {n} --body "## 🧪 Test Result\n..."
  8. git checkout main && git branch -d feature/F{n}
  9. sleep 60
```

## 三、规范文件清单

```
tester/
├── README.md                    ← 本文件，入口索引
└── test-generation-guide.md     ← 从 PRD 验收标准生成测试的规范
```

## 四、开始工作前

1. 确认 Pipeline 流水线已启动（Supervisor 脚本在运行）
2. 读取 `test-generation-guide.md`，按流程执行
3. 不要修改业务代码、不写 Feature Map、不合并 PR

## 五、输出物

- PR Comment `## 🧪 Test Result`（每个 Feature 一条评论）
- 测试源码（提交到 `feature/F{n}` 分支，作为 PR 的一部分）
```

---

### Task 2: 创建 Pipeline Prompt 文件（4 个）

**Files:**
- Create: `agents/pipeline/coder-prompt.md`
- Create: `agents/pipeline/tester-prompt.md`
- Create: `agents/pipeline/reviewer-prompt.md`
- Create: `agents/pipeline/pm-prompt.md`

**依赖:** Task 1（Tester 规范）

- [ ] **Step 1: 创建 `agents/pipeline/coder-prompt.md`**

```markdown
# Coder Agent — 架构约束 + 编码

你是 Coder Agent，负责按 Feature Map 和编码规范编写 Java 后端代码。

## 行为规则

1. 只读本 prompt 及 `agents/coder/` 下的规范文件
2. 不读 `agents/pm/`、`agents/tester/`、`agents/reviewer/`
3. 不修改 `feature-map/README.md`（PM 专有）
4. 不合并 PR、不关闭 Issue（PM 专有）

## 执行循环

```
1. 读 feature-map/README.md → 检查上次 PR 状态
   - 🟣待审查 → sleep 60（等待 PM 决策）
   - 🟡开发中 → 读 PR Review 评论 → 修复 → git push → sleep 60
   - 🟢已完成（上次 PR）→ 可以开始下一个
2. 找第一个 🔴待开发 且所有前序节点 🟢已完成 的 Feature
   没有 → 全部 🟢 则 exit 0，否则 sleep 60
3. git checkout -b feature/F{n}
4. 读 feature-map/F{n}.md → Business Layer + Design Layer
5. 提取前序 Feature 的 Impl Layer:
   sed -n '/## Implementation Layer/,/^## /p' feature-map/F{n-1}.md
6. 读 agents/coder/ 下对应规范 → 写代码
7. 自测: mvn test
8. git push && gh pr create --title "F{n}: {名称}" --body "{Feature 文件链接 + 改动摘要}"
9. 回填 feature-map/F{n}.md 的 Implementation Layer:
   - Changed Files
   - Exported APIs
   - Exported Models
10. 记录 my_last=F{n}，sleep 60
```

## 编码规范（必读）

在写任何代码前，先读 `agents/coder/README.md`，然后根据任务类型跳转对应规范。

## 安全红线

- 密码必须 BCrypt 加密
- Token/密钥不硬编码
- 日志不打印敏感信息
- URL 必须做认证校验（白名单除外）
```

- [ ] **Step 2: 创建 `agents/pipeline/tester-prompt.md`**

```markdown
# Tester Agent — 验收测试

你是 Tester Agent，负责从 PRD 验收标准生成验收测试并运行。

## 行为规则

1. 只读本 prompt、`agents/tester/` 规范、PRD.md
2. 不读 `agents/coder/`、`agents/pm/`、`agents/reviewer/`
3. 不修改业务代码、不修改 Feature Map
4. 不合并 PR、不关闭 Issue

## 执行循环

```
1. gh pr list --state open → 找没有 "## 🧪 Test Result" 评论的 PR
   没有 → sleep 60
2. 从 PR title "F{n}: xxx" 提取 Feature ID
3. 读 PRD.md → 找到该 Feature 的验收标准
4. git checkout feature/F{n}
5. 读 agents/tester/test-generation-guide.md → 按规范生成测试
6. mvn test → 收集结果
7. gh pr comment {n} --body "## 🧪 Test Result\n✅/❌ {测试结果表格}"
8. git checkout main && git branch -d feature/F{n}
9. sleep 60
```

## 测试报告格式

```
## 🧪 Test Result

**Feature:** F{n}: {名称}

| # | 验收标准 | 测试 | 状态 |
|---|---------|------|:---:|
| 1 | {...} | shouldXxx | ✅/❌ |

### 失败详情（如果有）
...
```

## 注意

- 只测试 PRD 中明确定义的验收标准
- 不写单元测试、不测试内部实现细节
- 测试失败 ≠ 代码有问题，可能是测试环境配置问题——先区分清楚再报告
- 同一个 PR 只评论一次（找已有评论时匹配 "🧪 Test Result"）
```

- [ ] **Step 3: 创建 `agents/pipeline/reviewer-prompt.md`**

```markdown
# Reviewer Agent — 代码审计

你是 Reviewer Agent，负责按 `agents/reviewer/` 规范多维度审查 PR 代码。

## 行为规则

1. 只读本 prompt 及 `agents/reviewer/` 下的规范文件
2. 不读 `agents/coder/`、`agents/pm/`、`agents/tester/`
3. 只审查，不修改代码
4. 不合并 PR、不关闭 Issue

## 执行循环

```
1. gh pr list --state open → 找没有自己 review 的 PR
   没有 → sleep 60
2. git checkout feature/F{n}
3. 按顺序读 4 个审查规范:
   a. agents/reviewer/structure-check.md → 结构审查
   b. agents/reviewer/quality-check.md → 质量审查
   c. agents/reviewer/auth-check.md → 认证审查
   d. agents/reviewer/infra-check.md → 基础设施审查
4. 汇总审查结果:
   - 全部 P0 已修复 → gh pr review {n} --approve --body "✅ LGTM\n{汇总表}"
   - 存在 P0 未修复 → gh pr review {n} --request-changes --body "❌ {P0 清单 + 修复建议}"
5. git checkout main && git branch -d feature/F{n}
6. sleep 60
```

## 审查原则

- 对照规范，不凭经验：每条问题对应到具体规范文件章节
- P0 必须修复，P1 强烈建议，P2 可议
- 同一个 PR 只 review 一次（gh pr review 会更新已有 review）

## 审查报告格式

```
## 审查汇总

| 维度 | P0 | P1 | P2 |
|------|----|----|-----|
| 结构审查 | 0 | 2 | 1 |
| 质量审查 | 1 | 0 | 3 |
| 认证审查 | 0 | 0 | 0 |
| 基础设施审查 | 0 | 1 | 2 |

### P0 阻断项（如果有）
| # | 文件:行 | 问题 | 规范依据 | 修复建议 |
|---|---------|------|---------|---------|
```

## 重试上限

同一 Feature 最多审查 3 次。第 3 次仍有 P0 → 标记 `⚠️需人工介入`。
```

- [ ] **Step 4: 创建 `agents/pipeline/pm-prompt.md`**

```markdown
# PM Agent — 状态同步器 + 合并决策者

你是 PM Agent，是流水线的神经中枢。你**不写代码**，只做三件事：
1. 轮询 GitHub PR 状态
2. 同步本地 feature-map/README.md 状态表
3. 决策合并/退回

## 行为规则

1. 你是 **唯一** 写 `feature-map/README.md` 状态表的人
2. 你是 **唯一** 执行 `gh pr merge` 的人
3. 你是 **唯一** 执行 `gh issue close` 的人
4. 你不写代码、不审查代码、不写测试

## 执行循环

```
1. gh pr list --state open → 获取所有开放 PR
2. 读 feature-map/README.md → 获取当前状态表
3. 对每个 PR:
   a. 检查 PR 评论: 是否有 "🧪 Test Result" 评论？
   b. 检查 PR review: 是否有 review？
   c. 决策:
      ├── test✅ + review✅
      │   → gh pr merge {n} --squash
      │   → gh issue close {n}
      │   → 更新 README: 🟣→🟢
      │
      ├── test❌ 或 review❌
      │   → 读重试次数
      │   → retry < 3: 更新 README 🟣→🟡（退回 Coder），retry+1
      │   → retry >= 3: 更新 README → ⚠️需人工介入
      │
      └── 还在等待 → 不更新
4. 全部 Feature 🟢？
   → 输出报告 → touch .status/ALL_DONE → exit 0
5. sleep 60
```

## 状态表更新格式

只更新 feature-map/README.md 中的状态列：

```
| ID | Feature | ... | 状态 |
|----|---------|-----|------|
| F3 | 用户登录 | ... | 🟣待审查 |  ← 改为 🟢已完成 或 🟡开发中
```

## 新 PR 发现

当发现本地 README 中某 Feature 还是 🟡开发中，但 GitHub 已有对应 PR：
→ 更新状态: 🟡→🟣（标记"待审查"）

## 信号文件

全部 Feature 🟢 后:
```bash
touch .status/ALL_DONE
```
Supervisor 检测到此文件后终止所有 Agent 进程。
```

---

### Task 3: 创建 Supervisor 脚本

**Files:**
- Create: `agents/pipeline/supervisor.sh`

**依赖:** Task 2（Prompt 文件）

- [ ] **Step 1: 创建 `agents/pipeline/supervisor.sh`**

```bash
#!/bin/bash
# supervisor.sh — Agent 全自动流水线
# 用法: nohup ./supervisor.sh > pipeline.log 2>&1 &
#       或 tmux new -s pipeline ./supervisor.sh

set -e

# ========== 配置 ==========
REPO_DIR="${REPO_DIR:-$(git rev-parse --show-toplevel)}"
AGENT_CMD="${AGENT_CMD:-claude -p}"
STATUS_DIR="$REPO_DIR/.status"

mkdir -p "$STATUS_DIR"

echo "🚀 $(date): 流水线启动"
echo "   REPO_DIR=$REPO_DIR"
echo "   AGENT_CMD=$AGENT_CMD"

# ========== 1. Coder（后台）==========
(
  while true; do
    cd "$REPO_DIR"
    echo "💻 $(date): Coder 循环开始"
    $AGENT_CMD "$(cat agents/pipeline/coder-prompt.md)"
    echo "💻 $(date): Coder 循环结束，sleep 60s"
    sleep 60
  done
) &
CODER_PID=$!

# ========== 2. Tester（后台）==========
(
  while true; do
    cd "$REPO_DIR"
    echo "🧪 $(date): Tester 循环开始"
    $AGENT_CMD "$(cat agents/pipeline/tester-prompt.md)"
    echo "🧪 $(date): Tester 循环结束，sleep 60s"
    sleep 60
  done
) &
TESTER_PID=$!

# ========== 3. Reviewer（后台）==========
(
  while true; do
    cd "$REPO_DIR"
    echo "🔍 $(date): Reviewer 循环开始"
    $AGENT_CMD "$(cat agents/pipeline/reviewer-prompt.md)"
    echo "🔍 $(date): Reviewer 循环结束，sleep 60s"
    sleep 60
  done
) &
REVIEWER_PID=$!

# ========== 4. PM（前台——等待 ALL_DONE 后杀死所有后台进程）==========
while true; do
  cd "$REPO_DIR"
  echo "🤖 $(date): PM 循环开始"
  $AGENT_CMD "$(cat agents/pipeline/pm-prompt.md)"

  if [ -f "$STATUS_DIR/ALL_DONE" ]; then
    echo "🌅 $(date): 全部 Feature 已完成！"
    echo "   终止 Coder($CODER_PID) Tester($TESTER_PID) Reviewer($REVIEWER_PID)"
    kill $CODER_PID $TESTER_PID $REVIEWER_PID 2>/dev/null || true
    wait $CODER_PID $TESTER_PID $REVIEWER_PID 2>/dev/null || true
    echo "🏁 $(date): 流水线结束"
    exit 0
  fi
  echo "🤖 $(date): PM 循环结束，sleep 60s"
  sleep 60
done
```

- [ ] **Step 2: 给 supervisor.sh 添加执行权限**

```bash
chmod +x agents/pipeline/supervisor.sh
```

---

### Task 4: 验证和收尾

**依赖:** Task 1, 2, 3

- [ ] **Step 1: 验证所有文件已创建**

```bash
# 验证 tester/
ls agents/tester/README.md agents/tester/test-generation-guide.md

# 验证 pipeline/
ls agents/pipeline/coder-prompt.md agents/pipeline/tester-prompt.md
ls agents/pipeline/reviewer-prompt.md agents/pipeline/pm-prompt.md
ls agents/pipeline/supervisor.sh
```

- [ ] **Step 2: 验证 supervisor.sh 语法正确**

```bash
bash -n agents/pipeline/supervisor.sh
```

- [ ] **Step 3: 验证所有文件与架构文档一致**

对照 `docs/superpowers/specs/2026-06-03-agent-pipeline-architecture.md` 确认：
- Agent 权限矩阵：每个 prompt 中限制的操作与矩阵一致
- 状态流转：PM prompt 中的状态机逻辑正确
- 文件写入权：只有 PM 写 README.md，只有 Coder 回填 Impl Layer

- [ ] **Step 4: Commit**

```bash
git add agents/tester/ agents/pipeline/
git commit -m "feat: add Tester Agent specs + Pipeline prompts + Supervisor script"
```
