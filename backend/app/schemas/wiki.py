from pydantic import BaseModel


class WikiGraphNode(BaseModel):
    key: str  # unique React Flow id: "{category}/{slug}", e.g. "entities/lora"
    id: str  # slug only, dùng cho API calls: "lora"
    title: str
    type: str  # model/method/concept/... hoặc "topic"/"summary"
    category: str  # entities/topics/summaries
    source_count: int
    backlink_count: int
    is_stub: bool


class WikiGraphEdge(BaseModel):
    id: str
    source: str  # node key "{category}/{slug}"
    target: str  # node key "{category}/{slug}"


class WikiGraphResponse(BaseModel):
    nodes: list[WikiGraphNode]
    edges: list[WikiGraphEdge]


class WikiPageResponse(BaseModel):
    slug: str
    category: str
    content: str
