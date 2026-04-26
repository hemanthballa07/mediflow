import uuid
from datetime import datetime, date, time
from typing import Any
from typing import Literal
from pydantic import BaseModel, EmailStr


# ── Catalog ───────────────────────────────────────────────────────────────────

class SpecialtyOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str

    model_config = {"from_attributes": True}


class SpecialtyCreate(BaseModel):
    name: str
    code: str


class FacilityOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    address: str | None
    timezone: str
    active: bool

    model_config = {"from_attributes": True}


class FacilityCreate(BaseModel):
    name: str
    code: str
    address: str | None = None
    timezone: str = "America/New_York"


class DepartmentOut(BaseModel):
    id: uuid.UUID
    facility_id: uuid.UUID
    specialty_id: uuid.UUID | None
    name: str
    code: str

    model_config = {"from_attributes": True}


class DepartmentCreate(BaseModel):
    facility_id: uuid.UUID
    specialty_id: uuid.UUID | None = None
    name: str
    code: str


class RoomOut(BaseModel):
    id: uuid.UUID
    facility_id: uuid.UUID
    department_id: uuid.UUID | None
    name: str
    kind: str
    active: bool

    model_config = {"from_attributes": True}


class RoomCreate(BaseModel):
    facility_id: uuid.UUID
    department_id: uuid.UUID | None = None
    name: str
    kind: str  # exam | procedure | imaging | ward


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    service: str
    db: Literal["ok", "error"]
    redis: Literal["ok", "error"]


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Literal["patient", "doctor"] = "patient"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Appointment Types ─────────────────────────────────────────────────────────

class AppointmentTypeCreate(BaseModel):
    department_id: uuid.UUID
    name: str
    duration_min: int = 30
    buffer_min: int = 10
    requires_referral: bool = False
    requires_fasting: bool = False
    color: str | None = None


class AppointmentTypeOut(BaseModel):
    id: uuid.UUID
    department_id: uuid.UUID
    name: str
    duration_min: int
    buffer_min: int
    requires_referral: bool
    requires_fasting: bool
    color: str | None
    active: bool

    model_config = {"from_attributes": True}


# ── Doctor Schedules ──────────────────────────────────────────────────────────

class DoctorScheduleCreate(BaseModel):
    doctor_id: uuid.UUID
    facility_id: uuid.UUID
    day_of_week: int              # 0=Mon … 6=Sun
    start_time: time
    end_time: time
    slot_duration_min: int = 30
    effective_from: date
    effective_to: date | None = None


