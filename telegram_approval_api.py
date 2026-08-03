import os
from datetime import datetime
from typing import Any

import requests
from fastapi import FastAPI, Header, HTTPException, Request
from sqlalchemy import create_engine, text

from functools import lru_cache
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("America/Sao_Paulo")

PLANTA_PADRAO = "IBRAC"

PLANTAS_DB = {
    "IBRAC": {
        "label": "IBRAC",
        "env": "ALMOXARIFADO_URL_IBRAC",
    },
    "CORI": {
        "label": "CORI",
        "env": "ALMOXARIFADO_URL_CORI",
    },
    "CORI_TRES_LAGOAS": {
        "label": "CORI TRÊS LAGOAS",
        "env": "ALMOXARIFADO_URL_CORI_TRES_LAGOAS",
    },
}


def now_br() -> datetime:
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


def normalizar_planta(valor: str | None) -> str:
    planta = str(valor or PLANTA_PADRAO).strip().upper()
    planta = planta.replace("-", "_").replace(" ", "_")

    aliases = {
        "CORI_TL": "CORI_TRES_LAGOAS",
        "CORI_3_LAGOAS": "CORI_TRES_LAGOAS",
        "CORI_TRESLAGOAS": "CORI_TRES_LAGOAS",
    }

    planta = aliases.get(planta, planta)

    if planta not in PLANTAS_DB:
        raise ValueError(f"Planta inválida: {planta}")

    return planta


def get_database_url(planta: str) -> str:
    planta = normalizar_planta(planta)
    env_name = PLANTAS_DB[planta]["env"]

    db_url = str(os.getenv(env_name, "")).strip()

    if not db_url:
        db_url = str(os.getenv("ALMOXARIFADO_URL", "")).strip()

    if not db_url:
        raise RuntimeError(
            f"URL do banco não configurada para {planta}. "
            f"Variável esperada: {env_name}"
        )

    return db_url


@lru_cache(maxsize=3)
def get_engine_for_plant(planta: str):
    return create_engine(
        get_database_url(planta),
        pool_pre_ping=True,
        pool_recycle=280,
        future=True,
    )


BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_SECRET = os.environ["TELEGRAM_WEBHOOK_SECRET"]
REJECT_STATUS = os.getenv("TELEGRAM_REJECT_STATUS", "Cancelado")


app = FastAPI(title="StockPro Telegram Approval API")


def bot_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram API error"))
    return data


def answer_callback(callback_query_id: str, message: str, alert: bool = False) -> None:
    bot_api(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_query_id,
            "text": message,
            "show_alert": alert,
            "cache_time": 0,
        },
    )


def find_approver(conn, telegram_user_id: int):
    return (
        conn.execute(
            text("""
            SELECT id, usuario_sistema, nome, pode_aprovar, ativo
            FROM telegram_aprovadores
            WHERE telegram_user_id = :telegram_user_id
            LIMIT 1
            """),
            {"telegram_user_id": telegram_user_id},
        )
        .mappings()
        .first()
    )


def register_event(
    conn,
    pedido_id: int,
    action: str,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    chat_id: int | None,
    message_id: int | None,
    result: str,
    details: str = "",
) -> None:
    conn.execute(
        text("""
            INSERT INTO telegram_aprovacao_eventos
            (
                pedido_id, acao, telegram_user_id, telegram_username,
                telegram_nome, chat_id, message_id, resultado,
                detalhes, criado_em
            )
            VALUES
            (
                :pedido_id, :acao, :telegram_user_id, :telegram_username,
                :telegram_nome, :chat_id, :message_id, :resultado,
                :detalhes, :criado_em
            )
            """),
        {
            "pedido_id": pedido_id,
            "acao": action,
            "telegram_user_id": telegram_user_id,
            "telegram_username": username,
            "telegram_nome": first_name,
            "chat_id": chat_id,
            "message_id": message_id,
            "resultado": result,
            "detalhes": details,
            "criado_em": now_br(),
        },
    )


