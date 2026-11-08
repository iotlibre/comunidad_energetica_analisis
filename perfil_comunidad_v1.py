"""
Módulo para gestión y procesamiento de perfiles de consumo comunitarios.
Maneja lectura, filtrado y agregación de perfiles de viviendas.
"""

from pathlib import Path
from typing import List, Dict, Tuple
import pandas as pd


def obtener_perfiles_validos(directorio: str) -> List[Path]:
    """
    Obtiene todos los archivos CSV que coincidan con el patrón *_profile.csv
    en el directorio especificado.
    
    Args:
        directorio (str): Ruta del directorio donde buscar los perfiles
        
    Returns:
        List[Path]: Lista de rutas de archivos válidos
        
    Raises:
        FileNotFoundError: Si el directorio no existe
        ValueError: Si no hay archivos que coincidan el patrón
    """
    ruta = Path(directorio)
    
    if not ruta.exists():
        raise FileNotFoundError(f"Directorio no encontrado: {ruta}")
    
    if not ruta.is_dir():
        raise ValueError(f"La ruta no es un directorio: {ruta}")
    
    # Busca todos los archivos que terminen en _profile.csv
    archivos = sorted(list(ruta.glob("*_profile.csv")))
    
    if not archivos:
        raise ValueError(f"No se encontraron archivos *_profile.csv en {ruta}")
    
    return archivos


def leer_perfil(ruta_archivo: Path) -> Tuple[pd.DataFrame, str]:
    """
    Lee un archivo CSV de perfil de consumo.
    
    Args:
        ruta_archivo (Path): Ruta del archivo CSV
        
    Returns:
        Tuple[pd.DataFrame, str]: DataFrame del perfil y nombre del archivo
        
    Raises:
        Exception: Si hay error al leer el archivo
    """
    try:
        df = pd.read_csv(ruta_archivo)
        return df, ruta_archivo.name
    except Exception as e:
        raise Exception(f"Error leyendo {ruta_archivo.name}: {str(e)}")


def generar_perfil_comunitario(directorio: str) -> Dict:
    """
    Procesa un directorio de perfiles y genera perfiles comunitarios por separado
    para días laborables y fines de semana.
    
    Args:
        directorio (str): Ruta del directorio con los perfiles
        
    Returns:
        Dict: Información del procesamiento y los perfiles resultantes
        
    Estructura del retorno (campos adicionales para cada categoría):
        {
            "status": "ok|error",
            "archivos_procesados": int,
            "archivos_procesados_weekday": int,
            "archivos_procesados_weekend": int,
            "archivos_fallidos": list,
            "archivos": list,
            "archivos_weekday": list,
            "archivos_weekend": list,
            "perfil_comunitario_weekday": dict,  # DataFrame como dict
            "perfil_comunitario_weekend": dict,  # DataFrame como dict
            "resumen": str
        }
    """
    resultado = {
        "status": "error",
        "archivos_procesados": 0,
        "archivos_procesados_weekday": 0,
        "archivos_procesados_weekend": 0,
        "archivos_fallidos": [],
        "archivos": [],
        "archivos_weekday": [],
        "archivos_weekend": [],
        "perfil_comunitario_weekday": {},
        "perfil_comunitario_weekend": {},
        "resumen": ""
    }
    
    try:
        # Paso 1: Obtener archivos válidos
        archivos = obtener_perfiles_validos(directorio)
        
        # Paso 2: Clasificar y procesar cada archivo
        weekday_dfs = []
        weekend_dfs = []
        
        for archivo in archivos:
            try:
                df, nombre = leer_perfil(archivo)
                resultado["archivos"].append(nombre)

                lower = nombre.lower()
                if "weekday" in lower:
                    weekday_dfs.append(df)
                    resultado["archivos_weekday"].append(nombre)
                elif "weekend" in lower:
                    weekend_dfs.append(df)
                    resultado["archivos_weekend"].append(nombre)
                else:
                    # Si no se especifica, lo tratamos como día laborable
                    weekday_dfs.append(df)
                    resultado["archivos_weekday"].append(nombre)
            except Exception as e:
                resultado["archivos_fallidos"].append({
                    "archivo": archivo.name,
                    "error": str(e)
                })
        
        # Control de que haya al menos un perfil en alguna categoría
        if not weekday_dfs and not weekend_dfs:
            resultado["status"] = "error"
            resultado["resumen"] = "No se pudo procesar ningún archivo válido"
            return resultado
        
        # Paso 3: Calcular medias separadas por categoría
        if weekday_dfs:
            dfw = pd.concat(weekday_dfs, ignore_index=True)
            perfil_weekday = dfw.groupby("month").mean()
            resultado["perfil_comunitario_weekday"] = perfil_weekday.to_dict()
            resultado["archivos_procesados_weekday"] = len(resultado["archivos_weekday"])
        if weekend_dfs:
            dfk = pd.concat(weekend_dfs, ignore_index=True)
            perfil_weekend = dfk.groupby("month").mean()
            resultado["perfil_comunitario_weekend"] = perfil_weekend.to_dict()
            resultado["archivos_procesados_weekend"] = len(resultado["archivos_weekend"])

        # Paso 4: Preparar respuesta general
        total = resultado["archivos_procesados_weekday"] + resultado["archivos_procesados_weekend"]
        resultado["status"] = "ok"
        resultado["archivos_procesados"] = total
        resultado["resumen"] = (
            f"Perfil comunitario generado desde {total} viviendas "
            f"({resultado['archivos_procesados_weekday']} laborables, {resultado['archivos_procesados_weekend']} fines de semana)"
        )
        return resultado
        
    except Exception as e:
        resultado["status"] = "error"
        resultado["resumen"] = f"Error en procesamiento: {str(e)}"
        return resultado


def guardar_perfil_comunitario(perfil_dict: Dict, nombre_salida: str = "perfil_comunitario_output.csv", directorio: str = "responses") -> str:
    """
    Guarda un diccionario de perfil comunitario en un archivo CSV.

    La función se puede invocar varias veces con distintos diccionarios, por
    ejemplo uno para los días laborables (`weekday`) y otro para los fines de
    semana (`weekend`). Se puede personalizar el nombre de salida para
    distinguirlos.
    
    Args:
        perfil_dict (Dict): Diccionario del perfil comunitario (salida de generar_perfil_comunitario)
        nombre_salida (str): Nombre del archivo de salida
        directorio (str): Directorio donde guardar el archivo. Por defecto "responses"
        
    Returns:
        str: Ruta del archivo guardado
    """    
    try:
        df = pd.DataFrame(perfil_dict)
        if df.index.name is not None or df.index.tolist() != list(range(len(df))):
            df = df.reset_index()
            if df.columns[0] != "month":
                df = df.rename(columns={df.columns[0]: "month"})

        ruta_salida = Path(directorio) / nombre_salida
        ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        
        df.to_csv(ruta_salida, index=False)
        return str(ruta_salida)
    except Exception as e:
        raise Exception(f"Error guardando perfil: {str(e)}")
