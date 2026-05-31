# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 仓库用途

这是一个 Java 后端开发规范仓库，用于约束 AI 代码生成行为。规范的目标技术栈为 Spring Boot 3 + Spring Cloud 微服务。

## 如何使用

在编写任何 Java 代码前，先读取 `agents/coder/README.md`（规范索引），根据当前任务类型找到对应的规范文件，读取并遵守。

规范文件禁止修改，只读。

## 目录结构

```
agents/coder/
├── README.md                  # 入口索引，按任务类型指引读取
├── architecture/              # 架构规范（包结构、微服务项目结构）
├── layered/                   # 分层规范（Controller、Service、Mapper）
├── infrastructure/            # 基础设施（Result、Swagger、配置、日志）
└── quality/                   # 质量规范（代码风格、国际化、错误码）
```
