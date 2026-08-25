from datetime import datetime

from pydantic import BaseModel


class SubmissionRecord(BaseModel):
    slug: str | None = None
    lang: str
    code: str
    submission_date: datetime


class QuestionContent(BaseModel):
    remote_markdown: str | None = None
    local_html: str | None = None
    local_markdown: str | None = None
    text: str | None = None


class ProblemRecord(BaseModel):
    slug: str | None = None
    id: int | None = None
    title: str | None = None
    url: str | None = None
    difficulty: str | None = None
    category: str | None = None
    tags: list[dict] | None = None
    raw_question_html: str | None = None

    # None = images part not processed yet. False = processed, question has
    # no <img> tags at all (imgs_local_paths will legitimately stay empty
    # forever). True = question has images (imgs_local_paths may still be
    # empty if every download failed — has_images alone tells you the part
    # ran; imgs_local_paths tells you whether it succeeded).
    has_images: bool | None = None
    imgs_local_paths: list[str] | None = None

    content: QuestionContent = QuestionContent()

    @property
    def images_populated(self) -> bool:
        """
        Whether the images part is genuinely done, not just attempted: true
        when the question has no images at all (`has_images=False`), or when
        it does and at least one was successfully downloaded. False when
        images exist but every download failed so far (worth retrying), or
        the images part hasn't run at all yet (`has_images` still None).
        """
        return self.has_images is False or bool(self.imgs_local_paths)
