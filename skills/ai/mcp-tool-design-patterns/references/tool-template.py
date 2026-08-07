"""MCP Tool Template — Python SDK (mcp >= 1.0)

Complete tool with:
- Pydantic input schema with validation
- Structured output (JSON)
- Error handling with user-friendly messages
- Docstring that becomes the tool description
"""

from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field, field_validator

# --- Input Schema -----------------------------------------------------------

class QueryMetricsInput(BaseModel):
    """Input schema for the query_metrics tool."""

    query: str = Field(
        description="PromQL/MetricsQL expression to evaluate",
        min_length=1,
        max_length=2000,
    )
    time_range: str = Field(
        default="1h",
        description="Lookback window (e.g. '5m', '1h', '24h')",
        pattern=r"^\d+[smhd]$",
    )
    step: str = Field(
        default="1m",
        description="Query resolution step",
        pattern=r"^\d+[smhd]$",
    )

    @field_validator("query")
    @classmethod
    def reject_dangerous_queries(cls, v: str) -> str:
        if "delete" in v.lower():
            raise ValueError("Destructive queries are not allowed")
        return v

# --- Tool Implementation -----------------------------------------------------

app = Server("metrics-query-server")


@app.tool()
async def query_metrics(input: QueryMetricsInput) -> list[TextContent]:
    """Query time-series metrics from VictoriaMetrics.

    Returns metric results as structured JSON with timestamps and values.
    Use PromQL or MetricsQL syntax for the query expression.
    """
    import json

    try:
        # Replace with actual backend call
        result = await _execute_query(
            query=input.query,
            time_range=input.time_range,
            step=input.step,
        )

        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "success",
                "query": input.query,
                "time_range": input.time_range,
                "result_count": len(result),
                "data": result,
            }, indent=2),
        )]

    except TimeoutError:
        return [TextContent(
            type="text",
            text=json.dumps({"status": "error", "error": "Query timed out. Try a shorter time_range or simpler expression."}),
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"status": "error", "error": str(e)}),
        )]


async def _execute_query(query: str, time_range: str, step: str) -> list[dict]:
    """Placeholder — replace with HTTP call to your metrics backend."""
    return [{"metric": {"__name__": "up"}, "values": [[1720000000, "1"]]}]
