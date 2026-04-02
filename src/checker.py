import logging
from datetime import datetime, date

from src.client import SanatorioClient
from src.notifier import TelegramNotifier
from src.storage import Storage

logger = logging.getLogger(__name__)


def parse_date(date_str: str) -> date | None:
    if not date_str:
        return None
    # Strip fractional seconds and timezone offset to get clean datetime
    clean = date_str.split(".")[0].split("+")[0]
    # Handle negative UTC offsets like -03:00
    # "2026-04-09T00:00:00-03:00" → find the T, then strip any -HH:MM after seconds
    t_idx = clean.find("T")
    if t_idx != -1:
        time_part = clean[t_idx + 1:]
        # If there's a - after the time (HH:MM:SS), it's a timezone
        parts = time_part.split("-")
        if len(parts) > 1:
            clean = clean[:t_idx + 1] + parts[0]
    try:
        return datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(clean, "%Y-%m-%d").date()
    except ValueError:
        return None


def run_check(client: SanatorioClient, notifier: TelegramNotifier | None = None,
              storage: Storage | None = None):
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
        appt_id = appt["Id"]
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
        logger.debug(f"  Search results for {doctor_name}: {professionals}")
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
        logger.debug(f"  Matched: especialidad={especialidad_id}, servicio={servicio_id}, sucursal={sucursal_id}")

        # Get prestaciones (e.g., CONSULTA)
        prestaciones = client.get_prestaciones(
            tipo_recurso, doctor_id, especialidad_id, servicio_id, sucursal_id,
        )
        logger.debug(f"  Prestaciones: {prestaciones}")

        # Match prestacion from the appointment
        appt_prestacion = appt.get("PrestacionesConcatenadas", "").strip().upper()
        matched_prest = [
            p["Id"] for p in prestaciones
            if p["Nombre"].strip().upper() == appt_prestacion
            and not p.get("HabilitadaTelemedicina", False)
        ]

        if matched_prest:
            prest_combos = [matched_prest]
            logger.debug(f"  Matched prestacion '{appt_prestacion}' -> {matched_prest}")
        else:
            # Fallback: try each non-telemedicine prestacion individually
            non_tele = [
                p["Id"] for p in prestaciones
                if not p.get("HabilitadaTelemedicina", False)
            ]
            if not non_tele:
                non_tele = [prestaciones[0]["Id"]] if prestaciones else []
            if not non_tele:
                logger.warning(f"No prestaciones found for {doctor_name}")
                continue
            prest_combos = [[pid] for pid in non_tele]
            logger.debug(f"  No exact prestacion match for '{appt_prestacion}', trying each: {prest_combos}")

        # Find first available slot
        first = None
        successful_combo = None
        for combo in prest_combos:
            logger.debug(f"  Trying availability: recurso={doctor_id}, especialidad={especialidad_id}, "
                         f"servicio={servicio_id}, sucursal={sucursal_id}, prestaciones={combo}")
            first = client.get_first_available(
                id_servicio=servicio_id,
                id_sucursal=sucursal_id,
                id_recurso=doctor_id,
                id_especialidad=especialidad_id,
                id_tipo_recurso=tipo_recurso,
                prestacion_ids=combo,
            )
            if first:
                successful_combo = combo
                break

        if not first:
            logger.info(f"  No available slots for {doctor_name}")
            continue

        first_date = parse_date(first["Fecha"])
        if not first_date:
            continue

        logger.info(f"  First available: {first_date}")

        if first_date >= appt_date:
            logger.info(f"  No earlier date available (first is {first_date})")
            continue

        # Fetch ALL available slots up to the appointment date
        fecha_hasta = appt_date.strftime("%m-%d-%Y")
        all_slots = client.get_available_slots(
            id_servicio=servicio_id,
            id_sucursal=sucursal_id,
            id_recurso=doctor_id,
            id_especialidad=especialidad_id,
            id_tipo_recurso=tipo_recurso,
            prestacion_ids=successful_combo,
            first_available=first,
            fecha_hasta=fecha_hasta,
        )

        # Keep only dates strictly before the appointment
        earlier = [s for s in all_slots if date.fromisoformat(s["date"]) < appt_date]

        # Filter out dismissed dates
        dismissed_dates = set()
        if storage and notifier:
            dismissed_dates = storage.get_dismissed_dates(notifier.chat_id, appt_id)
            if dismissed_dates:
                logger.info(f"  Dismissed dates: {dismissed_dates}")

        available = [s for s in earlier if s["date"] not in dismissed_dates]

        if not available:
            logger.info(f"  All earlier dates dismissed or none found")
            continue

        logger.info(f"  EARLIER SLOTS FOUND: {len(available)} day(s)")
        for day in available:
            logger.info(f"    {day['date']}: {', '.join(day['times'])}")

        finding = {
            "doctor": doctor_name,
            "service": appt["Servicio"],
            "location": appt["Sucursal"],
            "current_date": appt_date.isoformat(),
            "current_time": appt_time,
            "available_days": available,
        }
        findings.append(finding)

        if notifier:
            notifier.send_available_slots(
                doctor=doctor_name,
                service=appt["Servicio"],
                location=appt["Sucursal"],
                current_date=appt_date,
                current_time=appt_time,
                available_days=available,
                appointment_id=appt_id,
                patient_name=client.patient_name,
            )

    if not findings:
        logger.info("No earlier appointments found")

    return findings
