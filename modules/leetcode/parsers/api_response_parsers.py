from datetime import UTC, datetime

import structlog

from modules.leetcode.settings import leetcode_settings

logger = structlog.get_logger(__name__)


def gql_question_data(response_data: dict) -> dict:
    # Contains raw leetcode question in html format
    question_data = response_data.get("data", {}).get("question", {})

    if not question_data:
        logger.warning("question_data_parse_empty", reason="no_question_in_response")

    raw_question_html = question_data.get("content", "")

    # Contains tag contains normal tag and slugified version (name, slug) vars.
    topic_tags = question_data.get("topicTags", [])

    slug = question_data.get("titleSlug")
    title = question_data.get("title")
    id = question_data.get("questionFrontendId")
    url = f"{leetcode_settings.BASE_URL}/problems/{slug}/"
    difficulty = question_data.get("difficulty")
    category = question_data.get("categoryTitle")

    logger.bind(slug=slug).info(
        "question_data_parsed",
        title=title,
        has_content=bool(raw_question_html),
        tag_count=len(topic_tags),
    )

    return {
        "id": id,
        "url": url,
        "slug": slug,
        "title": title,
        "tags": topic_tags,
        "category": category,
        "difficulty": difficulty,
        "raw_question_html": raw_question_html,
    }


def gql_submission_list(response_data: dict) -> list[dict]:
    submissions = (
        response_data.get("data", {})
        .get("questionSubmissionList", {})
        .get("submissions", [])
    )
    logger.info("submission_list_parsed", submission_count=len(submissions))
    return submissions


def gql_recent_ac_submissions(response_data: dict) -> list[dict]:
    """Flattens a recentAcSubmissionList response into {slug, title, timestamp} dicts."""
    raw_submissions = response_data.get("data", {}).get("recentAcSubmissionList", [])

    parsed = []
    for item in raw_submissions:
        raw_timestamp = item.get("timestamp")
        timestamp = (
            datetime.fromtimestamp(int(raw_timestamp), tz=UTC)
            if raw_timestamp
            else None
        )
        parsed.append(
            {
                "slug": item.get("titleSlug"),
                "title": item.get("title"),
                "timestamp": timestamp,
            }
        )

    logger.info("recent_ac_submissions_parsed", submission_count=len(parsed))
    return parsed


def gql_submission_data(response_data: dict) -> dict:
    data = response_data.get("data", {}).get("submissionDetails", {})

    if not data:
        logger.warning(
            "submission_data_parse_empty", reason="no_submission_details_in_response"
        )
        return {}

    lang = data.get("lang", {}).get("name", None)
    code = data.get("code", None)
    timestamp = data.get("timestamp", None)

    if timestamp:
        submission_date = datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
    else:
        submission_date = None

    logger.info("submission_data_parsed", lang=lang, has_code=bool(code))

    return {
        "lang": lang,
        "code": code,
        "submission_date": submission_date,
    }
