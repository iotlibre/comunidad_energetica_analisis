import configparser
import csv
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from typing import Literal, Optional
from consulta_baisca_v30 import procesar_consumos
from consulta_baisca_v30 import generar_y_guardar_reading_register
from perfil_diario_v9 import generate_daily_profile, generate_daily_profile_extended, generate_poruno_profiles_batch, generate_poruno_8760_batch, validar_suma_poruno_8760, corregir_y_combinar_poruno_8760, calcular_reparto_kwh_poruno
from perfil_comunidad_v1 import generar_perfil_comunitario, guardar_perfil_comunitario
from PVGIS_consulta_horaria_v03 import (
    generar_pvgis_horario,
    DEFAULT_OUTPUT_FILENAME,
)
from pvgis_perfiles_medios import calcular_perfiles_medios_por_usuario
from calculo_autoconsumida_v0 import (
    calcular_energia_autoconsumida,
    calcular_proyeccion_autoconsumida_batch,
)
import secrets

app = FastAPI()
API_PROJECT_ROOT = Path(__file__).resolve().parent
DATADIS_PROCESS_LOCK = threading.Lock()

# Configuración de autenticación básica
security = HTTPBasic()

def _load_api_credentials():
    config_path = Path(__file__).with_name("config_datadis.ini")
    config = configparser.ConfigParser(interpolation=None)
    with config_path.open(encoding="utf-8") as config_file:
        config.read_file(config_file)

    try:
        username = config["api_auth"]["username"].strip()
        password = config["api_auth"]["password"].strip()
    except KeyError as error:
        raise RuntimeError(
            f"Falta la configuración de autenticación HTTP Basic en {config_path}."
        ) from error

    if not username or not password:
        raise RuntimeError(
            f"El usuario y la contraseña HTTP Basic deben estar definidos en {config_path}."
        )

    return username, password