class DoctorScheduleOut(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    facility_id: uuid.UUID
    day_of_week: int
    start_time: time
    end_time: time
    slot_duration_min: int
    effective_from: date
    effective_to: date | None

    model_config = {"from_attributes": True}


class SlotGenerateRequest(BaseModel):
    doctor_id: uuid.UUID
    from_date: date
    to_date: date


class DoctorTimeOffCreate(BaseModel):
    doctor_id: uuid.UUID
    start_ts: datetime
    end_ts: datetime
    reason: str | None = None


class DoctorTimeOffOut(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    start_ts: datetime
    end_ts: datetime
    reason: str | None

    model_config = {"from_attributes": True}


# ── Slots ─────────────────────────────────────────────────────────────────────

class SlotCreate(BaseModel):
    doctor_id: uuid.UUID
    date: date
    start_time: time
    end_time: time


class DoctorOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    specialty: str
    facility_id: uuid.UUID | None
    department_id: uuid.UUID | None
    specialty_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class SlotOut(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    facility_id: uuid.UUID | None
    department_id: uuid.UUID | None
    date: date
    start_time: time
    end_time: time
    status: str

    model_config = {"from_attributes": True}


# ── Bookings ──────────────────────────────────────────────────────────────────

class BookingCreate(BaseModel):
    slot_id: uuid.UUID
    appointment_type_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    reason_for_visit: str | None = None


class BookingOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    slot_id: uuid.UUID
    appointment_type_id: uuid.UUID | None
    room_id: uuid.UUID | None
    status: str
    reason_for_visit: str | None
    notes: str | None
    checked_in_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BookingStatusUpdate(BaseModel):
    notes: str | None = None


class BookingCancel(BaseModel):
    reason: str | None = None


# ── Lab Reports ───────────────────────────────────────────────────────────────

class ReportCreate(BaseModel):
    patient_id: uuid.UUID
    report_type: str
    data: str | None = None


class ReportOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    report_type: str
    status: str
    data: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportPage(BaseModel):
    items: list[ReportOut]
    next_cursor: uuid.UUID | None = None


# ── Audit ─────────────────────────────────────────────────────────────────────

class AuditLogOut(BaseModel):
    id: int
    ts: datetime
    user_id: uuid.UUID | None
    action: str
    target: str | None
    details: dict[str, Any] | None

    model_config = {"from_attributes": True}


# ── Generic ───────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str


# ── Waitlist ──────────────────────────────────────────────────────────────────

class WaitlistEntryCreate(BaseModel):
    department_id: uuid.UUID
    appointment_type_id: uuid.UUID | None = None
    doctor_id: uuid.UUID | None = None
    notes: str | None = None


class WaitlistEntryOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    department_id: uuid.UUID
    appointment_type_id: uuid.UUID | None
    doctor_id: uuid.UUID | None
    status: str
    priority: int
    notes: str | None
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WaitlistPositionOut(BaseModel):
    entry: WaitlistEntryOut
    position: int


# ── Patient Preferences ───────────────────────────────────────────────────────

class PatientPreferenceOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    preferred_channel: str
    language: str
    reminder_hours_before: list[int]
    email_notifications: bool
    sms_notifications: bool
    push_notifications: bool

    model_config = {"from_attributes": True}


class PatientPreferenceUpdate(BaseModel):
    preferred_channel: str | None = None     # email | sms | push
    language: str | None = None
    reminder_hours_before: list[int] | None = None
    email_notifications: bool | None = None
    sms_notifications: bool | None = None
    push_notifications: bool | None = None


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    channel: str
    type: str
    subject: str | None
    body: str
    recipient: str
    status: str
    attempts: int
    sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Clinical — Encounters ─────────────────────────────────────────────────────

class EncounterCreate(BaseModel):
    booking_id: uuid.UUID | None = None
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    facility_id: uuid.UUID | None = None
    encounter_type: str = "office_visit"
    chief_complaint: str | None = None
    notes: str | None = None
    encounter_date: date


class EncounterOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID | None
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    facility_id: uuid.UUID | None
    encounter_type: str
    status: str
    chief_complaint: str | None
    notes: str | None
    encounter_date: date
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Clinical — Vitals ─────────────────────────────────────────────────────────

class VitalCreate(BaseModel):
    bp_systolic: int | None = None
    bp_diastolic: int | None = None
    heart_rate: int | None = None
    temperature_f: float | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    spo2: float | None = None
    respiratory_rate: int | None = None


class VitalOut(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    bp_systolic: int | None
    bp_diastolic: int | None
    heart_rate: int | None
    temperature_f: float | None
    weight_kg: float | None
    height_cm: float | None
    spo2: float | None
    respiratory_rate: int | None
    recorded_by: uuid.UUID
    recorded_at: datetime

    model_config = {"from_attributes": True}


# ── Clinical — Diagnoses ──────────────────────────────────────────────────────

class DiagnosisCreate(BaseModel):
    icd10_code: str
    description: str
    diagnosis_type: str = "primary"
    onset_date: date | None = None


class DiagnosisOut(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    icd10_code: str
    description: str
    diagnosis_type: str
    onset_date: date | None
    resolved: bool
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Clinical — Prescriptions ──────────────────────────────────────────────────

class PrescriptionCreate(BaseModel):
    drug_name: str
    dose: str
    frequency: str
    route: str | None = None
    start_date: date
    end_date: date | None = None
    refills: int = 0
    notes: str | None = None


class PrescriptionOut(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    drug_name: str
    dose: str
    frequency: str
    route: str | None
    start_date: date
    end_date: date | None
    refills: int
    notes: str | None
    prescriber_id: uuid.UUID
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Clinical — Allergies ──────────────────────────────────────────────────────

class AllergyCreate(BaseModel):
    allergen: str
    reaction: str | None = None
    severity: str = "unknown"
    onset_date: date | None = None


class AllergyOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    allergen: str
    reaction: str | None
    severity: str
    onset_date: date | None
    status: str
    recorded_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Clinical — Problem List ───────────────────────────────────────────────────

class ProblemCreate(BaseModel):
    icd10_code: str | None = None
    description: str
    status: str = "active"
    onset_date: date | None = None


class ProblemOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    icd10_code: str | None
    description: str
    status: str
    onset_date: date | None
    resolved_date: date | None
    noted_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Clinical — Chart (composite read) ────────────────────────────────────────

class EncounterWithDetails(EncounterOut):
    vitals: list[VitalOut] = []
    diagnoses: list[DiagnosisOut] = []
    prescriptions: list[PrescriptionOut] = []


class PatientChartOut(BaseModel):
    patient_id: uuid.UUID
    allergies: list[AllergyOut] = []
    problem_list: list[ProblemOut] = []
    encounters: list[EncounterWithDetails] = []


# ── Referrals ─────────────────────────────────────────────────────────────────

class ReferralCreate(BaseModel):
    patient_id: uuid.UUID
    receiving_department_id: uuid.UUID
    encounter_id: uuid.UUID | None = None
    reason: str
    urgency: Literal["routine", "urgent", "stat"] = "routine"
    notes: str | None = None
    referring_doctor_id: uuid.UUID | None = None  # admin only; doctors auto-resolved


class ReferralOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    referring_doctor_id: uuid.UUID
    receiving_department_id: uuid.UUID
    encounter_id: uuid.UUID | None
    reason: str
    urgency: str
    status: str
    notes: str | None
    referred_at: datetime
    responded_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReferralStatusUpdate(BaseModel):
    status: Literal["accepted", "rejected", "completed"]
    notes: str | None = None


# ── Orders ────────────────────────────────────────────────────────────────────

class OrderCreate(BaseModel):
    encounter_id: uuid.UUID
    order_type: Literal["lab", "imaging", "procedure"]
    cpt_code: str
    description: str
    priority: Literal["routine", "urgent", "stat"] = "routine"
    notes: str | None = None
    ordering_doctor_id: uuid.UUID | None = None  # admin only; doctors auto-resolved


class OrderOut(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    ordering_doctor_id: uuid.UUID
    order_type: str
    cpt_code: str
    description: str
    status: str
    priority: str
    notes: str | None
    ordered_at: datetime
    resulted_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Billing — Insurance Plans ─────────────────────────────────────────────────

class InsurancePlanCreate(BaseModel):
    name: str
    payer_id: str
    plan_type: Literal["HMO", "PPO", "EPO", "POS", "HDHP"]


class InsurancePlanOut(BaseModel):
    id: uuid.UUID
    name: str
    payer_id: str
    plan_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Billing — Patient Insurance ───────────────────────────────────────────────

class PatientInsuranceCreate(BaseModel):
    insurance_plan_id: uuid.UUID
    member_id: str
    group_number: str | None = None
    effective_date: date
    termination_date: date | None = None
    is_primary: bool = True


class PatientInsuranceOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    insurance_plan_id: uuid.UUID
    member_id: str
    group_number: str | None
    effective_date: date
    termination_date: date | None
    is_primary: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Billing — Charge Masters ──────────────────────────────────────────────────

class ChargeMasterCreate(BaseModel):
    cpt_code: str
    description: str
    base_price: float
    department_id: uuid.UUID | None = None
    active: bool = True


class ChargeMasterOut(BaseModel):
    id: uuid.UUID
    cpt_code: str
    description: str
    base_price: float
    department_id: uuid.UUID | None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Billing — Claims ──────────────────────────────────────────────────────────

class ClaimLineItemCreate(BaseModel):
    order_id: uuid.UUID | None = None
    cpt_code: str
    icd10_codes: list[str] = []
    description: str
    units: int = 1
    unit_price: float | None = None


class ClaimLineItemOut(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    order_id: uuid.UUID | None
    cpt_code: str
    icd10_codes: list[str]
    description: str
    units: int
    unit_price: float
    total_price: float
    created_at: datetime

    model_config = {"from_attributes": True}


class ClaimCreate(BaseModel):
    encounter_id: uuid.UUID
    patient_insurance_id: uuid.UUID
    line_items: list[ClaimLineItemCreate]
    ordering_doctor_id: uuid.UUID | None = None


class ClaimOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    patient_insurance_id: uuid.UUID
    ordering_doctor_id: uuid.UUID
    status: str
    total_charged: float
    total_paid: float
    submitted_at: datetime | None
    adjudicated_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ClaimDetailOut(ClaimOut):
    line_items: list[ClaimLineItemOut] = []
    payments: list["PaymentOut"] = []


# ── Billing — Payments ────────────────────────────────────────────────────────

class PaymentCreate(BaseModel):
    payer: Literal["patient", "insurance"]
    amount: float
    payment_method: Literal["check", "eft", "card", "cash"]
    reference_number: str | None = None
    paid_at: datetime


class PaymentOut(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    payer: str
    amount: float
    payment_method: str
    reference_number: str | None
    paid_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
