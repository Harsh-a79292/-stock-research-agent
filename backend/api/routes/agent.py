"""
api/routes/agent.py
───────────────────
FastAPI route for executing the LangGraph stock research agent.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.agent.graph import agent_graph
from backend.db.supabase_client import save_research_report

router = APIRouter(prefix="/agent", tags=["Agent"])


class AgentRunRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language stock research query.")

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Query cannot be empty or whitespace.")
        return clean


class AgentRunResponse(BaseModel):
    query: str
    ticker: str | None = None
    intent: str = "price_check"
    tool_results: dict[str, Any] = Field(default_factory=dict)
    analysis: str = ""
    error: str | None = None
    saved_report_id: str | None = None
    save_status: str | None = None


@router.post("/run", response_model=AgentRunResponse, summary="Run Stock Research Agent")
async def run_agent(payload: AgentRunRequest) -> AgentRunResponse:
    """
    Execute the LangGraph stock research agent for a natural language query
    and persist successful research results to Supabase.
    """
    try:
        state = agent_graph.invoke({"query": payload.query})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e}")

    save_res = save_research_report(state)
    saved_id = None
    if save_res.get("status") == "success" and isinstance(save_res.get("report"), dict):
        saved_id = save_res["report"].get("id")

    return AgentRunResponse(
        query=state.get("query", payload.query),
        ticker=state.get("ticker"),
        intent=state.get("intent", "price_check"),
        tool_results=state.get("tool_results") or {},
        analysis=state.get("analysis") or "",
        error=state.get("error"),
        saved_report_id=saved_id,
        save_status=save_res.get("status"),
    )
