"""FastAPI 接口：POST /query 自然语言问数。

启动：uvicorn app:app --port 9092
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from agent import get_conn, query


class QueryRequest(BaseModel):
    question: str
    user: str = "analyst"


app = FastAPI(title="NL2SQL", description="自然语言问数 Agent（防注入/表级权限/只读）")


@app.post("/query")
def ask(req: QueryRequest) -> dict:
    conn = get_conn()
    try:
        return query(req.question, req.user, conn=conn)
    finally:
        conn.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
