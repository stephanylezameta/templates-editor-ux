"""
app.py — Interfaz Streamlit para el Editor de Templates.

Punto de entrada de la aplicación. Diseño de página única con tabs:
- Tab 1: Tabla con edición inline por fila (expandible)
- Tab 2: Descarga y resumen de cambios
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
from validator import validate_distribution

# ---------------------------------------------------------------------------
# Configuración de página y CSS
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Editor de Templates", layout="wide", page_icon="📝")

st.markdown(
    """
    <style>
        .main .block-container { padding-top: 0.2rem; padding-bottom: 0.2rem; max-width: 100%; }
        h1 { font-size: 12pt; color: #1a5276; margin-bottom: 0.2rem; }
        h2, h3 { font-size: 10pt; color: #1a5276; margin-bottom: 0.1rem; }
        p, li, span, label, .stMarkdown, .stText { font-size: 9pt !important; }
        .stAlert { padding: 0.3rem 0.5rem; font-size: large; }
        div[data-testid="stSidebar"] { background-color: #f0f4f8; }
        div[data-testid="stVerticalBlock"] > div { gap: 0.1rem; }
        .stTextInput input, .stTextArea textarea {
            font-size: 12pt !important;
            padding: 0.15rem 0.3rem !important;
        }
        .stTextArea textarea { min-height: 2.5rem !important; resize: vertical; }
        .stTextInput label, .stTextArea label { font-size: 8pt !important; margin-bottom: 0; }
        button { font-size: 12pt !important; padding: 0.15rem 0.4rem !important; }
        details { margin-bottom: 0.1rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Editor de Wording")

# ---------------------------------------------------------------------------
# Session state — inicialización
# ---------------------------------------------------------------------------
if "original_df" not in st.session_state:
    st.session_state.original_df = None
if "accumulated_changes" not in st.session_state:
    st.session_state.accumulated_changes = {}
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
        "Versión anterior", versiones, format_func=lambda x: os.path.basename(x),
    )
else:
    st.sidebar.info("No hay versiones guardadas")

st.sidebar.header("✏️ Cambios")
st.sidebar.metric("Registros modificados", len(st.session_state.accumulated_changes))

# ---------------------------------------------------------------------------
# Preparar DataFrame para mostrar
# ---------------------------------------------------------------------------
hidden_columns = config.get("hidden_columns", ["event"])
column_order_first = config.get("column_order", ["title", "detail"])

df_display = df_filtrado.copy()
for hcol in hidden_columns:
    if hcol in df_display.columns:
        df_display = df_display.drop(columns=[hcol])

cols_primero = [c for c in column_order_first if c in df_display.columns]
cols_resto = [c for c in df_display.columns if c not in cols_primero]
df_display = df_display[cols_primero + cols_resto]

# ---------------------------------------------------------------------------
# Pasos a seguir
# ---------------------------------------------------------------------------
st.info("**Pasos:** Filtra → Expande una fila para editar → Guarda → Descarga el Excel")

# ---------------------------------------------------------------------------
# Indicador de cambios
# ---------------------------------------------------------------------------
if st.session_state.accumulated_changes:
    st.warning(f"✏️ {len(st.session_state.accumulated_changes)} registros modificados pendientes de descarga")

    # Resumen de registros modificados
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

# ---------------------------------------------------------------------------
# Botones de acción (arriba)
# ---------------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    if st.button("Detectar cambios", use_container_width=True):
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
            else:
                st.info("No hay versión anterior seleccionada para comparar.")
        except Exception as e:
            st.error(f"Error al detectar cambios: {e}")

with col2:
    if st.session_state.accumulated_changes:
        try:
            from openpyxl.styles import PatternFill

            FIXED_COLS = ["Casos de Uso", "AUDIENCIA", "Oferta", "template_id"]
            changed_cols = set()
            for tid, cols in st.session_state.accumulated_changes.items():
                changed_cols.update(cols.keys())

            export_cols = FIXED_COLS + [c for c in changed_cols if c not in FIXED_COLS]
            export_cols = [c for c in export_cols if c in st.session_state.working_df.columns]

            df_cambios = st.session_state.working_df[
                st.session_state.working_df["template_id"]
                .astype(str)
                .isin([str(k) for k in st.session_state.accumulated_changes.keys()])
            ][export_cols].copy()

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
                file_name=f"cambios_{pd.Timestamp.now().strftime('%Y-%m-%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Error al generar archivo de descarga: {e}")
    else:
        st.info("No hay registros modificados para descargar")

st.divider()
# ---------------------------------------------------------------------------
# Tabla con filas expandibles para edición (paginada)
# ---------------------------------------------------------------------------
if df_display.empty:
    st.info("No se encontraron templates con los criterios seleccionados.")
else:
    editable_cols = [
        c for c in df_display.columns
        if c not in set(config.get("ignored_columns", [])) | {"template_id"}
    ]

    # Paginación
    PAGE_SIZE = 20
    total_rows = len(df_display)
    total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)

    if "current_page" not in st.session_state:
        st.session_state.current_page = 0

    # Slice de la página actual
    start_idx = st.session_state.current_page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_rows)
    df_page = df_display.iloc[start_idx:end_idx]

    for i, (idx, row) in enumerate(df_page.iterrows(), start=start_idx):
        tid = str(row.get("template_id", ""))
        # Indicador visual si fue modificado
        modified_marker = " ✅" if tid in st.session_state.accumulated_changes else ""

        # Resumen compacto de la fila (mostrar Oferta + template_id)
        oferta_val = str(row.get("Oferta", ""))[:50] if "Oferta" in row.index else ""
        label = f"**{oferta_val}** — {tid}{modified_marker}"

        with st.expander(label, expanded=False):
            # Botón guardar a la derecha (arriba)
            _, btn_col = st.columns([5, 1])
            with btn_col:
                save_clicked = st.button("Guardar", key=f"save_{i}_{tid}", type="primary", use_container_width=True)

            # Mostrar campos en 3 columnas
            new_values = {}
            col_groups = [editable_cols[j:j+3] for j in range(0, len(editable_cols), 3)]
            for group in col_groups:
                input_cols = st.columns(len(group))
                for k, col_name in enumerate(group):
                    current_val = str(row[col_name]) if col_name in row.index and pd.notna(row[col_name]) else ""
                    with input_cols[k]:
                        if col_name in ("detail", "title"):
                            new_values[col_name] = st.text_area(
                                col_name, value=current_val, key=f"row_{i}_{tid}_{col_name}", height=68
                            )
                        else:
                            new_values[col_name] = st.text_input(
                                col_name, value=current_val, key=f"row_{i}_{tid}_{col_name}"
                            )

            # Guardar
            if save_clicked:
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
                    st.rerun()
                else:
                    st.info("Sin cambios respecto al original.")

    # Controles de paginación (abajo)
    st.divider()
    pag_left, pag_center, pag_right = st.columns([1, 2, 1])
    with pag_left:
        if st.button("◀ Anterior", disabled=st.session_state.current_page == 0, key="pag_prev"):
            st.session_state.current_page -= 1
            st.rerun()
    with pag_center:
        st.markdown(
            f"<div style='text-align:center'>Página **{st.session_state.current_page + 1}** de **{total_pages}** ({total_rows} registros)</div>",
            unsafe_allow_html=True,
        )
    with pag_right:
        if st.button("Siguiente ▶", disabled=st.session_state.current_page >= total_pages - 1, key="pag_next"):
            st.session_state.current_page += 1
            st.rerun()