USERNAME, PASSWORD = _load_api_credentials()

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    """Verifica las credenciales de usuario."""
    correct_username = secrets.compare_digest(credentials.username, USERNAME)
    correct_password = secrets.compare_digest(credentials.password, PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# Modelo de entrada
class SolicitudPerfilComunidad(BaseModel):
    """Modelo para solicitar el perfil comunitario"""
    directorio: str = "responses"  # directorio por defecto


class SolicitudPerfilPorunoBatch(BaseModel):
    """Modelo para solicitar la generación batch de perfiles poruno."""
    directorio: str = "responses"
    num_users_ce: int


class SolicitudPerfilPoruno8760(BaseModel):
    """Modelo para solicitar la generación de perfiles poruno 8760."""
    directorio: str = "responses"
    year: int = 2027


class SolicitudValidacionSuma(BaseModel):
    """Modelo para validar que la suma de coeficientes poruno sea 1 por hora."""
    directorio: str = "responses"
    year: int = 2027
    num_users_ce: int


class SolicitudCorregirCombinar(BaseModel):
    """Modelo para corregir último usuario y combinar todos en un fichero."""
    directorio: str = "responses"
    year: int = 2027


class SolicitudCupsListReparto(BaseModel):
    """Modelo para calcular reparto kWh y generar cups_list_reparto.csv."""
    directorio: str = "responses"
    year: int = 2026
    pvgis_file: Optional[str] = Field(
        default="pvgis_indextime_spain.txt",
        description=(
            "Fichero PVGIS relativo a directorio. Por defecto "
            "pvgis_indextime_spain.txt."
        ),
    )


class SolicitudConsultaPvgis(BaseModel):
    """Modelo para solicitar una consulta PVGIS y generar el perfil horario."""
    lat: float = 43.38
    lon: float = -2.58
    startyear: int = 2023
    endyear: int = 2023
    peakpower: float = 100
    angle: float = 21
    azimuth: float = 0
    loss: float = 14
    directorio: str = "responses"


class SolicitudPerfilesMediosPvgis(BaseModel):
    """Modelo para calcular perfiles estacionales medios por usuario."""
    num_usuarios: int = Field(gt=0, strict=True)
    year: int = Field(default=2023, ge=1, le=9999)
    directorio: str = "responses"


class SolicitudCalculoAutoconsumida(BaseModel):
    """Modelo para calcular energía de autoconsumo por usuario y mes."""
    directorio: str = "responses"
    mes_inicio: int
    anio_inicio: int
    mes_fin: int
    anio_fin: int


class SolicitudConsultarConsumosPorGrupos(BaseModel):
    """Configuración para consultar secuencialmente los CUPS de un grupo."""

    output_file: str = "cups_consultation_results.json"
    distributor: int = Field(default=8, ge=0)
    point_type: int = Field(default=5, ge=0, alias="CodepointType")
    ano_de_inicio: int = Field(default=2025, ge=1)
    mes_inicio: int = Field(default=1, ge=1, le=12)
    ano_final: int = Field(default=2025, ge=1)
    mes_final: int = Field(default=12, ge=1, le=12)
    threshold: int = Field(default=200, ge=0)


class SolicitudProyeccionAutoconsumida(BaseModel):
    """Modelo para calcular en lote proyecciones de autoconsumo."""
    directorio: str = Field(
        default="responses",
        description="Directorio con JSON de consumo y los ficheros de coeficientes."
    )
    metodo_coeficientes: Literal["poruno", "fijo"] = Field(
        default="poruno",
        description=(
            "Método de coeficientes: 'poruno' conserva los ficheros horarios "
            "existentes; 'fijo' usa cups_list_coeficientes.csv."
        ),
    )
    pvgis_file: Optional[str] = Field(
        default="pvgis_indextime_spain.txt",
        description=(
            "Fichero PVGIS compartido, relativo a directorio. Por defecto "
            "pvgis_indextime_spain.txt."
        )
    )
    output_file: Optional[str] = Field(
        default="trasposición_calculo_autoconsumida.json",
        description=(
            "Nombre o ruta relativa del JSON de salida dentro de directorio. "
            "Por defecto trasposición_calculo_autoconsumida.json."
        )
    )


@app.get("/reading_register/{linea}", summary="Configurar la consulta a DATADIS")
def generar_reading_register(linea: str, username: str = Depends(authenticate)):
    """
    Ejemplo del formato: ES0021000009999999VV,14444448L,8,5,2025,1,2025,12
    """
    try:
        with DATADIS_PROCESS_LOCK:
            return generar_y_guardar_reading_register(linea)

    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/ejecutar", summary="Consultar a DATADIS")
def ejecutar_script(username: str = Depends(authenticate)):
    try:
        with DATADIS_PROCESS_LOCK:
            procesar_consumos()
        return {
            "status": "ok",
            "message": "Procesamiento de consumos completado exitosamente"
        }

    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _resolve_group_consultation_paths(
    solicitud: SolicitudConsultarConsumosPorGrupos,
) -> tuple[Path, Path, Path]:
    project_root = API_PROJECT_ROOT
    responses_dir = project_root / "responses"

    output_name = Path(solicitud.output_file)
    if output_name.name != solicitud.output_file or output_name.name in {"", ".", ".."}:
        raise HTTPException(
            status_code=400,
            detail="output_file debe ser un nombre de archivo, no una ruta.",
        )
    return (
        responses_dir,
        responses_dir / "cups_list.csv",
        responses_dir / output_name.name,
    )


def _load_group_cups(cups_list_path: Path) -> list[dict[str, str]]:
    try:
        with cups_list_path.open(encoding="utf-8-sig", newline="") as cups_file:
            reader = csv.DictReader(cups_file)
            if reader.fieldnames != ["cups", "cif"]:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "cups_list.csv debe contener las columnas cups,cif "
                        "y en ese orden."
                    ),
                )
            entries = []
            seen_cups = set()
            for line_number, row in enumerate(reader, start=2):
                cups = (row.get("cups") or "").strip()
                cif = (row.get("cif") or "").strip()
                if not cups or not cif:
                    raise HTTPException(
                        status_code=400,
                        detail=f"cups_list.csv contiene campos vacíos en línea {line_number}.",
                    )
                if cups in seen_cups:
                    raise HTTPException(
                        status_code=400,
                        detail=f"cups_list.csv contiene el CUPS duplicado {cups}.",
                    )
                seen_cups.add(cups)
                entries.append({"cups": cups, "cif": cif})
    except OSError as error:
        raise HTTPException(
            status_code=400, detail="No se pudo leer responses/cups_list.csv."
        ) from error
    if not entries:
        raise HTTPException(
            status_code=400, detail="responses/cups_list.csv no contiene CUPS."
        )
    return entries


def _group_result_path(
    responses_dir: Path,
    cups: str,
    ano_de_inicio: int,
    mes_inicio: int,
    ano_final: int,
    mes_final: int,
) -> Path:
    return responses_dir / (
        f"{cups}_{ano_de_inicio}_{mes_inicio:02d}_{ano_final}_{mes_final:02d}.json"
    )


