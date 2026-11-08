#!/usr/bin/env python3
"""Consulta secuencialmente los consumos DATADIS de cups_list.csv mediante la API."""

from __future__ import annotations

import argparse
import configparser
import csv
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RESPONSES_DIR = PROJECT_ROOT / "responses"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config_datadis.ini"
DEFAULT_OUTPUT_NAME = "cups_consultation_results.json"
DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_RECORD_THRESHOLD = 200
REQUEST_TIMEOUT_SECONDS = 220


class ConsultationError(Exception):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class Period:
    start_year: int
    start_month: int
    end_year: int
    end_month: int

    def validate(self) -> None:
        if self.start_year < 1 or self.end_year < 1:
            raise ValueError("El año debe ser mayor que cero.")
        if self.start_month not in range(1, 13) or self.end_month not in range(1, 13):
            raise ValueError("El mes debe estar entre 1 y 12.")
        if (self.start_year, self.start_month) > (self.end_year, self.end_month):
            raise ValueError("El período inicial no puede ser posterior al final.")

    def filename_suffix(self) -> str:
        return (
            f"{self.start_year}_{self.start_month:02d}_"
            f"{self.end_year}_{self.end_month:02d}"
        )

    def reading_register_line(self, cups: str, cif: str) -> str:
        return (
            f"{cups},{cif},8,5,{self.start_year},{self.start_month},"
            f"{self.end_year},{self.end_month}"
        )


def load_api_credentials(config_path: Path) -> tuple[str, str]:
    config = configparser.ConfigParser(interpolation=None)
    try:
        with config_path.open(encoding="utf-8") as config_file:
            config.read_file(config_file)
        username = config["api_auth"]["username"].strip()
        password = config["api_auth"]["password"].strip()
    except (OSError, configparser.Error, KeyError) as error:
        raise ValueError(
            f"No se pudieron cargar las credenciales de API desde {config_path}."
        ) from error
    if not username or not password:
        raise ValueError(
            f"La sección [api_auth] de {config_path} debe incluir usuario y contraseña."
        )
    return username, password


