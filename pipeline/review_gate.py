"""
Review Gate for 어쩌다지식 YouTube Pipeline.

Handles:
  1. Uploading draft videos to Google Drive folder "어쩌다지식_검토대기"
  2. Sending Telegram notification with inline approve/reject buttons
  3. Polling data/pending_approvals.json for reviewer decision

The Telegram bot receives callback_query events when the reviewer taps a button.
A separate bot webhook handler (or polling loop in review_gate) updates the
pending_approvals.json file. main.py then polls this file.

Telegram bot setup:
  - Create bot via @BotFather
  - Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars
  - The bot must be added to the chat

Google Drive setup:
  - Service account with Drive API access
  - GOOGLE_DRIVE_FOLDER_ID env var pointing to "어쩌다지식_검토대기" folder
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PENDING_APPROVALS_FILE = Path("data/pending_approvals.json")
POLL_INTERVAL_SECONDS = 15
APPROVAL_TIMEOUT_SECONDS = 24 * 3600  # 24 hours


@dataclass
class ApprovalRecord:
    """Tracks a single video pending review."""
    video_id: str
    video_path: str
    drive_url: str
    title: str
    category: str
    telegram_message_id: Optional[int]
    status: str  # "pending" | "approved" | "rejected"
    created_at: str
    decided_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "video_path": self.video_path,
            "drive_url": self.drive_url,
            "title": self.title,
            "category": self.category,
            "telegram_message_id": self.telegram_message_id,
            "status": self.status,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ApprovalRecord":
        return cls(**data)


class ReviewGate:
    """Manages the human review gate for generated videos."""

    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        drive_folder_id: Optional[str] = None,
        approvals_file: Path = PENDING_APPROVALS_FILE,
    ):
        self.telegram_token = telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.drive_folder_id = drive_folder_id or os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
        self.approvals_file = Path(approvals_file)
        self.approvals_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.telegram_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram notifications disabled")
        if not self.drive_folder_id:
            logger.warning("GOOGLE_DRIVE_FOLDER_ID not set — Drive upload disabled")

    # ------------------------------------------------------------------
    # Google Drive upload
    # ------------------------------------------------------------------

    def upload_draft(self, video_path: str | Path, script_result) -> str:
        """
        Upload draft video to Google Drive review folder.

        Args:
            video_path: Local path to the video file.
            script_result: ScriptResult with title and category.

        Returns:
            Google Drive shareable URL.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if not self.drive_folder_id:
            logger.warning("No Drive folder ID configured — skipping Drive upload")
            return f"file://{video_path.absolute()}"

        logger.info(f"Uploading to Google Drive: {video_path.name} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            # Build Drive service
            creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_path:
                creds = service_account.Credentials.from_service_account_file(
                    creds_path,
                    scopes=["https://www.googleapis.com/auth/drive.file"],
                )
            else:
                import google.auth
                creds, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/drive.file"]
                )

            service = build("drive", "v3", credentials=creds, cache_discovery=False)

            # File metadata
            file_metadata = {
                "name": f"[검토대기] {script_result.title} - {video_path.name}",
                "parents": [self.drive_folder_id],
                "mimeType": "video/mp4",
            }

            # Resumable upload for large files
            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                resumable=True,
                chunksize=5 * 1024 * 1024,  # 5MB chunks
            )

            request = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id,webViewLink",
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    logger.info(f"Upload progress: {pct}%")

            file_id = response.get("id", "")
            drive_url = response.get("webViewLink", "")

            # Make file viewable by anyone with link (for review)
            service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
            ).execute()

            # Get updated link
            file_info = service.files().get(
                fileId=file_id,
                fields="webViewLink"
            ).execute()
            drive_url = file_info.get("webViewLink", drive_url)

            logger.info(f"Uploaded to Drive: {drive_url}")
            return drive_url

        except ImportError:
            logger.error("google-api-python-client not installed")
            return f"file://{video_path.absolute()}"
        except Exception as e:
            logger.error(f"Drive upload failed: {e}")
            raise

    # ------------------------------------------------------------------
    # Telegram notification
    # ------------------------------------------------------------------

    def notify_telegram(self, drive_url: str, script_result, video_id: str) -> Optional[int]:
        """
        Send Telegram notification with approve/reject buttons.

        Args:
            drive_url: Google Drive URL of the uploaded video.
            script_result: ScriptResult with title, category, description.
            video_id: Unique run/video ID for callback tracking.

        Returns:
            Telegram message ID (for reference) or None if not configured.
        """
        if not self.telegram_token or not self.telegram_chat_id:
            logger.warning("Telegram not configured — skipping notification")
            return None

        CATEGORY_KO = {
            "psychology": "심리학",
            "life": "생활잡학",
            "tech": "IT/테크",
        }
        category_ko = CATEGORY_KO.get(script_result.category, script_result.category)
        total_duration = sum(s.duration_estimate for s in script_result.scenes)
        duration_min = total_duration / 60

        description_short = script_result.description[:150]
        if len(script_result.description) > 150:
            description_short += "..."

        message_text = (
            f"🎬 *새 영상 검토 요청*\n\n"
            f"📌 *제목:* {script_result.title}\n"
            f"📂 *카테고리:* {category_ko}\n"
            f"⏱ *예상 길이:* {duration_min:.1f}분\n"
            f"🆔 *영상 ID:* `{video_id}`\n\n"
            f"📝 *설명:*\n{description_short}\n\n"
            f"🔗 [드라이브에서 보기]({drive_url})\n\n"
            f"승인 또는 반려를 선택해주세요:"
        )

        # Inline keyboard buttons
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ 승인 (업로드)",
                        "callback_data": f"approve:{video_id}",
                    },
                    {
                        "text": "❌ 반려 (취소)",
                        "callback_data": f"reject:{video_id}",
                    },
                ]
            ]
        }

        import urllib.request
        import urllib.parse

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.telegram_chat_id,
            "text": message_text,
            "parse_mode": "Markdown",
            "reply_markup": keyboard,
            "disable_web_page_preview": False,
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            if result.get("ok"):
                msg_id = result["result"]["message_id"]
                logger.info(f"Telegram notification sent: message_id={msg_id}")
                return msg_id
            else:
                logger.error(f"Telegram API error: {result}")
                return None

        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return None

    # ------------------------------------------------------------------
    # Approval tracking
    # ------------------------------------------------------------------

    def _load_approvals(self) -> dict:
        """Load pending approvals from JSON file."""
        if not self.approvals_file.exists():
            return {"approvals": {}}
        try:
            return json.loads(self.approvals_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load approvals file: {e}")
            return {"approvals": {}}

    def _save_approvals(self, data: dict) -> None:
        """Persist approval records to JSON file."""
        self.approvals_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def create_approval_record(
        self,
        video_id: str,
        video_path: str | Path,
        drive_url: str,
        script_result,
        telegram_message_id: Optional[int],
    ) -> ApprovalRecord:
        """Create and persist an approval record."""
        record = ApprovalRecord(
            video_id=video_id,
            video_path=str(video_path),
            drive_url=drive_url,
            title=script_result.title,
            category=script_result.category,
            telegram_message_id=telegram_message_id,
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        data = self._load_approvals()
        data["approvals"][video_id] = record.to_dict()
        self._save_approvals(data)
        logger.info(f"Approval record created for video_id={video_id}")
        return record

    def wait_for_approval(
        self,
        video_id: str,
        timeout_seconds: int = APPROVAL_TIMEOUT_SECONDS,
        poll_interval: int = POLL_INTERVAL_SECONDS,
    ) -> str:
        """
        Poll for approval decision on a video.

        Also starts a background Telegram polling loop to receive button callbacks.

        Args:
            video_id: The unique video ID to watch.
            timeout_seconds: Max wait time before timing out.
            poll_interval: Seconds between file polls.

        Returns:
            "approved" | "rejected" | "timeout"
        """
        logger.info(
            f"Waiting for approval on video_id={video_id} "
            f"(timeout={timeout_seconds / 3600:.1f}h, poll={poll_interval}s)"
        )

        # Start Telegram callback polling in background
        stop_polling = [False]
        import threading

        if self.telegram_token:
            poll_thread = threading.Thread(
                target=self._telegram_callback_poller,
                args=(stop_polling,),
                daemon=True,
                name="telegram-poller",
            )
            poll_thread.start()
        else:
            poll_thread = None

        deadline = time.time() + timeout_seconds
        try:
            while time.time() < deadline:
                status = self._check_approval_status(video_id)
                if status in ("approved", "rejected"):
                    logger.info(f"Decision received for {video_id}: {status}")
                    return status

                remaining = int(deadline - time.time())
                logger.debug(f"Still waiting for approval ({remaining}s remaining)...")
                time.sleep(poll_interval)

            logger.warning(f"Approval timeout for video_id={video_id}")
            return "timeout"

        finally:
            stop_polling[0] = True

    def _check_approval_status(self, video_id: str) -> str:
        """Check current approval status from the JSON file."""
        data = self._load_approvals()
        record_data = data.get("approvals", {}).get(video_id)
        if record_data:
            return record_data.get("status", "pending")
        return "pending"

    def record_decision(self, video_id: str, decision: str, notes: str = "") -> None:
        """
        Record a human's approval decision.

        Called by the Telegram callback handler or manually.

        Args:
            video_id: Video to decide on.
            decision: "approved" or "rejected".
            notes: Optional reviewer notes.
        """
        if decision not in ("approved", "rejected"):
            raise ValueError(f"Invalid decision: {decision}. Must be 'approved' or 'rejected'")

        data = self._load_approvals()
        if video_id not in data.get("approvals", {}):
            logger.warning(f"Video {video_id} not found in approvals — creating entry")
            data.setdefault("approvals", {})[video_id] = {
                "video_id": video_id,
                "status": decision,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            data["approvals"][video_id]["status"] = decision
            data["approvals"][video_id]["decided_at"] = datetime.now(timezone.utc).isoformat()
            data["approvals"][video_id]["notes"] = notes

        self._save_approvals(data)
        logger.info(f"Decision recorded: video_id={video_id}, decision={decision}")

    def _telegram_callback_poller(self, stop_flag: list[bool]) -> None:
        """
        Poll Telegram for callback_query events from inline keyboard buttons.

        Updates pending_approvals.json when a button is pressed.
        Runs in a background thread during wait_for_approval().
        """
        if not self.telegram_token:
            return

        import urllib.request
        import urllib.parse

        last_update_id = 0
        base_url = f"https://api.telegram.org/bot{self.telegram_token}"

        logger.debug("Telegram callback poller started")

        while not stop_flag[0]:
            try:
                # Get updates with long-polling (30s timeout)
                params = urllib.parse.urlencode({
                    "offset": last_update_id + 1,
                    "timeout": 20,
                    "allowed_updates": '["callback_query"]',
                })
                url = f"{base_url}/getUpdates?{params}"

                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=35) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                if not data.get("ok"):
                    time.sleep(5)
                    continue

                updates = data.get("result", [])
                for update in updates:
                    update_id = update.get("update_id", 0)
                    if update_id > last_update_id:
                        last_update_id = update_id

                    callback = update.get("callback_query", {})
                    if not callback:
                        continue

                    callback_id = callback.get("id", "")
                    callback_data = callback.get("data", "")

                    # Parse "approve:video_id" or "reject:video_id"
                    if ":" in callback_data:
                        action, vid_id = callback_data.split(":", 1)
                        if action in ("approve", "reject"):
                            decision = "approved" if action == "approve" else "rejected"
                            logger.info(f"Telegram callback: {action} for {vid_id}")
                            self.record_decision(vid_id, decision)

                            # Send answer to dismiss the loading state on button
                            answer_url = f"{base_url}/answerCallbackQuery"
                            answer_text = "✅ 승인 처리됨!" if decision == "approved" else "❌ 반려 처리됨"
                            answer_payload = json.dumps({
                                "callback_query_id": callback_id,
                                "text": answer_text,
                                "show_alert": True,
                            }).encode("utf-8")
                            try:
                                answer_req = urllib.request.Request(
                                    answer_url,
                                    data=answer_payload,
                                    headers={"Content-Type": "application/json"},
                                    method="POST",
                                )
                                urllib.request.urlopen(answer_req, timeout=10)
                            except Exception:
                                pass  # Non-critical

            except Exception as e:
                if not stop_flag[0]:
                    logger.debug(f"Telegram poller error (will retry): {e}")
                    time.sleep(10)

        logger.debug("Telegram callback poller stopped")

    # ------------------------------------------------------------------
    # Convenience: full review flow
    # ------------------------------------------------------------------

    def submit_for_review(
        self,
        video_id: str,
        video_path: str | Path,
        script_result,
    ) -> ApprovalRecord:
        """
        Full flow: upload to Drive + send Telegram notification + create record.

        Args:
            video_id: Unique video/run ID.
            video_path: Local video file path.
            script_result: ScriptResult object.

        Returns:
            ApprovalRecord with initial "pending" status.
        """
        # 1. Upload to Drive
        drive_url = self.upload_draft(video_path, script_result)

        # 2. Notify via Telegram
        msg_id = self.notify_telegram(drive_url, script_result, video_id)

        # 3. Create approval record
        record = self.create_approval_record(
            video_id=video_id,
            video_path=video_path,
            drive_url=drive_url,
            script_result=script_result,
            telegram_message_id=msg_id,
        )

        logger.info(
            f"Video submitted for review: {video_id}\n"
            f"  Drive URL: {drive_url}\n"
            f"  Telegram message_id: {msg_id}"
        )
        return record


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    gate = ReviewGate()
    print(f"ReviewGate ready")
    print(f"  Telegram configured: {bool(gate.telegram_token)}")
    print(f"  Drive folder: {gate.drive_folder_id or '(not set)'}")