def _group_file_signature(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_ino, stat.st_size, stat.st_mtime_ns


def _count_group_result(path: Path) -> int:
    try:
        with path.open(encoding="utf-8") as result_file:
            result = json.load(result_file)
    except json.JSONDecodeError as error:
        if "consulta ya realizada en las últimas 24 horas" in error.doc.casefold():
            raise ValueError(
                "DATADIS indica que esta consulta ya se realizó en las últimas "
                "24 horas; no hay un resultado JSON de lecturas disponible."
            ) from error
        raise ValueError(
            f"El archivo {path.name} no contiene un JSON válido."
        ) from error
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"No se pudo leer el JSON de respuesta {path.name}.") from error
    if not isinstance(result, list):
        raise ValueError(f"El JSON de respuesta {path.name} no contiene una lista.")
    return len(result)


def _save_group_report_exclusive(path: Path, report: dict) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as report_file:
            json.dump(report, report_file, ensure_ascii=False, indent=2)
            report_file.write("\n")
        try:
            os.link(temporary_path, path)
        except FileExistsError as error:
            raise HTTPException(
                status_code=409,
                detail="El fichero de resultado ya existe; no se ha sobrescrito.",
            ) from error
    finally:
        temporary_path.unlink(missing_ok=True)


def _stream_group_consultation_locked(
    solicitud: SolicitudConsultarConsumosPorGrupos,
    responses_dir: Path,
    output_path: Path,
    entries: list[dict[str, str]],
):
    if output_path.exists():
        yield json.dumps(
            {
                "event": "already_exists",
                "message": "El fichero de resultado ya existe; no se consultó DATADIS.",
                "output_file": output_path.name,
            },
            ensure_ascii=False,
        ) + "\n"
        return

    results = []
    total = len(entries)
    for index, entry in enumerate(entries, start=1):
        cups = entry["cups"]
        yield json.dumps(
            {
                "event": "progress",
                "state": "processing",
                "processed": index - 1,
                "total": total,
                "cups": cups,
            },
            ensure_ascii=False,
        ) + "\n"

        result_path = _group_result_path(
            responses_dir,
            cups,
            solicitud.ano_de_inicio,
            solicitud.mes_inicio,
            solicitud.ano_final,
            solicitud.mes_final,
        )
        if result_path.exists():
            result_entry = {
                "cups": cups,
                "status": "skipped_existing",
                "record_count": None,
                "error": None,
                "message": (
                    f"Ya existe {result_path.name}; no se consultó DATADIS "
                    "ni se modificó el archivo."
                ),
            }
            results.append(result_entry)
            yield json.dumps(
                {
                    "event": "progress",
                    "state": "completed",
                    "processed": index,
                    "total": total,
                    "cups": cups,
                    "status": result_entry["status"],
                    "record_count": None,
                },
                ensure_ascii=False,
            ) + "\n"
            continue

        previous_signature = _group_file_signature(result_path)
        phase = "reading_register"
        try:
            reading_line = (
                f"{cups},{entry['cif']},{solicitud.distributor},"
                f"{solicitud.point_type},{solicitud.ano_de_inicio},"
                f"{solicitud.mes_inicio},{solicitud.ano_final},"
                f"{solicitud.mes_final}"
            )
            register_result = generar_y_guardar_reading_register(reading_line)
            if not isinstance(register_result, dict) or register_result.get("status") != "ok":
                raise ValueError("No se pudo configurar el registro de lectura.")
            phase = "datadis_execution"
            procesar_consumos()
            phase = "result_file"
            current_signature = _group_file_signature(result_path)
            if current_signature is None:
                raise ValueError(f"No se generó el archivo esperado {result_path.name}.")
            if (
                previous_signature is not None
                and previous_signature == current_signature
            ):
                raise ValueError(
                    f"El archivo {result_path.name} no se actualizó; se descartan datos previos."
                )
            record_count = _count_group_result(result_path)
            status = (
                "with_readings"
                if record_count > solicitud.threshold
                else "insufficient_readings"
            )
            result_entry = {
                "cups": cups,
                "status": status,
                "record_count": record_count,
                "error": None,
            }
        except Exception as error:
            result_entry = {
                "cups": cups,
                "status": "error",
                "record_count": None,
                "error": {
                    "category": phase,
                    "message": (
                        str(error)
                        if isinstance(error, (ValueError, OSError))
                        else "La consulta o ejecución de DATADIS ha fallado."
                    ),
                },
            }
        results.append(result_entry)
        yield json.dumps(
            {
                "event": "progress",
                "state": "completed",
                "processed": index,
                "total": total,
                "cups": cups,
                "status": result_entry["status"],
                "record_count": result_entry["record_count"],
            },
            ensure_ascii=False,
        ) + "\n"

    report = {
        "period": {
            "start_year": solicitud.ano_de_inicio,
            "start_month": solicitud.mes_inicio,
            "end_year": solicitud.ano_final,
            "end_month": solicitud.mes_final,
        },
        "record_threshold_exclusive": solicitud.threshold,
        "summary": {
            "processed": len(results),
            "with_readings": sum(
                item["status"] == "with_readings" for item in results
            ),
            "insufficient_readings": sum(
                item["status"] == "insufficient_readings" for item in results
            ),
            "errors": sum(item["status"] == "error" for item in results),
            "skipped_existing": sum(
                item["status"] == "skipped_existing" for item in results
            ),
        },
        "results": results,
    }
    _save_group_report_exclusive(output_path, report)
    yield json.dumps(
        {
            "event": "summary",
            **report,
            "output_file": str(output_path),
        },
        ensure_ascii=False,
    ) + "\n"


