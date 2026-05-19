from pathlib import Path
import requests
from utils import emoji_prioridade, emoji_status, get_config, link_pedido

ULTRAMSG_INSTANCE = str(get_config("ULTRAMSG_INSTANCE", ""))
ULTRAMSG_TOKEN = str(get_config("ULTRAMSG_TOKEN", ""))
WHATSAPP_DESTINATARIOS = [n.strip() for n in str(get_config("WHATSAPP_DESTINATARIOS", "")).split(",") if n.strip()]
WHATSAPP_ENVIAR_PDF = str(get_config("WHATSAPP_ENVIAR_PDF", "SIM")).upper()
BASE_URL = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE}"


def whatsapp_configurado():
    return bool(ULTRAMSG_INSTANCE and ULTRAMSG_TOKEN and WHATSAPP_DESTINATARIOS)


def enviar_whatsapp_texto(mensagem):
    if not whatsapp_configurado():
        print("WhatsApp não configurado")
        return False
    sucesso = True
    for numero in WHATSAPP_DESTINATARIOS:
        try:
            r = requests.post(f"{BASE_URL}/messages/chat", data={"token": ULTRAMSG_TOKEN, "to": numero, "body": mensagem}, timeout=20)
            print(r.text)
            if r.status_code != 200:
                sucesso = False
        except Exception as erro:
            print(erro)
            sucesso = False
    return sucesso


def enviar_whatsapp_pdf(caminho_pdf, legenda=""):
    if WHATSAPP_ENVIAR_PDF != "SIM":
        return False
    caminho_pdf = Path(caminho_pdf)
    if not caminho_pdf.exists():
        return False
    sucesso = True
    for numero in WHATSAPP_DESTINATARIOS:
        try:
            with open(caminho_pdf, "rb") as arquivo:
                r = requests.post(f"{BASE_URL}/messages/document", files={"filename": arquivo}, data={"token": ULTRAMSG_TOKEN, "to": numero, "caption": legenda}, timeout=40)
            print(r.text)
            if r.status_code != 200:
                sucesso = False
        except Exception as erro:
            print(erro)
            sucesso = False
    return sucesso


def bloco_cabecalho(titulo, numero, prioridade=None):
    extra = f"\nPrioridade: {emoji_prioridade(prioridade)} *{prioridade.upper()}*" if prioridade else ""
    return f"{titulo}\n\nPedido: *{numero}*{extra}"


def mensagem_pedido_criado(numero, pedido_id, usuario, fornecedor, valor_total, prioridade):
    return f"""{bloco_cabecalho('🛒 *NOVO PEDIDO DE COMPRA*', numero, prioridade)}

Solicitante: {usuario}
Fornecedor: {fornecedor}
Valor total: *{valor_total}*

Status: 🟡 *ABERTO*

🔗 Acessar pedido:
{link_pedido(pedido_id)}"""


def mensagem_status_alterado(numero, pedido_id, status, usuario, prioridade="Normal"):
    return f"""{bloco_cabecalho('🔔 *ATUALIZAÇÃO DE PEDIDO*', numero, prioridade)}

Novo status: {emoji_status(status)} *{status.upper()}*
Alterado por: {usuario}

🔗 Acessar pedido:
{link_pedido(pedido_id)}"""


def mensagem_pedido_editado(numero, pedido_id, usuario, prioridade="Normal"):
    return f"""{bloco_cabecalho('✏️ *PEDIDO EDITADO*', numero, prioridade)}

Editado por: {usuario}

🔗 Acessar pedido:
{link_pedido(pedido_id)}"""


def mensagem_pedido_excluido(numero, usuario):
    return f"""🗑️ *PEDIDO EXCLUÍDO*

Pedido: *{numero}*
Excluído por: {usuario}"""
