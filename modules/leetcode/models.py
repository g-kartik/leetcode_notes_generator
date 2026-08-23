from datetime import datetime

from pydantic import BaseModel


class SubmissionDetails(BaseModel):
    lang: str
    code: str
    submitted_date: datetime


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
    content_txt: str | None = None
    submission: SubmissionDetails | None = None
