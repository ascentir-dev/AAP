"""Tests for src/hosting/uploader.py — boto3 mocked."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.hosting.uploader import generate_landing_page, upload_video


def make_settings():
    s = MagicMock()
    s.cloudflare_r2_account_id = "abc123"
    s.cloudflare_r2_access_key_id = "key-id"
    s.cloudflare_r2_secret_access_key = "secret"
    s.cloudflare_r2_bucket = "lead-videos"
    s.cloudflare_r2_public_url = "https://videos.example.com"
    s.cloudflare_pages_base_url = "https://go.example.com"
    s.book_a_call_url = "https://calendly.com/frank/intro"
    return s


def make_lead(lead_id: str = "abc123def456"):
    return {
        "lead_id": lead_id,
        "first_name": "Alice",
        "last_name": "Smith",
        "company": "Acme",
    }


@pytest.mark.asyncio
async def test_upload_video_returns_correct_url():
    s3_mock = MagicMock()
    settings = make_settings()

    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        path = Path(tmp.name)
        with patch("src.hosting.uploader.boto3.client", return_value=s3_mock):
            url = await upload_video(path, "lead-001", settings)

    assert url == "https://videos.example.com/videos/lead-001.mp4"


@pytest.mark.asyncio
async def test_upload_video_calls_s3_upload():
    s3_mock = MagicMock()
    settings = make_settings()

    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        path = Path(tmp.name)
        with patch("src.hosting.uploader.boto3.client", return_value=s3_mock):
            await upload_video(path, "lead-002", settings)

    s3_mock.upload_file.assert_called_once()
    call_kwargs = s3_mock.upload_file.call_args
    assert call_kwargs[0][1] == "lead-videos"
    assert call_kwargs[0][2] == "videos/lead-002.mp4"


@pytest.mark.asyncio
async def test_generate_landing_page_returns_correct_url():
    s3_mock = MagicMock()
    settings = make_settings()
    lead = make_lead("myid12345678")

    with patch("src.hosting.uploader.boto3.client", return_value=s3_mock):
        url = await generate_landing_page(lead, "https://videos.example.com/videos/myid12345678.mp4", settings)

    assert url == "https://go.example.com/v/myid12345678"


@pytest.mark.asyncio
async def test_generate_landing_page_uploads_html():
    s3_mock = MagicMock()
    settings = make_settings()
    lead = make_lead("html-test-id")

    with patch("src.hosting.uploader.boto3.client", return_value=s3_mock):
        await generate_landing_page(lead, "https://videos.example.com/videos/test.mp4", settings)

    s3_mock.put_object.assert_called_once()
    call_kwargs = s3_mock.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "lead-videos"
    assert call_kwargs["Key"] == "pages/html-test-id.html"
    assert call_kwargs["ContentType"] == "text/html"
    # HTML must include first_name and book_a_call_url
    html_body = call_kwargs["Body"].decode("utf-8")
    assert "Alice" in html_body
    assert "https://calendly.com/frank/intro" in html_body


@pytest.mark.asyncio
async def test_landing_page_contains_video_autoplay():
    s3_mock = MagicMock()
    settings = make_settings()
    lead = make_lead("video-test")
    video_url = "https://videos.example.com/videos/test.mp4"

    with patch("src.hosting.uploader.boto3.client", return_value=s3_mock):
        await generate_landing_page(lead, video_url, settings)

    html_body = s3_mock.put_object.call_args[1]["Body"].decode("utf-8")
    assert "autoplay" in html_body
    assert video_url in html_body
