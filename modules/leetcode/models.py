from datetime import datetime

from pydantic import BaseModel


class SubmissionDetails(BaseModel):
    lang: str
    code: str
    submitted_date: datetime


class QuestionRecord(BaseModel):
    slug: str | None = None
    id: int | None = None
    title: str | None = None
    url: str | None = None
    difficulty: str | None = None
    category: str | None = None
    tags: list[dict] | None = None
    content_html: str | None = None
    content_md: str | None = None
    content_txt: str | None = None
    submission: SubmissionDetails | None = None
