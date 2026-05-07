"""
app.py — Interfaz Streamlit para el Editor de Templates.

Punto de entrada de la aplicación. Carga datos, aplica autocompletado,
gestiona filtros, edición inline con acumulación de cambios entre filtros,
validación de distribución, guardado de versiones y descarga de cambios.
"""

import io
import os
import sys

import streamlit as st
import pandas as pd

# ---------------------------------------------------------------------------
# Asegurar que los módulos locales sean importables
# ---------------------------------------------------------------------------
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from data_loader import load_config, load_resultado, list_versions, load_version, save_version
from editor import detect_changes, ChangeReport
from exporter import export_changes
from mapper import autocomplete
from validator import validate_distribution

# ---------------------------------------------------------------------------
# Configuración de página y CSS corporativo
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Editor de Templates", layout="wide", page_icon="📝")

st.markdown(
    """
    <style>
        .main .block-container { padding-top: 1rem; padding-bottom: 1rem; }
        h1, h2, h3 { color: #1a5276; }
        h1 { font-size: 1.8rem; }
        .stMetric label { font-size: 0.85rem; }
        .stMetric [data-testid="stMetricValue"] { font-size: 1.4rem; color: #1a5276; }
        div[data-testid="stSidebar"] { background-color: #f0f4f8; }
        div[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📝 Editor de Templates")

# ---------------------------------------------------------------------------
# Session state — inicialización
# ---------------------------------------------------------------------------
if "original_df" not in st.session_state:
    st.session_state.original_df = None
if "accumulated_changes" not in st.session_state:
    st.session_state.accumulated_changes = {}  # {template_id: {col: new_val}}
if "report" not in st.session_state:
    st.session_state.report = None
if "working_df" not in st.session_state:
    st.session_state.working_df = None

# ---------------------------------------------------------------------------
# Cargar configuración
# ---------------------------------------------------------------------------
try:
    config = load_config(os.path.join(_script_dir, "config.json"))
except Exception as e:
    st.error(f"Error al cargar la configuración: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Cargar datos y aplicar autocompletado (solo la primera vez)
# ---------------------------------------------------------------------------
if st.session_state.original_df is None:
    try:
        df_raw = load_resultado(config)
    except Exception as e:
        st.error(f"Error al cargar resultado.xlsx: {e}")
        st.stop()

    # Autocompletado de campos vacíos desde los propios datos
    ignored = config.get("ignored_columns", [])
    df_raw = autocomplete(df_raw, ignored_columns=ignored)

    st.session_state.original_df = df_raw.copy()

    # Eliminar columnas ignoradas al cargar
    drop_cols = config.get("drop_columns", [])
    for col in drop_cols:
        if col in st.session_state.original_df.columns:
            st.session_state.original_df = st.session_state.original_df.drop(columns=[col])

    # Filtrar solo scenarios permitidos
    allowed = config.get("allowed_scenarios")
    if allowed and "scenario_id" in st.session_state.original_df.columns:
        st.session_state.original_df = st.session_state.original_df[
            st.session_state.original_df["scenario_id"].astype(str).isin([str(s) for s in allowed])
        ].reset_index(drop=True)

    # Excluir registros con patrones ignorados en template_id (ej. ITM#)
    exclude_patterns = config.get("exclude_template_patterns", [])
    if exclude_patterns and "template_id" in st.session_state.original_df.columns:
        for pattern in exclude_patterns:
            st.session_state.original_df = st.session_state.original_df[
                ~st.session_state.original_df["template_id"].astype(str).str.contains(pattern, na=False)
            ].reset_index(drop=True)

# ---------------------------------------------------------------------------
# Construir working_df: original + cambios acumulados
# ---------------------------------------------------------------------------
working_df = st.session_state.original_df.copy()
for tid, changes in st.session_state.accumulated_changes.items():
    mask = working_df["template_id"].astype(str) == str(tid)
    for col, val in changes.items():
        if col in working_df.columns:
            working_df.loc[mask, col] = val
st.session_state.working_df = working_df

# ---------------------------------------------------------------------------
# Sidebar — Filtros
# ---------------------------------------------------------------------------
st.sidebar.header("🔍 Filtros")

filter_columns = config.get("filter_columns", [])
filtros_activos: dict[str, str] = {}

for col in filter_columns:
    if col in working_df.columns:
        opciones = ["Todos"] + sorted(working_df[col].dropna().astype(str).unique().tolist())
        seleccion = st.sidebar.selectbox(col, opciones, key=f"filter_{col}")
        if seleccion != "Todos":
            filtros_activos[col] = seleccion

# Aplicar filtros al working_df
df_filtrado = working_df.copy()
for col, val in filtros_activos.items():
    df_filtrado = df_filtrado[df_filtrado[col].astype(str) == val]

st.sidebar.metric("Templates mostrados", len(df_filtrado))

# ---------------------------------------------------------------------------
# Sidebar — Versiones
# ---------------------------------------------------------------------------
st.sidebar.header("📂 Versiones")
versiones = list_versions(config)
version_seleccionada = None
if versiones:
    version_seleccionada = st.sidebar.selectbox(
        "Versión anterior",
        versiones,
        format_func=lambda x: os.path.basename(x),
    )
else:
    st.sidebar.info("No hay versiones guardadas")

# ---------------------------------------------------------------------------
# Sidebar — Contador de cambios
# ---------------------------------------------------------------------------
st.sidebar.header("✏️ Cambios")
st.sidebar.metric("Registros modificados", len(st.session_state.accumulated_changes))

# ---------------------------------------------------------------------------
# Área principal — Preparar DataFrame para edición
# ---------------------------------------------------------------------------
hidden_columns = config.get("hidden_columns", ["event"])
column_order_first = config.get("column_order", ["title", "detail"])

# Ocultar columnas (ej. event)
df_display = df_filtrado.copy()
for hcol in hidden_columns:
    if hcol in df_display.columns:
        df_display = df_display.drop(columns=[hcol])

# Reordenar: title y detail primero, luego el resto
cols_primero = [c for c in column_order_first if c in df_display.columns]
cols_resto = [c for c in df_display.columns if c not in cols_primero]
df_display = df_display[cols_primero + cols_resto]

# ---------------------------------------------------------------------------
# Pasos a seguir (arriba de la tabla)
# ---------------------------------------------------------------------------
st.info(
    "📋 **Pasos a seguir:**\n"
    "1. Usa los filtros del panel lateral para encontrar los templates que deseas editar.\n"
    "2. Haz clic en una fila de la tabla para editarla (se abre un popup).\n"
    "3. Modifica los campos y haz clic en **Guardar cambio**.\n"
    "4. Usa **Descargar cambios** para obtener un Excel con las modificaciones."
)

# ---------------------------------------------------------------------------
# Session state para edición por registro
# ---------------------------------------------------------------------------
if "editing_tid" not in st.session_state:
    st.session_state.editing_tid = None

# ---------------------------------------------------------------------------
# Función de diálogo para editar un registro
# ---------------------------------------------------------------------------
@st.dialog("✏️ Editar registro", width="large")
def edit_dialog(tid: str):
    """Popup modal para editar los campos de un template."""
    # Obtener fila actual con cambios acumulados
    row_mask = st.session_state.working_df["template_id"].astype(str) == tid
    if not row_mask.any():
        st.error("No se encontró el registro.")
        return

    row_data = st.session_state.working_df[row_mask].iloc[0]
    st.caption(f"Template: **{tid}**")

    # Columnas editables
    editable_cols = [
        c for c in df_display.columns
        if c not in set(config.get("ignored_columns", [])) | {"template_id"}
    ]

    # Mostrar campos en 2 columnas para aprovechar espacio
    new_values = {}
    col_pairs = [editable_cols[i:i+2] for i in range(0, len(editable_cols), 2)]
    for pair in col_pairs:
        cols = st.columns(len(pair))
        for j, col_name in enumerate(pair):
            current_val = str(row_data[col_name]) if col_name in row_data.index and pd.notna(row_data[col_name]) else ""
            with cols[j]:
                new_values[col_name] = st.text_area(col_name, value=current_val, height=68, key=f"dlg_{tid}_{col_name}")

    st.divider()
    if st.button("💾 Guardar cambio", use_container_width=True, type="primary"):
        # Comparar contra original
        original_row_mask = st.session_state.original_df["template_id"].astype(str) == tid
        original_row = st.session_state.original_df[original_row_mask].iloc[0] if original_row_mask.any() else None

        changes_made = False
        for col_name in editable_cols:
            new_val = new_values[col_name]
            orig_val = str(original_row[col_name]) if original_row is not None and col_name in original_row.index and pd.notna(original_row[col_name]) else ""

            if new_val != orig_val:
                if tid not in st.session_state.accumulated_changes:
                    st.session_state.accumulated_changes[tid] = {}
                st.session_state.accumulated_changes[tid][col_name] = new_val
                changes_made = True

        if changes_made:
            st.session_state.editing_tid = None
            st.rerun()
        else:
            st.info("No se detectaron cambios respecto al original.")

# ---------------------------------------------------------------------------
# Tabla de solo lectura con selección
# ---------------------------------------------------------------------------
if df_display.empty:
    st.info("No se encontraron templates con los criterios seleccionados.")
else:
    event = st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="tabla_seleccion",
    )

    # Detectar fila seleccionada y abrir diálogo
    selected_rows = event.selection.rows if event.selection else []

    if selected_rows:
        idx = selected_rows[0]
        row_selected = df_display.iloc[idx]
        tid = str(row_selected.get("template_id", ""))
        if tid:
            edit_dialog(tid)

    # Indicador de cambios pendientes
    if st.session_state.accumulated_changes:
        st.warning(
            f"Hay {len(st.session_state.accumulated_changes)} registros modificados pendientes de descarga"
        )

# ---------------------------------------------------------------------------
# Botones de acción
# ---------------------------------------------------------------------------
st.divider()
col1, col2 = st.columns(2)

# --- Botón 1: Detectar cambios ---
with col1:
    if st.button("🔎 Detectar cambios", use_container_width=True):
        try:
            if version_seleccionada:
                df_anterior = load_version(version_seleccionada)
                report = detect_changes(st.session_state.working_df, df_anterior)
                st.session_state.report = report

                if not report.has_changes:
                    st.info("No se detectaron cambios respecto a la versión anterior.")
                else:
                    resumen = report.summary
                    st.write(
                        f"**Resumen:** {resumen['modified']} modificados, "
                        f"{resumen['added']} agregados, "
                        f"{resumen['deleted']} eliminados"
                    )

                    if report.modified:
                        with st.expander(f"📝 Modificados ({resumen['modified']})"):
                            for change in report.modified:
                                st.markdown(f"**{change.template_id}**")
                                for fc in change.field_changes:
                                    st.text(f"  {fc.field}: {fc.old_value} → {fc.new_value}")

                    if report.added:
                        with st.expander(f"➕ Agregados ({resumen['added']})"):
                            for change in report.added:
                                st.text(change.template_id)

                    if report.deleted:
                        with st.expander(f"➖ Eliminados ({resumen['deleted']})"):
                            for change in report.deleted:
                                st.text(change.template_id)
            else:
                st.info("No hay versión anterior seleccionada para comparar.")
        except Exception as e:
            st.error(f"Error al detectar cambios: {e}")

# --- Botón 2: Descargar cambios ---
with col2:
    if st.session_state.accumulated_changes:
        try:
            from openpyxl.styles import PatternFill

            # Columnas fijas que siempre aparecen
            FIXED_COLS = ["Casos de Uso", "AUDIENCIA", "Oferta", "template_id"]

            # Recopilar columnas modificadas
            changed_cols = set()
            for tid, cols in st.session_state.accumulated_changes.items():
                changed_cols.update(cols.keys())

            # Columnas finales: fijas + solo las que cambiaron (sin duplicar)
            export_cols = FIXED_COLS + [c for c in changed_cols if c not in FIXED_COLS]
            export_cols = [c for c in export_cols if c in st.session_state.working_df.columns]

            # Filtrar solo registros modificados
            df_cambios = st.session_state.working_df[
                st.session_state.working_df["template_id"]
                .astype(str)
                .isin([str(k) for k in st.session_state.accumulated_changes.keys()])
            ][export_cols].copy()

            # Escribir Excel con resaltado amarillo en celdas modificadas
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df_cambios.to_excel(writer, index=False, sheet_name="Cambios")
                ws = writer.sheets["Cambios"]
                yellow = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")

                for row_idx, (_, row) in enumerate(df_cambios.iterrows(), start=2):
                    tid = str(row.get("template_id", ""))
                    if tid in st.session_state.accumulated_changes:
                        for col_name in st.session_state.accumulated_changes[tid]:
                            if col_name in export_cols:
                                col_idx = export_cols.index(col_name) + 1
                                ws.cell(row=row_idx, column=col_idx).fill = yellow

            excel_bytes = buffer.getvalue()

            st.download_button(
                "📥 Descargar cambios",
                data=excel_bytes,
                file_name="cambios.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Error al generar archivo de descarga: {e}")
    else:
        st.info("No hay registros modificados para descargar")

# ---------------------------------------------------------------------------
# Resumen de registros modificados (por Caso de Uso, Audiencia, Producto)
# ---------------------------------------------------------------------------
if st.session_state.accumulated_changes:
    st.divider()
    st.subheader("📊 Registros modificados")

    modified_tids = [str(k) for k in st.session_state.accumulated_changes.keys()]
    df_modified = st.session_state.working_df[
        st.session_state.working_df["template_id"].astype(str).isin(modified_tids)
    ]

    group_cols = []
    for col in ["Casos de Uso", "AUDIENCIA", "Oferta"]:
        if col in df_modified.columns:
            group_cols.append(col)

    if group_cols:
        grouped = df_modified.groupby(group_cols).size().reset_index(name="Registros modificados")
        for _, row in grouped.iterrows():
            parts = [str(row[c]) for c in group_cols]
            st.write(f"• **{', '.join(parts)}** — {row['Registros modificados']} registros modificados")
    else:
        st.write(f"Total: {len(modified_tids)} registros modificados")