def load_cups(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as source_file:
            reader = csv.DictReader(source_file)
            if not reader.fieldnames or not {"cups", "cif"}.issubset(reader.fieldnames):
                raise ValueError("El CSV debe incluir las columnas 'cups' y 'cif'.")
            entries = []
            seen_cups = set()
            for line_number, row in enumerate(reader, start=2):
                cups = (row.get("cups") or "").strip()
                cif = (row.get("cif") or "").strip()
                if not cups or not cif:
                    raise ValueError(
                        f"El CSV contiene cups o cif vacío en la línea {line_number}."
                    )
                if cups in seen_cups:
                    raise ValueError(f"El CSV contiene el CUPS duplicado {cups}.")
                seen_cups.add(cups)
                entries.append({"cups": cups, "cif": cif})
    except OSError as error:
        raise ValueError(f"No se pudo leer el CSV de CUPS {path}.") from error
    if not entries:
        raise ValueError(f"El CSV de CUPS está vacío: {path}.")
    return entries


def _check_api_response(response: requests.Response, endpoint: str) -> dict[str, Any]:
    if response.status_code == 401:
        raise ConsultationError(
            "authentication", f"La API rechazó la autenticación en {endpoint}."
        )
    if not response.ok:
        raise ConsultationError(
            "http", f"La API devolvió HTTP {response.status_code} en {endpoint}."
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise ConsultationError(
            "api", f"La respuesta de {endpoint} no contiene JSON válido."
        ) from error
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise ConsultationError(
            "api", f"La API indicó un error al ejecutar {endpoint}."
        )
    return payload


def _request_api(
    session: requests.Session,
    api_url: str,
    credentials: tuple[str, str],
    endpoint: str,
) -> dict[str, Any]:
    try:
        response = session.get(
            f"{api_url.rstrip('/')}{endpoint}",
            auth=credentials,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout as error:
        raise ConsultationError(
            "connection", "Tiempo de espera agotado al conectar con la API."
        ) from error
    except requests.exceptions.ConnectionError as error:
        raise ConsultationError(
            "connection", "No se pudo conectar con la API."
        ) from error
    except requests.RequestException as error:
        raise ConsultationError(
            "request", "Falló la petición a la API."
        ) from error
    return _check_api_response(response, endpoint.split("?", 1)[0])


def _response_path(responses_dir: Path, cups: str, period: Period) -> Path:
    return responses_dir / f"{cups}_{period.filename_suffix()}.json"


def _file_signature(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_ino, stat.st_size, stat.st_mtime_ns


def _count_response_records(path: Path) -> int:
    try:
        with path.open(encoding="utf-8") as response_file:
            payload = json.load(response_file)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ConsultationError(
            "result_file",
            f"No se pudo leer el resultado JSON de la consulta ({path.name}).",
        ) from error
    if not isinstance(payload, list):
        raise ConsultationError(
            "result_file",
            f"El resultado de la consulta no es una lista JSON ({path.name}).",
        )
    return len(payload)


def _consult_one(
    entry: dict[str, str],
    period: Period,
    threshold: int,
    responses_dir: Path,
    api_url: str,
    credentials: tuple[str, str],
    session: requests.Session,
) -> dict[str, Any]:
    cups = entry["cups"]
    response_path = _response_path(responses_dir, cups, period)
    previous_signature = _file_signature(response_path)
    reading_line = period.reading_register_line(cups, entry["cif"])
    encoded_line = quote(reading_line, safe="")

    _request_api(
        session,
        api_url,
        credentials,
        f"/reading_register/{encoded_line}",
    )
    _request_api(session, api_url, credentials, "/ejecutar")

    current_signature = _file_signature(response_path)
    if current_signature is None:
        raise ConsultationError(
            "result_file",
            f"La API no generó el archivo esperado {response_path.name}.",
        )
    if previous_signature is not None and current_signature == previous_signature:
        raise ConsultationError(
            "result_file",
            f"El archivo {response_path.name} no se actualizó; no se usarán datos previos.",
        )

    record_count = _count_response_records(response_path)
    return {
        "cups": cups,
        "status": (
            "with_readings" if record_count > threshold else "insufficient_readings"
        ),
        "record_count": record_count,
        "error": None,
    }


def _write_result_exclusive(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as result_file:
            json.dump(result, result_file, ensure_ascii=False, indent=2)
            result_file.write("\n")
        try:
            os.link(temporary_path, path)
        except FileExistsError as error:
            raise FileExistsError(
                f"El fichero de resultado ya existe: {path}"
            ) from error
    finally:
        temporary_path.unlink(missing_ok=True)


def run_batch(
    input_path: Path,
    responses_dir: Path,
    output_path: Path,
    config_path: Path,
    period: Period,
    threshold: int = DEFAULT_RECORD_THRESHOLD,
    api_url: str = DEFAULT_API_URL,
    session: requests.Session | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    if output_path.exists():
        return None, True
    if threshold < 0:
        raise ValueError("El umbral de registros no puede ser negativo.")
    period.validate()
    entries = load_cups(input_path)
    credentials = load_api_credentials(config_path)
    request_session = session or requests.Session()

    results = []
    for entry in entries:
        try:
            result = _consult_one(
                entry,
                period,
                threshold,
                responses_dir,
                api_url,
                credentials,
                request_session,
            )
        except ConsultationError as error:
            result = {
                "cups": entry["cups"],
                "status": "error",
                "record_count": None,
                "error": {"category": error.category, "message": str(error)},
            }
        results.append(result)

    summary = {
        "processed": len(results),
        "with_readings": sum(
            result["status"] == "with_readings" for result in results
        ),
        "insufficient_readings": sum(
            result["status"] == "insufficient_readings" for result in results
        ),
        "errors": sum(result["status"] == "error" for result in results),
    }
    report = {
        "period": {
            "start_year": period.start_year,
            "start_month": period.start_month,
            "end_year": period.end_year,
            "end_month": period.end_month,
        },
        "record_threshold_exclusive": threshold,
        "summary": summary,
        "results": results,
    }
    _write_result_exclusive(output_path, report)
    return report, False


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consulta consumos DATADIS para los CUPS de un CSV usando la API del proyecto."
    )
    parser.add_argument("--responses-dir", type=Path, default=DEFAULT_RESPONSES_DIR)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--start-year", type=int, default=2025)
    parser.add_argument("--start-month", type=int, default=1)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--end-month", type=int, default=12)
    parser.add_argument("--threshold", type=int, default=DEFAULT_RECORD_THRESHOLD)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    responses_dir = args.responses_dir.resolve()
    input_path = (args.input or responses_dir / "cups_list.csv").resolve()
    output_candidate = args.output or Path(DEFAULT_OUTPUT_NAME)
    output_path = (
        output_candidate
        if output_candidate.is_absolute()
        else responses_dir / output_candidate
    ).resolve()

    if output_path.exists():
        print(
            f"El fichero de resultado ya existe: {output_path}. "
            "No se consultó la API."
        )
        return 0

    try:
        report, skipped = run_batch(
            input_path=input_path,
            responses_dir=responses_dir,
            output_path=output_path,
            config_path=args.config.resolve(),
            period=Period(
                args.start_year,
                args.start_month,
                args.end_year,
                args.end_month,
            ),
            threshold=args.threshold,
            api_url=args.api_url,
        )
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if skipped:
        print(f"El fichero de resultado ya existe: {output_path}. No se consultó la API.")
        return 0
    assert report is not None
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(f"Resultado guardado en {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
