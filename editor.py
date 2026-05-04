"""
editor.py — Edición y detección de cambios entre versiones de templates.

Compara DataFrames por template_id y genera un ChangeReport con templates
modificados, agregados y eliminados. Detecta qué campos específicos cambiaron
con valor anterior y nuevo.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass
class FieldChange:
    field: str
    old_value: Any
    new_value: Any


@dataclass
class TemplateChange:
    template_id: str
    change_type: str  # "modified" | "added" | "deleted"
    field_changes: list[FieldChange] = field(default_factory=list)


@dataclass
class ChangeReport:
    modified: list[TemplateChange] = field(default_factory=list)
    added: list[TemplateChange] = field(default_factory=list)
    deleted: list[TemplateChange] = field(default_factory=list)
    timestamp: str = ""

    @property
    def has_changes(self) -> bool:
        return bool(self.modified or self.added or self.deleted)

    @property
    def summary(self) -> dict:
        return {
            "modified": len(self.modified),
            "added": len(self.added),
            "deleted": len(self.deleted),
        }


def detect_changes(
    current: pd.DataFrame,
    previous: pd.DataFrame | None,
    key: str = "template_id",
) -> ChangeReport:
    """Compara dos DataFrames por key. Identifica modificados, agregados y eliminados.

    - IDs solo en current → added
    - IDs solo en previous → deleted
    - IDs en ambos → comparar campo a campo; si difieren → modified con FieldChange
    - Si previous es None o está vacío → todos son added
    """
    report = ChangeReport(timestamp=datetime.now().isoformat())

    # Si no hay versión anterior, todos los templates actuales son "added"
    if previous is None or previous.empty:
        for _, row in current.iterrows():
            report.added.append(
                TemplateChange(
                    template_id=str(row[key]),
                    change_type="added",
                )
            )
        return report

    current_ids = set(current[key].astype(str))
    previous_ids = set(previous[key].astype(str))

    added_ids = current_ids - previous_ids
    deleted_ids = previous_ids - current_ids
    common_ids = current_ids & previous_ids

    # Added
    for tid in added_ids:
        report.added.append(
            TemplateChange(template_id=tid, change_type="added")
        )

    # Deleted
    for tid in deleted_ids:
        report.deleted.append(
            TemplateChange(template_id=tid, change_type="deleted")
        )

    # Modified — comparar campo a campo para IDs comunes
    current_indexed = current.set_index(current[key].astype(str))
    previous_indexed = previous.set_index(previous[key].astype(str))

    # Columnas a comparar: todas excepto la key
    compare_cols = [c for c in current.columns if c != key]

    for tid in common_ids:
        curr_row = current_indexed.loc[tid]
        prev_row = previous_indexed.loc[tid]

        field_changes: list[FieldChange] = []
        for col in compare_cols:
            old_val = prev_row[col] if col in previous_indexed.columns else None
            new_val = curr_row[col] if col in current_indexed.columns else None

            # Comparar como strings para manejar NaN y tipos mixtos
            if str(old_val) != str(new_val):
                field_changes.append(
                    FieldChange(field=col, old_value=old_val, new_value=new_val)
                )

        if field_changes:
            report.modified.append(
                TemplateChange(
                    template_id=tid,
                    change_type="modified",
                    field_changes=field_changes,
                )
            )

    return report


def highlight_changes(df: pd.DataFrame, original: pd.DataFrame) -> pd.DataFrame:
    """Retorna un DataFrame booleano del mismo shape que df.

    True donde el valor difiere del original.
    Si los DataFrames tienen distinto número de filas, compara solo las filas comunes.
    """
    common_rows = min(len(df), len(original))

    df_cmp = df.iloc[:common_rows].reset_index(drop=True)
    orig_cmp = original.iloc[:common_rows].reset_index(drop=True)

    # Asegurar mismas columnas para la comparación
    common_cols = [c for c in df.columns if c in original.columns]

    # Construir DataFrame booleano con el shape completo de df
    result = pd.DataFrame(False, index=range(len(df)), columns=df.columns)

    # Comparar como strings para manejar NaN y tipos mixtos de forma consistente
    for col in common_cols:
        result.loc[:common_rows - 1, col] = (
            df_cmp[col].astype(str) != orig_cmp[col].astype(str)
        )

    # Filas extra en df (sin correspondencia en original) se marcan como True
    if len(df) > common_rows:
        result.iloc[common_rows:] = True

    return result
