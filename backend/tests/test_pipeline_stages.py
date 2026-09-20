"""Unit tests for the individual pipeline stages.

Each stage is tested for the behaviour the product promises, not just for "it
returns something": redaction must not eat a PIN code, the lexicon must make two
languages agree, priority must reproduce the published arithmetic, and the SLA
must let a hazard shorten a deadline but never lengthen one.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config.policy import dedup_config, priority_config
from app.models import GeocodeCache, Issue, Ward
from app.pipeline import lexicon
from app.pipeline.dedup import decide
from app.pipeline.fallback_clf import understand_offline
from app.pipeline.geocode import geocode_text, haversine_m, in_city, resolve_location
from app.pipeline.priority import band_for_score, compute_priority
from app.pipeline.redact import redact
from app.pipeline.sla import assign_sla, evaluate_sla, sla_hours_for
from app.pipeline.ward import ward_for_point
from app.security import decrypt_text, encrypt_text, verify_token, issue_token, authenticate


# ---------------------------------------------------------------------------
#  Redaction
# ---------------------------------------------------------------------------
class TestRedaction:
    @pytest.mark.parametrize(
        "text,placeholder",
        [
            ("Call me on 9876543210", "[PHONE]"),
            ("Call +91 98765 43210 please", "[PHONE]"),
            ("contact 07030123456 now", "[PHONE]"),
            ("mail me at resident@example.com", "[EMAIL]"),
            ("Aadhaar 2345 6789 0123", "[ID-NUMBER]"),
            ("car MH12AB1234 is parked", "[VEHICLE]"),
            ("PAN ABCDE1234F", "[PAN]"),
            ("माझा नंबर 9822012345 आहे", "[PHONE]"),
        ],
    )
    def test_masks_identifiers(self, text: str, placeholder: str) -> None:
        assert placeholder in redact(text).text

    @pytest.mark.parametrize(
        "text",
        [
            "Pothole at Katraj, pin 411046",       # PIN code is location, not identity
            "House no 42, plot 7",                  # address numbers are useful
            "Budget 15000 for year 2026",
            "",
        ],
    )
    def test_keeps_useful_numbers(self, text: str) -> None:
        """Over-redaction would make the complaint useless to the officer."""
        assert redact(text).text == text
        assert not redact(text).found_any

    def test_reports_what_it_removed(self) -> None:
        result = redact("ring 9876543210 or mail a@b.com")
        assert result.counts == {"email": 1, "phone": 1}
        assert "phone number" in result.notice

    def test_aadhaar_wins_over_phone(self) -> None:
        """A 12-digit ID must not be chopped into a 10-digit phone match."""
        result = redact("234567890123")
        assert result.text == "[ID-NUMBER]"


# ---------------------------------------------------------------------------
#  Lexicon: the cross-lingual guarantee
# ---------------------------------------------------------------------------
class TestLexicon:
    MARATHI = "कात्रज डेअरी समोर मोठा खड्डा आहे, शाळेजवळ"
    HINGLISH = "Katraj dairy ke saamne bada gaddha hai, school ke paas"
    ENGLISH = "Large pothole opposite Katraj dairy near the school"

    def test_same_problem_three_languages_same_summary(self) -> None:
        summaries = {lexicon.analyse(t).summary_en for t in (self.MARATHI, self.HINGLISH, self.ENGLISH)}
        assert len(summaries) == 1, f"languages disagreed: {summaries}"

    def test_same_problem_same_match_key(self) -> None:
        keys = {lexicon.analyse(t).match_text for t in (self.MARATHI, self.HINGLISH, self.ENGLISH)}
        assert len(keys) == 1, f"match keys disagreed: {keys}"

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("कात्रज मध्ये खड्डा आहे", "mr"),
            ("यहाँ गड्ढा है, कृपया ठीक करें", "hi"),
            ("Katraj me gaddha hai bhai", "hinglish"),
            ("There is a pothole here, please fix it", "en"),
            ("", "unknown"),
        ],
    )
    def test_language_detection(self, text: str, expected: str) -> None:
        assert lexicon.detect_language(text)[0] == expected

    def test_transliteration_folds_to_same_landmark(self) -> None:
        assert lexicon.fold(lexicon.transliterate("कात्रज")) == lexicon.fold("Katraj")

    def test_hazards_are_extracted(self) -> None:
        analysis = lexicon.analyse("हडपसर मध्ये मॅनहोलचे झाकण नाही, खूप धोकादायक")
        assert "open_manhole" in analysis.hazards

    def test_unknown_text_yields_nothing(self) -> None:
        analysis = lexicon.analyse("qwerty asdfgh zxcvbn")
        assert analysis.best_category[0] is None
        assert analysis.summary_en == ""

    def test_match_key_is_order_independent(self) -> None:
        """Term match order must not change the similarity key."""
        a = lexicon.analyse("pothole near Katraj school")
        b = lexicon.analyse("school near Katraj pothole")
        assert a.match_text == b.match_text


# ---------------------------------------------------------------------------
#  Offline classifier
# ---------------------------------------------------------------------------
class TestOfflineClassifier:
    @pytest.mark.parametrize(
        "text,category",
        [
            ("कात्रज डेअरी समोर मोठा खड्डा आहे", "pothole_road"),
            ("Kothrud me kachra nahi uthaya, badbu aa rahi hai", "garbage_waste"),
            ("हडपसर मध्ये मॅनहोलचे झाकण नाही", "drainage_sewage"),
            ("स्वारगेट येथे विजेची तार लोंबकळत आहे", "streetlight"),
        ],
    )
    def test_classifies_across_languages(self, text: str, category: str) -> None:
        assert understand_offline(text).category == category

    def test_gibberish_gets_low_confidence_not_a_guess(self) -> None:
        """Unreadable input must route to a human, never be confidently filed."""
        reading = understand_offline("zxcvbn qwerty asdfgh")
        threshold = priority_config()  # policy is loaded; confidence lives elsewhere
        assert threshold is not None
        assert reading.confidence_0to1 < 0.55

    def test_short_input_cannot_be_highly_confident(self) -> None:
        assert understand_offline("road").confidence_0to1 < 0.55

    def test_always_returns_a_valid_reading(self) -> None:
        for text in ("", "   ", "!!!", "a"):
            reading = understand_offline(text)
            assert reading.category
            assert 0.0 <= reading.confidence_0to1 <= 1.0

    def test_hazard_raises_severity(self) -> None:
        assert understand_offline("खुली वीज तार आहे, करंट येतो").severity_1to5 == 5


# ---------------------------------------------------------------------------
#  Geography
# ---------------------------------------------------------------------------
class TestGeography:
    def test_haversine_known_distance(self) -> None:
        # Katraj to Swargate is about 5 km.
        metres = haversine_m(18.4575, 73.8677, 18.5018, 73.8586)
        assert 4500 < metres < 5500

    def test_city_bounds(self) -> None:
        assert in_city(18.51, 73.85)
        assert not in_city(19.07, 72.87)  # Mumbai
        assert not in_city(None, None)

    def test_point_lands_in_its_own_ward(self) -> None:
        hit = ward_for_point(18.4575, 73.8677)
        assert hit is not None
        assert hit.code == "W05"  # Katraj

    def test_no_coordinate_no_ward(self) -> None:
        assert ward_for_point(None, None) is None

    def test_geocode_cache_is_used_and_no_network_is_touched(self, db) -> None:
        """A cached row must be returned without any outbound request."""
        query = "Katraj dairy"
        db.add(
            GeocodeCache(
                query_hash=__import__("hashlib").sha256(query.lower().encode()).hexdigest(),
                query=query,
                lat=18.4575,
                lon=73.8677,
                display_name="Katraj, Pune",
                source="nominatim",
                confidence=0.75,
            )
        )
        db.flush()
        result = geocode_text(db, query)
        assert result.resolved
        assert result.lat == pytest.approx(18.4575)
        assert "cache" in result.note

    def test_landmark_fallback_works_offline(self, db) -> None:
        """With no network at all, a named locality still gets a pin."""
        result = resolve_location(db, location_text="somewhere vague", landmarks=["Katraj"])
        assert result.resolved
        assert result.source == "landmark"
        assert result.confidence < 1.0  # and it says it is approximate

    def test_unresolvable_location_is_reported_not_guessed(self, db) -> None:
        result = resolve_location(db, location_text="", landmarks=[])
        assert not result.resolved
        assert result.source == "unknown"


# ---------------------------------------------------------------------------
#  SLA
# ---------------------------------------------------------------------------
class TestSla:
    def test_category_default(self) -> None:
        assert sla_hours_for("pothole_road")[0] == 72

    def test_hazard_shortens_deadline(self) -> None:
        assert sla_hours_for("pothole_road", ["live_wire"])[0] == 4

    def test_hazard_never_lengthens_deadline(self) -> None:
        """water_supply is 24h; a 24h open_manhole override must not extend it."""
        base = sla_hours_for("water_supply")[0]
        with_hazard = sla_hours_for("water_supply", ["open_manhole"])[0]
        assert with_hazard <= base

    def test_tightest_hazard_wins(self) -> None:
        assert sla_hours_for("other", ["flooding", "live_wire"])[0] == 4

    def test_breach_detection(self) -> None:
        now = datetime.now(timezone.utc)
        state = evaluate_sla(
            hours=24,
            created_at=now - timedelta(hours=30),
            deadline=now - timedelta(hours=6),
            now=now,
        )
        assert state.breached
        assert "Breached" in state.label

    def test_resolved_issue_judged_at_resolution_time(self) -> None:
        """Closing on time must not later become a breach just because time passed."""
        now = datetime.now(timezone.utc)
        created = now - timedelta(days=10)
        state = evaluate_sla(
            hours=72,
            created_at=created,
            deadline=created + timedelta(hours=72),
            resolved_at=created + timedelta(hours=20),
            now=now,
        )
        assert not state.breached

    def test_assignment_sets_deadline_from_creation(self) -> None:
        created = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
        assignment = assign_sla("garbage_waste", [], created)
        assert assignment.deadline == created + timedelta(hours=48)


# ---------------------------------------------------------------------------
#  Priority
# ---------------------------------------------------------------------------
class TestPriority:
    def _issue(self, db, **overrides) -> Issue:
        ward = db.query(Ward).filter(Ward.code == "W05").one()
        defaults = dict(
            issue_code="ISU-TEST01",
            title="Test",
            category="pothole_road",
            status="received",
            lat=18.4575,
            lon=73.8677,
            ward_id=ward.id,
            report_count=1,
            severity=3,
            hazard_flags=[],
            sla_hours=72,
            created_at=datetime.now(timezone.utc),
        )
        defaults.update(overrides)
        issue = Issue(**defaults)
        db.add(issue)
        db.flush()
        return issue

    def test_reproduces_the_published_worked_example(self, db) -> None:
        """The PS-18 brief's example must come out of the config, not a fudge.

        Severity 4 (+32) + open manhole (+20) + near school (+10)
        + 9 reports (+14) = 76, before any SLA pressure.
        """
        issue = self._issue(
            db,
            severity=4,
            hazard_flags=["open_manhole", "near_school"],
            report_count=9,
        )
        result = compute_priority(db, issue, now=issue.created_at)
        points = {c.key: c.points for c in result.components}
        assert points["severity"] == 32
        assert points["hazard:open_manhole"] == 20
        assert points["hazard:near_school"] == 10
        assert round(points["cluster"]) == 14

    def test_more_reports_raise_priority_sublinearly(self, db) -> None:
        """Log scaling: the 2nd report matters far more than the 50th."""
        one = compute_priority(db, self._issue(db, issue_code="A", report_count=1))
        ten = compute_priority(db, self._issue(db, issue_code="B", report_count=10))
        hundred = compute_priority(db, self._issue(db, issue_code="C", report_count=100))
        assert one.score < ten.score < hundred.score
        assert (ten.score - one.score) > (hundred.score - ten.score)

    def test_score_is_capped(self, db) -> None:
        issue = self._issue(
            db,
            severity=5,
            hazard_flags=["live_wire", "open_manhole", "flooding", "accident_risk"],
            report_count=500,
        )
        result = compute_priority(db, issue)
        assert result.score <= priority_config()["max_score"]

    def test_every_component_explains_itself(self, db) -> None:
        result = compute_priority(db, self._issue(db, severity=4, hazard_flags=["live_wire"]))
        assert result.components
        for component in result.components:
            assert component.label
            assert component.detail
            assert component.source in {"ai", "citizens", "map", "policy", "equity"}

    def test_equity_boost_is_opt_in_and_visible(self, db) -> None:
        issue = self._issue(db)
        without = compute_priority(db, issue, underserved_wards=[], equity_enabled=True)
        with_boost = compute_priority(db, issue, underserved_wards=["W05"], equity_enabled=True)
        disabled = compute_priority(db, issue, underserved_wards=["W05"], equity_enabled=False)

        assert with_boost.score > without.score
        assert with_boost.equity_applied
        assert not disabled.equity_applied
        assert disabled.score == without.score
        assert any(c.source == "equity" for c in with_boost.components)

    def test_no_double_charge_for_the_same_school(self, db) -> None:
        """A near_school hazard already charged must suppress the map-derived bonus."""
        flagged = self._issue(db, issue_code="D", hazard_flags=["near_school"])
        result = compute_priority(db, flagged)
        keys = [c.key for c in result.components]
        assert "hazard:near_school" in keys
        assert "vulnerable:school" not in keys

    def test_bands(self) -> None:
        assert band_for_score(90) == "P1"
        assert band_for_score(60) == "P2"
        assert band_for_score(40) == "P3"
        assert band_for_score(10) == "P4"


# ---------------------------------------------------------------------------
#  Deduplication
# ---------------------------------------------------------------------------
class TestDedup:
    def _open_issue(self, db, **overrides) -> Issue:
        analysis = lexicon.analyse("कात्रज डेअरी समोर मोठा खड्डा आहे, शाळेजवळ")
        defaults = dict(
            issue_code="ISU-EXIST",
            title=analysis.summary_en,
            match_text=analysis.match_text,
            category="pothole_road",
            status="received",
            lat=18.4575,
            lon=73.8677,
            report_count=1,
            severity=4,
            created_at=datetime.now(timezone.utc),
        )
        defaults.update(overrides)
        issue = Issue(**defaults)
        db.add(issue)
        db.flush()
        return issue

    def test_cross_language_duplicate_is_merged(self, db) -> None:
        """The headline claim: Marathi and Hinglish reports of one pothole merge."""
        self._open_issue(db)
        incoming = lexicon.analyse("Katraj dairy ke saamne bada gaddha hai, school ke paas")
        decision = decide(
            db,
            category="pothole_road",
            match_text=incoming.match_text,
            lat=18.4576,
            lon=73.8679,
        )
        assert decision.decision == "merge"
        assert decision.issue is not None

    def test_far_away_same_category_is_not_merged(self, db) -> None:
        self._open_issue(db)
        incoming = lexicon.analyse("Hadapsar me bada gaddha hai")
        decision = decide(
            db,
            category="pothole_road",
            match_text=incoming.match_text,
            lat=18.5089,   # ~8 km away
            lon=73.9260,
        )
        assert decision.decision == "new"

    def test_different_category_is_never_a_candidate(self, db) -> None:
        self._open_issue(db)
        incoming = lexicon.analyse("कात्रज डेअरी समोर कचरा आहे")
        decision = decide(
            db,
            category="garbage_waste",
            match_text=incoming.match_text,
            lat=18.4575,
            lon=73.8677,
        )
        assert decision.decision == "new"

    def test_outside_time_window_is_not_a_candidate(self, db) -> None:
        window = dedup_config()["window_days"]
        old = datetime.now(timezone.utc) - timedelta(days=window + 5)
        self._open_issue(db, created_at=old)
        incoming = lexicon.analyse("Katraj dairy ke saamne bada gaddha hai, school ke paas")
        decision = decide(
            db,
            category="pothole_road",
            match_text=incoming.match_text,
            lat=18.4576,
            lon=73.8679,
        )
        assert decision.decision == "new"

    def test_resolved_issues_are_not_candidates(self, db) -> None:
        self._open_issue(db, status="resolved")
        incoming = lexicon.analyse("Katraj dairy ke saamne bada gaddha hai, school ke paas")
        decision = decide(
            db,
            category="pothole_road",
            match_text=incoming.match_text,
            lat=18.4576,
            lon=73.8679,
        )
        assert decision.decision == "new"

    def test_locationless_report_never_auto_merges(self, db) -> None:
        """Without a pin we cannot tell one pothole from the next street's."""
        self._open_issue(db)
        incoming = lexicon.analyse("कात्रज डेअरी समोर मोठा खड्डा आहे, शाळेजवळ")
        decision = decide(
            db,
            category="pothole_road",
            match_text=incoming.match_text,
            lat=None,
            lon=None,
        )
        assert decision.decision in {"review", "new"}
        assert decision.decision != "merge"

    def test_every_decision_carries_an_explanation(self, db) -> None:
        self._open_issue(db)
        for lat, lon in ((18.4576, 73.8679), (18.5089, 73.9260)):
            decision = decide(
                db,
                category="pothole_road",
                match_text=lexicon.analyse("Katraj dairy bada gaddha").match_text,
                lat=lat,
                lon=lon,
            )
            assert decision.explanation


# ---------------------------------------------------------------------------
#  Security
# ---------------------------------------------------------------------------
class TestSecurity:
    def test_raw_text_round_trips_through_encryption(self) -> None:
        text = "कात्रज मध्ये खड्डा, नंबर 9822012345"
        cipher = encrypt_text(text)
        assert cipher != text
        assert decrypt_text(cipher) == text

    def test_bad_ciphertext_degrades_instead_of_raising(self) -> None:
        assert decrypt_text("not-a-valid-token") == ""

    def test_token_round_trip(self) -> None:
        officer = authenticate("officer", "officer")
        assert verify_token(issue_token(officer)).username == "officer"

    def test_tampered_token_rejected(self) -> None:
        from app.security import AuthError

        token = issue_token(authenticate("officer", "officer"))
        with pytest.raises(AuthError):
            verify_token(token[:-4] + "aaaa")

    def test_wrong_password_rejected(self) -> None:
        from app.security import AuthError

        with pytest.raises(AuthError):
            authenticate("officer", "not-the-password")
