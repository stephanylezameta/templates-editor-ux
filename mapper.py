"""Autocompletado de campos vacíos usando relaciones extraídas de los propios datos."""
from __future__ import annotations

import re

import pandas as pd


def extract_channel_id(template_id: str):
    """Extrae el channel_id desde template_id buscando el patrón #XXX.

    Ejemplos: #AU1 → AU1, #CAP → CAP.
    Retorna None si no encuentra el patrón.
    """
    match = re.search(r"#([A-Z0-9]+)", str(template_id))
    return match.group(1) if match else None


def build_mapeos_from_data(df: pd.DataFrame) -> dict:
    """Construye mapeos dinámicamente a partir de los registros que SÍ tienen datos completos.

    Extrae relaciones:
    - scenario_id → Casos de Uso
    - channel_id (extraído de template_id) → AUDIENCIA
    - item_id → Oferta

    Retorna dict con la misma estructura que mapeos.json.
    """
    mapeos: dict = {"scenario_id": {}, "channel_id": {}, "item_id": {}}

    for _, row in df.iterrows():
        # scenario_id → Casos de Uso
        caso = row.get("Casos de Uso")
        sid = str(row.get("scenario_id", ""))
        if caso and str(caso).strip() and sid:
            mapeos["scenario_id"][sid] = {"Casos de Uso": str(caso).strip()}

        # channel_id (desde template_id) → AUDIENCIA
        audiencia = row.get("AUDIENCIA")
        tid = str(row.get("template_id", ""))
        channel = extract_channel_id(tid)
        if audiencia and str(audiencia).strip() and channel:
            mapeos["channel_id"][channel] = {"AUDIENCIA": str(audiencia).strip()}

        # item_id → Oferta
        oferta = row.get("Oferta")
        iid = str(row.get("item_id", ""))
        if oferta and str(oferta).strip() and iid:
            mapeos["item_id"][iid] = {"Oferta": str(oferta).strip()}

    return mapeos


def autocomplete(
    df: pd.DataFrame, ignored_columns: list = None
) -> pd.DataFrame:
    """Completa campos vacíos usando relaciones extraídas de los propios datos.

    1. Construye mapeos desde registros completos
    2. Aplica mapeos a registros con campos vacíos

    Retorna df_completado.
    """
    df = df.copy()
    skip = set(ignored_columns or [])

    # Construir mapeos desde los datos completos
    mapeos = build_mapeos_from_data(df)

    for idx, row in df.iterrows():
        template_id = str(row.get("template_id", ""))

        # Recopilar campos mapeables para esta fila
        campos_mapeados: dict[str, str] = {}

        # Mapeo por scenario_id
        sid = str(row.get("scenario_id", ""))
        if sid in mapeos["scenario_id"]:
            campos_mapeados.update(mapeos["scenario_id"][sid])

        # Mapeo por channel_id (extraído de template_id)
        channel = extract_channel_id(template_id)
        if channel and channel in mapeos["channel_id"]:
            campos_mapeados.update(mapeos["channel_id"][channel])

        # Mapeo por item_id
        iid = str(row.get("item_id", ""))
        if iid in mapeos["item_id"]:
            campos_mapeados.update(mapeos["item_id"][iid])

        # Aplicar mapeos solo a campos vacíos
        for campo, valor_mapeo in campos_mapeados.items():
            if campo in skip:
                continue
            if campo not in df.columns:
                continue
            valor = row[campo]
            es_vacio = pd.isna(valor) or (isinstance(valor, str) and valor.strip() == "")
            if es_vacio:
                df.at[idx, campo] = valor_mapeo

    return df
