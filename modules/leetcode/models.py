from pydantic import BaseModel


class QuestionRecord(BaseModel):
    slug: str
    id: int | None = None
    title: str
    url: str
    difficulty: str | None = None
    category: str | None = None
    tags: list[str] = []
    content_html: str | None = None
    content_md: str | None = None
    content_plain: str | None = None
    is_paid_only: bool = False
