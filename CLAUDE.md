# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库用途

这是一个 Java 后端开发规范仓库，用于约束 AI 代码生成行为。规范的目标技术栈为 Spring Boot 3 + Spring Cloud 微服务。

包含两个阶段的 Agent：
1. **coder/** — 架构约束：按规范写 Java 代码
2. **reviewer/** — 代码审计：多维度审查 AI 生成的代码

> 未来规划：阶段 1（analyst）—— 需求 → PRD → 技术规格 → API 设计 → 数据库设计。待建设。

## 如何使用

### 开发流程

```
阶段 1（coder）：按设计文档 + 架构规范生成 Java 代码
  入口：agents/coder/README.md

阶段 2（reviewer）：多维度审计 + 输出审计报告 + 修复建议
  入口：agents/reviewer/README.md
```

### 已有设计文档时

在编写任何 Java 代码前，先读取 `agents/coder/README.md`（规范索引），根据当前任务类型找到对应的规范文件，读取并遵守。

规范文件禁止修改，只读。

## 目录结构

```
agents/
├── coder/                      # 架构约束
│   ├── README.md               # 入口索引，按任务类型指引读取
│   ├── architecture/           # 架构规范（包结构、微服务项目结构）
│   ├── layered/                # 分层规范（Controller、Service、Mapper）
│   ├── infrastructure/         # 基础设施（Result、Swagger、配置、日志）
│   ├── auth/                   # 认证授权（基础→SSO→OAuth2）
│   └── quality/                # 质量规范（代码风格、国际化、错误码、数据库）
├── reviewer/                   # 代码审计
│   ├── README.md               # 审查入口，按流程执行
│   ├── structure-check.md      # 结构审查（包结构、分层调用、命名、注入）
│   ├── quality-check.md        # 质量审查（异常、日志、Result、数据库、校验）
│   ├── auth-check.md           # 认证审查（StpKit、登录、拦截器、权限）
│   └── infra-check.md          # 基础设施审查（Swagger、配置、Redis、国际化）
```
