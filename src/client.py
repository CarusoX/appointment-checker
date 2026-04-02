import base64
import logging
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://miportal.sanatorioallende.com/backend"
API_URL = f"{BASE_URL}/api/"
TOKEN_URL = f"{BASE_URL}/Token"
SISTEMA = base64.b64encode(b"app-portal-paciente").decode()

class SanatorioClient:
    def __init__(self, dni: str, password: str):
        self.dni = dni
        self.password = password
        self.session = requests.Session()
        self.token = None
        self.patient_id = None
        self.patient_age = None
        self.patient_sex = None
        self.financiador_id = None
        self.plan_id = None

    def _b64(self, text: str) -> str:
        return base64.b64encode(text.encode()).decode()

    def login(self) -> dict:
        payload = {
            "IdTipoDocumento": 1,
            "NumeroDocumento": self._b64(self.dni),
            "Password": self._b64(self.password),
            "Sistema": SISTEMA,
            "Grant_type": "password",
            "Id": 0,
            "ChangePassword": False,
            "IsAnonymous": False,
            "SolicitarReCaptcha": False,
        }
        resp = self.session.post(
            TOKEN_URL,
            json=payload,
            headers={
                "Authorization": "Bearer",
                "Content-Type": "application/json",
            },
        )

        try:
            data = resp.json()
        except Exception:
            data = {"_raw": resp.text[:1000]}

        if not resp.ok:
            raise Exception(f"Login failed (HTTP {resp.status_code}): {data}")

        self.token = data.get("access_token") or data.get("Access_token")
        if not self.token:
            raise Exception(f"Login response missing token: {data}")

        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        logger.info("Logged in successfully")
        return data

    def _get(self, endpoint: str) -> dict | list:
        resp = self.session.get(f"{API_URL}{endpoint}")
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, json=None) -> dict | list:
        resp = self.session.post(f"{API_URL}{endpoint}", json=json)
        resp.raise_for_status()
        return resp.json()

    def load_patient_info(self):
        """Load patient ID, age, sex, and coverage info."""
        info = self._get("Usuario/GetInfoSeguridadCurrentUser/")
        paciente = info["Paciente"]
        self.patient_id = paciente["Id"]
        self.patient_age = paciente["Edad"]
        sexo = paciente.get("Sexo", "")
        self.patient_sex = sexo[0].upper() if sexo else "M"
        logger.info(f"Patient: {paciente['NombrePaciente']} (ID {self.patient_id})")

        coverages = self._get(f"Cobertura/ObtenerPorIdPaciente/{self.patient_id}")
        active = [c for c in coverages if c.get("Activa") and c.get("VisiblePortalWeb")]
        if active:
            cov = active[0]
            self.financiador_id = cov["IdMutual"]
            self.plan_id = cov["IdPlanMutual"]
            logger.info(f"Coverage: {cov.get('MutualNombre', cov.get('NombreCorto', '?'))} (plan {self.plan_id})")
        else:
            raise Exception("No active coverage found")

    def get_upcoming_appointments(self) -> list[dict]:
        """Fetch future assigned appointments."""
        now = datetime.now()
        future = now + timedelta(days=90)
        payload = {
            "CurrentPage": 1,
            "FechaDesde": now.strftime("%-m/%-d/%Y %H:%M"),
            "FechaHasta": future.strftime("%-m/%-d/%Y %H:%M"),
            "IdServicio": 0,
            "PageSize": 50,
            "UsePagination": False,
            "IdPaciente": self.patient_id,
        }
        data = self._post("turnos/ObtenerTurnosParaPortalPorFiltro", json=payload)
        rows = data.get("Rows", [])
        # Only keep assigned (IdEstado=1) appointments
        return [r for r in rows if r.get("IdEstado") == 1]

    def get_prestaciones(self, id_tipo_recurso: int, id_recurso: int,
                         id_especialidad: int, id_servicio: int, id_sucursal: int) -> list[dict]:
        """Get available prestaciones for a doctor in a service/location."""
        endpoint = (
            f"PrestacionMedica/ObtenerPorRecursoEspecialidadServicioSucursalParaPortalWeb"
            f"/{id_tipo_recurso}/{id_recurso}/{id_especialidad}/{id_servicio}/{id_sucursal}"
        )
        return self._get(endpoint)

    def search_professional(self, name: str) -> list[dict]:
        """Search for a professional by name to get their specialty/service IDs."""
        data = self._post(
            "TurnosBuscadorGenerico/ObtenerEspecialidadServicioProfesionalPorCriterio",
            json={"Criterio": name},
        )
        return data.get("Profesionales", [])

    def get_first_available(self, id_servicio: int, id_sucursal: int,
                            id_recurso: int, id_especialidad: int,
                            id_tipo_recurso: int, prestacion_ids: list[int]) -> dict | None:
        """Get the first assignable appointment slot for a doctor."""
        payload = {
            "IdPaciente": self.patient_id,
            "IdServicio": id_servicio,
            "IdSucursal": id_sucursal,
            "IdRecurso": id_recurso,
            "IdEspecialidad": id_especialidad,
            "ControlarEdad": True,
            "EdadPaciente": self.patient_age,
            "SexoPaciente": self.patient_sex,
            "IdFinanciador": self.financiador_id,
            "IdTipoRecurso": id_tipo_recurso,
            "IdPlan": self.plan_id,
            "Prestaciones": [
                {"IdPrestacion": pid, "IdItemSolicitudEstudios": 0}
                for pid in prestacion_ids
            ],
            "IdSistemaCliente": 2,
            "IdTipoBusqueda": 1,
        }
        resp = self.session.post(
            f"{API_URL}DisponibilidadDeTurnos/ObtenerPrimerTurnoAsignableParaPortalWebConParticular",
            json=payload,
        )
        logger.debug(f"  Availability response ({resp.status_code}): {resp.text[:1000]}")
        resp.raise_for_status()
        data = resp.json()
        slots = data.get("PrimerosTurnosDeCadaRecurso", [])
        if not slots:
            msgs = data.get("MensajesValidacion", [])
            if msgs:
                logger.info(f"  Validation messages: {msgs}")
        return slots[0] if slots else None

    def get_available_slots(self, id_servicio: int, id_sucursal: int,
                            id_recurso: int, id_especialidad: int,
                            id_tipo_recurso: int, prestacion_ids: list[int],
                            first_available: dict, fecha_hasta: str) -> list[dict]:
        """Get all available slots from the first available date up to fecha_hasta.

        Args:
            first_available: Slot dict returned by get_first_available().
            fecha_hasta: End date in MM-DD-YYYY format.

        Returns:
            Sorted list of {'date': 'YYYY-MM-DD', 'times': ['HH:MM', ...]}.
        """
        # Derive FechaDesde from first_available's Fecha
        fecha_raw = first_available["Fecha"]  # e.g. "2026-04-06T00:00:00-03:00"
        date_part = fecha_raw.split("T")[0]   # "2026-04-06"
        y, m, d = date_part.split("-")
        fecha_desde = f"{m}-{d}-{y}"

        # Top-level dates use no leading zeros (M-D-YYYY)
        fecha_desde_short = f"{int(m)}-{int(d)}-{y}"
        fecha_hasta_parts = fecha_hasta.split("-")
        fecha_hasta_short = f"{int(fecha_hasta_parts[0])}-{int(fecha_hasta_parts[1])}-{fecha_hasta_parts[2]}"

        payload = {
            "CriterioBusquedaDto": {
                "IdPaciente": self.patient_id,
                "IdServicio": id_servicio,
                "IdSucursal": id_sucursal,
                "IdRecurso": id_recurso,
                "IdEspecialidad": id_especialidad,
                "ControlarEdad": True,
                "EdadPaciente": self.patient_age,
                "SexoPaciente": self.patient_sex,
                "IdTipoDeTurno": first_available.get("IdTipoTurnoRecomendado", 2),
                "IdFinanciador": self.financiador_id,
                "IdTipoRecurso": id_tipo_recurso,
                "IdPlan": self.plan_id,
                "Prestaciones": [
                    {"IdPrestacion": pid, "IdItemSolicitudEstudios": 0}
                    for pid in prestacion_ids
                ],
                "IdSistemaCliente": 2,
                "IdTipoBusqueda": 1,
                "FechaDesde": fecha_desde,
                "FechaHasta": fecha_hasta,
            },
            "PrimerosAsignablesDto": {
                "PrimerosTurnosDeCadaRecurso": [first_available],
                "MensajesValidacion": [],
            },
            "FechaDesde": fecha_desde_short,
            "FechaHasta": fecha_hasta_short,
        }
        resp = self.session.post(
            f"{API_URL}DisponibilidadDeTurnos/ObtenerTurnosDisponiblesParaPortalConParticular",
            json=payload,
        )
        logger.debug(f"  All slots response ({resp.status_code}): {resp.text[:2000]}")
        resp.raise_for_status()
        data = resp.json()

        by_date = {}
        for resource in data:
            for day in resource.get("SituacionesPorDia", []):
                slots = day.get("TurnosAsignables", [])
                if not slots:
                    continue
                fecha = day["Fecha"].split("T")[0]
                times = by_date.setdefault(fecha, set())
                for s in slots:
                    times.add(s["Hora"])

        return sorted(
            [{"date": d, "times": sorted(t)} for d, t in by_date.items()],
            key=lambda d: d["date"],
        )
