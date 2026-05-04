"""
app.py — Interfaz Streamlit para el Editor de Templates.

Punto de entrada de la aplicación. Carga configuración y datos,
ofrece filtros en el sidebar, edición inline con st.data_editor,
y botones para guardar versión, detectar cambios, exportar y enviar por correo.
"""

import os
import sys

import streamlit as st
import pandas as pd

# Asegurar que el directorio del script esté en el path para imports locales
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from data_loader import load_config, load_resultado, list_versions, load_version, save_version
from editor import detect_changes, highlight_changes, ChangeReport
from exporter import export_changes
from mailer import send_report

# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Editor de Templates", layout="wide")
st.title("Editor de Templates")

# ---------------------------------------------------------------------------
# Inicializar session state
# ---------------------------------------------------------------------------
if "original_df" not in st.session_state:
    st.session_state.original_df = None
if "report" not in st.session_state:
    st.session_state.report = None
if "export_path" not in st.session_state:
    st.session_state.export_path = None

# ---------------------------------------------------------------------------
# Cargar configuración y datos
# ---------------------------------------------------------------------------
try:
    config = load_config(os.path.join(_script_dir, "config.json"))
except Exception as e:
    st.error(f"Error al cargar la configuración: {e}")
    st.stop()

try:
    df_original = load_resultado(config)
    if st.session_state.original_df is None:
        st.session_state.original_df = df_original.copy()
except Exception as e:
    st.error(f"Error al cargar resultado.xlsx: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar — Filtros
# ---------------------------------------------------------------------------
st.sidebar.header("Filtros")

filter_values: dict[str, str] = {}
for col in config.get("filter_columns", []):
    if col in df_original.columns:
        unique_vals = sorted(df_original[col].dropna().astype(str).unique().tolist())
        options = ["Todos"] + unique_vals
        filter_values[col] = st.sidebar.selectbox(col, options, index=0)

# Aplicar filtros
df_filtrado = df_original.copy()
for col, val in filter_values.items():
    if val != "Todos":
        df_filtrado = df_filtrado[df_filtrado[col].astype(str) == val]

# ---------------------------------------------------------------------------
# Sidebar — Versiones
# ---------------------------------------------------------------------------
st.sidebar.header("Versiones")

versions = list_versions(config)
version_labels = [os.path.basename(v) for v in versions] if versions else []
version_options = ["(ninguna)"] + version_labels

selected_version_label = st.sidebar.selectbox("Versión anterior", version_options, index=0)

selected_version_path: str | None = None
if selected_version_label != "(ninguna)" and versions:
    idx = version_labels.index(selected_version_label)
    selected_version_path = versions[idx]

# Conteo de templates
st.sidebar.metric("Templates mostrados", len(df_filtrado))

# ---------------------------------------------------------------------------
# Área principal — Editor de datos
# ---------------------------------------------------------------------------
df_editado = st.data_editor(df_filtrado, num_rows="dynamic", width="stretch")

# Indicador de cambios pendientes
if not df_editado.equals(st.session_state.original_df):
    st.warning("Hay cambios sin guardar")

# ---------------------------------------------------------------------------
# Botones de acción
# ---------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

# --- Guardar versión ---
with col1:
    if st.button("Guardar versión"):
        try:
            path = save_version(df_editado, config)
            st.session_state.original_df = df_editado.copy()
            st.success(f"Versión guardada: {os.path.basename(path)}")
        except Exception as e:
            st.error(f"Error al guardar versión: {e}")

# --- Detectar cambios ---
with col2:
    if st.button("Detectar cambios"):
        try:
            if selected_version_path:
                df_anterior = load_version(selected_version_path)
            else:
                df_anterior = None

            report = detect_changes(df_editado, df_anterior)
            st.session_state.report = report

            if not report.has_changes:
                st.info("No se detectaron cambios respecto a la versión anterior.")
            else:
                summary = report.summary
                st.success(
                    f"Cambios detectados — Modificados: {summary['modified']}, "
                    f"Agregados: {summary['added']}, Eliminados: {summary['deleted']}"
                )

                if report.modified:
                    with st.expander(f"Modificados ({summary['modified']})"):
                        for change in report.modified:
                            st.markdown(f"**{change.template_id}**")
                            for fc in change.field_changes:
                                st.text(f"  {fc.field}: {fc.old_value} → {fc.new_value}")

                if report.added:
                    with st.expander(f"Agregados ({summary['added']})"):
                        for change in report.added:
                            st.markdown(f"- {change.template_id}")

                if report.deleted:
                    with st.expander(f"Eliminados ({summary['deleted']})"):
                        for change in report.deleted:
                            st.markdown(f"- {change.template_id}")
        except Exception as e:
            st.error(f"Error al detectar cambios: {e}")

# --- Exportar cambios ---
with col3:
    if st.button("Exportar cambios"):
        try:
            report = st.session_state.report
            if report is None or not report.has_changes:
                st.info("No hay cambios para exportar. Detecta cambios primero.")
            else:
                path = export_changes(report, config["versions_dir"])
                st.session_state.export_path = path
                st.success(f"Cambios exportados: {path}")
        except Exception as e:
            st.error(f"Error al exportar cambios: {e}")

# --- Enviar por correo ---
with col4:
    if st.button("Enviar por correo"):
        try:
            report = st.session_state.report
            export_path = st.session_state.export_path

            if report is None or not report.has_changes:
                st.info("No hay cambios para enviar. Detecta y exporta cambios primero.")
            elif export_path is None:
                st.info("Exporta los cambios primero antes de enviar por correo.")
            else:
                send_report(report, export_path, config)
                st.success("Correo enviado exitosamente.")
        except Exception as e:
            st.error(f"Error al enviar correo: {e}")
