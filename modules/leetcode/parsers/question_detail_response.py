from modules.leetcode.settings import leetcode_settings


def gql_question_data_parser(gql_data: dict) -> dict:
    # Contains raw leetcode question in html format
    raw_html_question = gql_data.get("content", "")

    # Contains tag contains normal tag and slugified version (name, slug) vars.
    topic_tags = gql_data.get("topicTags", [])

    slug = gql_data.get("titleSlug")
    title = gql_data.get("title")
    id = gql_data.get("questionFrontendId")
    url = f"{leetcode_settings.BASE_URL}/problems/{slug}/"
    difficulty = gql_data.get("difficulty")
    category = gql_data.get("categoryTitle")

    return {
        "id": id,
        "url": url,
        "slug": slug,
        "title": title,
        "tags": topic_tags,
        "category": category,
        "difficulty": difficulty,
        "content_html": raw_html_question,
    }
