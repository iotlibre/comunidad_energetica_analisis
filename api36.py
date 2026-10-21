import configparser
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from typing import Optional
from consulta_baisca_v30 import procesar_consumos
from consulta_baisca_v30 import generar_y_guardar_reading_register
from perfil_diario_v9 import generate_daily_profile, generate_daily_profile_extended, generate_poruno_profiles_batch, generate_poruno_8760_batch, validar_suma_poruno_8760, corregir_y_combinar_poruno_8760, calcular_reparto_kwh_poruno
from perfil_comunidad_v1 import generar_perfil_comunitario, guardar_perfil_comunitario
from PVGIS_consulta_horaria_v03 import (
    generar_pvgis_horario,
    DEFAULT_OUTPUT_FILENAME,
)
from pvgis_perfiles_medios import calcular_perfiles_medios_por_usuario
from calculo_autoconsumida_v0 import calcular_energia_autoconsumida, calcular_proyeccion_autoconsumida
import secrets

app = FastAPI()

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


class SolicitudCorregirCombinar(BaseModel):
    """Modelo para corregir último usuario y combinar todos en un fichero."""
    directorio: str = "responses"
    year: int = 2027


class SolicitudCupsListReparto(BaseModel):
    """Modelo para calcular reparto kWh y generar cups_list_reparto.csv."""
    directorio: str = "responses"
    year: int = 2026


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


class SolicitudProyeccionAutoconsumida(BaseModel):
    """Modelo para calcular la proyección de autoconsumo a partir de un JSON de consumo."""
    archivo_json: str = Field(
        default="responses/ES0031300697756015XX0F_2026_01_2026_12.json",
        description="Ruta completa al JSON de consumo a procesar."
    )
    pvgis_file: Optional[str] = Field(
        default="responses/pvgis_indextime_spain.txt",
        description="Ruta al fichero PVGIS horario."
    )
    coef_file: Optional[str] = Field(
        default="responses/ES0031300697756015XX0F_8760_poruno_2026.txt",
        description=(
            "Ruta al fichero de coeficientes poruno del CUPS, o un valor numérico expresado como string "
            "(por ejemplo '0.0232') para aplicar un coeficiente constante a todas las horas."
        )
    )
    historial_file: Optional[str] = Field(
        default="responses/resultados_calculo_autoconsumida.json",
        description="Ruta opcional del historial JSON donde se registrará el resultado."
    )


@app.get("/reading_register/{linea}", summary="Configurar la consulta a DATADIS")
def generar_reading_register(linea: str, username: str = Depends(authenticate)):
    """
    Ejemplo del formato: ES0021000009999999VV,14444448L,8,5,2025,1,2025,12
    """
    try:
        resultado = generar_y_guardar_reading_register(linea)
        return resultado

    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/ejecutar", summary="Consultar a DATADIS")
def ejecutar_script(username: str = Depends(authenticate)):
    try:
        procesar_consumos()
        return {
            "status": "ok",
            "message": "Procesamiento de consumos completado exitosamente"
        }

    except Exception as e:
        return {"status": "error", "detail": str(e)}


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
    """
    try:
        resultado = validar_suma_poruno_8760(solicitud.directorio, solicitud.year)
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
        resultado = calcular_reparto_kwh_poruno(solicitud.directorio, solicitud.year)
        return resultado

    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/reparto/proyeccion_autoconsumida",
    summary="Calcular proyección de autoconsumo hora a hora",
    description=(
        "Calcula la proyección de autoconsumo a partir de un fichero JSON de consumo. "
        "El parámetro coef_file puede ser una ruta a un fichero de coeficientes o un valor numérico "
        "(por ejemplo '0.0232') que se aplicará como coeficiente constante para todas las horas."
    ),
)
def proyeccion_autoconsumida_endpoint(solicitud: SolicitudProyeccionAutoconsumida, username: str = Depends(authenticate)):
    """Calcula la proyección de autoconsumo a partir de un fichero JSON de consumo."""
    try:
        resultado = calcular_proyeccion_autoconsumida(
            solicitud.archivo_json,
            pvgis_file=solicitud.pvgis_file,
            coef_file=solicitud.coef_file,
            historial_file=solicitud.historial_file,
        )
        if resultado.get("status") == "error":
            raise HTTPException(status_code=400, detail=resultado.get("message", "Error en el cálculo"))
        return resultado

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
