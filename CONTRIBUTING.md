# 贡献指南

感谢你考虑为 Spark 做贡献！无论是新增规范、改进检查规则、优化报告格式，还是修复 Bug，我们都非常欢迎。

## 开发环境

```bash
# 1. Fork & Clone
git clone https://github.com/YOUR_USERNAME/spark.git
cd spark

# 2. 安装依赖（只需 PyYAML）
pip install pyyaml

# 3. 运行测试，确认环境正常
python3 -m pytest agents/*/tests/ -v
```

## 项目结构

```
agents/
├── coder/          # 编码规范库（Markdown 规范文件）
├── reviewer/       # 代码审查系统（Python CLI + YAML 检查清单）
├── scheduler/      # 流水线调度引擎（Python）
└── pm/             # 需求沟通 Agent

benchmarks/hooks/   # 基准测试采集与合成脚本
docs/               # 项目文档
```

## 贡献流程

1. **Fork 仓库**，创建你的特性分支：
   ```bash
   git checkout -b feat/your-feature
   ```

2. **编写代码并测试**：
   ```bash
   python3 -m pytest agents/*/tests/ -v
   ```

3. **提交**（使用 [Conventional Commits](https://www.conventionalcommits.org/) 风格）：
   ```bash
   git commit -m "feat: 描述你的改动"
   ```

4. **推送并创建 Pull Request**。

## 贡献方向

- **新增规范文件**：补充当前规范库未覆盖的领域（如消息队列、定时任务）
- **扩展检查清单**：在 `agents/reviewer/check_system/rules/ai-checklist.yaml` 中添加新的检查规则
- **改进报告模板**：优化 Markdown 报告的可读性和信息密度
- **增强调度引擎**：支持更复杂的 DAG 流转逻辑
- **增加测试覆盖**：补充边界场景的测试用例
- **完善基准测试**：扩展 `benchmarks/hooks/schema.py` 和 `compare.py` 的分析维度

## 规范文件编写指南

规范文件放在 `agents/coder/` 下，遵循以下约定：

1. **每个规范文件必须包含**：
   - 明确的适用范围
   - 正确示例（✅）和错误示例（❌）
   - 代码片段标注语言类型

2. **修改规范后**，同步更新 `agents/reviewer/check_system/rules/ai-checklist.yaml` 中的对应检查规则

3. **新增规范文件后**，更新 `agents/coder/README.md`（规范索引）添加指向

## Code Review

所有 PR 会经过：
1. 自动化测试（GitHub Actions）
2. 人工 Review — 关注：规范一致性、测试覆盖、文档同步

## 提问

如有问题，欢迎在 GitHub Issues 中提出讨论。
