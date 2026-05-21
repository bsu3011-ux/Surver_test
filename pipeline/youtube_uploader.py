"""
YouTube Uploader for 어쩌다지식 YouTube Pipeline.

Uses google-api-python-client with OAuth2 to upload videos to YouTube.
Supports resumable uploads for large files.

Authentication setup:
  1. Create OAuth2 credentials in GCP Console (YouTube Data API v3)
  2. Download client_secrets.json
  3. Set YOUTUBE_CLIENT_SECRETS_FILE env var pointing to this file
  4. On first run, a browser OAuth flow will complete and save a token
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# YouTube API settings
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
YOUTUBE_CATEGORY_EDUCATION = "27"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Resumable upload chunk size (5 MB)
UPLOAD_CHUNK_SIZE = 5 * 1024 * 1024

# Description template for 어쩌다지식
DESCRIPTION_TEMPLATE = """{description}

━━━━━━━━━━━━━━━━━━━━━━━
📚 어쩌다지식 채널
일상 속 숨겨진 흥미로운 지식들을 쉽고 재미있게 풀어드립니다!

👍 좋아요와 구독은 큰 힘이 됩니다
🔔 알림설정하면 새 영상을 놓치지 않아요
━━━━━━━━━━━━━━━━━━━━━━━

{seo_description}

#어쩌다지식 #{category_tag} #지식 #잡학다식"""

CATEGORY_TAGS = {
    "psychology": "심리학",
    "life": "생활잡학",
    "tech": "IT테크",
}

TOKEN_FILE = Path("data/youtube_token.json")


