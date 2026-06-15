from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.db.models import ProcessResult
from app.config import DEFAULT_GOVERNMENT_WARNING, get_settings


def submission_payload(**overrides):
    payload = {
        "brand": "Brand",
        "classType": "Wine",
        "address": "123 Main",
        "netContents": "750ml",
        "alcohol": "12%",
        "origin": "France",
        "appellation": "Bordeaux",
        "warning": "Government warning",
        "category": "Red Wine",
        "images": "label-front.png",
    }
    payload.update(overrides)
    return payload


def test_management_routes_require_authentication(unauthenticated_client) -> None:
    response = unauthenticated_client.get("/submissions")
    assert response.status_code == 401


def test_management_routes_accept_configured_api_key(unauthenticated_client, monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "test-api-key")
    get_settings.cache_clear()
    try:
        response = unauthenticated_client.post(
            "/submissions",
            json=submission_payload(),
            headers={"X-API-Key": "test-api-key"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 201
    assert response.json()["brand"] == "Brand"


def test_openapi_documents_api_key_header(unauthenticated_client) -> None:
    response = unauthenticated_client.get("/openapi.json")

    assert response.status_code == 200
    security_schemes = response.json()["components"]["securitySchemes"]
    assert security_schemes["APIKeyHeader"]["in"] == "header"
    assert security_schemes["APIKeyHeader"]["name"] == "X-API-Key"


def test_login_and_session_flow(unauthenticated_client) -> None:
    login_response = unauthenticated_client.post(
        "/auth/login",
        json={"username": "testadmin", "password": "testadmin"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["authenticated"] is True

    session_response = unauthenticated_client.get("/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["authenticated"] is True

    logout_response = unauthenticated_client.post("/auth/logout")
    assert logout_response.status_code == 200

    session_after_logout = unauthenticated_client.get("/auth/session")
    assert session_after_logout.json()["authenticated"] is False


def test_dashboard_stats_reports_submission_and_queue_counts(client, monkeypatch) -> None:
    from app.api import admin as admin_api

    monkeypatch.setattr(
        admin_api,
        "get_worker_health",
        lambda: {
            "worker_available": True,
            "worker_status": "online",
            "worker_count": 1,
        },
    )
    client.post("/submissions", json=submission_payload())
    client.post("/submissions", json=submission_payload(brand="Another"))

    response = client.get("/admin/dashboard/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["submission_count"] == 2
    assert body["queue_count"] == 2
    assert body["processing_enabled"] is True
    assert body["worker_available"] is True
    assert body["worker_status"] == "online"
    assert body["worker_count"] == 1


def test_process_results_list_and_delete(client, db_session) -> None:
    submission_id = client.post("/submissions", json=submission_payload()).json()["id"]
    result = ProcessResult(
        submission_id=submission_id,
        combined_image="/data/processed/result.png",
        match_results=[],
        approved=False,
        process_started=datetime.now(UTC),
        status="completed",
    )
    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)

    list_response = client.get("/process-results")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == result.id
    assert list_response.json()[0]["combinedImageUrl"] == f"/process-results/{result.id}/image"

    delete_response = client.delete(f"/process-results/{result.id}")
    assert delete_response.status_code == 204

    detail_response = client.get(f"/process-results/{result.id}")
    assert detail_response.status_code == 404


def test_gui_page_is_served(unauthenticated_client) -> None:
    response = unauthenticated_client.get("/gui")
    assert response.status_code == 200
    assert "COLA Label Matcher" in response.text
    assert 'id="submission-queue"' in response.text
    assert 'id="worker-status"' in response.text


def test_submission_warning_is_fixed_on_create_and_update(client) -> None:
    create_response = client.post(
        "/submissions",
        json=submission_payload(warning="user supplied warning"),
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["warning"] == DEFAULT_GOVERNMENT_WARNING

    update_response = client.patch(
        f"/submissions/{body['id']}",
        json={"warning": "another warning"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["warning"] == DEFAULT_GOVERNMENT_WARNING


def test_submissions_list_omits_nested_process_results_shape_that_requires_derived_fields(client, db_session) -> None:
    submission_id = client.post("/submissions", json=submission_payload()).json()["id"]
    db_session.add(
        ProcessResult(
            submission_id=submission_id,
            combined_image="/data/processed/result.png",
            match_results=[],
            approved=False,
            process_started=datetime.now(UTC),
            status="completed",
        )
    )
    db_session.commit()

    response = client.get("/submissions")

    assert response.status_code == 200
    assert response.json()[0]["processResults"] is None


def test_submission_detail_can_include_serialized_process_results(client, db_session) -> None:
    submission_id = client.post("/submissions", json=submission_payload()).json()["id"]
    result = ProcessResult(
        submission_id=submission_id,
        combined_image="/data/processed/result.png",
        match_results=[],
        approved=False,
        process_started=datetime.now(UTC),
        status="completed",
    )
    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)

    response = client.get(f"/submissions/{submission_id}", params={"include_results": True})

    assert response.status_code == 200
    assert response.json()["processResults"][0]["id"] == result.id
    assert response.json()["processResults"][0]["combinedImageUrl"] == f"/process-results/{result.id}/image"


def test_image_upload_returns_relative_path(client, monkeypatch, tmp_path) -> None:
    from app.api import images as images_api

    monkeypatch.setattr(
        images_api,
        "get_settings",
        lambda: SimpleNamespace(image_base_dir=str(tmp_path)),
    )

    response = client.post(
        "/images/upload",
        files={"image": ("label.png", b"png-bytes", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["path"].startswith("uploads/")
    assert body["path"].endswith("-label.png")
    assert (tmp_path / body["path"]).exists()


def test_image_upload_sanitizes_original_filename_reference(client, monkeypatch, tmp_path) -> None:
    from app.api import images as images_api

    monkeypatch.setattr(
        images_api,
        "get_settings",
        lambda: SimpleNamespace(image_base_dir=str(tmp_path)),
    )

    response = client.post(
        "/images/upload",
        files={"image": ("../Front Label (Final).PNG", b"png-bytes", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["path"].startswith("uploads/")
    assert body["path"].endswith("-Front-Label-Final.png")
    assert (tmp_path / body["path"]).exists()


def test_image_inventory_lists_serves_and_deletes_files(client, monkeypatch, tmp_path) -> None:
    from app.api import images as images_api

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    image_path = uploads_dir / "sample.png"
    image_path.write_bytes(b"png-bytes")

    monkeypatch.setattr(
        images_api,
        "get_settings",
        lambda: SimpleNamespace(image_base_dir=str(tmp_path)),
    )

    list_response = client.get("/images")
    assert list_response.status_code == 200
    body = list_response.json()
    assert body[0]["path"] == "uploads/sample.png"
    assert body[0]["previewUrl"].endswith("uploads%2Fsample.png")

    file_response = client.get("/images/file", params={"path": "uploads/sample.png"})
    assert file_response.status_code == 200
    assert file_response.content == b"png-bytes"

    delete_response = client.delete("/images", params={"path": "uploads/sample.png"})
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] == "uploads/sample.png"
    assert not image_path.exists()


def test_process_result_image_is_served(client, db_session, monkeypatch, tmp_path) -> None:
    from app.api import process_results as process_results_api

    processed_dir = tmp_path / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    result_image = processed_dir / "result.png"
    result_image.write_bytes(b"png-bytes")

    monkeypatch.setattr(
        process_results_api,
        "get_settings",
        lambda: SimpleNamespace(processed_image_dir=str(processed_dir)),
    )

    submission_id = client.post("/submissions", json=submission_payload()).json()["id"]
    result = ProcessResult(
        submission_id=submission_id,
        combined_image=str(result_image),
        match_results=[],
        approved=False,
        process_started=datetime.now(UTC),
        status="completed",
    )
    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)

    response = client.get(f"/process-results/{result.id}/image")

    assert response.status_code == 200
    assert response.content == b"png-bytes"
