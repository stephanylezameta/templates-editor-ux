"""
exporter.py — Exportación de ChangeReport a archivo Excel.

Genera un archivo Excel con tres hojas (Modificados, Agregados, Eliminados)
a partir de un ChangeReport. Para templates modificados, incluye columnas
{campo}_anterior y {campo}_nuevo por cada campo que cambió.
"""

import os
from datetime import datetime

import pandas as pd

from editor import ChangeReport


def export_changes(report: ChangeReport, output_dir: str) -> str:
    """Genera un Excel con 3 hojas a partir del ChangeReport.

    Hojas:
        - Modificados: template_id + {campo}_anterior / {campo}_nuevo por cada campo cambiado
        - Agregados: template_id + change_type
        - Eliminados: template_id + change_type

    Args:
        report: ChangeReport con los cambios detectados.
        output_dir: Directorio donde se guardará el archivo.

    Returns:
        Ruta absoluta del archivo Excel generado.

    Raises:
        IOError: Si falla la escritura del archivo.
    """
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"cambios_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)

    # --- Hoja Modificados ---
    modified_rows = []
    for change in report.modified:
        row: dict = {"template_id": change.template_id}
        for fc in change.field_changes:
            row[f"{fc.field}_anterior"] = fc.old_value
            row[f"{fc.field}_nuevo"] = fc.new_value
        modified_rows.append(row)

    df_modified = pd.DataFrame(modified_rows) if modified_rows else pd.DataFrame(columns=["template_id"])

    # --- Hoja Agregados ---
    added_rows = [
        {"template_id": change.template_id, "change_type": change.change_type}
        for change in report.added
    ]
    df_added = pd.DataFrame(added_rows) if added_rows else pd.DataFrame(columns=["template_id", "change_type"])

    # --- Hoja Eliminados ---
    deleted_rows = [
        {"template_id": change.template_id, "change_type": change.change_type}
        for change in report.deleted
    ]
    df_deleted = pd.DataFrame(deleted_rows) if deleted_rows else pd.DataFrame(columns=["template_id", "change_type"])

    # --- Escribir Excel ---
    try:
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            df_modified.to_excel(writer, sheet_name="Modificados", index=False)
            df_added.to_excel(writer, sheet_name="Agregados", index=False)
            df_deleted.to_excel(writer, sheet_name="Eliminados", index=False)
    except Exception as exc:
        raise IOError(f"Error al escribir el archivo de exportación: {exc}") from exc

    return filepath
