import os
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def get_config(nome, padrao=""):
    try:
        if nome in st.secrets:
            return st.secrets[nome]
    except Exception:
        pass
    return os.getenv(nome, padrao)


APP_BASE_URL = str(get_config("APP_BASE_URL", "http://localhost:8501")).rstrip("/")


def agora():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def formatar_produto_id(id_produto):
    return f"PROD-{int(id_produto):06d}"


def formatar_pedido_id(id_pedido):
    return f"PC-{int(id_pedido):06d}"


def valor_moeda(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def link_pedido(id_pedido):
    return f"{APP_BASE_URL}?pedido={id_pedido}"


def emoji_status(status):
    return {"Aberto":"🟡","Aprovado":"🟢","Comprado":"🔵","Recebido":"📦","Cancelado":"🔴","Editado":"✏️","Excluído":"🗑️"}.get(status,"🔔")


def emoji_prioridade(prioridade):
    return {"Baixa":"🟢","Normal":"⚪","Alta":"🟠","Urgente":"🔴"}.get(prioridade,"⚪")