def _stream_group_consultation(
    solicitud: SolicitudConsultarConsumosPorGrupos,
    responses_dir: Path,
    output_path: Path,
    entries: list[dict[str, str]],
):
    with DATADIS_PROCESS_LOCK:
        yield from _stream_group_consultation_locked(
            solicitud,
            responses_dir,
            output_path,
            entries,
        )


@app.post(
    "/consultar_consumos_por_grupos",
    summary="Consultar consumos DATADIS para los CUPS de un grupo",
    description=(
        "Consulta secuencialmente los CUPS de `responses/cups_list.csv`. "
        "Devuelve eventos NDJSON de progreso y un resumen final. Si el fichero "
        "de informe ya existe, termina sin ejecutar consultas. Si ya existe el "
        "JSON individual de un CUPS para el período solicitado, lo omite sin "
        "consultar DATADIS ni modificar ese archivo."
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Flujo NDJSON con eventos de progreso y resumen.",
            "content": {
                "application/x-ndjson": {
                    "schema": {"type": "string"},
                    "example": (
                        '{"event":"progress","state":"processing","processed":0,'
                        '"total":2,"cups":"ES..."}\\n'
                        '{"event":"summary","summary":{"processed":2,'
                        '"with_readings":1,"insufficient_readings":0,"errors":1}}\\n'
                    ),
                }
            },
        },
        400: {"description": "CSV, directorio o parámetros no válidos."},
        401: {"description": "Credenciales HTTP Basic no válidas."},
        409: {"description": "El fichero de resultado ya existe."},
    },
)
def consultar_consumos_por_grupos(
    solicitud: SolicitudConsultarConsumosPorGrupos,
    username: str = Depends(authenticate),
):
    if (solicitud.ano_de_inicio, solicitud.mes_inicio) > (
        solicitud.ano_final,
        solicitud.mes_final,
    ):
        raise HTTPException(
            status_code=422,
            detail="El período inicial no puede ser posterior al período final.",
        )
    responses_dir, cups_list_path, output_path = _resolve_group_consultation_paths(
        solicitud
    )
    if output_path.exists():
        return StreamingResponse(
            _stream_group_consultation(
                solicitud, responses_dir, output_path, []
            ),
            media_type="application/x-ndjson",
        )
    entries = _load_group_cups(cups_list_path)
    return StreamingResponse(
        _stream_group_consultation(
            solicitud, responses_dir, output_path, entries
        ),
        media_type="application/x-ndjson",
    )


