"""SQL 生成：LLM 把自然语言问题转成 SQL（prompt 注入 schema + 权限 + 只读约束）。"""
from __future__ import annotations

from openai import OpenAI

from config import get_llm_config


class SQLGenerator:
    def __init__(self):
        cfg = get_llm_config()
        self._client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])
        self._model = cfg["model"]
        self._temperature = cfg["temperature"]
        self._max_tokens = cfg["max_tokens"]

    def generate(self, question: str, schema_text: str, authorized_tables: list[str]) -> str:
        """生成 SQL 文本（去掉 markdown 围栏和结尾分号）。"""
        prompt = self._build_prompt(question, schema_text, authorized_tables)
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        content = resp.choices[0].message.content.strip()
        return self._clean_sql(content)

    def _clean_sql(self, content: str) -> str:
        """去掉 markdown 代码块围栏和结尾分号。"""
        content = content.strip()
        content = content.strip("`")
        if content.lower().startswith("sql"):
            content = content[3:].strip()
        return content.strip().rstrip(";").strip()

    def _build_prompt(self, question: str, schema_text: str, authorized_tables: list[str]) -> str:
        tables = ", ".join(authorized_tables)
        return f"""你是一名 SQL 专家。把用户的自然语言问题转成一条 MySQL SELECT 语句。

【数据库表结构（真实，列名以此为准）】
{schema_text}

【该用户授权可查的表】
{tables}

【用户问题】
{question}

要求：
1. 只输出一条 SELECT 语句，不要任何解释、注释、代码块围栏。
2. 列名、表名必须来自上面的真实表结构，禁止编造不存在的列或表。
3. 生成最符合问题语义的 SELECT；当前用户授权表为上述列表，若问题涉及未授权表，也如实生成对应查询（系统的权限校验器会拦截越权）。
4. 禁止 UPDATE/DELETE/INSERT/DROP 等写操作。
5. 不要以分号结尾。
直接输出 SQL："""
