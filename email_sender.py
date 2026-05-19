from pathlib import Path
import smtplib
from email.message import EmailMessage
from utils import get_config, emoji_prioridade, emoji_status, link_pedido

EMAIL_SMTP_HOST = str(get_config("EMAIL_SMTP_HOST", ""))
EMAIL_SMTP_PORT = int(str(get_config("EMAIL_SMTP_PORT", "587") or "587"))
EMAIL_SMTP_USER = str(get_config("EMAIL_SMTP_USER", ""))
EMAIL_SMTP_PASSWORD = str(get_config("EMAIL_SMTP_PASSWORD", ""))
EMAIL_REMETENTE = str(get_config("EMAIL_REMETENTE", EMAIL_SMTP_USER))
EMAIL_DESTINATARIOS = [e.strip() for e in str(get_config("EMAIL_DESTINATARIOS", "")).split(",") if e.strip()]
EMAIL_USAR_TLS = str(get_config("EMAIL_USAR_TLS", "SIM")).upper() == "SIM"
EMAIL_ENVIAR_PDF = str(get_config("EMAIL_ENVIAR_PDF", "SIM")).upper() == "SIM"


def email_configurado():
    return bool(
        EMAIL_SMTP_HOST
        and EMAIL_SMTP_PORT
        and EMAIL_SMTP_USER
        and EMAIL_SMTP_PASSWORD
        and EMAIL_REMETENTE
        and EMAIL_DESTINATARIOS
    )


def enviar_email_notificacao(assunto: str, mensagem: str, caminho_pdf=None, legenda: str = ""):
    if not email_configurado():
        print("Email não configurado")
        return False

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = EMAIL_REMETENTE
    msg["To"] = ", ".join(EMAIL_DESTINATARIOS)
    msg.set_content(mensagem)

    if caminho_pdf and EMAIL_ENVIAR_PDF:
        pdf = Path(caminho_pdf)
        if pdf.exists():
            msg.add_attachment(
                pdf.read_bytes(),
                maintype="application",
                subtype="pdf",
                filename=pdf.name,
            )

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=30) as smtp:
            if EMAIL_USAR_TLS:
                smtp.starttls()
            smtp.login(EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception as erro:
        print("Erro ao enviar email:", erro)
        return False



def mensagem_pedido_criado(numero, pedido_id, usuario, fornecedor, total, prioridade):
    return f"""🛒 NOVO PEDIDO DE COMPRA

Pedido: {numero}
Fornecedor: {fornecedor}
Valor: {total}
Prioridade: {prioridade}
Criado por: {usuario}
"""


def mensagem_status_alterado(numero, pedido_id, status, usuario, prioridade):
    return f"""📦 ATUALIZAÇÃO DE PEDIDO

Pedido: {numero}
Prioridade: {prioridade}

Novo status: {status}
Alterado por: {usuario}
"""


def mensagem_pedido_editado(numero, pedido_id, usuario, prioridade):
    return f"""✏️ PEDIDO DE COMPRA EDITADO

Pedido: {numero}
Prioridade: {prioridade}
Editado por: {usuario}
"""


def mensagem_pedido_excluido(numero, pedido_id, usuario, prioridade):
    return f"""🗑️ PEDIDO DE COMPRA EXCLUÍDO

Pedido: {numero}
Prioridade: {prioridade}
Excluído por: {usuario}
"""



def email_configurado():
    try:
        return bool(EMAIL_SMTP_HOST and EMAIL_SMTP_PORT and EMAIL_SMTP_USER and EMAIL_SMTP_PASSWORD and EMAIL_REMETENTE and EMAIL_DESTINATARIOS)
    except Exception:
        return False
