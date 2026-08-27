from pydantic import BaseModel, Field


class PrefillContent(BaseModel):
    """AI-generated draft content mapping onto the notes template's prefillable
    sections (see resources/templates/leetcode_notes_plain.md.j2). This is the
    schema handed to the AI provider and validated against on the way back."""

    problem_summary: str = ""
    pattern: list[str] = Field(default_factory=list)
    core_idea: list[str] = Field(default_factory=list)
    invariant: list[str] = Field(default_factory=list)
    trap: list[str] = Field(default_factory=list)
    recognition_clue: list[str] = Field(default_factory=list)
    complexity_time: str = ""
    complexity_space: str = ""
    takeaway: list[str] = Field(default_factory=list)
