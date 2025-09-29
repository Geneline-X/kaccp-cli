"""
Storage utilities for uploading files to GCS with progress tracking.
"""
import io
import os
import logging
from typing import Optional
from google.cloud import storage
from google.oauth2 import service_account
from .config import settings

_client: Optional[storage.Client] = None


def get_gcs_client() -> storage.Client:
    global _client
    if _client is not None:
        return _client
    creds_info = settings.gcs_credentials_info()
    if creds_info:
        credentials = service_account.Credentials.from_service_account_info(creds_info)
        _client = storage.Client(credentials=credentials, project=creds_info.get("project_id"))
    else:
        # Falls back to ADC via GOOGLE_APPLICATION_CREDENTIALS
        _client = storage.Client()
    return _client


def upload_file(local_path: str, object_name: str, content_type: str = "audio/wav") -> str:
    """
    Upload a file to GCS with compact progress tracking.
    Shows file size and upload status in a single line.
    """
    if not settings.gcs_bucket:
        raise RuntimeError("GCS_BUCKET is not configured")
    
    # Get file size for progress display
    file_size = os.path.getsize(local_path)
    file_size_mb = file_size / (1024 * 1024)
    
    client = get_gcs_client()
    bucket = client.bucket(settings.gcs_bucket)
    blob = bucket.blob(object_name)
    blob.upload_from_filename(local_path, content_type=content_type)
    
    logging.info(f"   {file_size_mb:.2f} MB ✓")
    
    return f"gs://{settings.gcs_bucket}/{object_name}"


def download_file(object_name: str, local_path: str) -> str:
    """
    Downloads the exported dataset from the configured GCS bucket to a local path.
    """
    if not settings.gcs_bucket:
        raise RuntimeError("GCS_BUCKET is not configured")
    client = get_gcs_client()
    bucket = client.bucket(settings.gcs_bucket)
    blob = bucket.blob(object_name)
    blob.download_to_filename(local_path)
    return local_path