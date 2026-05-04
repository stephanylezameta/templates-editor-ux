"""data_loader.py — Carga de datos y persistencia de versiones."""

import json
import os
from datetime import datetime
from glob import glob

import pandas as pd


def load_config(path: str = "config.json") -> dict:
    """Carga configuración desde JSON.

    Args:
        path: Ruta al archivo de configuración.

    Returns:
        Diccionario con la configuración.

    Raises:
        FileNotFoundError: Si el archivo no existe.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_resultado(config: dict) -> pd.DataFrame:
    """Lee resultado.xlsx desde ruta local.

    Args:
        config: Diccionario de configuración con clave ``resultado_path``.

    Returns:
        DataFrame con los templates vigentes.
    """
    path = config["resultado_path"]
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Archivo de resultado no encontrado: {path}")
    try:
        return pd.read_excel(path, engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"No se pudo leer el archivo '{path}': {exc}") from exc


def list_versions(config: dict) -> list[str]:
    """Lista archivos de versión ordenados por nombre descendente (más reciente primero).

    Args:
        config: Diccionario de configuración con clave ``versions_dir``.

    Returns:
        Lista de rutas a archivos ``version_*.xlsx``, ordenadas descendentemente.
        Lista vacía si el directorio no existe.
    """
    versions_dir = config["versions_dir"]
    if not os.path.isdir(versions_dir):
        return []
    pattern = os.path.join(versions_dir, "version_*.xlsx")
    files = glob(pattern)
    return sorted(files, reverse=True)


def load_version(path: str) -> pd.DataFrame:
    """Lee un archivo de versión específico.

    Args:
        path: Ruta al archivo de versión ``.xlsx``.

    Returns:
        DataFrame con el contenido de la versión.
    """
    return pd.read_excel(path, engine="openpyxl")


def save_version(df: pd.DataFrame, config: dict) -> str:
    """Guarda el DataFrame como nueva versión con marca de tiempo.

    Crea el directorio de versiones si no existe. El archivo se nombra
    ``version_YYYYMMDD_HHMMSS.xlsx``.

    Args:
        df: DataFrame a guardar.
        config: Diccionario de configuración con clave ``versions_dir``.

    Returns:
        Ruta del archivo de versión creado.

    Raises:
        IOError: Si falla la escritura (permisos, disco, etc.).
    """
    versions_dir = config["versions_dir"]
    os.makedirs(versions_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"version_{timestamp}.xlsx"
    path = os.path.join(versions_dir, filename)
    try:
        df.to_excel(path, index=False, engine="openpyxl")
    except Exception as exc:
        raise IOError(f"No se pudo guardar la versión en '{path}': {exc}") from exc
    return path
