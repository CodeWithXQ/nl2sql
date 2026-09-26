# NL2SQL 自助取数 Agent 设计开发文档

> 项目定位：给数据库装一个「能听懂人话、但绝不越权」的取数窗口。业务人员用自然语言问数据，Agent 转成 SQL 安全执行返回——核心壁垒不是「生成 SQL」，而是**四道关校验**（防注入 / 表级权限 / Schema 对齐 / 只读）。

---

## 1. 项目概述

### 1.1 一句话叙事

> 接真实 MySQL 表结构，LLM 把自然语言问题转成 SQL，生成后过四道关（注入 / 语法 / 权限 / 只读）才允许在只读连接上执行，返回结果 + 可解释的 SQL。

### 1.2 为什么做（真实付费刚需）

| 付费参照 | 产品 / 收费 |
|---|---|
| 阿里云 | DAS Agent 按 0.01 元/字符收费的 NL2SQL |
| 华为 | GaussDB 内置 NL2SQL 问数 |
| 中兴 | Nebula-EBASE NL2SQL 售卖 |

企业 BI 自助取数减人力，是云厂商在收钱的真实场景，不是「旅行规划 / 客服问答」那类 demo。

### 1.3 与已有项目的主线

```
TPC-H Agent（造引擎，底层）→ DB Doctor（诊断慢查询，运维）→ NL2SQL（自然语言问数，交互层）
```

三个项目串成「**AI 赋能数据库全链路**」：造引擎 → 治病 → 对话。这是区别于「只会调 API 做聊天 demo」的护城河。

---

## 2. 需求分析

### 2.1 目标场景

- 业务/运营人员不会写 SQL，用大白话查数（「最近 30 天北京的待支付订单有多少」）。
- 数据团队给业务开自助取数窗口，但要保证：**不越权、不被注入、不瞎编列名、只读**。

### 2.2 核心功能

| 功能 | 输入 | 输出 |
|---|---|---|
| F1 Schema 管理 | 真实 MySQL 库 | 表/列/类型结构摘要（喂 LLM） |
| F2 权限管理 | 用户 + 表权限映射 | 授权表集合 |
| F3 SQL 生成 | 自然语言 + schema + 权限 | 候选 SQL |
| F4 SQL 校验（四道关） | 候选 SQL | 放行 / 拦截 + 原因 |
| F5 执行 | 通过校验的 SQL | 查询结果 + 生成的 SQL |
| F6 评测 | NL2SQL 测试集 | 正确率 / 越权拦截 / 注入拦截 / 幻觉 |

### 2.3 非功能需求

- **只读**：任何写操作（UPDATE/DELETE/INSERT/DROP）一律拒绝。
- **可解释**：返回结果必须附带生成的 SQL，让用户看到「这答案怎么来的」。
- **可复现**：所有评测指标本地可重跑。

---

## 3. 系统架构

```
自然语言问题
   │
   ▼
① Schema 对齐 ── 读真实表结构（SHOW CREATE TABLE）+ 用户授权表
   │
   ▼
② LLM 生成 SQL（DeepSeek，prompt 注入 schema + 权限 + 只读约束）
   │
   ▼
③ SQL 校验器（四道关，缺一不可）
   ├─ 关1 注入防护：黑名单 + 多语句检测
   ├─ 关2 语法校验：sqlglot 解析 + EXPLAIN 试跑
   ├─ 关3 表级权限：提取 SQL 涉及的表 ⊆ 授权表
   └─ 关4 只读校验：仅放行单条 SELECT
   │
   ▼
④ 执行（只读连接）→ 返回结果 + 生成的 SQL
```

---

## 4. 技术选型

| 组件 | 选型 | 理由 |
|---|---|---|
| 语言 | Python 3.13 | LLM 生态，复用 rag/db-doctor 经验 |
| 数据库 | MySQL 8.0（复用 db_doctor 库） | orders 已有 100 万行，省造数 |
| DB 驱动 | PyMySQL | 纯 Python |
| LLM | DeepSeek（OpenAI 兼容） | 复用已有 key |
| SQL 解析 | sqlglot 30.x | 语法解析 / 表名提取 / 语句类型，工业级 |
| 结构化输出 | Pydantic | 校验结果可解析 |
| Web 框架 | FastAPI + uvicorn | 对外接口 |

> 刻意不引入 LangChain：核心链路（schema 对齐 / 生成 / 四道关校验 / 评测）自己实现。sqlglot 只做「SQL 解析」这一纯工具活，校验逻辑（注入规则 / 权限比对 / 只读判断）自己写。

---

## 5. 详细设计

### 5.1 Schema 管理 `schema_manager.py`

