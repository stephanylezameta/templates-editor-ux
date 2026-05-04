"""Autocompletado de campos vacíos usando reglas de mapeo configurables."""

import json
import os
import re

import pandas as pd


def load_mapeos(path: str = "mapeos.json") -> dict:
    """Lee reglas de mapeo desde un archivo JSON.

    Si el archivo no existe, retorna un dict vacío sin lanzar error.
    """
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_channel_id(template_id: str) -> str | None:
    """Extrae el channel_id desde template_id buscando el patrón #XXX.

    Ejemplos: #AU1 → AU1, #CAP → CAP.
    Retorna None si no encuentra el patrón.
    """
    match = re.search(r"#([A-Z0-9]+)", template_id)
    return match.group(1) if match else None


def autocomplete(
    df: pd.DataFrame, mapeos: dict, ignored_columns: list[str] | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Completa campos vacíos del DataFrame usando reglas de mapeo.

    Busca mapeos por scenario_id, channel_id (extraído de template_id)
    e item_id. Registra advertencias para campos vacíos sin mapeo.
    Los campos en ignored_columns se saltan sin generar advertencia.

    Retorna (df_completado, lista_advertencias).
    """
    df = df.copy()
    advertencias: list[str] = []
    skip = set(ignored_columns or [])

    for idx, row in df.iterrows():
        template_id = str(row.get("template_id", ""))

        # Recopilar todos los campos mapeables para esta fila
        campos_mapeados: dict[str, str] = {}

        # Mapeo por scenario_id
        if "scenario_id" in mapeos:
            sid = str(row.get("scenario_id", ""))
            if sid in mapeos["scenario_id"]:
                campos_mapeados.update(mapeos["scenario_id"][sid])

        # Mapeo por channel_id (extraído de template_id)
        if "channel_id" in mapeos:
            channel = extract_channel_id(template_id)
            if channel and channel in mapeos["channel_id"]:
                campos_mapeados.update(mapeos["channel_id"][channel])

        # Mapeo por item_id
        if "item_id" in mapeos:
            iid = str(row.get("item_id", ""))
            if iid in mapeos["item_id"]:
                campos_mapeados.update(mapeos["item_id"][iid])

        # Aplicar mapeos solo a campos vacíos
        for campo in df.columns:
            if campo in skip:
                continue
            valor = row[campo]
            es_vacio = pd.isna(valor) or (isinstance(valor, str) and valor.strip() == "")

            if not es_vacio:
                continue

            if campo in campos_mapeados:
                df.at[idx, campo] = campos_mapeados[campo]
            else:
                advertencias.append(
                    f"Registro {template_id}: campo '{campo}' vacío sin mapeo"
                )

    return df, advertencias
