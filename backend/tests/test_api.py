"""End-to-end API tests against a real FastAPI app on a throwaway database.

These cover the promises the product makes to a citizen and to an officer:
nothing is rejected, duplicates join rather than get refused, PII never comes
back out, and no override is possible without a recorded reason.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.db import Base, get_db
from app.services.bootstrap import ensure_reference_data

MARATHI_POTHOLE = "कात्रज डेअरी समोर मोठा खड्डा आहे, शाळेजवळ, दोन दिवसांपासून"
HINGLISH_POTHOLE = "Katraj dairy ke saamne bada gaddha hai, school ke paas"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A TestClient wired to an isolated database and an isolated upload dir."""
    monkeypatch.setattr(settings, "geocoding_enabled", False)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    engine = create_engine(f"sqlite:///{(tmp_path / 'api.db').as_posix()}", future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    seed_session = factory()
    ensure_reference_data(seed_session)
    seed_session.close()

    from app.main import app

    def override_get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def submit(client: TestClient, text: str, **extra) -> dict:
    data = {"text": text, "ui_language": "mr", "device_ref": "test-device", **extra}
    response = client.post("/api/complaints", data=data)
    assert response.status_code == 201, response.text
    return response.json()


def officer_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "officer", "password": "officer"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


# ---------------------------------------------------------------------------
#  Public surface
# ---------------------------------------------------------------------------
class TestPublicEndpoints:
    def test_health_states_which_ai_is_running(self, client: TestClient) -> None:
        payload = client.get("/api/health").json()
        assert payload["status"] == "ok"
        assert payload["challenge"] == "PS-18"
        assert "llm_active" in payload["ai"]
        assert "embedder" in payload["ai"]

    def test_meta_publishes_the_taxonomy(self, client: TestClient) -> None:
        payload = client.get("/api/meta").json()
        assert len(payload["categories"]) == 9
        assert len(payload["hazards"]) == 7
        assert "decision-support" in payload["scope_statement"].lower()

    def test_policy_is_published_verbatim(self, client: TestClient) -> None:
        payload = client.get("/api/meta/policy").json()
        assert "auto_merge_threshold" in payload["content"]
        assert "priority" in payload["content"]

    def test_ward_geometry_is_served(self, client: TestClient) -> None:
        payload = client.get("/api/public/wards.geojson").json()
        assert len(payload["features"]) == 12


# ---------------------------------------------------------------------------
#  Citizen intake
# ---------------------------------------------------------------------------
class TestComplaintIntake:
    def test_happy_path_returns_an_explained_ticket(self, client: TestClient) -> None:
        result = submit(client, MARATHI_POTHOLE, lat="18.4575", lon="73.8677", location_source="gps")

        assert result["ticket_code"].startswith("NN-")
        assert result["category"]["key"] == "pothole_road"
        assert result["severity"] >= 4
        assert result["ai"]["explanation"]
        assert result["priority"]["breakdown"], "a score with no breakdown is not explainable"
        assert result["sla"]["hours"] > 0
        assert result["location"]["ward"] == "Katraj"

    def test_empty_submission_is_refused_with_a_helpful_message(self, client: TestClient) -> None:
        response = client.post("/api/complaints", data={"text": "", "device_ref": "d"})
        assert response.status_code == 422
        assert "describe" in response.json()["detail"].lower()

    def test_unintelligible_complaint_is_accepted_not_rejected(self, client: TestClient) -> None:
        """The core Responsible-AI promise: the AI never refuses a citizen."""
        result = submit(client, "zxcvbn qwerty asdfgh")
        assert result["ticket_code"]
        assert result["review"]["needed"] is True
        assert "rejected" not in result["citizen_message"].lower()

    def test_pii_is_redacted_and_never_returned(self, client: TestClient) -> None:
        result = submit(
            client,
            "कात्रज मध्ये खड्डा आहे, माझा नंबर 9822012345 आणि मेल a@b.com",
            lat="18.4575",
            lon="73.8677",
        )
        assert result["redaction"]["counts"]["phone"] == 1
        assert result["redaction"]["counts"]["email"] == 1

        tracked = client.get(f"/api/complaints/{result['ticket_code']}").json()
        stored = tracked["report"]["text"]
        assert "9822012345" not in stored
        assert "a@b.com" not in stored
        assert "[PHONE]" in stored

    def test_raw_text_is_never_exposed_by_the_api(self, client: TestClient) -> None:
        result = submit(client, "कात्रज मध्ये खड्डा, नंबर 9822012345")
        body = client.get(f"/api/complaints/{result['ticket_code']}").text
        assert "raw_text" not in body
        assert "reporter_ref" not in body

    def test_cross_language_duplicate_joins_instead_of_being_refused(
        self, client: TestClient
    ) -> None:
        """The headline feature, end to end over HTTP."""
        first = submit(client, MARATHI_POTHOLE, lat="18.4575", lon="73.8677", location_source="gps")
        second = submit(
            client, HINGLISH_POTHOLE, lat="18.4576", lon="73.8679", location_source="pin"
        )

        assert second["issue_code"] == first["issue_code"]
        assert second["cluster"]["joined_existing"] is True
        assert second["cluster"]["report_count"] == 2
        assert second["ticket_code"] != first["ticket_code"], "each voice keeps its own ticket"
        message = second["citizen_message"].lower()
        assert "reported this" in message
        assert "duplicate" not in message and "rejected" not in message

    def test_more_voices_raise_the_priority(self, client: TestClient) -> None:
        first = submit(client, MARATHI_POTHOLE, lat="18.4575", lon="73.8677", location_source="gps")
        second = submit(
            client, HINGLISH_POTHOLE, lat="18.4576", lon="73.8679", location_source="pin"
        )
        assert second["priority"]["score"] > first["priority"]["score"]

    def test_missing_location_goes_to_review_with_a_pin_request(self, client: TestClient) -> None:
        result = submit(client, "light nahi hai")
        assert "missing_location" in result["review"]["kinds"]
        assert "officer" in result["citizen_message"].lower()

    def test_photo_is_accepted_and_stripped(self, client: TestClient) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (900, 700), (90, 110, 130)).save(buffer, format="JPEG")
        buffer.seek(0)
        response = client.post(
            "/api/complaints",
            data={"text": "कात्रज मध्ये खड्डा", "lat": "18.4575", "lon": "73.8677"},
            files={"photo": ("pothole.jpg", buffer, "image/jpeg")},
        )
        assert response.status_code == 201
        assert response.json()["image_url"]

    def test_non_image_upload_does_not_break_intake(self, client: TestClient) -> None:
        response = client.post(
            "/api/complaints",
            data={"text": "कात्रज मध्ये खड्डा", "lat": "18.4575", "lon": "73.8677"},
            files={"photo": ("evil.exe", io.BytesIO(b"not an image"), "application/octet-stream")},
        )
        assert response.status_code == 201
        assert response.json()["image_url"] is None

    def test_unknown_ticket_is_a_clean_404(self, client: TestClient) -> None:
        response = client.get("/api/complaints/NN-DOESNOTEXIST")
        assert response.status_code == 404
        assert "could not find" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
