"""
Unit tests for Phase 9A: CDS Engine.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.schemas import CdsAlertOut, VitalCreate
from app.services.cds import CdsService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_allergy(allergen: str):
    a = MagicMock()
    a.allergen = allergen
    return a


def _make_prescription(drug_name: str, status: str = "active"):
    rx = MagicMock()
    rx.drug_name = drug_name
    rx.status = status
    return rx


def _make_cds_rule(rule_type: str, rule_key: str, severity: str, message: str):
    r = MagicMock()
    r.rule_type = rule_type
    r.rule_key = rule_key
    r.severity = severity
    r.message = message
    r.active = True
    return r


async def _mock_db_execute_side_effects(allergy_rows, allergy_rules, rx_rows, ddi_rules):
    call_count = 0

    async def _execute(q):
        nonlocal call_count
        res = MagicMock()
        if call_count == 0:
            res.scalars.return_value.all.return_value = allergy_rows
        elif call_count == 1:
            res.scalars.return_value.all.return_value = allergy_rules
        elif call_count == 2:
            res.scalars.return_value.all.return_value = rx_rows
        elif call_count == 3:
            res.scalars.return_value.all.return_value = ddi_rules
        call_count += 1
        return res

    return _execute


# ── Drug-allergy: critical blocks ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_drug_allergy_critical_alert_fires():
    allergy = _make_allergy("penicillin")
    rule = _make_cds_rule("drug_allergy", "penicillin", "critical", "Penicillin allergy — blocked")

    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects(
        allergy_rows=[allergy],
        allergy_rules=[rule],
        rx_rows=[],
        ddi_rules=[],
    )

    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_prescription(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            drug_name="amoxicillin-penicillin",
            current_user_id=uuid.uuid4(),
            db=db,
        )

    drug_allergy_alerts = [a for a in alerts if a.rule_type == "drug_allergy"]
    assert len(drug_allergy_alerts) >= 1
    assert drug_allergy_alerts[0].severity == "critical"


@pytest.mark.asyncio
async def test_drug_allergy_no_alert_when_no_matching_allergy():
    allergy = _make_allergy("aspirin")
    rule = _make_cds_rule("drug_allergy", "penicillin", "critical", "Penicillin allergy — blocked")

    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects(
        allergy_rows=[allergy],
        allergy_rules=[rule],
        rx_rows=[],
        ddi_rules=[],
    )

    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_prescription(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            drug_name="ibuprofen",
            current_user_id=uuid.uuid4(),
            db=db,
        )

    assert not any(a.rule_type == "drug_allergy" for a in alerts)


# ── Drug-drug interaction ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_drug_drug_interaction_fires_when_patient_has_other_drug():
    rule = _make_cds_rule("drug_drug", "aspirin|warfarin", "warning", "Bleeding risk")
    active_rx = _make_prescription("warfarin")

    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects(
        allergy_rows=[],
        allergy_rules=[],
        rx_rows=[active_rx],
        ddi_rules=[rule],
    )

    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_prescription(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            drug_name="aspirin",
            current_user_id=uuid.uuid4(),
            db=db,
        )

    ddi_alerts = [a for a in alerts if a.rule_type == "drug_drug"]
    assert len(ddi_alerts) == 1
    assert ddi_alerts[0].severity == "warning"


@pytest.mark.asyncio
async def test_drug_drug_no_alert_when_patient_lacks_interacting_drug():
    rule = _make_cds_rule("drug_drug", "aspirin|warfarin", "warning", "Bleeding risk")
    active_rx = _make_prescription("metformin")

    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects(
        allergy_rows=[],
        allergy_rules=[],
        rx_rows=[active_rx],
        ddi_rules=[rule],
    )

    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_prescription(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            drug_name="aspirin",
            current_user_id=uuid.uuid4(),
            db=db,
        )

    assert not any(a.rule_type == "drug_drug" for a in alerts)


# ── Vital alerts ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vital_tachycardia_warning():
    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects([], [], [], [])

    payload = VitalCreate(heart_rate=130)
    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_vitals(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            payload=payload,
            current_user_id=uuid.uuid4(),
            db=db,
        )

    hr_alert = next((a for a in alerts if a.rule_key == "HR_HIGH"), None)
    assert hr_alert is not None
    assert hr_alert.severity == "warning"


@pytest.mark.asyncio
async def test_vital_hypertensive_crisis_critical():
    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects([], [], [], [])

    payload = VitalCreate(bp_systolic=190, bp_diastolic=80)
    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_vitals(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            payload=payload,
            current_user_id=uuid.uuid4(),
            db=db,
        )

    sbp_alert = next((a for a in alerts if a.rule_key == "SBP_CRISIS"), None)
    assert sbp_alert is not None
    assert sbp_alert.severity == "critical"


@pytest.mark.asyncio
async def test_vital_hypoxia_critical():
    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects([], [], [], [])

    payload = VitalCreate(spo2=88)
    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_vitals(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            payload=payload,
            current_user_id=uuid.uuid4(),
            db=db,
        )

    spo2_alert = next((a for a in alerts if a.rule_key == "SPO2_LOW"), None)
    assert spo2_alert is not None
    assert spo2_alert.severity == "critical"


@pytest.mark.asyncio
async def test_vital_fever_warning():
    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects([], [], [], [])

    payload = VitalCreate(temperature_f=104.0)
    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_vitals(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            payload=payload,
            current_user_id=uuid.uuid4(),
            db=db,
        )

    temp_alert = next((a for a in alerts if a.rule_key == "TEMP_HIGH"), None)
    assert temp_alert is not None
    assert temp_alert.severity == "warning"


@pytest.mark.asyncio
async def test_vital_no_alerts_for_normal_values():
    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects([], [], [], [])

    payload = VitalCreate(heart_rate=75, bp_systolic=120, bp_diastolic=80, spo2=98, temperature_f=98.6, respiratory_rate=16)
    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_vitals(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            payload=payload,
            current_user_id=uuid.uuid4(),
            db=db,
        )

    assert len(alerts) == 0


# ── qSOFA sepsis score ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_qsofa_score_2_fires_critical():
    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects([], [], [], [])

    # RR >= 22 (+1) + SBP <= 100 (+1) = score 2
    payload = VitalCreate(respiratory_rate=24, bp_systolic=95)
    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_vitals(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            payload=payload,
            current_user_id=uuid.uuid4(),
            db=db,
        )

    qsofa_alert = next((a for a in alerts if a.rule_type == "sepsis_score"), None)
    assert qsofa_alert is not None
    assert qsofa_alert.severity == "critical"
    assert "qSOFA" in qsofa_alert.message


@pytest.mark.asyncio
async def test_qsofa_score_1_does_not_fire():
    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects([], [], [], [])

    # Only RR >= 22 (+1) — score = 1
    payload = VitalCreate(respiratory_rate=24, bp_systolic=120)
    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_vitals(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            payload=payload,
            current_user_id=uuid.uuid4(),
            db=db,
        )

    assert not any(a.rule_type == "sepsis_score" for a in alerts)


# ── publish_critical_alerts ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_critical_alerts_only_publishes_critical():
    alerts = [
        CdsAlertOut(rule_type="vital_alert", severity="warning", message="HR high"),
        CdsAlertOut(rule_type="vital_alert", severity="critical", message="SpO2 low"),
    ]
    encounter_id = uuid.uuid4()

    with patch("app.services.cds.publish", AsyncMock()) as mock_pub:
        await CdsService.publish_critical_alerts(encounter_id, alerts)
        mock_pub.assert_called_once()
        call_args = mock_pub.call_args[0]
        assert call_args[0] == f"cds:{encounter_id}"
        import json
        data = json.loads(call_args[1])
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_publish_critical_alerts_skips_when_no_critical():
    alerts = [
        CdsAlertOut(rule_type="vital_alert", severity="warning", message="HR high"),
    ]
    with patch("app.services.cds.publish", AsyncMock()) as mock_pub:
        await CdsService.publish_critical_alerts(uuid.uuid4(), alerts)
        mock_pub.assert_not_called()


# ── RR elevated alert ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_elevated_rr_warning():
    db = AsyncMock()
    db.execute.side_effect = await _mock_db_execute_side_effects([], [], [], [])

    payload = VitalCreate(respiratory_rate=22)
    with patch.object(CdsService, "_audit_alerts", AsyncMock()):
        alerts = await CdsService.evaluate_vitals(
            encounter_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            payload=payload,
            current_user_id=uuid.uuid4(),
            db=db,
        )

    rr_alert = next((a for a in alerts if a.rule_key == "RR_HIGH"), None)
    assert rr_alert is not None
    assert rr_alert.severity == "warning"