@app.post("/ejecutar/calculo_autoconsumida", summary="Calcular energía de autoconsumo por usuario y mes")
def calculo_autoconsumida_endpoint(solicitud: SolicitudCalculoAutoconsumida, username: str = Depends(authenticate)):
    """
    Calcula la energía de autoconsumo (consumption, surplus, generation, selfConsumption) 
    por usuario y mes dentro del rango de fechas especificado.

    Parámetros:
        directorio (str): Directorio con los archivos JSON de datos energéticos. Default: "responses"
        mes_inicio (int): Mes de inicio (1-12)
        anio_inicio (int): Año de inicio
        mes_fin (int): Mes de fin (1-12)
        anio_fin (int): Año de fin
    """
    try:
        resultado = calcular_energia_autoconsumida(
            solicitud.directorio,
            solicitud.mes_inicio,
            solicitud.anio_inicio,
            solicitud.mes_fin,
            solicitud.anio_fin
        )
        
        if resultado["status"] == "error":
            raise HTTPException(status_code=400, detail=resultado["message"])
        
        return resultado

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/generate_daily_profile", summary="Generar el perfil diario de un CUPS")
def generate_profile_endpoint(file_path: str, username: str = Depends(authenticate)):
    """
    Incluir el fichero con el perfil
    Ejemplo: ES0021000004444444ZZ_2025_01_2025_12.json
    """
    try:
        # Call the function to generate the daily profile
        result = generate_daily_profile(file_path)
        return {
            "status": "ok",
            "message": "Daily profile generated successfully.",
            "weekday_file": result["weekday_file"],
            "weekend_file": result["weekend_file"]
        }

    except FileNotFoundError as e:
        return {"status": "error", "detail": str(e)}

    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get(
    "/generate_daily_profile_extended",
    summary="Generar el perfil diario ampliado de un CUPS",
)
def generate_extended_profile_endpoint(
    file_path: str, username: str = Depends(authenticate)
):
    try:
        result = generate_daily_profile_extended(file_path)
        return {
            "status": "ok",
            "message": "Extended daily profile generated successfully.",
            "output_file": result["output_file"],
        }
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


def _load_daily_profile_batch_cups(cups_list_path: Path) -> list[str]:
    try:
        with cups_list_path.open(encoding="utf-8-sig", newline="") as source_file:
            reader = csv.DictReader(source_file)
            if not reader.fieldnames or "cups" not in reader.fieldnames:
                raise HTTPException(
                    status_code=400,
                    detail="responses/cups_list.csv debe incluir la columna 'cups'.",
                )
            cups_list = []
            seen_cups = set()
            for line_number, row in enumerate(reader, start=2):
                cups = (row.get("cups") or "").strip()
                if not cups:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "responses/cups_list.csv contiene un CUPS vacío "
                            f"en la línea {line_number}."
                        ),
                    )
                if cups in seen_cups:
                    raise HTTPException(
                        status_code=400,
                        detail=f"responses/cups_list.csv contiene el CUPS duplicado {cups}.",
                    )
                seen_cups.add(cups)
                cups_list.append(cups)
    except OSError as error:
        raise HTTPException(
            status_code=400,
            detail="No se pudo leer responses/cups_list.csv.",
        ) from error

    if not cups_list:
        raise HTTPException(
            status_code=400,
            detail="responses/cups_list.csv no contiene CUPS.",
        )
    return cups_list


def _daily_profile_input_candidates(
    responses_dir: Path,
    cups: str,
) -> list[Path]:
    filename_pattern = re.compile(
        rf"^{re.escape(cups)}_\d{{4}}_(?:0?[1-9]|1[0-2])_"
        rf"\d{{4}}_(?:0?[1-9]|1[0-2])\.json$"
    )
    return sorted(
        path
        for path in responses_dir.iterdir()
        if path.is_file() and filename_pattern.fullmatch(path.name)
    )


