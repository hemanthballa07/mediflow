"""
Unit tests for HL7 v2 parser and ADT handlers.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.hl7 import parse_message, build_ack, _field


# ── Parser ────────────────────────────────────────────────────────────────────

_SAMPLE_A01 = (
    "MSH|^~\\&|HOSP_SYS|HOSP|MEDIFLOW|MEDIFLOW|20240315120000||ADT^A01|MSG001|P|2.5\r"
    "EVN|A01|20240315120000\r"
    "PID|1||PT12345^^^MRN||DOE^JOHN||19800415|M|||123 MAIN ST^^SPRINGFIELD^IL^62701||||(217)555-1234\r"
    "PV1|1|I|MED1^101^A|||||||||||||||1234567\r"
)

_SAMPLE_A08 = (
    "MSH|^~\\&|HOSP_SYS|HOSP|MEDIFLOW|MEDIFLOW|20240315130000||ADT^A08|MSG002|P|2.5\r"
    "EVN|A08|20240315130000\r"
    "PID|1||PT12345^^^MRN||SMITH^JANE||19800415|F|||456 OAK AVE^^CHICAGO^IL^60601\r"
)


def test_parse_msh_segment():
    parsed = parse_message(_SAMPLE_A01)
    assert "MSH" in parsed
    assert "PID" in parsed


def test_parse_message_type():
    parsed = parse_message(_SAMPLE_A01)
    msg_type = _field(parsed, "MSH", 9, 0)
    assert msg_type == "ADT"


def test_parse_pid_patient_id():
    parsed = parse_message(_SAMPLE_A01)
    pid3 = _field(parsed, "PID", 3)
    assert pid3 == "PT12345"


def test_parse_pid_name_family():
    parsed = parse_message(_SAMPLE_A01)
    family = _field(parsed, "PID", 5, 0)
    assert family == "DOE"


def test_parse_pid_name_given():
    parsed = parse_message(_SAMPLE_A01)
    given = _field(parsed, "PID", 5, 1)
    assert given == "JOHN"


def test_parse_pid_dob():
    parsed = parse_message(_SAMPLE_A01)
    dob = _field(parsed, "PID", 7)
    assert dob == "19800415"


def test_parse_newline_separator():
    raw = _SAMPLE_A01.replace("\r", "\n")
    parsed = parse_message(raw)
    assert "MSH" in parsed
    assert "PID" in parsed


def test_field_missing_returns_empty():
    parsed = parse_message(_SAMPLE_A01)
    result = _field(parsed, "ZZZ", 1)
    assert result == ""


def test_field_out_of_range_returns_empty():
    parsed = parse_message(_SAMPLE_A01)
    result = _field(parsed, "MSH", 99)
    assert result == ""


# ── ACK builder ───────────────────────────────────────────────────────────────

def test_build_ack_aa():
    parsed = parse_message(_SAMPLE_A01)
    ack = build_ack(parsed, "AA")
    assert "MSH" in ack
    assert "MSA|AA" in ack
    assert "MSG001" in ack


def test_build_ack_ae_with_error():
    parsed = parse_message(_SAMPLE_A01)
    ack = build_ack(parsed, "AE", "Unknown message type")
    assert "MSA|AE" in ack
    assert "Unknown message type" in ack


def test_build_ack_control_id_echoed():
    parsed = parse_message(_SAMPLE_A01)
    ack = build_ack(parsed, "AA")
    assert "MSG001" in ack


def test_build_ack_empty_parsed():
    ack = build_ack({}, "AE", "Parse error")
    assert "MSA|AE" in ack


# ── ADT handlers ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_a01_creates_user():
    from app.services.hl7 import handle_a01
    from app.models.models import User

    parsed = parse_message(_SAMPLE_A01)

    db = AsyncMock()
    mock_select_result = MagicMock()
    mock_select_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_select_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    with patch("app.services.hl7.encrypt_value", return_value="enc_email"), \
         patch("app.services.hl7.hmac_email", return_value="hashed_email"):
        await handle_a01(parsed, db)

    assert db.add.call_count >= 2
    calls = [c[0][0] for c in db.add.call_args_list]
    user_added = any(isinstance(c, User) for c in calls)
    assert user_added


@pytest.mark.asyncio
async def test_handle_a01_updates_existing_user():
    from app.services.hl7 import handle_a01
    from app.models.models import User, AuditLog

    parsed = parse_message(_SAMPLE_A01)

    existing_user = MagicMock(spec=User)
    existing_user.id = uuid.uuid4()
    existing_user.name = "Old Name"

    db = AsyncMock()
    mock_select_result = MagicMock()
    mock_select_result.scalar_one_or_none.return_value = existing_user
    db.execute = AsyncMock(return_value=mock_select_result)
    db.add = MagicMock()
    db.flush = AsyncMock()

    with patch("app.services.hl7.encrypt_value", return_value="enc_email"), \
         patch("app.services.hl7.hmac_email", return_value="hashed_email"):
        await handle_a01(parsed, db)

    assert existing_user.name == "JOHN DOE"


@pytest.mark.asyncio
async def test_handle_a08_updates_demographics():
    from app.services.hl7 import handle_a08
    from app.models.models import User, AuditLog

    parsed = parse_message(_SAMPLE_A08)

    existing_user = MagicMock(spec=User)
    existing_user.id = uuid.uuid4()
    existing_user.name = "Old Name"

    db = AsyncMock()
    mock_select_result = MagicMock()
    mock_select_result.scalar_one_or_none.return_value = existing_user
    db.execute = AsyncMock(return_value=mock_select_result)
    db.add = MagicMock()
    db.flush = AsyncMock()

    with patch("app.services.hl7.hmac_email", return_value="hashed_email"):
        await handle_a08(parsed, db)

    assert existing_user.name == "JANE SMITH"


@pytest.mark.asyncio
async def test_handle_a08_noop_when_user_not_found():
    from app.services.hl7 import handle_a08

    parsed = parse_message(_SAMPLE_A08)

    db = AsyncMock()
    mock_select_result = MagicMock()
    mock_select_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_select_result)
    db.add = MagicMock()

    with patch("app.services.hl7.hmac_email", return_value="hashed_email"):
        await handle_a08(parsed, db)

    db.add.assert_not_called()
