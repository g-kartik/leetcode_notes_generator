from datetime import UTC, datetime

from modules.leetcode.settings import leetcode_settings


def gql_question_data(response_data: dict) -> dict:
    # Contains raw leetcode question in html format
    question_data = response_data.get("data", {}).get("question", {})

    raw_question_html = question_data.get("content", "")

    # Contains tag contains normal tag and slugified version (name, slug) vars.
    topic_tags = question_data.get("topicTags", [])

    slug = question_data.get("titleSlug")
    title = question_data.get("title")
    id = question_data.get("questionFrontendId")
    url = f"{leetcode_settings.BASE_URL}/problems/{slug}/"
    difficulty = question_data.get("difficulty")
    category = question_data.get("categoryTitle")

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
    return (
        response_data.get("data", {})
        .get("questionSubmissionList", {})
        .get("submissions", [])
    )


def gql_submission_data(response_data: dict) -> dict:
    data = response_data.get("data", {}).get("submissionDetails", {})

    if not data:
        return {}

    lang = data.get("lang", {}).get("name", None)
    code = data.get("code", None)
    timestamp = data.get("timestamp", None)

    if timestamp:
        submission_date = datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
    else:
        submission_date = None

    return {
        "lang": lang,
        "code": code,
        "submission_date": submission_date,
    }