- 连 MySQL，`SHOW TABLES` + `SHOW CREATE TABLE` 拉真实表结构。
- 缓存为 schema 摘要（表名 → 列名 + 类型 + 备注），喂给 LLM。
- 提供 `get_tables()`、`get_schema_text()`（给 prompt 用）。

### 5.2 权限管理 `rbac.py`

- 内存/文件里的「用户 → 授权表」映射（演示用静态配置，生产接 DB）。
- `authorized_tables(user)` 返回该用户能查的表集合。
- 越权时抛出 `PermissionDenied`，带「涉及表 / 授权表」证据。

### 5.3 SQL 生成 `sql_generator.py`

- Prompt 三段：① schema 摘要（真实列名）② 用户授权表范围 ③ 约束（只生成单条 SELECT、列名必须真实存在、禁止写操作、禁止注释）。
- DeepSeek 生成，温度 0.1，返回 SQL 文本（不强制 JSON，SQL 本身是文本）。

### 5.4 SQL 校验器 `sql_validator.py`（核心壁垒）

四道关，任意一道不过即拦截，返回结构化拒绝原因：

```python
class ValidationResult(BaseModel):
    ok: bool
    sql: str
    reason: str          # 拦截原因（ok=False 时）
    tables: list[str]    # SQL 涉及的表
    checks: dict         # 四道关逐项结果
```

| 关 | 实现 | 拦截条件 |
|---|---|---|
| 1 注入防护 | 黑名单正则（UPDATE/DELETE/INSERT/DROP/ALTER/GRANT/INTO OUTFILE 等）+ 多语句检测（`;` 后仍有内容） | 命中即拦 |
| 2 语法校验 | sqlglot 解析（parse 失败=语法错）+ 可选 EXPLAIN 试跑 | parse 异常 / EXPLAIN 报错 |
| 3 表级权限 | sqlglot `find_all(Table)` 提取表名 → 比对授权表 | 有表不在授权集 |
| 4 只读校验 | sqlglot 判断根语句类型 | 非 SELECT 即拦 |

### 5.5 执行器 `executor.py`

- 用**只读连接**（`SET SESSION TRANSACTION READ ONLY`）执行通过校验的 SQL。
- 返回结果集 + 列名 + 生成的 SQL（可解释）。

### 5.6 评测 `evaluate.py`

| 指标 | 测试集 | 计算 |
|---|---|---|
| 生成 SQL 正确率 | 50 条自然语言问题 + 期望结果 | 执行结果比对 |
| 越权拦截率 | 无权限用户问越权表 | 应 100% 拦截 |
| 注入拦截率 | 注入样本（`; DROP`、`UNION SELECT` 等） | 应 100% 拦截 |
| Schema 幻觉率 | 问不存在的列/表 | 应 0%（不编列名） |

---

## 6. 数据模型（复用 db_doctor 库 + 扩 2 表）

```
orders（复用已有 100 万行）：id, user_id, status, amount, create_time, remark
users（新造 10 万行）：id, name, city, level
products（新造 1000 行）：id, name, category, price
```

3 表才展示 NL2SQL 的 join 能力（「北京用户买了多少单」「哪个品类卖最好」）。

---

## 7. 可验证指标定义

| 指标 | 目标 |
|---|---|
| 生成 SQL 正确率 | ≥ 80%（50 条测试集） |
| 越权拦截率 | 100% |
| 注入拦截率 | 100% |
| Schema 幻觉率 | 0%（不编造列/表名） |

---

## 8. 开发里程碑

| 阶段 | 内容 |
|---|---|
| M1（Day1-2） | Schema 管理 + 权限管理 + users/products 造数 |
| M2（Day3-5） | SQL 生成 + 四道关校验器 |
| M3（Day6-8） | 50 条测试集 + 评测四指标 |
| M4（Day9-10） | FastAPI + README + GitHub |

---

## 9. 测试方案

| 层 | 覆盖 |
|---|---|
| 单元 | sql_validator 四道关（注入/语法/权限/只读） |
| 单元 | rbac 授权表比对 |
| 集成 | evaluate.py 四指标 |

---

## 10. 诚实边界

- 数据自建，非真实生产。
- 正确率基于自构造测试集，非生产验证。
- NL2SQL **不做模型微调**，靠 prompt + 校验器，如实说。
- 权限是静态配置演示，生产要接真实权限系统（如实说）。

---

## 11. 风险与对策

| 风险 | 对策 |
|---|---|
| LLM 生成 SQL 不稳定 | 温度 0.1 + 校验器兜底 + 失败重试 |
| 表名提取不准确（子查询/别名） | sqlglot find_all(Table) 兜底 |
| 注入样本绕过黑名单 | 多语句检测 + 只读 + 只放行 SELECT 三层叠加 |

---

*文档版本 v1.0 · 2026-09-26*
