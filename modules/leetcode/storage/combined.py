from pydantic import BaseModel

from modules.leetcode.models import ProblemRecord, QuestionContent, SubmissionRecord


class CombinedQuestionRecord(BaseModel):
    """
    Read-only join of a ProblemRecord and its SubmissionRecord, built here in
    the storage layer for callers (e.g. the renderer) that need both problem
    and submission data together. Never persisted — this is not a store, it
    exists only to hand a merged view back to callers.
    """

    slug: str | None = None
    id: int | None = None
    title: str | None = None
    url: str | None = None
    difficulty: str | None = None
    category: str | None = None
    tags: list[dict] | None = None
    raw_question_html: str | None = None

    has_images: bool | None = None
    imgs_local_paths: list[str] | None = None

    content: QuestionContent = QuestionContent()
    submission: SubmissionRecord | None = None

    @property
    def has_local_variant(self) -> bool:
        """See ProblemRecord.has_local_variant — same logic, same fields."""
        return bool(self.has_images) and bool(self.imgs_local_paths)

    @classmethod
    def from_parts(
        cls, problem: ProblemRecord, submission: SubmissionRecord | None
    ) -> "CombinedQuestionRecord":
        """Builds a combined record from a ProblemRecord and its (possibly absent) SubmissionRecord."""
        return cls(**problem.model_dump(), submission=submission)
