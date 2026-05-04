"""
mailer.py — Envío de reportes de cambios por correo electrónico.

Construye el cuerpo HTML del correo con resumen de cambios y envía
por SMTP a la lista de destinatarios con el Excel de exportación adjunto.
"""

import os
import smtplib
from datetime import datetime
from email.encoders import encode_base64
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from editor import ChangeReport


def build_email_body(report: ChangeReport) -> str:
    """Genera cuerpo HTML con resumen de cambios resaltados.

    Incluye conteos de templates modificados, agregados y eliminados,
    lista los template_ids afectados por categoría, y para los modificados
    detalla los campos que cambiaron.
    """
    counts = report.summary
    modified_count = counts["modified"]
    added_count = counts["added"]
    deleted_count = counts["deleted"]

    html_parts: list[str] = []

    html_parts.append(
        "<html><body>"
        "<h2>Reporte de Cambios en Templates</h2>"
        f"<p><strong>Fecha:</strong> {report.timestamp}</p>"
        "<h3>Resumen</h3>"
        "<ul>"
        f"<li>Modificados: {modified_count}</li>"
        f"<li>Agregados: {added_count}</li>"
        f"<li>Eliminados: {deleted_count}</li>"
        "</ul>"
    )

    # Modificados — con detalle de campos
    if report.modified:
        html_parts.append("<h3>Templates Modificados</h3><ul>")
        for change in report.modified:
            fields = ", ".join(fc.field for fc in change.field_changes)
            html_parts.append(
                f"<li><strong>{change.template_id}</strong> — "
                f"campos: {fields}</li>"
            )
        html_parts.append("</ul>")

    # Agregados
    if report.added:
        html_parts.append("<h3>Templates Agregados</h3><ul>")
        for change in report.added:
            html_parts.append(f"<li>{change.template_id}</li>")
        html_parts.append("</ul>")

    # Eliminados
    if report.deleted:
        html_parts.append("<h3>Templates Eliminados</h3><ul>")
        for change in report.deleted:
            html_parts.append(f"<li>{change.template_id}</li>")
        html_parts.append("</ul>")

    html_parts.append("</body></html>")

    return "".join(html_parts)


def send_report(
    report: ChangeReport, attachment_path: str, config: dict
) -> None:
    """Envía correo a recipients con body HTML y adjunto Excel.

    Lee config["smtp"] (host, port, user, password, use_tls) y
    config["recipients"] para construir y enviar el mensaje.

    Raises:
        ConnectionError: si no puede conectar al servidor SMTP.
        smtplib.SMTPException: si falla el envío del correo.
    """
    smtp_cfg = config["smtp"]
    recipients = config["recipients"]

    # Construir mensaje MIME
    msg = MIMEMultipart()
    msg["From"] = smtp_cfg["user"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = (
        f"Reporte de Cambios en Templates - {datetime.now().strftime('%Y-%m-%d')}"
    )

    # Cuerpo HTML
    body = build_email_body(report)
    msg.attach(MIMEText(body, "html"))

    # Adjunto Excel
    filename = os.path.basename(attachment_path)
    with open(attachment_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    # Enviar por SMTP
    try:
        server = smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"])
    except (OSError, smtplib.SMTPException) as exc:
        raise ConnectionError(
            f"No se pudo conectar a {smtp_cfg['host']}:{smtp_cfg['port']}: {exc}"
        ) from exc

    try:
        if smtp_cfg.get("use_tls", False):
            server.starttls()
        server.login(smtp_cfg["user"], smtp_cfg["password"])
        server.sendmail(smtp_cfg["user"], recipients, msg.as_string())
    except smtplib.SMTPException:
        raise
    finally:
        server.quit()
