from pydantic import BaseModel


class QuestionRecord(BaseModel):
    slug: str
    id: int | None = None
    title: str
    url: str
    difficulty: str | None = None
    category: str | None = None
    tags: list[dict] = []
    content_html: str = ""
    content_md: str | None = None
    content_plain: str | None = None
