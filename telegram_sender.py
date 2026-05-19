import os
import requests
from utils import get_config

TELEGRAM_BOT_TOKEN = str(get_config("TELEGRAM_BOT_TOKEN", ""))
TELEGRAM_CHAT_ID = str(get_config("TELEGRAM_CHAT_ID", ""))
TELEGRAM_ATIVO = str(get_config("TELEGRAM_ATIVO", "SIM")).upper() == "SIM"


def telegram_configurado():
    return bool(TELEGRAM_ATIVO and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def enviar_telegram(mensagem: str):
    if not telegram_configurado():
        print("Telegram não configurado")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code == 200 and resp.json().get("ok"):
            return True
        print("Erro Telegram:", resp.status_code, resp.text)
        return False
    except Exception as erro:
        print("Erro ao enviar Telegram:", erro)
        return False


def enviar_telegram_documento(caminho_arquivo: str, legenda: str = ""):
    """Envia documento/anexo para o grupo do Telegram."""
    if not telegram_configurado():
        print("Telegram não configurado")
        return False

    if not caminho_arquivo:
        print("Arquivo não informado para Telegram")
        return False

    if not os.path.exists(caminho_arquivo):
        print(f"Arquivo não encontrado para Telegram: {caminho_arquivo}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"

    try:
        with open(caminho_arquivo, "rb") as arquivo:
            files = {"document": arquivo}
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": legenda or "Arquivo anexado",
                "parse_mode": "HTML",
            }
            resp = requests.post(url, data=data, files=files, timeout=60)

        if resp.status_code == 200 and resp.json().get("ok"):
            return True

        print("Erro Telegram documento:", resp.status_code, resp.text)
        return False
    except Exception as erro:
        print("Erro ao enviar documento Telegram:", erro)
        return False


def enviar_telegram_com_anexo(mensagem: str, caminho_arquivo: str | None = None, legenda: str = ""):
    """Envia a mensagem e, se houver arquivo, envia o documento em seguida."""
    ok_msg = enviar_telegram(mensagem)
    ok_doc = True

    if caminho_arquivo:
        ok_doc = enviar_telegram_documento(caminho_arquivo, legenda or "📎 Orçamento / anexo do pedido")

    return ok_msg and ok_doc
