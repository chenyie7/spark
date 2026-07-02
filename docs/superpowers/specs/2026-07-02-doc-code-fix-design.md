# 文档与代码修复 — 设计文档

日期: 2026-07-02
状态: 已确认

## 背景

在 commit `86d8740` 中，reviewer 的 check_system 进行了重构：删除了 `scanner.py`、`config.py`、`code-check-config.yaml`、`program-checks.yaml` 和旧 hooks，替换为 "fuck-u-code MCP 静态分析 + AI 统一审查" 的新工作流。但多处文档和代码未同步更新，导致：

- 文档引用已删除的文件和命令
- 规则数量与实际不一致
- 代码中存在写入已删除文件的逻辑
- 存在僵尸依赖

## 修改范围

A（修文档）+ B（修代码）+ 新手引导写入 README。

## 修改清单

### 代码修复（2 个文件）

#### 1. `agents/scheduler/pipeline_engine/cli.py`

- L61: 删除或修正写入已删除文件 `code-check-config.yaml` 的逻辑

#### 2. `agents/reviewer/check_system/requirements.txt`

- 删除 `tree-sitter>=0.23.0`
- 删除 `tree-sitter-java>=0.23.0`

### 文档修复（5 个文件）

#### 3. `CLAUDE.md`

| L39-51 | 删除已废弃的 `scan` CLI 命令示例 |
| L98 | 删除 "46 条确定性规则"，去掉具体数字 |
| 目录结构 | 更新 `check_system/` 下的文件列表（移除 scanner.py, config.py, program-checks.yaml） |

#### 4. `agents/reviewer/README.md`

**重写以下章节**，描述当前 "fuck-u-code MCP 静态分析 + AI 统一审查" 两步流程：
- "审查流程" 部分
- "目录结构" 部分
- 删除所有对 scanner.py, config.py, code-check-config.yaml, program-checks.yaml, hooks/ 的引用

#### 5. `agents/reviewer/review.skill.md`

- "50条审查清单" → "涵盖结构、质量、认证、基础设施等多维度审查"

#### 6. `agents/scheduler/pipeline.yaml`

- "50条审查清单" → "涵盖结构、质量、认证、基础设施等多维度审查"

#### 7. `agents/scheduler/build.skill.md`

- 删除或修正 `--continue` 的引用（实际不存在该参数）

### 新增内容（1 个文件）

#### 8. `README.md`（项目根目录）

新增 "快速开始" 章节，包含：
- 环境要求（Python 版本、Node.js、Java）
- 依赖安装步骤
- MCP 配置说明（fuck-u-code）
- 第一个 `/build` 使用示例

## 执行顺序

1. 修复代码（cli.py, requirements.txt）
2. 重写 reviewer/README.md（核心改动）
3. 修复 CLAUDE.md
4. 修复 review.skill.md, pipeline.yaml, build.skill.md
5. 给 README.md 新增快速开始章节
6. 全局复查，确保无遗漏

## 验收标准

- `grep -r "scanner.py\|program-checks\|code-check-config" --include="*.md"` 仅在历史描述中提及，无功能性引用
- `grep -r "46 条\|50 条\|50条" --include="*.md"` 无结果
- `grep -r "tree-sitter" requirements.txt` 无结果
- `grep -r "\-\-continue" --include="*.md"` 仅在描述非本项目的其他内容中出现
- `README.md` 包含完整的快速开始章节
- `cli.py` 不再引用不存在的配置文件