@app.post(
    "/generate_daily_profile_batch",
    summary="Generar perfiles diarios en lote",
    description=(
        "Lee los CUPS de `responses/cups_list.csv` y genera secuencialmente "
        "los perfiles weekday/weekend en CSV para los archivos de consumo "
        "disponibles. El período se obtiene del nombre de cada archivo."
    ),
    responses={
        200: {"description": "Resumen y resultado individual por CUPS."},
        400: {"description": "CSV o archivos de entrada ambiguos/no válidos."},
        401: {"description": "Credenciales HTTP Basic no válidas."},
    },
)
def generate_daily_profile_batch_endpoint(
    username: str = Depends(authenticate),
):
    responses_dir = API_PROJECT_ROOT / "responses"
    if not responses_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail="No existe el directorio responses/.",
        )
    cups_list = _load_daily_profile_batch_cups(responses_dir / "cups_list.csv")

    selections = {}
    output_owners = {}
    for cups in cups_list:
        candidates = _daily_profile_input_candidates(responses_dir, cups)
        if len(candidates) > 1:
            selections[cups] = {
                "status": "error",
                "error": (
                    "Hay varios archivos de entrada para el CUPS; no se puede "
                    "determinar cuál procesar: "
                    + ", ".join(path.name for path in candidates)
                ),
            }
        elif not candidates:
            selections[cups] = {"status": "missing_input"}
        else:
            output_names = (
                f"{cups[-5:]}_weekday_profile.csv",
                f"{cups[-5:]}_weekend_profile.csv",
            )
            selections[cups] = {
                "status": "pending",
                "path": candidates[0],
                "output_names": output_names,
            }
            for output_name in output_names:
                output_owners.setdefault(output_name, []).append(cups)

    for output_name, owners in output_owners.items():
        if len(owners) > 1:
            for cups in owners:
                selections[cups] = {
                    "status": "error",
                    "error": (
                        f"El archivo de salida {output_name} colisiona entre "
                        f"los CUPS: {', '.join(owners)}."
                    ),
                }

    for cups, selection in selections.items():
        if selection["status"] != "pending":
            continue
        existing_outputs = [
            name
            for name in selection["output_names"]
            if (responses_dir / name).exists()
        ]
        if existing_outputs:
            selection.update(
                status="error",
                error=(
                    "No se sobrescribieron perfiles existentes: "
                    + ", ".join(existing_outputs)
                ),
            )

    results = []
    for cups in cups_list:
        selection = selections[cups]
        if selection["status"] == "missing_input":
            results.append(
                {
                    "cups": cups,
                    "status": "missing_input",
                    "input_file": None,
                    "weekday_file": None,
                    "weekend_file": None,
                    "error": None,
                }
            )
            continue
        if selection["status"] == "error":
            results.append(
                {
                    "cups": cups,
                    "status": "error",
                    "input_file": selection.get("path").name
                    if selection.get("path")
                    else None,
                    "weekday_file": None,
                    "weekend_file": None,
                    "error": selection["error"],
                }
            )
            continue

        input_path = selection["path"]
        try:
            generated = generate_daily_profile(
                input_path.name,
                responses_dir=responses_dir,
                overwrite=False,
            )
            results.append(
                {
                    "cups": cups,
                    "status": "generated",
                    "input_file": input_path.name,
                    "weekday_file": generated["weekday_file"],
                    "weekend_file": generated["weekend_file"],
                    "error": None,
                }
            )
        except Exception as error:
            results.append(
                {
                    "cups": cups,
                    "status": "error",
                    "input_file": input_path.name,
                    "weekday_file": None,
                    "weekend_file": None,
                    "error": str(error),
                }
            )

    return {
        "summary": {
            "total": len(cups_list),
            "generated": sum(item["status"] == "generated" for item in results),
            "missing_input": sum(
                item["status"] == "missing_input" for item in results
            ),
            "errors": sum(item["status"] == "error" for item in results),
        },
        "results": results,
    }


@app.post(
    "/generate_daily_profile_extended_batch",
    summary="Generar en lote perfiles diarios ampliados",
    description=(
        "Lee los CUPS de `responses/cups_list.csv` y procesa secuencialmente "
        "el archivo de consumo disponible para cada CUPS, utilizando el período "
        "indicado en el propio nombre de archivo. No requiere cuerpo de petición."
    ),
    responses={
        200: {"description": "Resumen y resultado individual por CUPS."},
        400: {"description": "CSV o archivos de entrada ambiguos/no válidos."},
        401: {"description": "Credenciales HTTP Basic no válidas."},
    },
)
def generate_extended_profile_batch_endpoint(
    username: str = Depends(authenticate),
):
    responses_dir = API_PROJECT_ROOT / "responses"
    if not responses_dir.is_dir():
        raise HTTPException(
            status_code=400,
            detail="No existe el directorio responses/.",
        )
    cups_list = _load_daily_profile_batch_cups(responses_dir / "cups_list.csv")

    input_paths = {}
    output_owners = {}
    for cups in cups_list:
        candidates = _daily_profile_input_candidates(
            responses_dir,
            cups,
        )
        if len(candidates) > 1:
            input_paths[cups] = {
                "status": "error",
                "error": (
                    "Hay varios archivos de entrada para el CUPS; no se puede "
                    "determinar cuál procesar: "
                    + ", ".join(path.name for path in candidates)
                ),
            }
        elif not candidates:
            input_paths[cups] = {"status": "missing_input"}
        else:
            input_paths[cups] = {"status": "pending", "path": candidates[0]}
            output_name = f"{cups[-5:]}_day_profile_extended.json"
            output_owners.setdefault(output_name, []).append(cups)

    for output_name, owners in output_owners.items():
        if len(owners) > 1:
            for cups in owners:
                input_paths[cups] = {
                    "status": "error",
                    "error": (
                        f"El nombre de salida {output_name} colisiona entre "
                        f"los CUPS: {', '.join(owners)}."
                    ),
                }

    results = []
    for cups in cups_list:
        selection = input_paths[cups]
        if selection["status"] == "missing_input":
            results.append(
                {
                    "cups": cups,
                    "status": "missing_input",
                    "input_file": None,
                    "output_file": None,
                    "error": None,
                }
            )
            continue
        if selection["status"] == "error":
            results.append(
                {
                    "cups": cups,
                    "status": "error",
                    "input_file": None,
                    "output_file": None,
                    "error": selection["error"],
                }
            )
            continue

        input_path = selection["path"]
        try:
            generated = generate_daily_profile_extended(
                input_path.name,
                responses_dir=responses_dir,
            )
            results.append(
                {
                    "cups": cups,
                    "status": "generated",
                    "input_file": input_path.name,
                    "output_file": generated["output_file"],
                    "error": None,
                }
            )
        except Exception as error:
            results.append(
                {
                    "cups": cups,
                    "status": "error",
                    "input_file": input_path.name,
                    "output_file": None,
                    "error": str(error),
                }
            )

    return {
        "summary": {
            "total": len(cups_list),
            "generated": sum(item["status"] == "generated" for item in results),
            "missing_input": sum(
                item["status"] == "missing_input" for item in results
            ),
            "errors": sum(item["status"] == "error" for item in results),
        },
        "results": results,
    }


