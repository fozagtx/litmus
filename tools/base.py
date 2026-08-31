"""
Base Tool Interface for Agent Execution.
Defines strict schemas, failure behavior, execution metadata, and trajectory recording.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import time
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata
        }


class BaseTool(ABC):
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]

    def execute(self, **kwargs) -> ToolResult:
        start_time = time.perf_counter()
        try:
            output = self._run(**kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return ToolResult(
                tool_name=self.name,
                success=True,
                output=output,
                execution_time_ms=round(duration_ms, 2),
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return ToolResult(
                tool_name=self.name,
                success=False,
                output=None,
                error=f"{type(e).__name__}: {str(e)}",
                execution_time_ms=round(duration_ms, 2),
            )

    @abstractmethod
    def _run(self, **kwargs) -> Any:
        pass
