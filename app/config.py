from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
import json
import os

class Settings(BaseSettings):
    port: int = Field(default=8081, alias="PORT")
    gcs_bucket: str = Field(default="", alias="GCS_BUCKET")
    chunk_seconds: int = Field(default=20, alias="CHUNK_SECONDS")
    yt_dlp_path: str = Field(default="yt-dlp", alias="YT_DLP_PATH")
    ffmpeg_path: str = Field(default="ffmpeg", alias="FFMPEG_PATH")
    ffprobe_path: str = Field(default="ffprobe", alias="FFPROBE_PATH")
    webhook_auth_token: Optional[str] = Field(default=None, alias="WEBHOOK_AUTH_TOKEN")
    default_webhook_url: Optional[str] = Field(default=None, alias="DEFAULT_WEBHOOK_URL")
    # Optional: inline JSON credentials for environments without files
    gcs_service_account_json: Optional[str] = Field(default=None, alias="GCS_SERVICE_ACCOUNT_JSON")

    # yt-dlp tuning
    yt_timeout_seconds: int = Field(default=300, alias="YT_TIMEOUT_SECONDS")
    yt_retries: int = Field(default=8, alias="YT_RETRIES")
    yt_socket_timeout: int = Field(default=30, alias="YT_SOCKET_TIMEOUT")
    yt_force_ipv4: bool = Field(default=True, alias="YT_FORCE_IPV4")
    yt_no_playlist: bool = Field(default=True, alias="YT_NO_PLAYLIST")
    yt_extra_args: Optional[str] = Field(default=None, alias="YT_EXTRA_ARGS")
    
    # Pydantic v2 settings config: ignore unrelated env keys (DATABASE_URL, etc.)
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    def gcs_credentials_info(self) -> Optional[dict]:
        if not self.gcs_service_account_json:
            return None
        try:
            return json.loads(self.gcs_service_account_json)
        except Exception:
            # Allow it to be a file path mistakenly set here
            if os.path.exists(self.gcs_service_account_json):
                with open(self.gcs_service_account_json, "r", encoding="utf-8") as f:
                    return json.load(f)
        return None

settings = Settings()