@app.post("/perfiles/comunidad", summary="Generar el perfil medio")
def guardar_perfil_comunitario_endpoint(solicitud: SolicitudPerfilComunidad, username: str = Depends(authenticate)):
    """
    Trabaja con todos los ficheros del directorio cuyo nombre cumpla con el formato 
    XXXXX_weekend_profile.csv  XXXXX_weekday_profile.csv
    Genera un perfil comunitario (laborables y fines de semana por separado) 
    
    Parámetros:
        directorio (str): Ruta del directorio con los perfiles. Default: "responses"
    """
    try:
        resultado = generar_perfil_comunitario(solicitud.directorio)
        
        if resultado["status"] == "error":
            raise HTTPException(
                status_code=400,
                detail=resultado["resumen"]
            )
        
        archivos_guardados = {}
        # Guardar cada perfil que exista en el mismo directorio de origen
        if resultado.get("perfil_comunitario_weekday"):
            archivos_guardados["weekday"] = guardar_perfil_comunitario(
                resultado["perfil_comunitario_weekday"],
                "perfil_comunitario_weekday.csv",
                solicitud.directorio
            )
        if resultado.get("perfil_comunitario_weekend"):
            archivos_guardados["weekend"] = guardar_perfil_comunitario(
                resultado["perfil_comunitario_weekend"],
                "perfil_comunitario_weekend.csv",
                solicitud.directorio
            )
        
        response = {
            "status": "ok",
            "archivos_procesados": resultado["archivos_procesados"],
            "archivos_procesados_weekday": resultado.get("archivos_procesados_weekday", 0),
            "archivos_procesados_weekend": resultado.get("archivos_procesados_weekend", 0),
            "archivos_guardados": archivos_guardados,
            "mensaje": "Perfiles guardados correctamente",
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:  
        raise HTTPException(
            status_code=500,
            detail=f"Error: {str(e)}"
        )


@app.post("/perfiles/poruno_batch", summary="Generar el tanto x 1")
def generar_poruno_batch(solicitud: SolicitudPerfilPorunoBatch, username: str = Depends(authenticate)):
    try:
        resultado = generate_poruno_profiles_batch(solicitud.directorio, solicitud.num_users_ce)
        return resultado

    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/perfiles/poruno_8760", summary="Extender a 8760 el tanto x 1")
def generar_poruno_8760_batch_endpoint(solicitud: SolicitudPerfilPoruno8760, username: str = Depends(authenticate)):
    """
    Es necesario el fichero cups_list.csv en el directorio de trabajo
    Contiene los CUPS con el código completo
    """
    try:
        resultado = generate_poruno_8760_batch(solicitud.directorio, solicitud.year)
        return resultado

    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/validar/suma_poruno", summary="Validar suma coeficientes poruno = 1")
def validar_suma_poruno_endpoint(solicitud: SolicitudValidacionSuma, username: str = Depends(authenticate)):
    """
    Valida que para cada hora del año, la suma de coeficientes poruno de todos los usuarios sea 1.
    Genera un archivo con las diferencias entre 1 y la suma real para cada hora.

    Parámetros:
        directorio (str): Ruta del directorio con los archivos *_8760_poruno_{year}.txt. Default: "responses"
        year (int): Año de referencia. Default: 2027
        num_users_ce (int): Número total de usuarios de la comunidad energética.
    """
    try:
        resultado = validar_suma_poruno_8760(
            solicitud.directorio, solicitud.year, solicitud.num_users_ce
        )
        return resultado

    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/corregir/suma_poruno_y_combinar", summary="Corregir último usuario y combinar todos")
def corregir_y_combinar_poruno_endpoint(solicitud: SolicitudCorregirCombinar, username: str = Depends(authenticate)):
    """
    Corrige los coeficientes del último usuario para que la suma de todos los usuarios sea exactamente 1 por hora.
    Genera un fichero combinado con todos los usuarios y modifica el archivo del último usuario.

    Parámetros:
        directorio (str): Ruta del directorio con los archivos *_8760_poruno_{year}.txt. Default: "responses"
        year (int): Año de referencia. Default: 2027
    
    Validación:
        - Si el ajuste necesario para cualquier hora no está en rango [-0.0001, 0.0001], devuelve error sin modificar.
    """
    try:
        resultado = corregir_y_combinar_poruno_8760(solicitud.directorio, solicitud.year)
        
        if resultado["status"] == "error":
            raise HTTPException(status_code=400, detail=resultado.get("message", "Error en corrección"))
        
        return resultado

    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/pvgis/consulta_horaria", summary="Consultar PVGIS y generar perfil horario")
def pvgis_consulta_horaria(solicitud: SolicitudConsultaPvgis, username: str = Depends(authenticate)):
    """Consulta PVGIS y genera el perfil horario ajustado a horario de España en formato JSON."""
    try:
        parametros = {
            "lat": solicitud.lat,
            "lon": solicitud.lon,
            "startyear": solicitud.startyear,
            "endyear": solicitud.endyear,
            "peakpower": solicitud.peakpower,
            "angle": solicitud.angle,
            "azimuth": solicitud.azimuth,
            "loss": solicitud.loss,
        }

        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), solicitud.directorio)
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, DEFAULT_OUTPUT_FILENAME)

        resultado = generar_pvgis_horario(parametros, output_path=output_path)
        return resultado

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/pvgis/consulta_horaria/perfiles_medios",
    summary="Calcular perfiles medios de generación por usuario",
)
def pvgis_perfiles_medios_por_usuario(
    solicitud: SolicitudPerfilesMediosPvgis,
    username: str = Depends(authenticate),
):
    """Devuelve perfiles horarios medios de verano e invierno por usuario."""
    input_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        solicitud.directorio,
        DEFAULT_OUTPUT_FILENAME,
    )
    try:
        return calcular_perfiles_medios_por_usuario(
            input_path,
            solicitud.num_usuarios,
            solicitud.year,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.post("/reparto/cups_list", summary="Calcular kWh asignado y porcentaje del total para cada usuario")
def calcular_cups_list_reparto_endpoint(solicitud: SolicitudCupsListReparto, username: str = Depends(authenticate)):
    """Genera cups_list_reparto.csv con kWh asignados y porcentaje de la energía PVGIS disponible."""
    try:
        resultado = calcular_reparto_kwh_poruno(
            solicitud.directorio,
            solicitud.year,
            solicitud.pvgis_file,
        )
        return resultado

    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/reparto/proyeccion_autoconsumida",
    summary="Calcular proyecciones de autoconsumo por directorio",
    description=(
        "Calcula balances horarios para los JSON de consumo del directorio, "
        "usando el fichero PVGIS compartido y el método de coeficientes seleccionado. "
        "El parámetro metodo_coeficientes admite 'poruno' para usar los coeficientes "
        "horarios de los ficheros PORUNO, o 'fijo' para usar el coeficiente constante "
        "definido para cada CUPS en cups_list_coeficientes.csv. El método 'fijo' no "
        "requiere ficheros PORUNO."
    ),
)
def proyeccion_autoconsumida_endpoint(solicitud: SolicitudProyeccionAutoconsumida, username: str = Depends(authenticate)):
    """Calcula proyecciones de autoconsumo para todos los usuarios del directorio."""
    try:
        return calcular_proyeccion_autoconsumida_batch(
            solicitud.directorio,
            pvgis_file=solicitud.pvgis_file,
            output_file=solicitud.output_file,
            metodo_coeficientes=solicitud.metodo_coeficientes,
        )
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