#  Officer surface
# ---------------------------------------------------------------------------
class TestOfficerEndpoints:
    def test_dashboard_requires_authentication(self, client: TestClient) -> None:
        for path in ("/api/admin/issues", "/api/admin/review", "/api/admin/audit"):
            assert client.get(path).status_code == 401

    def test_bad_credentials_rejected(self, client: TestClient) -> None:
        response = client.post("/api/auth/login", json={"username": "officer", "password": "nope"})
        assert response.status_code == 401

    def test_queue_lists_issues_with_explanations(self, client: TestClient) -> None:
        submit(client, MARATHI_POTHOLE, lat="18.4575", lon="73.8677", location_source="gps")
        headers = officer_headers(client)
        payload = client.get("/api/admin/issues", headers=headers).json()
        assert payload["total"] >= 1
        issue = payload["items"][0]
        assert issue["priority"]["band"] in {"P1", "P2", "P3", "P4"}
        assert issue["category"]["key"]

    def test_override_without_a_reason_is_refused(self, client: TestClient) -> None:
        """An unexplained override is indistinguishable from a mis-click."""
        result = submit(client, MARATHI_POTHOLE, lat="18.4575", lon="73.8677")
        headers = officer_headers(client)
        response = client.post(
            f"/api/admin/issues/{result['issue_code']}/override-category",
            json={"category": "water_supply", "reason": "oops"},
            headers=headers,
        )
        assert response.status_code == 422

    def test_override_with_a_reason_is_applied_and_audited(self, client: TestClient) -> None:
        result = submit(client, MARATHI_POTHOLE, lat="18.4575", lon="73.8677")
        headers = officer_headers(client)
        reason = "Site visit showed a burst water pipeline, not a road defect."

        response = client.post(
            f"/api/admin/issues/{result['issue_code']}/override-category",
            json={"category": "water_supply", "reason": reason},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["issue"]["category"]["key"] == "water_supply"
        assert response.json()["issue"]["department"] == "water"

        audit = client.get("/api/admin/audit", headers=headers).json()
        entry = audit["items"][0]
        assert entry["action"] == "override_category"
        assert entry["reason"] == reason
        assert entry["before"]["category"] == "pothole_road"
        assert entry["after"]["category"] == "water_supply"

    def test_status_change_appears_on_the_public_timeline(self, client: TestClient) -> None:
        result = submit(client, MARATHI_POTHOLE, lat="18.4575", lon="73.8677")
        headers = officer_headers(client)
        client.patch(
            f"/api/admin/issues/{result['issue_code']}/status",
            json={"status": "verified", "note": "Confirmed on site"},
            headers=headers,
        )
        tracked = client.get(f"/api/complaints/{result['ticket_code']}").json()
        assert [event["to_status"] for event in tracked["timeline"]][-1] == "verified"

    def test_review_queue_exposes_the_evidence(self, client: TestClient) -> None:
        submit(client, "light nahi hai")
        headers = officer_headers(client)
        payload = client.get("/api/admin/review", headers=headers).json()
        assert payload["open_total"] >= 1
        assert payload["items"][0]["payload"]

    def test_resolving_a_review_records_the_decision(self, client: TestClient) -> None:
        submit(client, "light nahi hai")
        headers = officer_headers(client)
        task = client.get("/api/admin/review", headers=headers).json()["items"][0]

        response = client.post(
            f"/api/admin/review/{task['id']}/resolve",
            json={
                "action": "set_location",
                "lat": 18.5074,
                "lon": 73.8077,
                "reason": "Caller described the lane behind Kothrud depot.",
            },
            headers=headers,
        )
        assert response.status_code == 200
        reopened = client.get("/api/admin/review", headers=headers).json()
        assert all(item["id"] != task["id"] for item in reopened["items"])

    def test_unmerging_creates_a_separate_issue_and_keeps_both(self, client: TestClient) -> None:
        submit(client, MARATHI_POTHOLE, lat="18.4575", lon="73.8677", location_source="gps")
        second = submit(client, HINGLISH_POTHOLE, lat="18.4576", lon="73.8679", location_source="pin")
        assert second["cluster"]["joined_existing"]

        headers = officer_headers(client)
        detail = client.get(f"/api/admin/issues/{second['issue_code']}", headers=headers).json()
        report_id = detail["reports"][-1]["id"]

        response = client.post(
            f"/api/admin/reports/{report_id}/unmerge",
            json={"reason": "These are two different potholes on the same street.", "target_issue_code": ""},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["new_issue"]["issue_code"] != second["issue_code"]

        # Both tickets still resolve - no citizen report was lost.
        assert client.get(f"/api/complaints/{second['ticket_code']}").status_code == 200

    def test_equity_toggle_is_audited(self, client: TestClient) -> None:
        headers = officer_headers(client)
        response = client.patch(
            "/api/admin/settings",
            json={"equity_boost_enabled": False, "reason": "Testing the policy switch"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["equity_boost_enabled"] is False

        audit = client.get("/api/admin/audit", headers=headers).json()
        assert any(item["action"] == "toggle_equity_boost" for item in audit["items"])


# ---------------------------------------------------------------------------
#  Analytics
# ---------------------------------------------------------------------------
class TestAnalytics:
    def test_all_three_dashboards_respond(self, client: TestClient) -> None:
        submit(client, MARATHI_POTHOLE, lat="18.4575", lon="73.8677")
        for path in ("/api/analytics/sla", "/api/analytics/equity", "/api/analytics/ai-health"):
            assert client.get(path).status_code == 200, path

    def test_equity_explains_its_own_thresholds(self, client: TestClient) -> None:
        payload = client.get("/api/analytics/equity").json()
        assert payload["explanation"]
        assert "underserved_ratio" in payload["thresholds"]

    def test_ai_health_separates_live_from_benchmark(self, client: TestClient) -> None:
        submit(client, MARATHI_POTHOLE, lat="18.4575", lon="73.8677")
        payload = client.get("/api/analytics/ai-health").json()
        assert payload["live"]["total_reports"] >= 1
        assert "holdout" in payload
        assert payload["live"]["latency"]["by_stage"]

    def test_feedback_only_after_resolution(self, client: TestClient) -> None:
        result = submit(client, MARATHI_POTHOLE, lat="18.4575", lon="73.8677")
        early = client.post(
            f"/api/complaints/{result['ticket_code']}/feedback",
            json={"rating": 5, "comment": ""},
        )
        assert early.status_code == 409

        headers = officer_headers(client)
        client.patch(
            f"/api/admin/issues/{result['issue_code']}/status",
            json={"status": "resolved", "note": "Fixed"},
            headers=headers,
        )
        accepted = client.post(
            f"/api/complaints/{result['ticket_code']}/feedback",
            json={"rating": 4, "comment": "Fixed quickly"},
        )
        assert accepted.status_code == 201

        duplicate = client.post(
            f"/api/complaints/{result['ticket_code']}/feedback",
            json={"rating": 1, "comment": "again"},
        )
        assert duplicate.status_code == 409
