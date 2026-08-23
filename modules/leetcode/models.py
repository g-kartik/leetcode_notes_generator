from datetime import datetime

from pydantic import BaseModel


class SubmissionDetails(BaseModel):
    lang: str
    code: str
    submission_date: datetime


class QuestionContent(BaseModel):
    remote_markdown: str | None = None
    local_html: str | None = None
    local_markdown: str | None = None
    text: str | None = None


class QuestionRecord(BaseModel):
    slug: str | None = None
    id: int | None = None
    title: str | None = None
    url: str | None = None
    difficulty: str | None = None
    category: str | None = None
    tags: list[dict] | None = None
    raw_question_html: str | None = None

    imgs_local_paths: list[str] | None = None

    content: QuestionContent = QuestionContent()
    submission: SubmissionDetails | None = None
