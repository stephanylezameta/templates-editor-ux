import pandas as pd


def validate_distribution(df: pd.DataFrame) -> list[str]:
    """Agrupa por template_id, scenario_id, group, item_id.
    Verifica que distribution_percentage sume 1 por grupo.
    Retorna lista de alertas (vacía si todo OK)."""
    if "distribution_percentage" not in df.columns:
        return []

    work = df.copy()
    work["distribution_percentage"] = pd.to_numeric(
        work["distribution_percentage"], errors="coerce"
    )
    work = work.dropna(subset=["distribution_percentage"])

    if work.empty:
        return []

    group_cols = ["template_id", "scenario_id", "group", "item_id"]
    grouped = work.groupby(group_cols, dropna=False)["distribution_percentage"].sum()

    alerts: list[str] = []
    for keys, total in grouped.items():
        if abs(total - 1.0) > 0.001:
            tid, sid, grp, iid = keys
            alerts.append(
                f"La distribución debe sumar 1 — Grupo "
                f"(template_id={tid}, scenario_id={sid}, "
                f"group={grp}, item_id={iid}) suma {total:.4f}"
            )

    return alerts
