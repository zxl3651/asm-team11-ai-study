import operator
from uuid import uuid4
from typing import Annotated, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    query: str
    query_analysis: dict
    search_results: list[dict]
    final_answer: str
    domain: str
    iteration_count: int

class QueryAnalysis(BaseModel):
    keywords: list[str] = Field(description="keywords")
    domain: Literal["medical","general","out_of_scope"] = Field(description="domain")
    intent: str = Field(description="intent")
    status: Literal["success","insufficient"] = Field(description="status")

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    thread_id: str = Field(default_factory=lambda: str(uuid4()))

class ChatResponse(BaseModel):
    answer: str
    domain: str = ""
    sources: list[str] = Field(default_factory=list)
    disclaimer: str = ""

class StreamEvent(BaseModel):
    event: str = "message"
    node: str = ""
    data: str = ""