def edit_decision_message(
    chat_id: int,
    message_id: int,
    original_text: str,
    decision_text: str,
) -> None:
    bot_api(
        "editMessageText",
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": f"{original_text}\n\n{decision_text}",
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": []},
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    update = await request.json()

    # Ajuda a descobrir o próprio ID do Telegram.
    message = update.get("message")
    if message and str(message.get("text", "")).strip() in {"/start", "/id"}:
        user = message.get("from", {})
        chat = message.get("chat", {})
        bot_api(
            "sendMessage",
            {
                "chat_id": chat.get("id"),
                "text": (
                    "Seu ID do Telegram é:\n"
                    f"<code>{user.get('id')}</code>\n\n"
                    "Informe este número ao administrador do StockPro."
                ),
                "parse_mode": "HTML",
            },
        )
        return {"ok": True}

    callback = update.get("callback_query")
    if not callback:
        return {"ok": True}

    callback_id = str(callback["id"])
    data = str(callback.get("data") or "")
    user = callback.get("from") or {}
    callback_message = callback.get("message") or {}
    chat = callback_message.get("chat") or {}

    try:
        action, planta_raw, pedido_raw = data.split(":", 2)
        planta = normalizar_planta(planta_raw)
        pedido_id = int(pedido_raw)
    except (ValueError, TypeError):
        answer_callback(callback_id, "Comando inválido.", alert=True)
        return {"ok": True}

    if action not in {"approve", "reject"}:
        answer_callback(callback_id, "Ação inválida.", alert=True)
        return {"ok": True}

    telegram_user_id = int(user["id"])
    username = user.get("username")
    first_name = user.get("first_name")
    chat_id = chat.get("id")
    message_id = callback_message.get("message_id")
    original_text = str(callback_message.get("text") or "")

    engine = get_engine_for_plant(planta)
    with engine.begin() as conn:
        approver = find_approver(conn, telegram_user_id)
        if not approver or not approver["ativo"] or not approver["pode_aprovar"]:
            register_event(
                conn,
                pedido_id,
                action,
                telegram_user_id,
                username,
                first_name,
                chat_id,
                message_id,
                "NEGADO",
                "Telegram ID sem permissão de aprovação",
            )
            answer_callback(
                callback_id, "Você não possui permissão para aprovar.", alert=True
            )
            return {"ok": True}

        pedido = (
            conn.execute(
                text(
                    "SELECT id, numero, status FROM pedidos WHERE id = :id FOR UPDATE"
                ),
                {"id": pedido_id},
            )
            .mappings()
            .first()
        )

        if not pedido:
            answer_callback(callback_id, "Pedido não encontrado.", alert=True)
            return {"ok": True}

        if pedido["status"] != "Aberto":
            register_event(
                conn,
                pedido_id,
                action,
                telegram_user_id,
                username,
                first_name,
                chat_id,
                message_id,
                "IGNORADO",
                f"Pedido já estava em status {pedido['status']}",
            )
            answer_callback(
                callback_id,
                f"Pedido já está em '{pedido['status']}'.",
                alert=True,
            )
            return {"ok": True}

        now = now_br()
        if action == "approve":
            new_status = "Aprovado"
            conn.execute(
                text("""
                    UPDATE pedidos
                    SET status = 'Aprovado',
                        aprovado_por = :usuario,
                        data_aprovacao = :agora,
                        observacao = CONCAT(
                            COALESCE(observacao, ''),
                            :log
                        )
                    WHERE id = :id
                    """),
                {
                    "id": pedido_id,
                    "usuario": approver["usuario_sistema"],
                    "agora": now,
                    "log": (
                        f"\n\n[{now:%d/%m/%Y %H:%M:%S}] Pedido aprovado "
                        f"via Telegram por {approver['usuario_sistema']} "
                        f"(Telegram ID {telegram_user_id})."
                    ),
                },
            )
            decision = (
                "✅ <b>APROVADO</b>\n"
                f"Por: {approver['nome'] or approver['usuario_sistema']}\n"
                f"Data: {now:%d/%m/%Y %H:%M}"
            )
        else:
            new_status = REJECT_STATUS
            conn.execute(
                text("""
                    UPDATE pedidos
                    SET status = :status,
                        cancelado_por = :usuario,
                        data_cancelamento = :agora,
                        observacao = CONCAT(
                            COALESCE(observacao, ''),
                            :log
                        )
                    WHERE id = :id
                    """),
                {
                    "id": pedido_id,
                    "status": new_status,
                    "usuario": approver["usuario_sistema"],
                    "agora": now,
                    "log": (
                        f"\n\n[{now:%d/%m/%Y %H:%M:%S}] Pedido recusado "
                        f"via Telegram por {approver['usuario_sistema']} "
                        f"(Telegram ID {telegram_user_id})."
                    ),
                },
            )
            decision = (
                "❌ <b>RECUSADO</b>\n"
                f"Por: {approver['nome'] or approver['usuario_sistema']}\n"
                f"Data: {now:%d/%m/%Y %H:%M}"
            )

        register_event(
            conn,
            pedido_id,
            action,
            telegram_user_id,
            username,
            first_name,
            chat_id,
            message_id,
            "SUCESSO",
            f"Novo status: {new_status}",
        )

    answer_callback(callback_id, "Decisão registrada.")
    if chat_id is not None and message_id is not None:
        edit_decision_message(chat_id, message_id, original_text, decision)

    return {"ok": True}
