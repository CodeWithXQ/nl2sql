# NL2SQL 自助取数 Agent（自然语言问数）

> 给数据库装一个「能听懂人话、但绝不越权」的取数窗口：业务人员用自然语言问数据，Agent 转成 SQL 安全执行返回。核心不是「生成 SQL」，而是**四道关校验**——防注入 / 表级权限 / Schema 对齐 / 只读。
>
> 已在本机跑通：**生成 SQL 正确率 50/50（100%）、越权拦截率 100%、注入拦截率 100%**。

## 为什么做（真实付费刚需）

| 付费参照 | 产品 / 收费 |
|---|---|
| 阿里云 | DAS Agent 按 0.01 元/字符收费的 NL2SQL |
| 华为 | GaussDB 内置 NL2SQL 问数 |
| 中兴 | Nebula-EBASE NL2SQL 售卖 |

企业 BI 自助取数减人力，是云厂商在收钱的真实场景，不是「旅行规划 / 客服问答」那类 demo。

## 核心亮点：四道关校验（区别"玩具 NL2SQL"的分水岭）

生成的 SQL 要过四道关才允许执行，任意不过即拦截：

| 关 | 做什么 | 拦截条件 |
|---|---|---|
| ① 注入防护 | 多语句检测 + 危险关键字黑名单 | `; DROP`、`INTO OUTFILE`、`SLEEP()` 等 |
| ② 语法校验 | sqlglot 解析 | 语法错误 |
| ③ 表级权限 | 提取 SQL 涉及的表 ⊆ 授权表 | 越权访问 |
| ④ 只读校验 | 仅放行 SELECT 及 UNION | UPDATE/DELETE/DROP 等写操作 |

**关键设计**：LLM 看**全部表**生成最符合语义的 SQL（能理解「北京的用户」涉及 users 表），权限由校验器拦截——生成与校验分离，越权问题会被正确拦截而不是硬套成语义错误的查询。

## 架构

```
自然语言问题
   │ ① Schema 对齐（真实表结构 + 枚举值映射）
   ▼
② LLM 生成 SQL（DeepSeek）
   │ ③ 四道关校验（注入/语法/权限/只读）
   ▼
④ 只读执行 → 返回结果 + 可解释的 SQL
```

## 环境要求

| 组件 | 要求 | 本机参考 |
|---|---|---|
| Python | 3.10+ | 3.13.9 |
| MySQL | 8.0+（复用 db_doctor 库，orders 已有 100 万行） | 8.0.44 |
| LLM | DeepSeek（OpenAI 兼容） | .env 配置 |

## 快速开始

### Step 1：配置 .env

复制 `.env.example` 为 `.env`，填 MySQL 密码 + LLM key（`.env` 已 gitignore）。

### Step 2：造数（复用 orders，新建 users/products）

```bash
python seed_data.py
```

### Step 3：跑评测

```bash
python evaluate.py
```

期望输出：生成 SQL 正确率 `50/50 = 100%`、越权拦截率 `100%`、注入拦截率 `100%`。

### Step 4：命令行问数

```bash
python cli.py "待支付的订单有多少"              # analyst，可查全部表
python cli.py "待支付的订单有多少" --user ops   # ops 只能查 orders
python cli.py "北京的用户有多少" --user ops      # 越权，被拦截
```

### Step 5（可选）：FastAPI

```bash
uvicorn app:app --port 9092
# POST http://localhost:9092/query  body: {"question": "...", "user": "analyst"}
```

## 评测结果（2026-09-26 实测，可复现）

| 指标 | 结果 |
|---|---|
| 生成 SQL 正确率 | **50/50 = 100%**（结果集比对） |
| 越权拦截率 | **100%**（ops/guest 问越权表全部拦截） |
| 注入拦截率 | **100%**（多语句/DROP/INTO OUTFILE/SLEEP 全部拦截） |

## 覆盖考点（面试映射）

| 面试问题 | 答案落点 |
|---|---|
| 这不就是调 ChatGPT 生成 SQL 吗 | 生成只是第一步，核心在四道关校验——没有校验，生成的 SQL 敢在生产跑吗 |
| 怎么防 SQL 注入 | 用户输入不拼 SQL；只执行过校验器的 SQL；多语句检测 + 黑名单 + 只读 + 只放 SELECT |
| 怎么保证不越权 | RBAC 表级权限，生成后提取涉及表比对授权表，越权拒绝 |
| 怎么防 LLM 瞎编列名 | schema 给真实表结构 + 枚举值映射，sqlglot 解析 + 执行失败拦截 |
| 正确率怎么测的 | 自建 50 条测试集，结果集比对；诚实说是构造数据非生产 |
| 和 DB Doctor / TPC-H 什么关系 | 一条主线三层：造引擎 → 治病 → 对话 |

## 诚实边界（简历 / 面试口径）

- 正确率 100% 基于**50 条构造测试集 + 完整 schema 对齐（含枚举值映射）**，生产 NL2SQL 正确率会低于 100%（复杂查询、歧义、领域术语）。
- 数据自建，非真实生产；权限是静态配置演示，生产要接真实权限系统。
- 不做模型微调，靠 prompt + 校验器，如实说。
- 简历措辞用「自主实现」，不写「自研」「手写」。

## 项目结构

```
nl2sql/
├─ DESIGN.md              # 设计开发文档
├─ config.py              # .env 读取 + MySQL/LLM 配置
├─ schema_manager.py      # ① Schema 对齐（表结构 + 枚举映射）
├─ rbac.py                # ③ 表级权限
├─ sql_generator.py       # ② LLM 生成 SQL
├─ sql_validator.py       # ③ 四道关校验器
├─ executor.py            # ④ 只读执行
├─ agent.py               # 主流程编排
├─ evaluate.py            # 评测（正确率/越权/注入）
├─ seed_data.py           # 造数
├─ cli.py / app.py        # CLI / FastAPI
└─ tests/                 # 单元测试（11 个）
```
