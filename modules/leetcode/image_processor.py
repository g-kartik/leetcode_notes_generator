from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .models import QuestionRecord
from .settings import leetcode_settings


class LeetCodeImageProcessor:
    def __init__(self):
        self.base_url = leetcode_settings.BASE_URL
        self.project_root = leetcode_settings.PROJECT_ROOT_DIR
        self.assets_dir = leetcode_settings.DSA_PROBLEMS_ASSETS_DIR
        self.image_session = requests.Session()
        self._setup_image_session()
        self._ensure_assets_dir_exists()

    def _setup_image_session(self) -> None:
        self.image_session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": str(self.base_url),
            }
        )

    def _ensure_assets_dir_exists(self):
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def _get_extension(self, url: str, content_type: str | None = None) -> str:
        """Extracts a file extension from the URL path, falling back to Content-Type, then 'png'."""
        path = urlparse(url).path
        if "." in path:
            ext = path.rsplit(".", 1)[-1].lower()
            if ext.isalnum() and len(ext) <= 4:
                return ext
        if content_type and "image/" in content_type:
            ext = content_type.split("image/")[-1].split(";")[0].strip()
            if ext.isalnum() and len(ext) <= 4:
                return "jpg" if ext == "jpeg" else ext
        return "png"

    def _create_problem_assets_dir(self, slug: str) -> Path:
        path = self.assets_dir / slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    def download_single_image(self, url: str, image_path: Path) -> Path | None:
        """Downloads an image to `stem_path` with a resolved extension, skipping if cached.

        `stem_path` should have no meaningful suffix yet (e.g. `.../two-sum/assets/0`); the real
        extension is resolved from the URL first and the Content-Type header second.
        Returns the final path the image was written to, or None on failure.
        """
        guessed_path = image_path.with_suffix(f".{self._get_extension(url)}")

        if guessed_path.exists():
            return guessed_path

        try:
            response = self.image_session.get(url, timeout=10)
            response.raise_for_status()
        except Exception as exc:
            print(f"Failed to download image: {exc}", url)
            return None

        ext = self._get_extension(url, response.headers.get("Content-Type"))
        final_path = image_path.with_suffix(f".{ext}")

        image_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(response.content)
        return final_path

    def process_question_images(self, question_record: QuestionRecord) -> dict | None:
        """Downloads all <img> tags in a question's content and rewrites their src to local paths."""
        soup = BeautifulSoup(str(question_record.raw_question_html), "html.parser")
        images = soup.find_all("img")

        if not images:
            return

        img_paths: list[str] = []
        slug = str(question_record.slug)
        problem_assets_dir = self._create_problem_assets_dir(slug)

        for idx, img in enumerate(images):
            src = str(img.get("src", "")).strip()

            if not src or urlparse(src).scheme not in ("http", "https"):
                print(f"{slug} Skipping invalid or relative img{idx}: {src}")
                img.decompose()
                continue

            image_path = problem_assets_dir / f"{idx}"
            saved_path = self.download_single_image(src, image_path)

            if saved_path is None:
                img.decompose()
                continue

            img["src"] = f"assets/{saved_path.name}"

            # Store relative to PROJECT_ROOT instead of the absolute filesystem path
            relative_saved_path = saved_path.relative_to(self.project_root)
            img_paths.append(str(relative_saved_path))

        return {
            "imgs_local_paths": img_paths,
            "content_local_html": str(soup),
        }
