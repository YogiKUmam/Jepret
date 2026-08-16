import uuid
from re import IGNORECASE, sub
from urllib.parse import urlsplit, urlunsplit

import httpx
import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.integrations.storage import Boto3StorageAdapter

pytestmark = pytest.mark.integration


def assert_storage_status(response: httpx.Response, expected_status: int) -> None:
    if response.status_code == expected_status:
        return

    snippet = " ".join(response.text.split())[:240]
    snippet = sub(r"https?://[^\s<\"']+", "<redacted-url>", snippet, flags=IGNORECASE)
    snippet = sub(r"\?[^\s<\"']+", "?<redacted>", snippet)
    snippet = sub(
        r"(signature|credential|security-token)(?:=|%3[dD])[^&\s<\"']+",
        r"\1=<redacted>",
        snippet,
        flags=IGNORECASE,
    )
    pytest.fail(
        f"Unexpected storage status: expected {expected_status}, "
        f"received {response.status_code}; body={snippet!r}",
        pytrace=False,
    )


def test_storage_status_failure_redacts_signed_urls() -> None:
    fake_secret = "must-not-leak"
    fake_url = f"http://localhost:9000/bucket/key?X-Amz-Signature={fake_secret}"
    response = httpx.Response(
        500,
        text=f"storage failed at {fake_url}",
        request=httpx.Request("GET", fake_url),
    )

    with pytest.raises(pytest.fail.Exception) as failure:
        assert_storage_status(response, 200)

    message = str(failure.value)
    assert fake_secret not in message
    assert fake_url not in message
    assert "<redacted-url>" in message
    assert "received 500" in message


@pytest.mark.asyncio
async def test_signed_browser_upload_is_create_only_and_privately_readable() -> None:
    settings = get_settings()
    adapter = Boto3StorageAdapter(
        internal_endpoint=str(settings.minio_endpoint),
        public_endpoint=str(settings.minio_public_endpoint),
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket=settings.minio_private_bucket,
    )
    object_key = f"integration/{uuid.uuid4()}.png"
    payload = b"\x89PNG\r\n\x1a\n" + b"jepret-integration"
    browser_origin = "http://localhost:8080"
    upload_headers = {
        "Content-Type": "image/png",
        "If-None-Match": "*",
        "Origin": browser_origin,
    }

    try:
        upload_url = await adapter.create_upload_url(
            object_key=object_key,
            content_type="image/png",
            expires_seconds=settings.storage_signed_url_ttl_seconds,
        )
        async with httpx.AsyncClient() as client:
            preflight_response = await client.options(
                upload_url,
                headers={
                    "Origin": browser_origin,
                    "Access-Control-Request-Method": "PUT",
                    "Access-Control-Request-Headers": "content-type,if-none-match",
                },
            )
            assert_storage_status(preflight_response, 204)
            assert preflight_response.headers["access-control-allow-origin"] == browser_origin
            allowed_methods = {
                method.strip().upper()
                for method in preflight_response.headers["access-control-allow-methods"].split(",")
            }
            allowed_headers = {
                header.strip().lower()
                for header in preflight_response.headers["access-control-allow-headers"].split(",")
            }
            assert "PUT" in allowed_methods
            assert {"content-type", "if-none-match"} <= allowed_headers

            foreign_preflight_response = await client.options(
                upload_url,
                headers={
                    "Origin": "https://untrusted.example",
                    "Access-Control-Request-Method": "PUT",
                    "Access-Control-Request-Headers": "content-type,if-none-match",
                },
            )
            assert "access-control-allow-origin" not in foreign_preflight_response.headers

            upload_response = await client.put(
                upload_url,
                content=payload,
                headers=upload_headers,
            )
            assert_storage_status(upload_response, 200)
            assert upload_response.headers["access-control-allow-origin"] == browser_origin

            overwrite_response = await client.put(
                upload_url,
                content=payload + b"-overwrite",
                headers=upload_headers,
            )
            assert_storage_status(overwrite_response, 412)
            assert overwrite_response.headers["access-control-allow-origin"] == browser_origin

            stored_object = await adapter.inspect_object(object_key=object_key)
            assert stored_object.size_bytes == len(payload)
            assert stored_object.content_type == "image/png"
            assert stored_object.signature == payload[:16]

            download_url = await adapter.create_download_url(
                object_key=object_key,
                expires_seconds=settings.storage_signed_url_ttl_seconds,
            )
            unsigned_download_url = urlunsplit(urlsplit(download_url)._replace(query=""))
            unsigned_download_response = await client.get(
                unsigned_download_url,
                headers={"Origin": browser_origin},
            )
            assert_storage_status(unsigned_download_response, 403)

            download_response = await client.get(
                download_url,
                headers={"Origin": browser_origin},
            )
            assert_storage_status(download_response, 200)
            assert download_response.headers["access-control-allow-origin"] == browser_origin
            assert download_response.content == payload

        with pytest.raises(ClientError) as missing_object_error:
            await adapter.inspect_object(object_key=f"integration/{uuid.uuid4()}.png")
        assert missing_object_error.value.response["Error"]["Code"] in {
            "404",
            "NoSuchKey",
            "NotFound",
        }
    finally:
        await adapter.delete_object(object_key=object_key)
