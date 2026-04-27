import uuid
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Allergy, CdsRule, Prescription
from app.schemas.schemas import CdsAlertOut, VitalCreate
from app.services.audit import AuditService
from app.db.redis_pubsub import publish


class CdsService:

    @staticmethod
    async def evaluate_prescription(
        encounter_id: uuid.UUID,
        patient_id: uuid.UUID,
        drug_name: str,
        current_user_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[CdsAlertOut]:
        alerts: list[CdsAlertOut] = []

        drug_lower = drug_name.lower()

        # ── Drug-allergy check ────────────────────────────────────────────────
        allergy_result = await db.execute(
            select(Allergy).where(
                Allergy.patient_id == patient_id,
            )
        )
        allergies = allergy_result.scalars().all()

        allergy_rules_result = await db.execute(
            select(CdsRule).where(
                CdsRule.rule_type == "drug_allergy",
                CdsRule.active == True,
            )
        )
        allergy_rules = allergy_rules_result.scalars().all()

        for rule in allergy_rules:
            if rule.rule_key.lower() in drug_lower:
                # Drug name contains this allergen substring — check if patient has it
                for allergy in allergies:
                    if rule.rule_key.lower() in allergy.allergen.lower():
                        alerts.append(CdsAlertOut(
                            rule_type="drug_allergy",
                            severity=rule.severity,
                            message=rule.message,
                            rule_key=rule.rule_key,
                        ))
                        break
            elif any(rule.rule_key.lower() in a.allergen.lower() for a in allergies):
                # Patient has this allergy and it could interact with the drug
                for allergy in allergies:
                    if rule.rule_key.lower() in allergy.allergen.lower():
                        if allergy.allergen.lower() in drug_lower or rule.rule_key.lower() in drug_lower:
                            alerts.append(CdsAlertOut(
                                rule_type="drug_allergy",
                                severity=rule.severity,
                                message=rule.message,
                                rule_key=rule.rule_key,
                            ))
                            break

        # ── Drug-drug interaction check ────────────────────────────────────────
        active_rx_result = await db.execute(
            select(Prescription).where(
                Prescription.patient_id == patient_id,
                Prescription.status == "active",
            )
        )
        active_rxs = active_rx_result.scalars().all()
        active_drug_names = [rx.drug_name.lower() for rx in active_rxs]

        ddi_rules_result = await db.execute(
            select(CdsRule).where(
                CdsRule.rule_type == "drug_drug",
                CdsRule.active == True,
            )
        )
        ddi_rules = ddi_rules_result.scalars().all()

        for rule in ddi_rules:
            parts = rule.rule_key.lower().split("|")
            if len(parts) != 2:
                continue
            drug_a, drug_b = parts[0].strip(), parts[1].strip()

            new_matches_a = drug_a in drug_lower
            new_matches_b = drug_b in drug_lower
            patient_has_a = any(drug_a in d for d in active_drug_names)
            patient_has_b = any(drug_b in d for d in active_drug_names)

            if (new_matches_a and patient_has_b) or (new_matches_b and patient_has_a):
                alerts.append(CdsAlertOut(
                    rule_type="drug_drug",
                    severity=rule.severity,
                    message=rule.message,
                    rule_key=rule.rule_key,
                ))

        await CdsService._audit_alerts(encounter_id, current_user_id, alerts, db)
        return alerts

    @staticmethod
    async def evaluate_vitals(
        encounter_id: uuid.UUID,
        patient_id: uuid.UUID,
        payload: VitalCreate,
        current_user_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[CdsAlertOut]:
        alerts: list[CdsAlertOut] = []

        # ── Vital sign threshold alerts ───────────────────────────────────────
        if payload.heart_rate is not None and payload.heart_rate > 120:
            alerts.append(CdsAlertOut(
                rule_type="vital_alert",
                severity="warning",
                message=f"Tachycardia: HR {payload.heart_rate} bpm (>120)",
                rule_key="HR_HIGH",
            ))

        if payload.bp_systolic is not None and payload.bp_systolic > 180:
            alerts.append(CdsAlertOut(
                rule_type="vital_alert",
                severity="critical",
                message=f"Hypertensive crisis: SBP {payload.bp_systolic} mmHg (>180)",
                rule_key="SBP_CRISIS",
            ))
        elif payload.bp_diastolic is not None and payload.bp_diastolic > 120:
            alerts.append(CdsAlertOut(
                rule_type="vital_alert",
                severity="critical",
                message=f"Hypertensive crisis: DBP {payload.bp_diastolic} mmHg (>120)",
                rule_key="DBP_CRISIS",
            ))

        if payload.spo2 is not None and payload.spo2 < 92:
            alerts.append(CdsAlertOut(
                rule_type="vital_alert",
                severity="critical",
                message=f"Hypoxia: SpO2 {payload.spo2}% (<92%)",
                rule_key="SPO2_LOW",
            ))

        if payload.respiratory_rate is not None and payload.respiratory_rate >= 22:
            alerts.append(CdsAlertOut(
                rule_type="vital_alert",
                severity="warning",
                message=f"Elevated respiratory rate: RR {payload.respiratory_rate} (≥22) — qSOFA component",
                rule_key="RR_HIGH",
            ))

        if payload.temperature_f is not None and payload.temperature_f > 103.0:
            alerts.append(CdsAlertOut(
                rule_type="vital_alert",
                severity="warning",
                message=f"Fever: Temperature {payload.temperature_f}°F (>103°F)",
                rule_key="TEMP_HIGH",
            ))

        # ── qSOFA sepsis score ────────────────────────────────────────────────
        qsofa_score = 0
        if payload.respiratory_rate is not None and payload.respiratory_rate >= 22:
            qsofa_score += 1
        if payload.bp_systolic is not None and payload.bp_systolic <= 100:
            qsofa_score += 1

        if qsofa_score >= 2:
            alerts.append(CdsAlertOut(
                rule_type="sepsis_score",
                severity="critical",
                message=f"qSOFA score ≥ 2 (score={qsofa_score}): possible sepsis — consider immediate evaluation",
                rule_key="qsofa",
            ))

        await CdsService._audit_alerts(encounter_id, current_user_id, alerts, db)
        return alerts

    @staticmethod
    async def _audit_alerts(
        encounter_id: uuid.UUID,
        user_id: uuid.UUID,
        alerts: list[CdsAlertOut],
        db: AsyncSession,
    ) -> None:
        for alert in alerts:
            await AuditService.log(
                db=db,
                action="CDS_ALERT_FIRED",
                user_id=user_id,
                target=str(encounter_id),
                details={
                    "rule_type": alert.rule_type,
                    "severity": alert.severity,
                    "message": alert.message,
                    "rule_key": alert.rule_key,
                    "encounter_id": str(encounter_id),
                },
            )

    @staticmethod
    async def publish_critical_alerts(
        encounter_id: uuid.UUID,
        alerts: list[CdsAlertOut],
    ) -> None:
        critical = [a for a in alerts if a.severity == "critical"]
        if not critical:
            return
        try:
            payload = json.dumps({
                "encounter_id": str(encounter_id),
                "alerts": [a.model_dump() for a in critical],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            await publish(f"cds:{encounter_id}", payload)
        except Exception:
            pass