class YouTubeUploader:
    """Uploads videos to YouTube with resumable upload support."""

    MAX_RETRIES = 5
    RETRY_BACKOFF_FACTOR = 2

    def __init__(
        self,
        client_secrets_file: Optional[str] = None,
        privacy: str = "public",
    ):
        """
        Initialize YouTube uploader.

        Args:
            client_secrets_file: Path to OAuth2 client secrets JSON.
                                  Defaults to YOUTUBE_CLIENT_SECRETS_FILE env var.
            privacy: Video privacy status ("public", "private", "unlisted").
        """
        self.client_secrets_file = client_secrets_file or os.environ.get(
            "YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json"
        )
        self.privacy = privacy
        self._service = None
        logger.info(f"YouTubeUploader initialized (privacy={privacy})")

    def _get_authenticated_service(self):
        """Get or create authenticated YouTube API service."""
        if self._service:
            return self._service

        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        creds = None

        # Try to load existing token
        if TOKEN_FILE.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(TOKEN_FILE), YOUTUBE_SCOPES
                )
            except Exception as e:
                logger.warning(f"Could not load existing token: {e}")

        # Refresh or re-authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("YouTube token refreshed")
                except Exception as e:
                    logger.warning(f"Token refresh failed: {e}. Re-authenticating...")
                    creds = None

            if not creds:
                if not Path(self.client_secrets_file).exists():
                    raise FileNotFoundError(
                        f"YouTube client secrets file not found: {self.client_secrets_file}\n"
                        "Download from GCP Console > APIs & Services > Credentials"
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secrets_file,
                    YOUTUBE_SCOPES,
                )
                # Use local server flow for interactive auth
                creds = flow.run_local_server(port=0)
                logger.info("YouTube OAuth2 authentication successful")

            # Save token for future use
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            logger.info(f"YouTube token saved to {TOKEN_FILE}")

        self._service = build(
            YOUTUBE_API_SERVICE_NAME,
            YOUTUBE_API_VERSION,
            credentials=creds,
            cache_discovery=False,
        )
        return self._service

    def upload(
        self,
        video_path: str | Path,
        script_result,
        notify_subscribers: bool = True,
    ) -> str:
        """
        Upload video to YouTube.

        Args:
            video_path: Local path to the MP4 video file.
            script_result: ScriptResult with title, description, tags, category.
            notify_subscribers: Whether to notify channel subscribers.

        Returns:
            Full YouTube video URL (https://youtu.be/{id}).

        Raises:
            FileNotFoundError: If video file doesn't exist.
            RuntimeError: If upload fails after all retries.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        file_size_mb = video_path.stat().st_size / 1024 / 1024
        logger.info(
            f"Starting YouTube upload: {video_path.name} ({file_size_mb:.1f} MB) | "
            f"Title: {script_result.title}"
        )

        # Build video metadata
        category_tag = CATEGORY_TAGS.get(script_result.category, "지식")
        description = DESCRIPTION_TEMPLATE.format(
            description=script_result.description,
            seo_description=script_result.seo_description,
            category_tag=category_tag,
        )

        # Limit tags to YouTube's 500 character total limit
        tags = self._trim_tags(script_result.tags)

        body = {
            "snippet": {
                "title": script_result.title[:100],  # YouTube title limit
                "description": description[:5000],    # YouTube desc limit
                "tags": tags,
                "categoryId": YOUTUBE_CATEGORY_EDUCATION,
                "defaultLanguage": "ko",
                "defaultAudioLanguage": "ko",
            },
            "status": {
                "privacyStatus": self.privacy,
                "selfDeclaredMadeForKids": False,
                "notifySubscribers": notify_subscribers,
            },
        }

        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=UPLOAD_CHUNK_SIZE,
        )

        service = self._get_authenticated_service()
        insert_request = service.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )

        video_id = self._execute_resumable_upload(insert_request, file_size_mb)
        video_url = f"https://youtu.be/{video_id}"

        logger.info(f"YouTube upload complete: {video_url}")
        return video_url

    def _execute_resumable_upload(self, request, file_size_mb: float) -> str:
        """
        Execute resumable upload with retry logic.

        Args:
            request: YouTube API insert request.
            file_size_mb: File size in MB for progress logging.

        Returns:
            YouTube video ID.
        """
        from googleapiclient.errors import HttpError

        response = None
        error = None
        retry = 0

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    uploaded_mb = file_size_mb * status.progress()
                    logger.info(f"Upload progress: {pct}% ({uploaded_mb:.1f}/{file_size_mb:.1f} MB)")

            except HttpError as e:
                if e.resp.status in (500, 502, 503, 504):
                    # Transient server error — retry with backoff
                    error = e
                    retry += 1
                    if retry > self.MAX_RETRIES:
                        logger.error(f"Upload failed after {self.MAX_RETRIES} retries: {e}")
                        raise

                    wait = self.RETRY_BACKOFF_FACTOR ** retry
                    logger.warning(f"Server error {e.resp.status}, retrying in {wait}s (attempt {retry}/{self.MAX_RETRIES})")
                    time.sleep(wait)

                elif e.resp.status == 403:
                    logger.error(f"YouTube API quota exceeded or permission denied: {e}")
                    raise RuntimeError(
                        "YouTube API quota exceeded. Check https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas"
                    ) from e
                else:
                    logger.error(f"Non-retryable HTTP error {e.resp.status}: {e}")
                    raise

            except Exception as e:
                error = e
                retry += 1
                if retry > self.MAX_RETRIES:
                    raise RuntimeError(f"Upload failed after {self.MAX_RETRIES} retries") from e

                wait = self.RETRY_BACKOFF_FACTOR ** retry
                logger.warning(f"Upload error (attempt {retry}/{self.MAX_RETRIES}): {e}. Retrying in {wait}s...")
                time.sleep(wait)

        if not response:
            raise RuntimeError("Upload completed but received no response from YouTube API")

        video_id = response.get("id", "")
        if not video_id:
            raise RuntimeError(f"Upload complete but no video ID in response: {response}")

        return video_id

    def _trim_tags(self, tags: list[str], max_total_chars: int = 450) -> list[str]:
        """Trim tags list to fit within YouTube's total tag character limit."""
        result = []
        total_chars = 0
        for tag in tags:
            # YouTube counts commas and spaces between tags
            tag_len = len(tag) + 2
            if total_chars + tag_len <= max_total_chars:
                result.append(tag)
                total_chars += tag_len
            else:
                break

        if len(result) < len(tags):
            logger.debug(f"Trimmed tags from {len(tags)} to {len(result)} to fit character limit")

        return result

    def update_thumbnail(self, video_id: str, thumbnail_path: str | Path) -> bool:
        """
        Set a custom thumbnail for a video.

        Args:
            video_id: YouTube video ID.
            thumbnail_path: Local path to thumbnail image (JPEG/PNG, max 2MB).

        Returns:
            True if successful.
        """
        thumbnail_path = Path(thumbnail_path)
        if not thumbnail_path.exists():
            logger.error(f"Thumbnail not found: {thumbnail_path}")
            return False

        try:
            from googleapiclient.http import MediaFileUpload

            service = self._get_authenticated_service()
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(
                    str(thumbnail_path),
                    mimetype="image/jpeg",
                ),
            ).execute()
            logger.info(f"Thumbnail set for video {video_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to set thumbnail: {e}")
            return False

    def get_video_url(self, video_id: str) -> str:
        """Return the full YouTube URL for a video ID."""
        return f"https://youtu.be/{video_id}"

    def get_video_stats(self, video_id: str) -> dict:
        """Fetch basic stats for a video (views, likes, comments)."""
        try:
            service = self._get_authenticated_service()
            response = service.videos().list(
                part="statistics,snippet",
                id=video_id,
            ).execute()

            items = response.get("items", [])
            if not items:
                return {}

            stats = items[0].get("statistics", {})
            return {
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "title": items[0].get("snippet", {}).get("title", ""),
            }
        except Exception as e:
            logger.error(f"Failed to get video stats: {e}")
            return {}


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    uploader = YouTubeUploader()
    print("YouTubeUploader ready.")
    print(f"  Client secrets: {uploader.client_secrets_file}")
    print(f"  Privacy: {uploader.privacy}")
