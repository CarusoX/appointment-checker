import logging
from datetime import datetime, date

from src.client import SanatorioClient
from src.notifier import TelegramNotifier

logger = logging.getLogger(__name__)


def parse_date(date_str: str) -> date | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(date_str.split(".")[0], "%Y-%m-%dT%H:%M:%S").date()
        except ValueError:
            continue
    return None


def run_check(client: SanatorioClient, notifier: TelegramNotifier | None = None):
    """Main check: get appointments, look for earlier availability, notify if found."""
    client.login()
    client.load_patient_info()

    appointments = client.get_upcoming_appointments()
    logger.info(f"Found {len(appointments)} upcoming appointment(s)")

    if not appointments:
        logger.info("No upcoming appointments to check")
        return []

    findings = []

    for appt in appointments:
        doctor_name = appt["Recurso"]
        doctor_id = appt["IdRecurso"]
        tipo_recurso = appt["IdTipoRecurso"]
        servicio_id = appt["IdServicio"]
        sucursal_id = appt["IdSucursal"]
        appt_date = parse_date(appt["Fecha"])
        appt_time = appt.get("Hora", "")

        if not appt_date or appt_date <= date.today():
            continue

        # Skip equipment-based resources (only doctors can be rescheduled online)
        if tipo_recurso != 1:
            logger.info(f"Skipping equipment resource: {doctor_name}")
            continue

        logger.info(
            f"Checking: {doctor_name} | {appt['Servicio']} | "
            f"{appt_date} {appt_time} @ {appt['Sucursal']}"
        )

        # Find doctor's specialty ID
        professionals = client.search_professional(doctor_name)
        # Match by resource ID and service
        match = next(
            (p for p in professionals
             if p["IdRecurso"] == doctor_id and p["IdServicio"] == servicio_id),
            None,
        )
        if not match:
            # Fallback: first match by resource ID
            match = next((p for p in professionals if p["IdRecurso"] == doctor_id), None)
        if not match:
            logger.warning(f"Could not find professional details for {doctor_name}")
            continue

        especialidad_id = match["IdEspecialidad"]

        # Get prestaciones (e.g., CONSULTA)
        prestaciones = client.get_prestaciones(
            tipo_recurso, doctor_id, especialidad_id, servicio_id, sucursal_id,
        )
        # Filter non-telemedicine prestaciones
        prest_ids = [
            p["Id"] for p in prestaciones
            if not p.get("HabilitadaTelemedicina", False)
        ]
        if not prest_ids:
            prest_ids = [prestaciones[0]["Id"]] if prestaciones else []
        if not prest_ids:
            logger.warning(f"No prestaciones found for {doctor_name}")
            continue

        # Check first available slot
        first = client.get_first_available(
            id_servicio=servicio_id,
            id_sucursal=sucursal_id,
            id_recurso=doctor_id,
            id_especialidad=especialidad_id,
            id_tipo_recurso=tipo_recurso,
            prestacion_ids=prest_ids,
        )

        if not first:
            logger.info(f"  No available slots for {doctor_name}")
            continue

        first_date = parse_date(first["Fecha"])
        first_time = first.get("Hora", "")

        if not first_date:
            continue

        logger.info(f"  First available: {first_date} {first_time}")

        if first_date < appt_date:
            finding = {
                "doctor": doctor_name,
                "service": appt["Servicio"],
                "location": appt["Sucursal"],
                "current_date": appt_date.isoformat(),
                "current_time": appt_time,
                "new_date": first_date.isoformat(),
                "new_time": first_time,
            }
            findings.append(finding)
            logger.info(f"  EARLIER SLOT FOUND!")

            if notifier:
                notifier.send_appointment_found(
                    doctor=doctor_name,
                    current_date=appt_date.strftime("%d/%m/%Y"),
                    new_date=first_date.strftime("%d/%m/%Y"),
                    new_time=first_time,
                )
        else:
            logger.info(f"  No earlier date available (first is {first_date})")

    if not findings:
        logger.info("No earlier appointments found")

    return findings
