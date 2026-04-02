"""
Discovery script — run this first to understand what the API returns.

Usage:
    cp .env.example .env   # fill in your DNI and password
    pip install -r requirements.txt
    python discover.py
"""

import json
import logging
import os
import sys

from dotenv import load_dotenv

from src.client import SanatorioClient

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def try_endpoint(client: SanatorioClient, method: str, endpoint: str, payload=None) -> dict | None:
    try:
        if method == "GET":
            resp = client.get(endpoint)
        else:
            resp = client.post(endpoint, json=payload or {})

        status = resp.status_code
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:500]

        return {"status": status, "body": body}
    except Exception as e:
        return {"status": "error", "body": str(e)}


def main():
    dni = os.getenv("DNI")
    password = os.getenv("PASSWORD")

    if not dni or not password:
        print("Set DNI and PASSWORD in .env first")
        sys.exit(1)

    client = SanatorioClient(dni, password)

    print("=" * 60)
    print("STEP 1: Login")
    print("=" * 60)
    try:
        login_data = client.login()
        print(f"Login OK. Keys: {list(login_data.keys())}")
        # Print non-sensitive fields
        for k, v in login_data.items():
            if "token" not in k.lower() and "password" not in k.lower():
                print(f"  {k}: {v}")
    except Exception as e:
        print(f"Login FAILED: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("STEP 2: Patient info")
    print("=" * 60)
    patient_endpoints = [
        ("GET", "Paciente/ObtenerParaPortalWeb"),
        ("POST", "Paciente/ObtenerPorFiltro", {}),
        ("GET", "Paciente/ObtenerTodos"),
        ("GET", "Usuario/GetInfoSeguridadCurrentUser/"),
    ]
    for args in patient_endpoints:
        method, endpoint = args[0], args[1]
        payload = args[2] if len(args) > 2 else None
        result = try_endpoint(client, method, endpoint, payload)
        print(f"\n  {method} {endpoint} -> {result['status']}")
        if result["status"] == 200:
            print(f"  Response: {json.dumps(result['body'], indent=2, ensure_ascii=False)[:2000]}")

    print("\n" + "=" * 60)
    print("STEP 3: Current appointments")
    print("=" * 60)
    appointment_endpoints = [
        ("POST", "TurnosBuscadorGenerico/ObtenerParaPortalWeb", {}),
        ("POST", "TurnosBuscadorGenerico/ObtenerPorFiltro", {}),
        ("GET", "TurnosBuscadorGenerico/ObtenerTodos"),
        ("POST", "Turnos/ConfirmacionDeTurnos/ObtenerParaPortalWeb", {}),
        ("POST", "Turnos/ConfirmacionDeTurnos/ObtenerPorFiltro", {}),
        ("POST", "Turnos/ConfirmacionDeTurnos/ComunicacionPorConfirmacionDeTurno/ObtenerParaPortalWeb", {}),
        ("POST", "Turnos/ReprogramacionDeTurnos/ObtenerParaPortalWeb", {}),
        ("POST", "PrestacionMedica/ObtenerParaPortalWeb", {}),
        ("POST", "PrestacionMedica/ObtenerPorFiltro", {}),
    ]
    for args in appointment_endpoints:
        method, endpoint = args[0], args[1]
        payload = args[2] if len(args) > 2 else None
        result = try_endpoint(client, method, endpoint, payload)
        print(f"\n  {method} {endpoint} -> {result['status']}")
        if result["status"] == 200:
            body_str = json.dumps(result["body"], indent=2, ensure_ascii=False)
            print(f"  Response: {body_str[:3000]}")
            if len(body_str) > 3000:
                print(f"  ... (truncated, total {len(body_str)} chars)")

    print("\n" + "=" * 60)
    print("STEP 4: Availability endpoints")
    print("=" * 60)
    availability_endpoints = [
        ("POST", "DisponibilidadDeTurnos/ObtenerCalendarioDisponibilidadGeneral", {}),
        ("POST", "DisponibilidadDeTurnos/ObtenerPorFiltro", {}),
        ("POST", "DisponibilidadDeTurnos/ObtenerTurnosDisponiblesConReglasExplicadas", {}),
        ("GET", "DisponibilidadDeTurnos/ObtenerTodos"),
        ("GET", "DisponibilidadDeTurnos/ObtenerNuevo"),
        ("POST", "DuracionDeTurnos/ObtenerPorFiltro", {}),
        ("POST", "PlantillasDeTurnos/ObtenerPorFiltro", {}),
        ("POST", "EstadosDeTurnos/ObtenerPorFiltro", {}),
    ]
    for args in availability_endpoints:
        method, endpoint = args[0], args[1]
        payload = args[2] if len(args) > 2 else None
        result = try_endpoint(client, method, endpoint, payload)
        print(f"\n  {method} {endpoint} -> {result['status']}")
        if result["status"] == 200:
            body_str = json.dumps(result["body"], indent=2, ensure_ascii=False)
            print(f"  Response: {body_str[:3000]}")
            if len(body_str) > 3000:
                print(f"  ... (truncated, total {len(body_str)} chars)")

    print("\n" + "=" * 60)
    print("STEP 5: Waiting/queue endpoints")
    print("=" * 60)
    other_endpoints = [
        ("GET", "EstadoEmpadronamiento/ObtenerParaPortalWeb"),
        ("POST", "EstadoEmpadronamiento/ObtenerPorFiltro", {}),
    ]
    for args in other_endpoints:
        method, endpoint = args[0], args[1]
        payload = args[2] if len(args) > 2 else None
        result = try_endpoint(client, method, endpoint, payload)
        print(f"\n  {method} {endpoint} -> {result['status']}")
        if result["status"] == 200:
            body_str = json.dumps(result["body"], indent=2, ensure_ascii=False)
            print(f"  Response: {body_str[:2000]}")

    print("\n" + "=" * 60)
    print("DONE. Share the output above so we can refine the checker.")
    print("=" * 60)


if __name__ == "__main__":
    main()
