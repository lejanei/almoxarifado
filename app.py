import os, io, base64, hashlib, html, unicodedata
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
import shop_manager_app as shop_manager
import producao_app as producao
import streamlit.components.v1 as components
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
    PageBreak,
    KeepTogether,
)

try:
    from telegram_sender import enviar_telegram as enviar_telegram_configurado
except Exception:
    enviar_telegram_configurado = None

DEFAULT_DB_URL = "mysql+pymysql://ljsyst02_adm:vinimalu121924@ljsystem.com.br/ljsyst02_almoxarifado?charset=utf8mb4"
APP_NAME = "StockPro Manutenção"
APP_SUBTITLE = "Controle de Estoque e Manutenção"
LOGO_PATH = Path(__file__).parent / "assets" / "logo_stockpro.svg"

APP_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def now_br():
    """Retorna data/hora local de Brasília sem timezone para salvar no MySQL DATETIME."""
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


def format_datetime_br(value):
    """Formata DATETIME do banco para exibição padrão Brasil."""
    if value is None or pd.isna(value):
        return ""
    try:
        return pd.to_datetime(value).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)


PLANTA_PADRAO = "IBRAC"

PLANTAS_DB = {
    "IBRAC": {
        "label": "IBRAC",
        "env": "ALMOXARIFADO_URL_IBRAC",
        "telegram_manutencao_env": "TELEGRAM_CHAT_ID_MANUTENCAO_IBRAC",
    },
    "CORI": {
        "label": "CORI",
        "env": "ALMOXARIFADO_URL_CORI",
        "telegram_manutencao_env": "TELEGRAM_CHAT_ID_MANUTENCAO_CORI",
    },
    "CORI_TRES_LAGOAS": {
        "label": "CORI TRÊS LAGOAS",
        "env": "ALMOXARIFADO_URL_CORI_TRES_LAGOAS",
        "telegram_manutencao_env": "TELEGRAM_CHAT_ID_MANUTENCAO_CORI_TRES_LAGOAS",
    },
}

TIPOS_MANUTENCAO = [
    "Corretiva",
    "Melhoria",
    "Rotina",
    "Rotina Preventiva",
    "Qualidade",
]


def normalizar_chave_planta(valor):
    texto = str(valor or PLANTA_PADRAO).strip().upper()
    texto = (
        unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    )
    texto = texto.replace("-", "_").replace(" ", "_")
    texto = "_".join(parte for parte in texto.split("_") if parte)

    aliases = {
        "CORI_TL": "CORI_TRES_LAGOAS",
        "CORI_3_LAGOAS": "CORI_TRES_LAGOAS",
        "CORI_TRES_LAGOAS": "CORI_TRES_LAGOAS",
        "CORI_TRESLAGOAS": "CORI_TRES_LAGOAS",
    }
    texto = aliases.get(texto, texto)
    return texto if texto in PLANTAS_DB else PLANTA_PADRAO


def get_planta_label(planta=None):
    chave = normalizar_chave_planta(
        planta or st.session_state.get("planta", PLANTA_PADRAO)
    )
    return PLANTAS_DB.get(chave, PLANTAS_DB[PLANTA_PADRAO])["label"]


def get_config_value(nome, default=""):
    v = os.getenv(nome)
    if v:
        return v
    try:
        if nome in st.secrets:
            return st.secrets[nome]
    except Exception:
        pass
    return default


def get_telegram_chat_id_manutencao_por_planta(planta=None):
    """Retorna o grupo Telegram de manutenção conforme a planta logada.

    Fallbacks:
    1) TELEGRAM_CHAT_ID_MANUTENCAO_<PLANTA>
    2) TELEGRAM_CHAT_ID_MANUTENCAO
    3) TELEGRAM_CHAT_ID
    """
    chave = normalizar_chave_planta(
        planta or st.session_state.get("planta", PLANTA_PADRAO)
    )
    planta_cfg = PLANTAS_DB.get(chave, PLANTAS_DB[PLANTA_PADRAO])
    env_name = planta_cfg.get("telegram_manutencao_env")

    if env_name:
        chat_id = str(get_config_value(env_name, "")).strip()
        if chat_id:
            return chat_id

    chat_id_manutencao = str(
        get_config_value("TELEGRAM_CHAT_ID_MANUTENCAO", "")
    ).strip()
    if chat_id_manutencao:
        return chat_id_manutencao

    return str(get_config_value("TELEGRAM_CHAT_ID", "")).strip()


def enviar_telegram_app(mensagem, chat_id=None):
    """Envia Telegram usando o mesmo padrão do pedido de compra, com fallback interno."""
    if enviar_telegram_configurado:
        try:
            return enviar_telegram_configurado(mensagem, chat_id=chat_id)
        except TypeError:
            return enviar_telegram_configurado(mensagem)

    token = str(get_config_value("TELEGRAM_BOT_TOKEN", ""))
    chat_id_default = str(get_config_value("TELEGRAM_CHAT_ID", ""))
    ativo = str(get_config_value("TELEGRAM_ATIVO", "SIM")).upper() == "SIM"
    if not ativo or not token or not chat_id_default:
        print("Telegram não configurado")
        return False

    try:
        import requests

        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": (chat_id or chat_id_default),
                "text": mensagem,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            return True
        print("Erro Telegram:", resp.status_code, resp.text)
        return False
    except Exception as erro:
        print("Erro ao enviar Telegram:", erro)
        return False


def get_cost_center_name_by_id(centro_custo_id):
    if not centro_custo_id:
        return "Não informado"
    try:
        df = fetch_df(
            "SELECT nome FROM centros_custo WHERE id=:id LIMIT 1",
            {"id": int(centro_custo_id)},
        )
        if not df.empty:
            return str(df.iloc[0]["nome"])
    except Exception:
        pass
    return "Não informado"


def notificar_telegram_nova_ordem(
    order_id,
    tipo,
    opened_by,
    maquina,
    centro_custo,
    start_dt,
    end_dt,
    problema,
    status,
    solucao="",
    planta=None,
):
    tipo_txt = "Preventiva" if str(tipo).upper() == "PREVENTIVA" else "Corretiva"
    planta_chave = normalizar_chave_planta(
        planta or st.session_state.get("planta", PLANTA_PADRAO)
    )
    planta_label = get_planta_label(planta_chave)
    inicio_txt = format_datetime_br(start_dt)
    fim_txt = format_datetime_br(end_dt) if end_dt else "Não informado"
    problema_txt = html.escape(str(problema or "Não informado"))
    solucao_txt = html.escape(str(solucao or ""))

    mensagem = f"""
🛠️ <b>Nova Ordem de Manutenção Aberta</b>

📌 <b>OS:</b> #{int(order_id)}
🏢 <b>Planta:</b> {html.escape(str(planta_label))}
🔧 <b>Tipo:</b> {html.escape(tipo_txt)}
🏭 <b>Máquina:</b> {html.escape(str(maquina or 'Não informado'))}
🏷️ <b>Centro de custo:</b> {html.escape(str(centro_custo or 'Não informado'))}
⚠️ <b>Status:</b> {html.escape(str(status or 'Aberta'))}
👤 <b>Aberta por:</b> {html.escape(str(opened_by or 'Sistema'))}
📅 <b>Início:</b> {html.escape(str(inicio_txt))}
📅 <b>Fim:</b> {html.escape(str(fim_txt))}

📋 <b>Descrição:</b>
{problema_txt}
""".strip()

    if solucao_txt:
        mensagem += f"\n\n✅ <b>Solução:</b>\n{solucao_txt}"

    chat_id_manutencao = get_telegram_chat_id_manutencao_por_planta(planta_chave)
    return enviar_telegram_app(mensagem, chat_id=chat_id_manutencao)


def get_database_url(planta=None):
    planta = normalizar_chave_planta(
        planta or st.session_state.get("planta", PLANTA_PADRAO)
    )

    # Primeiro procura variável específica da planta.
    planta_cfg = PLANTAS_DB.get(planta, PLANTAS_DB[PLANTA_PADRAO])
    secret_name = planta_cfg.get("env")
    if secret_name:
        v = get_config_value(secret_name, "")
        if v:
            return v

    # Fallback compatível com versão antiga.
    v = get_config_value("ALMOXARIFADO_URL", "")
    if v:
        return v

    return DEFAULT_DB_URL


def get_current_database_url():
    return get_database_url(st.session_state.get("planta", PLANTA_PADRAO))


DATABASE_URL = get_database_url(PLANTA_PADRAO)
st.set_page_config(page_title=APP_NAME, page_icon="📦", layout="wide")


def load_logo_base64():
    try:
        return base64.b64encode(LOGO_PATH.read_bytes()).decode("utf-8")
    except Exception:
        return ""


logo_b64 = load_logo_base64()

st.markdown(
    """
<style>
:root { --border: rgba(148,163,184,.18); --text:#e5e7eb; --muted:#94a3b8; --brand:#0ea5a4; --brand2:#14b8a6; }
html,body,[data-testid="stAppViewContainer"],[data-testid="stApp"]{background:linear-gradient(180deg,#0b1220 0%,#0a0f1c 100%);color:var(--text);}
.block-container{padding-top:1rem;padding-bottom:1rem;} header[data-testid="stHeader"]{background:transparent;}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#0f172a 0%,#111827 100%);border-right:1px solid var(--border);}
section[data-testid="stSidebar"] *{color:var(--text)!important;}
.hero-card,.section-card,.login-wrap,div[data-testid="stMetric"],div[data-testid="stDataFrame"]{background:linear-gradient(180deg,rgba(31,41,55,.96) 0%,rgba(17,24,39,.96) 100%)!important;border:1px solid var(--border)!important;color:var(--text)!important;border-radius:18px;box-shadow:0 14px 30px rgba(0,0,0,.18);} .hero-card{border-left:4px solid var(--brand2)!important;} div[data-testid="stMetric"]{border-top:3px solid var(--brand)!important;}
.hero-card{padding:1.2rem 1.3rem;border-radius:22px;margin-bottom:1rem;}
.brand-chip{display:inline-block;padding:.34rem .78rem;border-radius:5px;background:rgba(20,184,166,.14);color:#99f6e4!important;font-size:.84rem;font-weight:700;margin-bottom:.45rem;border:1px solid rgba(20,184,166,.18);}
.brand-title{font-size:1.7rem;font-weight:800;color:#f8fafc!important;margin:0;}
.brand-subtitle,.small-muted{color:var(--muted)!important;}
.sidebar-brand{padding:.9rem 1rem;border:1px solid rgba(255,255,255,.08);border-radius:18px;background:linear-gradient(180deg,rgba(30,41,59,.65) 0%,rgba(15,23,42,.55) 100%);margin-bottom:.9rem;}
.stButton > button,.stDownloadButton > button{border-radius:12px;font-weight:700;border:1px solid rgba(20,184,166,.22);background:linear-gradient(90deg,var(--brand) 0%,var(--brand2) 100%);color:white!important;}
.stTextInput input,.stTextArea textarea,.stNumberInput input,div[data-baseweb="select"] > div,[data-testid="stDateInputField"]{background:rgba(15,23,42,.85)!important;color:var(--text)!important;border:1px solid var(--border)!important;border-radius:10px!important;}
[data-baseweb="select"] *{color:var(--text)!important;}
</style>
""",
    unsafe_allow_html=True,
)


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def format_number(v):
    try:
        return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return v


def df_to_excel_bytes(sheets):
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as w:
        for n, df in sheets.items():
            df.to_excel(w, index=False, sheet_name=n[:31])
    return b.getvalue()


def app_header(title, subtitle=""):
    logo_html = (
        f'<img src="data:image/svg+xml;base64,{logo_b64}" style="height:66px;">'
        if logo_b64
        else "📦"
    )
    st.markdown(
        f"""<div class="hero-card">            
            <h1 class="brand-title">{APP_NAME}</h1>
            <h3 class="brand-title">{title}</h3>
            <p class="brand-subtitle">{subtitle or APP_SUBTITLE}</p></div></div></div>""",
        unsafe_allow_html=True,
    )


def combine_date_time(d, t):
    return datetime.combine(d, t)


def format_duration(start_dt, end_dt):
    if pd.isna(start_dt) or pd.isna(end_dt):
        return ""
    delta = pd.to_datetime(end_dt) - pd.to_datetime(start_dt)
    mins = int(delta.total_seconds() // 60)
    if mins < 0:
        return ""
    return f"{mins//60}h {mins%60}min"


@st.cache_resource
def get_engine_cached(db_url):
    return create_engine(db_url, pool_pre_ping=True, pool_recycle=3600, future=True)


def get_engine():
    return get_engine_cached(get_current_database_url())


def init_db():
    ddls = [
        """CREATE TABLE IF NOT EXISTS centros_custo (id INT AUTO_INCREMENT PRIMARY KEY,nome VARCHAR(150) NOT NULL UNIQUE,descricao TEXT,ativo TINYINT(1) NOT NULL DEFAULT 1,criado_em VARCHAR(50)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS orcamentos_mensais (id INT AUTO_INCREMENT PRIMARY KEY,ano INT NOT NULL,mes INT NOT NULL,centro_custo_id INT NULL,valor_orcado DECIMAL(15,2) NOT NULL DEFAULT 0,alerta_percentual DECIMAL(5,2) NOT NULL DEFAULT 80,criado_em VARCHAR(50),atualizado_em VARCHAR(50),UNIQUE KEY uq_orc_mes_cc (ano,mes,centro_custo_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY,nome VARCHAR(150) NOT NULL,usuario VARCHAR(80) NOT NULL UNIQUE,email VARCHAR(150),perfil VARCHAR(50),senha_hash VARCHAR(64),ativo TINYINT(1) NOT NULL DEFAULT 1,criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS products (id INT AUTO_INCREMENT PRIMARY KEY,codigo VARCHAR(80) NULL UNIQUE,nome VARCHAR(150) NOT NULL,descricao TEXT,unidade VARCHAR(20) NOT NULL DEFAULT 'UN',estoque_atual DECIMAL(18,3) NOT NULL DEFAULT 0,estoque_minimo DECIMAL(18,3) NOT NULL DEFAULT 0,
            valor_unitario DECIMAL(18,4) NOT NULL DEFAULT 0,criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS movements (id INT AUTO_INCREMENT PRIMARY KEY,produto_id INT NOT NULL,tipo VARCHAR(30) NOT NULL,quantidade DECIMAL(18,3) NOT NULL,observacao TEXT,usuario_lancamento VARCHAR(150),criado_em DATETIME NOT NULL,CONSTRAINT fk_movements_product FOREIGN KEY (produto_id) REFERENCES products(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS machines (id INT AUTO_INCREMENT PRIMARY KEY,nome VARCHAR(150) NOT NULL,status VARCHAR(50) NOT NULL DEFAULT 'Ativa',criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS problem_locations ( id INT AUTO_INCREMENT PRIMARY KEY,nome VARCHAR(150) NOT NULL, descricao TEXT,ativo TINYINT(1) NOT NULL DEFAULT 1,created_at DATETIME NOT NULL,updated_at DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY,nome VARCHAR(150) NOT NULL,setor VARCHAR(100),funcao VARCHAR(100),criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS service_orders (id INT AUTO_INCREMENT PRIMARY KEY,tipo VARCHAR(20) NOT NULL,opened_by VARCHAR(150) NOT NULL,machine_id INT NOT NULL,start_datetime DATETIME NOT NULL,end_datetime DATETIME NULL,problem_description TEXT,status VARCHAR(50) NOT NULL DEFAULT 'Aberta',solution_description TEXT,created_at DATETIME NOT NULL,updated_at DATETIME NULL,CONSTRAINT fk_so_machine FOREIGN KEY (machine_id) REFERENCES machines(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS service_order_employees (id INT AUTO_INCREMENT PRIMARY KEY,order_id INT NOT NULL,employee_id INT NOT NULL,start_datetime DATETIME NOT NULL,end_datetime DATETIME NULL,created_at DATETIME NOT NULL,CONSTRAINT fk_soe_order FOREIGN KEY (order_id) REFERENCES service_orders(id),CONSTRAINT fk_soe_employee FOREIGN KEY (employee_id) REFERENCES employees(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS audit_logs (id INT AUTO_INCREMENT PRIMARY KEY,usuario VARCHAR(150) NOT NULL, acao VARCHAR(150) NOT NULL,entidade VARCHAR(100),entidade_id VARCHAR(100),detalhes TEXT,criado_em DATETIME NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS service_order_parts (id INT AUTO_INCREMENT PRIMARY KEY,order_id INT NOT NULL,product_id INT NOT NULL,quantidade DECIMAL(18,3) NOT NULL,created_at DATETIME NOT NULL,CONSTRAINT fk_sop_order FOREIGN KEY (order_id) REFERENCES service_orders(id),CONSTRAINT fk_sop_product FOREIGN KEY (product_id) REFERENCES products(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS pmoc_maquinas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            codigo VARCHAR(30) NOT NULL UNIQUE,
            marca VARCHAR(100),
            modelo VARCHAR(100),
            capacidade INT,
            unidade_capacidade VARCHAR(10) DEFAULT 'BTU',
            local VARCHAR(200),
            status VARCHAR(20) DEFAULT 'ATIVA',
            periodicidade_dias INT NOT NULL DEFAULT 90,
            observacao TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS pmoc_preventivas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero VARCHAR(30),
            maquina_id INT NOT NULL,
            tipo_servico VARCHAR(30) DEFAULT 'HIGIENIZACAO',
            data_programada DATE,
            data_execucao DATE NULL,
            status VARCHAR(20) DEFAULT 'ABERTA',
            gerou_proxima TINYINT(1) NOT NULL DEFAULT 0,
            preventiva_origem_id INT NULL,
            observacao TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NULL,
            INDEX idx_pmoc_preventiva_maquina (maquina_id),
            CONSTRAINT fk_pmoc_preventiva_maquina
                FOREIGN KEY (maquina_id)
                REFERENCES pmoc_maquinas(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS pmoc_preventiva_executores (
            id INT AUTO_INCREMENT PRIMARY KEY,
            preventiva_id INT NOT NULL,
            funcionario_id INT NOT NULL,
            INDEX idx_pmoc_prev_exec_preventiva (preventiva_id),
            INDEX idx_pmoc_prev_exec_funcionario (funcionario_id),
            CONSTRAINT fk_pmoc_prev_exec_preventiva
                FOREIGN KEY (preventiva_id)
                REFERENCES pmoc_preventivas(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_pmoc_prev_exec_funcionario
                FOREIGN KEY (funcionario_id)
                REFERENCES employees(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS pmoc_preventiva_fotos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            preventiva_id INT NOT NULL,
            nome_arquivo VARCHAR(255) NOT NULL,
            caminho VARCHAR(500) NOT NULL,
            enviado_por VARCHAR(100),
            data_envio DATETIME NOT NULL,
            INDEX idx_pmoc_foto_preventiva (preventiva_id),
            CONSTRAINT fk_pmoc_foto_preventiva
                FOREIGN KEY (preventiva_id)
                REFERENCES pmoc_preventivas(id)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS pmoc_corretivas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero VARCHAR(30),
            maquina_id INT NOT NULL,
            service_order_id INT NOT NULL,
            status VARCHAR(20) DEFAULT 'ABERTA',
            observacao TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NULL,
            INDEX idx_pmoc_corretiva_maquina (maquina_id),
            INDEX idx_pmoc_corretiva_os (service_order_id),
            UNIQUE KEY uq_pmoc_service_order (service_order_id),
            CONSTRAINT fk_pmoc_corretiva_maquina
                FOREIGN KEY (maquina_id)
                REFERENCES pmoc_maquinas(id),
            CONSTRAINT fk_pmoc_corretiva_os
                FOREIGN KEY (service_order_id)
                REFERENCES service_orders(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS pmoc_preventiva_checklist (
            id INT AUTO_INCREMENT PRIMARY KEY,
            preventiva_id INT NOT NULL,
            grupo VARCHAR(50) NOT NULL,
            item VARCHAR(255) NOT NULL,
            executado TINYINT(1) NOT NULL DEFAULT 0,
            observacao VARCHAR(500),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NULL,
            INDEX idx_pmoc_checklist_preventiva (preventiva_id),
            CONSTRAINT fk_pmoc_checklist_preventiva
                FOREIGN KEY (preventiva_id)
                REFERENCES pmoc_preventivas(id)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS pmoc_preventiva_medicoes (
            id INT AUTO_INCREMENT PRIMARY KEY,

            preventiva_id INT NOT NULL,

            temperatura_retorno DECIMAL(6,2),
            temperatura_insuflada DECIMAL(6,2),

            corrente DECIMAL(6,2),
            tensao DECIMAL(6,2),

            pressao_alta DECIMAL(6,2),
            pressao_baixa DECIMAL(6,2),

            observacao TEXT,

            created_at DATETIME NOT NULL,
            updated_at DATETIME NULL,

            UNIQUE KEY uk_pmoc_medicao (preventiva_id),

            CONSTRAINT fk_pmoc_medicao
                FOREIGN KEY (preventiva_id)
                REFERENCES pmoc_preventivas(id)
                ON DELETE CASCADE
        )
        ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS telegram_aprovadores (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario_sistema VARCHAR(100) NOT NULL,
            nome VARCHAR(150),
            telegram_user_id BIGINT NOT NULL UNIQUE,
            telegram_username VARCHAR(100),
            pode_aprovar TINYINT(1) NOT NULL DEFAULT 1,
            ativo TINYINT(1) NOT NULL DEFAULT 1,
            criado_em DATETIME NOT NULL,
            atualizado_em DATETIME NULL,
            INDEX idx_telegram_aprovador_usuario (usuario_sistema)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS telegram_aprovacao_eventos (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            pedido_id INT NOT NULL,
            acao VARCHAR(30) NOT NULL,
            telegram_user_id BIGINT NOT NULL,
            telegram_username VARCHAR(100),
            telegram_nome VARCHAR(150),
            chat_id BIGINT,
            message_id BIGINT,
            resultado VARCHAR(30) NOT NULL,
            detalhes VARCHAR(500),
            criado_em DATETIME NOT NULL,
            INDEX idx_tg_evento_pedido (pedido_id),
            INDEX idx_tg_evento_usuario (telegram_user_id),
            CONSTRAINT fk_tg_evento_pedido
                FOREIGN KEY (pedido_id)
                REFERENCES pedidos(id)
                ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    ]
    with get_engine().begin() as conn:
        for ddl in ddls:
            conn.execute(text(ddl))
        for sql in [
            "ALTER TABLE products ADD COLUMN centro_custo_id INT NULL",
            "ALTER TABLE products ADD COLUMN valor_unitario DECIMAL(18,4) NOT NULL DEFAULT 0",
            "ALTER TABLE service_orders ADD COLUMN centro_custo_id INT NULL",
            "ALTER TABLE pedidos ADD COLUMN centro_custo_id INT NULL",
            "ALTER TABLE pedidos ADD COLUMN tipo_orcamento VARCHAR(20) NOT NULL DEFAULT 'OPEX'",
            "ALTER TABLE orcamentos_mensais ADD COLUMN tipo_orcamento VARCHAR(20) NOT NULL DEFAULT 'OPEX'",
            "ALTER TABLE service_orders ADD COLUMN gera_parada TINYINT(1) NOT NULL DEFAULT 1",
            "ALTER TABLE service_orders ADD COLUMN tipo_manutencao VARCHAR(50) DEFAULT 'Corretiva'",
            "ALTER TABLE service_orders ADD COLUMN problem_location_id INT NULL",
            "ALTER TABLE pmoc_maquinas ADD COLUMN periodicidade_dias INT NOT NULL DEFAULT 90",
            "ALTER TABLE pmoc_preventivas ADD COLUMN gerou_proxima TINYINT(1) NOT NULL DEFAULT 0",
            "ALTER TABLE pmoc_preventivas ADD COLUMN preventiva_origem_id INT NULL",
        ]:
            try:
                conn.execute(text(sql))
            except Exception:
                pass


def fetch_df(q, p=None):
    with get_engine().connect() as conn:
        return pd.read_sql(text(q), conn, params=p or {})


def execute(q, p=None):
    with get_engine().begin() as conn:
        return conn.execute(text(q), p or {})


def log_action(usuario, acao, entidade="", entidade_id="", detalhes=""):
    try:
        execute(
            "INSERT INTO audit_logs (usuario, acao, entidade, entidade_id, detalhes, criado_em) VALUES (:usuario, :acao, :entidade, :entidade_id, :detalhes, :criado_em)",
            {
                "usuario": usuario,
                "acao": acao,
                "entidade": entidade,
                "entidade_id": str(entidade_id) if entidade_id != "" else "",
                "detalhes": detalhes,
                "criado_em": now_br(),
            },
        )
    except Exception:
        pass


def get_audit_logs(limit=200, usuario=None):
    params = {"limite": int(limit)}
    sql = "SELECT id, usuario, acao, entidade, entidade_id, detalhes, criado_em FROM audit_logs"
    if usuario:
        sql += " WHERE usuario = :usuario"
        params["usuario"] = usuario
    sql += " ORDER BY id DESC LIMIT :limite"
    return fetch_df(sql, params)


def get_user_opened_orders(username):
    return fetch_df(
        "SELECT id, tipo, opened_by, machine_id, start_datetime, end_datetime, problem_description, gera_parada, status, solution_description, created_at, updated_at FROM service_orders WHERE opened_by = :username ORDER BY id DESC",
        {"username": username},
    )


def update_user_record(user_id, nome, usuario_login, email, perfil, ativo):
    execute(
        "UPDATE users SET nome=:nome, usuario=:usuario, email=:email, perfil=:perfil, ativo=:ativo, atualizado_em=:atualizado_em WHERE id=:id",
        {
            "id": int(user_id),
            "nome": nome.strip(),
            "usuario": usuario_login.strip(),
            "email": email.strip(),
            "perfil": perfil,
            "ativo": 1 if ativo else 0,
            "atualizado_em": now_br(),
        },
    )


def update_user_password(user_id, senha):
    execute(
        "UPDATE users SET senha_hash=:senha_hash, atualizado_em=:agora WHERE id=:id",
        {"id": int(user_id), "senha_hash": hash_password(senha), "agora": now_br()},
    )


def delete_user_record(user_id):
    execute("DELETE FROM users WHERE id = :id", {"id": int(user_id)})


def get_cost_centers(only_active=True):
    sql = "SELECT id,nome,descricao,ativo FROM centros_custo"
    if only_active:
        sql += " WHERE ativo=1"
    sql += " ORDER BY nome"
    return fetch_df(sql)


def select_cost_center(label="Centro de custo", key=None, allow_empty=True):
    centros = get_cost_centers()
    options = []
    if allow_empty:
        options.append("Sem centro de custo")
    if not centros.empty:
        options += [f"ID {int(r['id'])} - {r['nome']}" for _, r in centros.iterrows()]
    selected = st.selectbox(label, options or ["Sem centro de custo"], key=key)
    if selected == "Sem centro de custo":
        return None
    return int(selected.split(" - ")[0].replace("ID ", ""))


def select_cost_center_with_current(
    label="Centro de custo", current_id=None, key=None, allow_empty=True
):
    centros = get_cost_centers()
    options = []

    if allow_empty:
        options.append("Sem centro de custo")

    if not centros.empty:
        options += [f"ID {int(r['id'])} - {r['nome']}" for _, r in centros.iterrows()]

    index = 0

    current_valid = False
    try:
        current_valid = current_id is not None and not pd.isna(current_id)
    except Exception:
        current_valid = current_id is not None

    if current_valid and not centros.empty:
        try:
            current_int = int(float(current_id))
            for i, opt in enumerate(options):
                if opt.startswith(f"ID {current_int} -"):
                    index = i
                    break
        except Exception:
            index = 0

    selected = st.selectbox(
        label, options or ["Sem centro de custo"], index=index, key=key
    )

    if selected == "Sem centro de custo":
        return None

    return int(selected.split(" - ")[0].replace("ID ", ""))


def get_users():
    return fetch_df(
        "SELECT id,nome,usuario,email,perfil,ativo,criado_em,atualizado_em FROM users ORDER BY nome"
    )


def count_users():
    df = fetch_df("SELECT COUNT(*) AS total FROM users")
    return int(df.iloc[0]["total"]) if not df.empty else 0


def authenticate_user(usuario, senha):
    df = fetch_df(
        "SELECT id,nome,usuario,email,perfil,ativo,senha_hash FROM users WHERE usuario=:usuario LIMIT 1",
        {"usuario": usuario.strip()},
    )
    if df.empty:
        return None
    r = df.iloc[0]
    if int(r["ativo"]) != 1 or (r["senha_hash"] or "") != hash_password(senha):
        return None
    return {
        "id": int(r["id"]),
        "nome": r["nome"],
        "usuario": r["usuario"],
        "email": r["email"],
        "perfil": r["perfil"],
    }


def create_user(nome, usuario, email, perfil, senha, ativo=True):
    execute(
        "INSERT INTO users (nome,usuario,email,perfil,senha_hash,ativo,criado_em,atualizado_em) VALUES (:nome,:usuario,:email,:perfil,:senha_hash,:ativo,:criado_em,:atualizado_em)",
        {
            "nome": nome.strip(),
            "usuario": usuario.strip(),
            "email": email.strip(),
            "perfil": perfil,
            "senha_hash": hash_password(senha),
            "ativo": 1 if ativo else 0,
            "criado_em": now_br(),
            "atualizado_em": now_br(),
        },
    )
    usuario_logado = st.session_state.get("user") or {}
    log_action(
        usuario_logado.get("usuario", "sistema"),
        "Criou usuário",
        "users",
        usuario.strip(),
        f"Perfil: {perfil}",
    )


def get_products():
    return fetch_df(
        "SELECT p.id,p.nome,p.descricao,p.unidade,p.estoque_atual,p.estoque_minimo,p.valor_unitario,p.centro_custo_id,cc.nome AS centro_custo,p.criado_em,p.atualizado_em FROM products p LEFT JOIN centros_custo cc ON cc.id=p.centro_custo_id ORDER BY p.nome"
    )


def create_product(
    nome,
    descricao,
    unidade,
    estoque_inicial,
    estoque_minimo,
    centro_custo_id=None,
    valor_unitario=0,
):
    execute(
        "INSERT INTO products (codigo,nome,descricao,unidade,estoque_atual,estoque_minimo,valor_unitario,centro_custo_id,criado_em,atualizado_em) VALUES (NULL,:nome,:descricao,:unidade,:estoque_atual,:estoque_minimo,:valor_unitario,:centro_custo_id,:criado_em,:atualizado_em)",
        {
            "nome": nome.strip(),
            "descricao": descricao.strip(),
            "unidade": unidade,
            "estoque_atual": float(estoque_inicial),
            "estoque_minimo": float(estoque_minimo),
            "valor_unitario": float(valor_unitario or 0),
            "centro_custo_id": centro_custo_id,
            "criado_em": now_br(),
            "atualizado_em": now_br(),
        },
    )
    log_action(
        st.session_state.get("user", {}).get("usuario", "sistema"),
        "Criou produto",
        "products",
        nome.strip(),
        f"Estoque inicial: {estoque_inicial}",
    )


def calcular_custo_medio_entrada(
    estoque_atual, valor_atual, quantidade_entrada, valor_entrada
):
    estoque_atual = float(estoque_atual or 0)
    valor_atual = float(valor_atual or 0)
    quantidade_entrada = float(quantidade_entrada or 0)
    valor_entrada = float(valor_entrada or 0)

    if quantidade_entrada <= 0:
        return valor_atual

    if estoque_atual <= 0 or valor_atual <= 0:
        return valor_entrada

    estoque_final = estoque_atual + quantidade_entrada
    if estoque_final <= 0:
        return valor_entrada

    return (
        (estoque_atual * valor_atual) + (quantidade_entrada * valor_entrada)
    ) / estoque_final


def register_stock_movement(
    produto_id,
    tipo,
    quantidade,
    observacao,
    usuario_lancamento,
    valor_unitario_entrada=0,
):
    produto = fetch_df(
        "SELECT id, estoque_atual, valor_unitario FROM products WHERE id=:id",
        {"id": int(produto_id)},
    )

    if produto.empty:
        raise ValueError("Produto não encontrado.")

    estoque_atual = float(produto.iloc[0]["estoque_atual"] or 0)
    valor_atual = float(produto.iloc[0].get("valor_unitario", 0) or 0)
    quantidade = float(quantidade)
    tipo = str(tipo).upper()

    if tipo == "ENTRADA":
        novo_estoque = estoque_atual + quantidade
        novo_valor = calcular_custo_medio_entrada(
            estoque_atual,
            valor_atual,
            quantidade,
            valor_unitario_entrada,
        )
    else:
        if quantidade > estoque_atual:
            raise ValueError("Estoque insuficiente para saída.")
        novo_estoque = estoque_atual - quantidade
        novo_valor = valor_atual

    execute(
        """UPDATE products
              SET estoque_atual=:estoque,
                  valor_unitario=:valor_unitario,
                  atualizado_em=:agora
            WHERE id=:id""",
        {
            "id": int(produto_id),
            "estoque": novo_estoque,
            "valor_unitario": novo_valor,
            "agora": now_br(),
        },
    )

    execute(
        """INSERT INTO movements
           (produto_id,tipo,quantidade,observacao,usuario_lancamento,criado_em)
           VALUES (:produto_id,:tipo,:quantidade,:observacao,:usuario_lancamento,:criado_em)""",
        {
            "produto_id": int(produto_id),
            "tipo": tipo,
            "quantidade": quantidade,
            "observacao": observacao,
            "usuario_lancamento": usuario_lancamento,
            "criado_em": now_br(),
        },
    )


def update_product_record(
    product_id,
    nome,
    descricao,
    unidade,
    estoque_minimo,
    centro_custo_id=None,
    valor_unitario=0,
):
    execute(
        """UPDATE products
              SET nome=:nome,
                  descricao=:descricao,
                  unidade=:unidade,
                  estoque_minimo=:estoque_minimo,
                  centro_custo_id=:centro_custo_id,
                  valor_unitario=:valor_unitario,
                  atualizado_em=:agora
            WHERE id=:id""",
        {
            "id": int(product_id),
            "nome": nome.strip(),
            "descricao": descricao.strip(),
            "unidade": unidade,
            "estoque_minimo": float(estoque_minimo),
            "centro_custo_id": centro_custo_id,
            "valor_unitario": float(valor_unitario or 0),
            "agora": now_br(),
        },
    )


def delete_product_record(product_id):
    mov = fetch_df(
        "SELECT COUNT(*) AS total FROM movements WHERE produto_id = :id",
        {"id": int(product_id)},
    )
    if not mov.empty and int(mov.iloc[0]["total"]) > 0:
        raise ValueError("Este produto possui movimentações e não pode ser excluído.")
    uso = fetch_df(
        "SELECT COUNT(*) AS total FROM service_order_parts WHERE product_id = :id",
        {"id": int(product_id)},
    )
    if not uso.empty and int(uso.iloc[0]["total"]) > 0:
        raise ValueError(
            "Este produto já foi utilizado em ordens e não pode ser excluído."
        )
    execute("DELETE FROM products WHERE id = :id", {"id": int(product_id)})


def get_movements(limit=200):
    return fetch_df(
        "SELECT m.id,p.id AS produto_id,p.nome AS produto,m.tipo,m.quantidade,p.unidade,m.usuario_lancamento,m.observacao,m.criado_em FROM movements m INNER JOIN products p ON p.id=m.produto_id ORDER BY m.id DESC LIMIT :limite",
        {"limite": int(limit)},
    )


def get_critical_products():
    return fetch_df(
        "SELECT id,nome,unidade,estoque_atual,estoque_minimo,(estoque_minimo-estoque_atual) AS falta_para_minimo FROM products WHERE estoque_atual<=estoque_minimo ORDER BY falta_para_minimo DESC,nome"
    )


def get_machines():
    return fetch_df(
        "SELECT id,nome,status,criado_em,atualizado_em FROM machines ORDER BY nome"
    )


def create_machine(nome, status):
    execute(
        "INSERT INTO machines (nome,status,criado_em,atualizado_em) VALUES (:nome,:status,:criado_em,:atualizado_em)",
        {
            "nome": nome.strip(),
            "status": status,
            "criado_em": now_br(),
            "atualizado_em": now_br(),
        },
    )


def update_machine(machine_id, nome, status):
    execute(
        "UPDATE machines SET nome=:nome,status=:status,atualizado_em=:agora WHERE id=:id",
        {
            "id": machine_id,
            "nome": nome.strip(),
            "status": status,
            "agora": now_br(),
        },
    )
    log_action(
        st.session_state.get("user", {}).get("usuario", "sistema"),
        "Atualizou máquina",
        "machines",
        machine_id,
        nome.strip(),
    )


def delete_machine_record(machine_id):
    uso = fetch_df(
        "SELECT COUNT(*) AS total FROM service_orders WHERE machine_id = :id",
        {"id": int(machine_id)},
    )
    if not uso.empty and int(uso.iloc[0]["total"]) > 0:
        raise ValueError(
            "Esta máquina possui ordens vinculadas e não pode ser excluída."
        )
    execute("DELETE FROM machines WHERE id = :id", {"id": int(machine_id)})


# ============================================================
# PMOC - MÁQUINAS DE AR-CONDICIONADO
# ============================================================


def get_pmoc_maquinas(apenas_ativas=False):
    sql = """
        SELECT
            id,
            codigo,
            marca,
            modelo,
            capacidade,
            unidade_capacidade,
            local,
            status,
            periodicidade_dias,
            observacao,
            created_at,
            updated_at
        FROM pmoc_maquinas
    """

    if apenas_ativas:
        sql += " WHERE UPPER(status) = 'ATIVA'"

    sql += " ORDER BY codigo"

    return fetch_df(sql)


def create_pmoc_maquina(
    codigo,
    marca,
    modelo,
    capacidade,
    unidade_capacidade,
    local,
    status,
    periodicidade_dias,
    observacao,
):
    codigo = str(codigo or "").strip().upper()

    if not codigo:
        raise ValueError("Informe o código da máquina.")

    existente = fetch_df(
        """
        SELECT id
        FROM pmoc_maquinas
        WHERE UPPER(codigo) = :codigo
        LIMIT 1
        """,
        {"codigo": codigo},
    )

    if not existente.empty:
        raise ValueError(f"Já existe uma máquina PMOC com o código {codigo}.")

    execute(
        """
        INSERT INTO pmoc_maquinas
        (
            codigo,
            marca,
            modelo,
            capacidade,
            unidade_capacidade,
            local,
            status,
            periodicidade_dias,
            observacao,
            created_at,
            updated_at
        )
        VALUES
        (
            :codigo,
            :marca,
            :modelo,
            :capacidade,
            :unidade_capacidade,
            :local,
            :status,
            :periodicidade_dias,
            :observacao,
            :created_at,
            :updated_at
        )
        """,
        {
            "codigo": codigo,
            "marca": str(marca or "").strip(),
            "modelo": str(modelo or "").strip(),
            "capacidade": int(capacidade or 0),
            "unidade_capacidade": str(unidade_capacidade or "BTU").strip(),
            "local": str(local or "").strip(),
            "status": str(status or "ATIVA").upper(),
            "observacao": str(observacao or "").strip(),
            "periodicidade_dias": int(periodicidade_dias or 90),
            "created_at": now_br(),
            "updated_at": now_br(),
        },
    )


def update_pmoc_maquina(
    maquina_id,
    codigo,
    marca,
    modelo,
    capacidade,
    unidade_capacidade,
    local,
    status,
    periodicidade_dias,
    observacao,
):
    codigo = str(codigo or "").strip().upper()

    if not codigo:
        raise ValueError("Informe o código da máquina.")

    duplicada = fetch_df(
        """
        SELECT id
        FROM pmoc_maquinas
        WHERE UPPER(codigo) = :codigo
          AND id <> :id
        LIMIT 1
        """,
        {
            "codigo": codigo,
            "id": int(maquina_id),
        },
    )

    if not duplicada.empty:
        raise ValueError(f"Já existe outra máquina com o código {codigo}.")

    execute(
        """
        UPDATE pmoc_maquinas
        SET
            codigo = :codigo,
            marca = :marca,
            modelo = :modelo,
            capacidade = :capacidade,
            unidade_capacidade = :unidade_capacidade,
            local = :local,
            status = :status,
            periodicidade_dias = :periodicidade_dias,
            observacao = :observacao,
            updated_at = :updated_at
        WHERE id = :id
        """,
        {
            "id": int(maquina_id),
            "codigo": codigo,
            "marca": str(marca or "").strip(),
            "modelo": str(modelo or "").strip(),
            "capacidade": int(capacidade or 0),
            "unidade_capacidade": str(unidade_capacidade or "BTU").strip(),
            "local": str(local or "").strip(),
            "status": str(status or "ATIVA").upper(),
            "periodicidade_dias": int(periodicidade_dias or 90),
            "observacao": str(observacao or "").strip(),
            "updated_at": now_br(),
        },
    )


def delete_pmoc_maquina(maquina_id):
    preventivas = fetch_df(
        """
        SELECT COUNT(*) AS total
        FROM pmoc_preventivas
        WHERE maquina_id = :id
        """,
        {"id": int(maquina_id)},
    )

    corretivas = fetch_df(
        """
        SELECT COUNT(*) AS total
        FROM pmoc_corretivas
        WHERE maquina_id = :id
        """,
        {"id": int(maquina_id)},
    )

    total_preventivas = (
        int(preventivas.iloc[0]["total"] or 0) if not preventivas.empty else 0
    )

    total_corretivas = (
        int(corretivas.iloc[0]["total"] or 0) if not corretivas.empty else 0
    )

    if total_preventivas > 0 or total_corretivas > 0:
        raise ValueError(
            "Esta máquina possui histórico de manutenção e não pode "
            "ser excluída. Altere o status para DESATIVADA."
        )

    execute(
        "DELETE FROM pmoc_maquinas WHERE id = :id",
        {"id": int(maquina_id)},
    )


# ============================================================
# PMOC - PREVENTIVAS
# ============================================================


def gerar_numero_preventiva_pmoc(preventiva_id):
    return f"PMC-{int(preventiva_id):06d}"


def get_pmoc_preventivas():
    return fetch_df("""
        SELECT
            p.id,
            p.numero,
            p.maquina_id,
            m.codigo AS maquina_codigo,
            m.marca,
            m.modelo,
            m.local,
            p.tipo_servico,
            p.data_programada,
            p.data_execucao,
            p.status,
            p.observacao,
            p.created_at,
            p.updated_at
        FROM pmoc_preventivas p
        INNER JOIN pmoc_maquinas m
            ON m.id = p.maquina_id
        ORDER BY
            p.data_programada DESC,
            p.id DESC
        """)


def get_pmoc_preventiva(preventiva_id):
    rows = fetch_df(
        """
        SELECT
            p.*,
            m.codigo AS maquina_codigo,
            m.marca,
            m.modelo,
            m.capacidade,
            m.unidade_capacidade,
            m.periodicidade_dias,
            m.local
        FROM pmoc_preventivas p
        INNER JOIN pmoc_maquinas m
            ON m.id = p.maquina_id
        WHERE p.id = :id
        LIMIT 1
        """,
        {"id": int(preventiva_id)},
    )

    if rows.empty:
        return None

    return rows.iloc[0]


def get_pmoc_preventiva_executores(preventiva_id):
    return fetch_df(
        """
        SELECT
            pe.id,
            pe.preventiva_id,
            pe.funcionario_id,
            e.nome,
            e.setor,
            e.funcao
        FROM pmoc_preventiva_executores pe
        INNER JOIN employees e
            ON e.id = pe.funcionario_id
        WHERE pe.preventiva_id = :id
        ORDER BY e.nome
        """,
        {"id": int(preventiva_id)},
    )


def get_pmoc_preventiva_fotos(preventiva_id):
    return fetch_df(
        """
        SELECT
            id,
            preventiva_id,
            nome_arquivo,
            caminho,
            enviado_por,
            data_envio
        FROM pmoc_preventiva_fotos
        WHERE preventiva_id = :id
        ORDER BY id DESC
        """,
        {"id": int(preventiva_id)},
    )


def create_pmoc_preventiva(
    maquina_id,
    tipo_servico,
    data_programada,
    status,
    observacao,
    executores_ids,
    fotos,
    usuario,
    data_execucao=None,
):
    result = execute(
        """
        INSERT INTO pmoc_preventivas
        (
            maquina_id,
            tipo_servico,
            data_programada,
            data_execucao,
            status,
            observacao,
            created_at,
            updated_at
        )
        VALUES
        (
            :maquina_id,
            :tipo_servico,
            :data_programada,
            :data_execucao,
            :status,
            :observacao,
            :created_at,
            :updated_at
        )
        """,
        {
            "maquina_id": int(maquina_id),
            "tipo_servico": str(tipo_servico or "HIGIENIZACAO").upper(),
            "data_programada": data_programada,
            "data_execucao": data_execucao,
            "status": str(status or "ABERTA").upper(),
            "observacao": str(observacao or "").strip(),
            "created_at": now_br(),
            "updated_at": now_br(),
        },
    )

    preventiva_id = int(result.lastrowid)
    numero = gerar_numero_preventiva_pmoc(preventiva_id)

    execute(
        """
        UPDATE pmoc_preventivas
        SET numero = :numero
        WHERE id = :id
        """,
        {
            "numero": numero,
            "id": preventiva_id,
        },
    )

    for funcionario_id in executores_ids:
        execute(
            """
            INSERT INTO pmoc_preventiva_executores
            (
                preventiva_id,
                funcionario_id
            )
            VALUES
            (
                :preventiva_id,
                :funcionario_id
            )
            """,
            {
                "preventiva_id": preventiva_id,
                "funcionario_id": int(funcionario_id),
            },
        )

    salvar_fotos_pmoc(
        preventiva_id=preventiva_id,
        numero=numero,
        fotos=fotos,
        usuario=usuario,
    )

    garantir_pmoc_checklist(preventiva_id)

    return preventiva_id, numero


def update_pmoc_preventiva(
    preventiva_id,
    maquina_id,
    tipo_servico,
    data_programada,
    data_execucao,
    status,
    observacao,
    executores_ids,
):
    execute(
        """
        UPDATE pmoc_preventivas
        SET
            maquina_id = :maquina_id,
            tipo_servico = :tipo_servico,
            data_programada = :data_programada,
            data_execucao = :data_execucao,
            status = :status,
            observacao = :observacao,
            updated_at = :updated_at
        WHERE id = :id
        """,
        {
            "id": int(preventiva_id),
            "maquina_id": int(maquina_id),
            "tipo_servico": str(tipo_servico or "").upper(),
            "data_programada": data_programada,
            "data_execucao": data_execucao,
            "status": str(status or "ABERTA").upper(),
            "observacao": str(observacao or "").strip(),
            "updated_at": now_br(),
        },
    )

    execute(
        """
        DELETE FROM pmoc_preventiva_executores
        WHERE preventiva_id = :id
        """,
        {"id": int(preventiva_id)},
    )

    for funcionario_id in executores_ids:
        execute(
            """
            INSERT INTO pmoc_preventiva_executores
            (
                preventiva_id,
                funcionario_id
            )
            VALUES
            (
                :preventiva_id,
                :funcionario_id
            )
            """,
            {
                "preventiva_id": int(preventiva_id),
                "funcionario_id": int(funcionario_id),
            },
        )


def salvar_fotos_pmoc(
    preventiva_id,
    numero,
    fotos,
    usuario,
):
    if not fotos:
        return

    pasta = Path("shop_data") / "pmoc" / str(numero)

    pasta.mkdir(
        parents=True,
        exist_ok=True,
    )

    for foto in fotos:
        nome_seguro = Path(foto.name).name
        destino = pasta / nome_seguro

        destino.write_bytes(foto.getbuffer())

        execute(
            """
            INSERT INTO pmoc_preventiva_fotos
            (
                preventiva_id,
                nome_arquivo,
                caminho,
                enviado_por,
                data_envio
            )
            VALUES
            (
                :preventiva_id,
                :nome_arquivo,
                :caminho,
                :enviado_por,
                :data_envio
            )
            """,
            {
                "preventiva_id": int(preventiva_id),
                "nome_arquivo": nome_seguro,
                "caminho": str(destino),
                "enviado_por": usuario,
                "data_envio": now_br(),
            },
        )


def delete_pmoc_foto(foto_id):
    foto = fetch_df(
        """
        SELECT caminho
        FROM pmoc_preventiva_fotos
        WHERE id = :id
        """,
        {"id": int(foto_id)},
    )

    if not foto.empty:
        caminho = Path(str(foto.iloc[0]["caminho"]))

        try:
            if caminho.exists():
                caminho.unlink()
        except Exception:
            pass

    execute(
        """
        DELETE FROM pmoc_preventiva_fotos
        WHERE id = :id
        """,
        {"id": int(foto_id)},
    )


def delete_pmoc_preventiva(preventiva_id):
    fotos = get_pmoc_preventiva_fotos(preventiva_id)

    for _, foto in fotos.iterrows():
        try:
            caminho = Path(str(foto["caminho"]))

            if caminho.exists():
                caminho.unlink()
        except Exception:
            pass

    execute(
        """
        DELETE FROM pmoc_preventiva_fotos
        WHERE preventiva_id = :id
        """,
        {"id": int(preventiva_id)},
    )

    execute(
        """
        DELETE FROM pmoc_preventiva_executores
        WHERE preventiva_id = :id
        """,
        {"id": int(preventiva_id)},
    )

    execute(
        """
        DELETE FROM pmoc_preventivas
        WHERE id = :id
        """,
        {"id": int(preventiva_id)},
    )


def gerar_proxima_preventiva_pmoc(
    preventiva_id,
    usuario,
):
    preventiva = get_pmoc_preventiva(preventiva_id)

    if preventiva is None:
        raise ValueError("Preventiva não encontrada.")

    if str(preventiva.get("status") or "").upper() != "EXECUTADA":
        return None

    if int(preventiva.get("gerou_proxima") or 0) == 1:
        return None

    maquina = fetch_df(
        """
        SELECT
            id,
            periodicidade_dias
        FROM pmoc_maquinas
        WHERE id = :id
        """,
        {"id": int(preventiva["maquina_id"])},
    )

    if maquina.empty:
        raise ValueError("Máquina PMOC não encontrada.")

    periodicidade = int(maquina.iloc[0]["periodicidade_dias"] or 90)

    data_base = pd.to_datetime(
        preventiva.get("data_execucao"),
        errors="coerce",
    )

    if pd.isna(data_base):
        data_base = pd.Timestamp(date.today())

    proxima_data = data_base.date() + timedelta(days=periodicidade)

    result = execute(
        """
        INSERT INTO pmoc_preventivas
        (
            maquina_id,
            tipo_servico,
            data_programada,
            data_execucao,
            status,
            gerou_proxima,
            preventiva_origem_id,
            observacao,
            created_at,
            updated_at
        )
        VALUES
        (
            :maquina_id,
            :tipo_servico,
            :data_programada,
            NULL,
            'ABERTA',
            0,
            :preventiva_origem_id,
            :observacao,
            :created_at,
            :updated_at
        )
        """,
        {
            "maquina_id": int(preventiva["maquina_id"]),
            "tipo_servico": str(preventiva.get("tipo_servico") or "HIGIENIZACAO"),
            "data_programada": proxima_data,
            "preventiva_origem_id": int(preventiva_id),
            "observacao": (
                f"Preventiva gerada automaticamente a partir de "
                f"{preventiva.get('numero')} por {usuario}."
            ),
            "created_at": now_br(),
            "updated_at": now_br(),
        },
    )

    nova_id = int(result.lastrowid)
    novo_numero = gerar_numero_preventiva_pmoc(nova_id)

    execute(
        """
        UPDATE pmoc_preventivas
        SET numero = :numero
        WHERE id = :id
        """,
        {
            "numero": novo_numero,
            "id": nova_id,
        },
    )

    execute(
        """
        UPDATE pmoc_preventivas
        SET
            gerou_proxima = 1,
            updated_at = :updated_at
        WHERE id = :id
        """,
        {
            "id": int(preventiva_id),
            "updated_at": now_br(),
        },
    )

    return nova_id, novo_numero, proxima_data


# ----------------------------------------------------------------
# -----------------PMOC - CORRETIVAS------------------------------
# ----------------------------------------------------------------


def gerar_numero_corretiva_pmoc(corretiva_id):
    return f"PMC-C-{int(corretiva_id):06d}"


def create_pmoc_corretiva(
    maquina_id,
    service_order_id,
    status="ABERTA",
    observacao="",
):
    existente = fetch_df(
        """
        SELECT id, numero
        FROM pmoc_corretivas
        WHERE service_order_id = :service_order_id
        LIMIT 1
        """,
        {"service_order_id": int(service_order_id)},
    )

    if not existente.empty:
        return (
            int(existente.iloc[0]["id"]),
            str(existente.iloc[0]["numero"]),
        )

    result = execute(
        """
        INSERT INTO pmoc_corretivas
        (
            maquina_id,
            service_order_id,
            status,
            observacao,
            created_at,
            updated_at
        )
        VALUES
        (
            :maquina_id,
            :service_order_id,
            :status,
            :observacao,
            :created_at,
            :updated_at
        )
        """,
        {
            "maquina_id": int(maquina_id),
            "service_order_id": int(service_order_id),
            "status": str(status or "ABERTA").upper(),
            "observacao": str(observacao or "").strip(),
            "created_at": now_br(),
            "updated_at": now_br(),
        },
    )

    corretiva_id = int(result.lastrowid)
    numero = gerar_numero_corretiva_pmoc(corretiva_id)

    execute(
        """
        UPDATE pmoc_corretivas
        SET numero = :numero
        WHERE id = :id
        """,
        {
            "numero": numero,
            "id": corretiva_id,
        },
    )

    return corretiva_id, numero


# ----------------------------------------------------------------------------
# ---------------------------HISTÓRICO PMOC-----------------------------------
# ----------------------------------------------------------------------------
def get_pmoc_historico_preventivas(maquina_id):
    return fetch_df(
        """
        SELECT
            p.id,
            p.numero,
            p.tipo_servico,
            p.data_programada,
            p.data_execucao,
            p.status,
            p.observacao,
            p.preventiva_origem_id,
            p.created_at
        FROM pmoc_preventivas p
        WHERE p.maquina_id = :maquina_id
        ORDER BY p.data_programada DESC, p.id DESC
        """,
        {"maquina_id": int(maquina_id)},
    )


def get_pmoc_historico_corretivas(maquina_id):
    return fetch_df(
        """
        SELECT
            pc.id,
            pc.numero,
            pc.service_order_id,
            pc.status AS status_pmoc,
            pc.observacao,
            so.status AS status_os,
            so.problem_description,
            so.solution_description,
            so.start_datetime,
            so.end_datetime
        FROM pmoc_corretivas pc

        LEFT JOIN service_orders so
            ON so.id = pc.service_order_id

        WHERE pc.maquina_id = :maquina_id

        ORDER BY
            so.start_datetime DESC,
            pc.id DESC
        """,
        {"maquina_id": int(maquina_id)},
    )


def get_pmoc_ultima_proxima_preventiva(maquina_id):
    return fetch_df(
        """
        SELECT
            MAX(
                CASE
                    WHEN status = 'EXECUTADA'
                    THEN data_execucao
                    ELSE NULL
                END
            ) AS ultima_execucao,

            MIN(
                CASE
                    WHEN status = 'ABERTA'
                     AND data_programada >= CURDATE()
                    THEN data_programada
                    ELSE NULL
                END
            ) AS proxima_programada,

            MIN(
                CASE
                    WHEN status = 'ABERTA'
                     AND data_programada < CURDATE()
                    THEN data_programada
                    ELSE NULL
                END
            ) AS preventiva_atrasada

        FROM pmoc_preventivas

        WHERE maquina_id = :maquina_id
        """,
        {"maquina_id": int(maquina_id)},
    )


PMOC_CHECKLIST_PADRAO = {
    "Evaporadora": [
        "Higienização realizada",
        "Serpentina limpa",
        "Bandeja limpa",
        "Dreno desobstruído",
        "Filtro limpo",
        "Ventilador limpo",
        "Sem corrosão",
        "Sem vazamentos",
    ],
    "Condensadora": [
        "Limpeza realizada",
        "Serpentina limpa",
        "Hélice íntegra",
        "Ventilador funcionando",
        "Sem vibração",
        "Sem corrosão",
        "Sem vazamentos",
    ],
    "Elétrica": [
        "Alimentação elétrica verificada",
        "Corrente verificada",
        "Tensão verificada",
        "Bornes apertados",
        "Disjuntor em condições",
        "Contatora em condições",
    ],
    "Operação": [
        "Resfriamento normal",
        "Ruído normal",
        "Temperatura insuflada verificada",
        "Temperatura de retorno verificada",
        "Pressão do gás verificada",
        "Funcionamento geral aprovado",
    ],
}


def get_pmoc_checklist(preventiva_id):
    return fetch_df(
        """
        SELECT
            id,
            preventiva_id,
            grupo,
            item,
            executado,
            observacao,
            created_at,
            updated_at
        FROM pmoc_preventiva_checklist
        WHERE preventiva_id = :preventiva_id
        ORDER BY grupo, id
        """,
        {"preventiva_id": int(preventiva_id)},
    )


def get_pmoc_medicao(preventiva_id):

    df = fetch_df(
        """
        SELECT *
        FROM pmoc_preventiva_medicoes
        WHERE preventiva_id=:id
        LIMIT 1
        """,
        {"id": preventiva_id},
    )

    if df.empty:
        return None

    return df.iloc[0]


def salvar_pmoc_medicao(
    preventiva_id,
    retorno,
    insuflada,
    corrente,
    tensao,
    pressao_alta,
    pressao_baixa,
    observacao,
):
    execute(
        """
        INSERT INTO pmoc_preventiva_medicoes
        (
            preventiva_id,
            temperatura_retorno,
            temperatura_insuflada,
            corrente,
            tensao,
            pressao_alta,
            pressao_baixa,
            observacao,
            created_at,
            updated_at
        )
        VALUES
        (
            :preventiva_id,
            :retorno,
            :insuflada,
            :corrente,
            :tensao,
            :pressao_alta,
            :pressao_baixa,
            :observacao,
            :created_at,
            :updated_at
        )

        ON DUPLICATE KEY UPDATE

            temperatura_retorno=VALUES(temperatura_retorno),
            temperatura_insuflada=VALUES(temperatura_insuflada),
            corrente=VALUES(corrente),
            tensao=VALUES(tensao),
            pressao_alta=VALUES(pressao_alta),
            pressao_baixa=VALUES(pressao_baixa),
            observacao=VALUES(observacao),
            updated_at=VALUES(updated_at)

        """,
        {
            "preventiva_id": preventiva_id,
            "retorno": retorno,
            "insuflada": insuflada,
            "corrente": corrente,
            "tensao": tensao,
            "pressao_alta": pressao_alta,
            "pressao_baixa": pressao_baixa,
            "observacao": observacao,
            "created_at": now_br(),
            "updated_at": now_br(),
        },
    )


def garantir_pmoc_checklist(preventiva_id):
    checklist_existente = get_pmoc_checklist(preventiva_id)

    if not checklist_existente.empty:
        return

    for grupo, itens in PMOC_CHECKLIST_PADRAO.items():
        for item in itens:
            execute(
                """
                INSERT INTO pmoc_preventiva_checklist
                (
                    preventiva_id,
                    grupo,
                    item,
                    executado,
                    observacao,
                    created_at,
                    updated_at
                )
                VALUES
                (
                    :preventiva_id,
                    :grupo,
                    :item,
                    0,
                    '',
                    :created_at,
                    :updated_at
                )
                """,
                {
                    "preventiva_id": int(preventiva_id),
                    "grupo": grupo,
                    "item": item,
                    "created_at": now_br(),
                    "updated_at": now_br(),
                },
            )


def salvar_pmoc_checklist(preventiva_id, respostas):
    with get_engine().begin() as conn:
        for resposta in respostas:
            conn.execute(
                text("""
                    UPDATE pmoc_preventiva_checklist
                    SET
                        executado = :executado,
                        observacao = :observacao,
                        updated_at = :updated_at
                    WHERE id = :id
                      AND preventiva_id = :preventiva_id
                    """),
                {
                    "id": int(resposta["id"]),
                    "preventiva_id": int(preventiva_id),
                    "executado": (1 if resposta["executado"] else 0),
                    "observacao": str(resposta.get("observacao") or "").strip(),
                    "updated_at": now_br(),
                },
            )


def texto_pdf(valor, padrao="-"):
    if valor is None:
        return padrao

    try:
        if pd.isna(valor):
            return padrao
    except Exception:
        pass

    texto = str(valor).strip()
    return texto if texto else padrao


def data_pdf(valor, com_hora=False):
    convertido = pd.to_datetime(
        valor,
        errors="coerce",
    )

    if pd.isna(convertido):
        return "-"

    formato = "%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y"

    return convertido.strftime(formato)


def gerar_laudo_pmoc_pdf(preventiva_id):
    preventiva = get_pmoc_preventiva(preventiva_id)

    if preventiva is None:
        raise ValueError("Preventiva PMOC não encontrada.")

    executores = get_pmoc_preventiva_executores(preventiva_id)

    checklist = get_pmoc_checklist(preventiva_id)

    medicao = get_pmoc_medicao(preventiva_id)

    fotos = get_pmoc_preventiva_fotos(preventiva_id)

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=(f"Laudo PMOC " f"{texto_pdf(preventiva.get('numero'))}"),
        author="StockPro",
    )

    styles = getSampleStyleSheet()

    titulo = ParagraphStyle(
        "TituloPMOC",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        spaceAfter=5 * mm,
    )

    subtitulo = ParagraphStyle(
        "SubtituloPMOC",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1F4E78"),
        spaceBefore=3 * mm,
        spaceAfter=2 * mm,
    )

    normal = ParagraphStyle(
        "NormalPMOC",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        alignment=TA_LEFT,
    )

    normal_centro = ParagraphStyle(
        "NormalCentroPMOC",
        parent=normal,
        alignment=TA_CENTER,
    )

    pequeno = ParagraphStyle(
        "PequenoPMOC",
        parent=normal,
        fontSize=7.5,
        leading=9,
    )

    elementos = []

    # =====================================================
    # CABEÇALHO
    # =====================================================

    elementos.append(
        Paragraph(
            "LAUDO DE MANUTENÇÃO PREVENTIVA - PMOC",
            titulo,
        )
    )

    elementos.append(
        Paragraph(
            (
                f"<b>Preventiva:</b> "
                f"{texto_pdf(preventiva.get('numero'))}"
                f"&nbsp;&nbsp;&nbsp;&nbsp;"
                f"<b>Status:</b> "
                f"{texto_pdf(preventiva.get('status'))}"
            ),
            normal_centro,
        )
    )

    elementos.append(Spacer(1, 4 * mm))

    # =====================================================
    # EQUIPAMENTO
    # =====================================================

    elementos.append(
        Paragraph(
            "1. IDENTIFICAÇÃO DO EQUIPAMENTO",
            subtitulo,
        )
    )

    capacidade = (
        f"{texto_pdf(preventiva.get('capacidade'), '0')} "
        f"{texto_pdf(preventiva.get('unidade_capacidade'), 'BTU')}"
    )

    dados_equipamento = [
        [
            Paragraph("<b>Código</b>", normal),
            Paragraph(
                texto_pdf(preventiva.get("maquina_codigo")),
                normal,
            ),
            Paragraph("<b>Local</b>", normal),
            Paragraph(
                texto_pdf(preventiva.get("local")),
                normal,
            ),
        ],
        [
            Paragraph("<b>Marca</b>", normal),
            Paragraph(
                texto_pdf(preventiva.get("marca")),
                normal,
            ),
            Paragraph("<b>Modelo</b>", normal),
            Paragraph(
                texto_pdf(preventiva.get("modelo")),
                normal,
            ),
        ],
        [
            Paragraph("<b>Capacidade</b>", normal),
            Paragraph(capacidade, normal),
            Paragraph("<b>Tipo de serviço</b>", normal),
            Paragraph(
                texto_pdf(preventiva.get("tipo_servico")),
                normal,
            ),
        ],
    ]

    tabela_equipamento = Table(
        dados_equipamento,
        colWidths=[
            30 * mm,
            58 * mm,
            32 * mm,
            58 * mm,
        ],
    )

    tabela_equipamento.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF2F8")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EAF2F8")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    elementos.append(tabela_equipamento)

    # =====================================================
    # DADOS DA PREVENTIVA
    # =====================================================

    elementos.append(
        Paragraph(
            "2. DADOS DA PREVENTIVA",
            subtitulo,
        )
    )

    nomes_executores = "-"

    if not executores.empty:
        nomes_executores = ", ".join(executores["nome"].dropna().astype(str).tolist())

    dados_preventiva = [
        [
            Paragraph("<b>Data programada</b>", normal),
            Paragraph(
                data_pdf(preventiva.get("data_programada")),
                normal,
            ),
            Paragraph("<b>Data executada</b>", normal),
            Paragraph(
                data_pdf(preventiva.get("data_execucao")),
                normal,
            ),
        ],
        [
            Paragraph("<b>Executor(es)</b>", normal),
            Paragraph(nomes_executores, normal),
            Paragraph("<b>Periodicidade</b>", normal),
            Paragraph(
                (f"{texto_pdf(preventiva.get('periodicidade_dias'), '90')} " f"dias"),
                normal,
            ),
        ],
    ]

    tabela_preventiva = Table(
        dados_preventiva,
        colWidths=[
            35 * mm,
            53 * mm,
            35 * mm,
            55 * mm,
        ],
    )

    tabela_preventiva.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF2F8")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EAF2F8")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    elementos.append(tabela_preventiva)

    # =====================================================
    # CHECKLIST
    # =====================================================

    elementos.append(
        Paragraph(
            "3. CHECKLIST TÉCNICO",
            subtitulo,
        )
    )

    if checklist.empty:
        elementos.append(
            Paragraph(
                "Checklist não preenchido.",
                normal,
            )
        )
    else:
        checklist_dados = [
            [
                Paragraph("<b>Grupo</b>", normal),
                Paragraph("<b>Item verificado</b>", normal),
                Paragraph("<b>Resultado</b>", normal),
                Paragraph("<b>Observação</b>", normal),
            ]
        ]

        for _, item in checklist.iterrows():
            executado = bool(int(item.get("executado") or 0))

            resultado = "CONFORME" if executado else "NÃO INFORMADO"

            checklist_dados.append(
                [
                    Paragraph(
                        texto_pdf(item.get("grupo")),
                        pequeno,
                    ),
                    Paragraph(
                        texto_pdf(item.get("item")),
                        pequeno,
                    ),
                    Paragraph(resultado, pequeno),
                    Paragraph(
                        texto_pdf(
                            item.get("observacao"),
                            "",
                        ),
                        pequeno,
                    ),
                ]
            )

        tabela_checklist = Table(
            checklist_dados,
            colWidths=[
                31 * mm,
                68 * mm,
                28 * mm,
                51 * mm,
            ],
            repeatRows=1,
        )

        tabela_checklist.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        elementos.append(tabela_checklist)

    # =====================================================
    # MEDIÇÕES
    # =====================================================

    elementos.append(
        Paragraph(
            "4. MEDIÇÕES",
            subtitulo,
        )
    )

    if medicao is None:
        elementos.append(
            Paragraph(
                "Medições não informadas.",
                normal,
            )
        )
    else:
        retorno = float(medicao.get("temperatura_retorno") or 0)

        insuflada = float(medicao.get("temperatura_insuflada") or 0)

        delta_t = retorno - insuflada

        if retorno == 0 and insuflada == 0:
            avaliacao = "Não informado"
        elif delta_t > 18:
            avaliacao = "Verificar vazão de ar ou medição"
        elif delta_t >= 12:
            avaliacao = "Excelente"
        elif delta_t >= 10:
            avaliacao = "Muito boa"
        elif delta_t >= 8:
            avaliacao = "Atenção"
        elif delta_t >= 6:
            avaliacao = "Verificar equipamento"
        else:
            avaliacao = "Baixa eficiência"

        dados_medicao = [
            [
                Paragraph("<b>Temperatura retorno</b>", normal),
                Paragraph(f"{retorno:.1f} °C", normal),
                Paragraph("<b>Temperatura insuflada</b>", normal),
                Paragraph(f"{insuflada:.1f} °C", normal),
            ],
            [
                Paragraph("<b>ΔT</b>", normal),
                Paragraph(f"{delta_t:.1f} °C", normal),
                Paragraph("<b>Avaliação térmica</b>", normal),
                Paragraph(avaliacao, normal),
            ],
            [
                Paragraph("<b>Corrente</b>", normal),
                Paragraph(
                    f"{float(medicao.get('corrente') or 0):.2f} A",
                    normal,
                ),
                Paragraph("<b>Tensão</b>", normal),
                Paragraph(
                    f"{float(medicao.get('tensao') or 0):.1f} V",
                    normal,
                ),
            ],
            [
                Paragraph("<b>Pressão alta</b>", normal),
                Paragraph(
                    f"{float(medicao.get('pressao_alta') or 0):.2f}",
                    normal,
                ),
                Paragraph("<b>Pressão baixa</b>", normal),
                Paragraph(
                    f"{float(medicao.get('pressao_baixa') or 0):.2f}",
                    normal,
                ),
            ],
        ]

        tabela_medicao = Table(
            dados_medicao,
            colWidths=[
                39 * mm,
                49 * mm,
                39 * mm,
                51 * mm,
            ],
        )

        tabela_medicao.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF2F8")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EAF2F8")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        elementos.append(tabela_medicao)

        observacao_medicao = texto_pdf(
            medicao.get("observacao"),
            "",
        )

        if observacao_medicao:
            elementos.append(Spacer(1, 2 * mm))

            elementos.append(
                Paragraph(
                    (f"<b>Observações das medições:</b> " f"{observacao_medicao}"),
                    normal,
                )
            )

    # =====================================================
    # OBSERVAÇÕES
    # =====================================================

    elementos.append(
        Paragraph(
            "5. OBSERVAÇÕES DA PREVENTIVA",
            subtitulo,
        )
    )

    elementos.append(
        Paragraph(
            texto_pdf(
                preventiva.get("observacao"),
                "Nenhuma observação registrada.",
            ),
            normal,
        )
    )

    # =====================================================
    # FOTOS
    # =====================================================

    elementos.append(
        Paragraph(
            "6. REGISTRO FOTOGRÁFICO",
            subtitulo,
        )
    )

    fotos_validas = []

    if not fotos.empty:
        for _, foto in fotos.iterrows():
            caminho = Path(str(foto.get("caminho") or ""))

            if caminho.exists():
                fotos_validas.append(
                    (
                        caminho,
                        texto_pdf(foto.get("nome_arquivo")),
                    )
                )

    if not fotos_validas:
        elementos.append(
            Paragraph(
                "Nenhuma fotografia registrada.",
                normal,
            )
        )
    else:
        linhas_fotos = []

        for indice in range(
            0,
            len(fotos_validas),
            2,
        ):
            linha = []

            for deslocamento in [0, 1]:
                posicao = indice + deslocamento

                if posicao < len(fotos_validas):
                    caminho, nome = fotos_validas[posicao]

                    try:
                        imagem = RLImage(
                            str(caminho),
                            width=78 * mm,
                            height=58 * mm,
                            kind="proportional",
                        )

                        conteudo = [
                            imagem,
                            Spacer(1, 1 * mm),
                            Paragraph(nome, pequeno),
                        ]

                        linha.append(KeepTogether(conteudo))
                    except Exception:
                        linha.append(
                            Paragraph(
                                f"Não foi possível carregar: {nome}",
                                pequeno,
                            )
                        )
                else:
                    linha.append("")

            linhas_fotos.append(linha)

        tabela_fotos = Table(
            linhas_fotos,
            colWidths=[89 * mm, 89 * mm],
            hAlign="CENTER",
        )

        tabela_fotos.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )

        elementos.append(tabela_fotos)

    # =====================================================
    # RESPONSÁVEIS E ASSINATURAS
    # =====================================================

    elementos.append(Spacer(1, 8 * mm))

    elementos.append(
        Paragraph(
            "7. RESPONSÁVEIS",
            subtitulo,
        )
    )

    assinaturas = [
        [
            Paragraph(
                "<br/><br/>_________________________________<br/>"
                "Executor responsável",
                normal_centro,
            ),
            Paragraph(
                "<br/><br/>_________________________________<br/>"
                "Responsável pelo setor",
                normal_centro,
            ),
        ]
    ]

    tabela_assinaturas = Table(
        assinaturas,
        colWidths=[89 * mm, 89 * mm],
    )

    tabela_assinaturas.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ]
        )
    )

    elementos.append(tabela_assinaturas)

    elementos.append(Spacer(1, 6 * mm))

    elementos.append(
        Paragraph(
            (
                f"Documento gerado pelo StockPro em "
                f"{now_br().strftime('%d/%m/%Y %H:%M')}."
            ),
            pequeno,
        )
    )

    doc.build(elementos)

    buffer.seek(0)

    return buffer.getvalue()


def get_problem_locations(only_active=False):
    sql = "SELECT id, nome, descricao, ativo, created_at, updated_at FROM problem_locations"
    if only_active:
        sql += " WHERE ativo=1"
    sql += " ORDER BY nome"
    return fetch_df(sql)


def create_problem_location(nome, descricao, ativo=True):
    execute(
        """
        INSERT INTO problem_locations
        (nome, descricao, ativo, created_at, updated_at)
        VALUES
        (:nome, :descricao, :ativo, :created_at, :updated_at)
        """,
        {
            "nome": str(nome or "").strip(),
            "descricao": str(descricao or "").strip(),
            "ativo": 1 if ativo else 0,
            "created_at": now_br(),
            "updated_at": now_br(),
        },
    )


def update_problem_location(location_id, nome, descricao, ativo=True):
    execute(
        """
        UPDATE problem_locations
        SET nome=:nome,
            descricao=:descricao,
            ativo=:ativo,
            updated_at=:updated_at
        WHERE id=:id
        """,
        {
            "id": int(location_id),
            "nome": str(nome or "").strip(),
            "descricao": str(descricao or "").strip(),
            "ativo": 1 if ativo else 0,
            "updated_at": now_br(),
        },
    )


def delete_problem_location(location_id):
    uso = fetch_df(
        "SELECT COUNT(*) AS total FROM service_orders WHERE problem_location_id=:id",
        {"id": int(location_id)},
    )

    if not uso.empty and int(uso.iloc[0]["total"] or 0) > 0:
        raise ValueError(
            "Este local do problema já está vinculado a ordens de serviço. "
            "Use Inativo para bloquear novos lançamentos."
        )

    execute(
        "DELETE FROM problem_locations WHERE id=:id",
        {"id": int(location_id)},
    )


def select_problem_location(
    label="Local do problema", current_id=None, key=None, allow_empty=True
):
    locais = get_problem_locations(only_active=True)

    options = []
    if allow_empty:
        options.append("Sem local do problema")

    if not locais.empty:
        options += [f"ID {int(r['id'])} - {r['nome']}" for _, r in locais.iterrows()]

    index = 0

    if current_id is not None and not pd.isna(current_id) and not locais.empty:
        try:
            current_int = int(float(current_id))
            for i, opt in enumerate(options):
                if opt.startswith(f"ID {current_int} -"):
                    index = i
                    break
        except Exception:
            index = 0

    selected = st.selectbox(
        label,
        options or ["Sem local do problema"],
        index=index,
        key=key,
    )

    if selected == "Sem local do problema":
        return None

    return int(selected.split(" - ")[0].replace("ID ", ""))


def get_employees():
    return fetch_df(
        "SELECT id,nome,setor,funcao,criado_em,atualizado_em FROM employees ORDER BY nome"
    )


def create_employee(nome, setor, funcao):
    execute(
        "INSERT INTO employees (nome,setor,funcao,criado_em,atualizado_em) VALUES (:nome,:setor,:funcao,:criado_em,:atualizado_em)",
        {
            "nome": nome.strip(),
            "setor": setor.strip(),
            "funcao": funcao.strip(),
            "criado_em": now_br(),
            "atualizado_em": now_br(),
        },
    )
    log_action(
        st.session_state.get("user", {}).get("usuario", "sistema"),
        "Criou funcionário",
        "employees",
        nome.strip(),
        f"Setor: {setor}",
    )


def update_employee(emp_id, nome, setor, funcao):
    execute(
        "UPDATE employees SET nome=:nome,setor=:setor,funcao=:funcao,atualizado_em=:agora WHERE id=:id",
        {
            "id": emp_id,
            "nome": nome.strip(),
            "setor": setor.strip(),
            "funcao": funcao.strip(),
            "agora": now_br(),
        },
    )
    log_action(
        st.session_state.get("user", {}).get("usuario", "sistema"),
        "Atualizou funcionário",
        "employees",
        emp_id,
        nome.strip(),
    )


def delete_employee_record(emp_id):
    uso = fetch_df(
        "SELECT COUNT(*) AS total FROM service_order_employees WHERE employee_id = :id",
        {"id": int(emp_id)},
    )
    if not uso.empty and int(uso.iloc[0]["total"]) > 0:
        raise ValueError(
            "Este funcionário possui apontamentos em ordens e não pode ser excluído."
        )
    execute("DELETE FROM employees WHERE id = :id", {"id": int(emp_id)})


def get_orders(tipo):
    return fetch_df(
        """
        SELECT 
            so.id,
            so.tipo,
            so.tipo_manutencao,
            so.opened_by,
            m.nome AS maquina,
            so.machine_id,
            so.problem_location_id,
            pl.nome AS local_problema,
            so.centro_custo_id,
            cc.nome AS centro_custo,
            so.start_datetime,
            so.end_datetime,
            so.problem_description,
            so.status,
            so.gera_parada,
            so.solution_description,
            so.created_at,
            so.updated_at
        FROM service_orders so
        INNER JOIN machines m ON m.id=so.machine_id
        LEFT JOIN problem_locations pl ON pl.id=so.problem_location_id
        LEFT JOIN centros_custo cc ON cc.id=so.centro_custo_id
        WHERE so.tipo=:tipo
        ORDER BY so.id DESC
        """,
        {"tipo": tipo},
    )


def prepare_orders_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["start_datetime"] = pd.to_datetime(out["start_datetime"], errors="coerce")
    out["end_datetime"] = pd.to_datetime(out["end_datetime"], errors="coerce")
    out["duracao_horas"] = (
        out["end_datetime"] - out["start_datetime"]
    ).dt.total_seconds() / 3600.0
    out["duracao_horas"] = out["duracao_horas"].fillna(0)
    return out


def calc_mttr(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    finalizadas = df[df["status"] == "Finalizada"].copy()
    if finalizadas.empty:
        return 0.0
    finalizadas = prepare_orders_metrics(finalizadas)
    valid = finalizadas[finalizadas["duracao_horas"] > 0]
    if valid.empty:
        return 0.0
    return float(valid["duracao_horas"].mean())


def calc_mtbf(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    finalizadas = df[df["status"] == "Finalizada"].copy()
    if finalizadas.empty:
        return 0.0
    finalizadas["start_datetime"] = pd.to_datetime(
        finalizadas["start_datetime"], errors="coerce"
    )
    finalizadas = finalizadas.dropna(subset=["start_datetime"]).sort_values(
        "start_datetime"
    )
    if len(finalizadas) < 2:
        return 0.0
    diffs = finalizadas["start_datetime"].diff().dropna().dt.total_seconds() / 3600.0
    diffs = diffs[diffs > 0]
    if diffs.empty:
        return 0.0
    return float(diffs.mean())


def get_top_used_parts(limit: int = 10) -> pd.DataFrame:
    return fetch_df(
        """SELECT p.id AS produto_id, p.nome, SUM(op.quantidade) AS total_usado, p.unidade
               FROM service_order_parts op
               INNER JOIN products p ON p.id = op.product_id
               GROUP BY p.id, p.nome, p.unidade
               ORDER BY total_usado DESC, p.nome
               LIMIT :limite""",
        {"limite": int(limit)},
    )


def get_top_employees_called(limit: int = 10) -> pd.DataFrame:
    return fetch_df(
        """SELECT e.id AS funcionario_id, e.nome, COUNT(*) AS total_acionamentos
               FROM service_order_employees oe
               INNER JOIN employees e ON e.id = oe.employee_id
               GROUP BY e.id, e.nome
               ORDER BY total_acionamentos DESC, e.nome
               LIMIT :limite""",
        {"limite": int(limit)},
    )


def delete_order_cascade(order_id: int, usuario_lancamento: str):
    with get_engine().begin() as conn:
        parts = (
            conn.execute(
                text(
                    "SELECT product_id, quantidade FROM service_order_parts WHERE order_id = :order_id"
                ),
                {"order_id": order_id},
            )
            .mappings()
            .all()
        )

        for part in parts:
            product_id = int(part["product_id"])
            quantidade = float(part["quantidade"])
            produto = (
                conn.execute(
                    text(
                        "SELECT id, estoque_atual FROM products WHERE id = :id FOR UPDATE"
                    ),
                    {"id": product_id},
                )
                .mappings()
                .first()
            )

            if produto:
                novo_estoque = float(produto["estoque_atual"]) + quantidade
                conn.execute(
                    text(
                        "UPDATE products SET estoque_atual = :estoque, atualizado_em = :agora WHERE id = :id"
                    ),
                    {"estoque": novo_estoque, "agora": now_br(), "id": product_id},
                )
                conn.execute(
                    text(
                        """INSERT INTO movements (produto_id, tipo, quantidade, observacao, usuario_lancamento, criado_em)
                               VALUES (:produto_id, 'ENTRADA', :quantidade, :observacao, :usuario_lancamento, :criado_em)"""
                    ),
                    {
                        "produto_id": product_id,
                        "quantidade": quantidade,
                        "observacao": f"Devolução de peça por exclusão da ordem {order_id}",
                        "usuario_lancamento": usuario_lancamento,
                        "criado_em": now_br(),
                    },
                )

        conn.execute(
            text("DELETE FROM service_order_parts WHERE order_id = :order_id"),
            {"order_id": order_id},
        )
        conn.execute(
            text("DELETE FROM service_order_employees WHERE order_id = :order_id"),
            {"order_id": order_id},
        )
        conn.execute(
            text("DELETE FROM service_orders WHERE id = :order_id"),
            {"order_id": order_id},
        )
    log_action(
        usuario_lancamento,
        "Excluiu ordem",
        "service_orders",
        order_id,
        "Exclusão em cascata com devolução de peças",
    )


def get_orders_filtered(
    tipo, machine_id=None, status=None, date_from=None, date_to=None
):
    params = {"tipo": tipo}
    sql = """
SELECT 
    so.id,
    so.tipo,
    so.tipo_manutencao,
    so.opened_by,
    m.nome AS maquina,
    so.machine_id,
    so.problem_location_id,
    pl.nome AS local_problema,
    so.centro_custo_id,
    cc.nome AS centro_custo,
    so.start_datetime,
    so.end_datetime,
    so.problem_description,
    so.status,
    so.gera_parada,
    so.solution_description,
    so.created_at,
    so.updated_at
FROM service_orders so
INNER JOIN machines m ON m.id=so.machine_id
LEFT JOIN problem_locations pl ON pl.id=so.problem_location_id
LEFT JOIN centros_custo cc ON cc.id=so.centro_custo_id
WHERE so.tipo=:tipo
"""
    if machine_id is not None:
        sql += " AND so.machine_id=:machine_id"
        params["machine_id"] = machine_id
    if status and status != "TODOS":
        sql += " AND so.status=:status"
        params["status"] = status
    if date_from is not None:
        sql += " AND so.start_datetime>=:date_from"
        params["date_from"] = f"{date_from} 00:00:00"
    if date_to is not None:
        sql += " AND so.start_datetime<=:date_to"
        params["date_to"] = f"{date_to} 23:59:59"
    sql += " ORDER BY so.id DESC"
    return fetch_df(sql, params)


def create_order(
    tipo,
    opened_by,
    machine_id,
    start_dt,
    end_dt,
    problem_description,
    status,
    solution_description,
    centro_custo_id=None,
    gera_parada=True,
    tipo_manutencao="Corretiva",
    problem_location_id=None,
):
    res = execute(
        """
        INSERT INTO service_orders
        (
            tipo,
            opened_by,
            machine_id,
            centro_custo_id,
            problem_location_id,
            gera_parada,
            tipo_manutencao,
            start_datetime,
            end_datetime,
            problem_description,
            status,
            solution_description,
            created_at,
            updated_at
        )
        VALUES
        (
            :tipo,
            :opened_by,
            :machine_id,
            :centro_custo_id,
            :problem_location_id,
            :gera_parada,
            :tipo_manutencao,
            :start_datetime,
            :end_datetime,
            :problem_description,
            :status,
            :solution_description,
            :created_at,
            :updated_at
        )
        """,
        {
            "tipo": tipo,
            "opened_by": opened_by,
            "machine_id": int(machine_id),
            "centro_custo_id": centro_custo_id,
            "problem_location_id": problem_location_id,
            "gera_parada": 1 if gera_parada else 0,
            "tipo_manutencao": tipo_manutencao,
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "problem_description": str(problem_description or "").strip(),
            "status": str(status or "Aberta").strip(),
            "solution_description": str(solution_description or "").strip(),
            "created_at": now_br(),
            "updated_at": now_br(),
        },
    )
    return getattr(res, "lastrowid", None)


def update_order(
    order_id,
    machine_id,
    start_dt,
    end_dt,
    problem_description,
    status,
    solution_description,
    centro_custo_id=None,
    gera_parada=True,
    tipo_manutencao="Corretiva",
    problem_location_id=None,
):
    execute(
        """
        UPDATE service_orders
        SET
            machine_id=:machine_id,
            centro_custo_id=:centro_custo_id,
            problem_location_id=:problem_location_id,
            gera_parada=:gera_parada,
            tipo_manutencao=:tipo_manutencao,
            start_datetime=:start_datetime,
            end_datetime=:end_datetime,
            problem_description=:problem_description,
            status=:status,
            solution_description=:solution_description,
            updated_at=:updated_at
        WHERE id=:id
        """,
        {
            "id": int(order_id),
            "machine_id": int(machine_id),
            "centro_custo_id": centro_custo_id,
            "problem_location_id": problem_location_id,
            "gera_parada": 1 if gera_parada else 0,
            "tipo_manutencao": tipo_manutencao,
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "problem_description": str(problem_description or "").strip(),
            "status": str(status or "Aberta").strip(),
            "solution_description": str(solution_description or "").strip(),
            "updated_at": now_br(),
        },
    )


def close_order(order_id, solution_description, end_dt):
    execute(
        "UPDATE service_orders SET status='Finalizada',solution_description=:solution_description,end_datetime=:end_datetime,updated_at=:updated_at WHERE id=:id",
        {
            "id": order_id,
            "solution_description": solution_description.strip(),
            "end_datetime": end_dt,
            "updated_at": now_br(),
        },
    )
    log_action(
        st.session_state.get("user", {}).get("usuario", "sistema"),
        "Fechou ordem",
        "service_orders",
        order_id,
        "Finalizada",
    )


def get_order_employees(order_id):
    return fetch_df(
        "SELECT oe.id,e.id AS funcionario_id,e.nome,e.setor,e.funcao,oe.start_datetime,oe.end_datetime FROM service_order_employees oe INNER JOIN employees e ON e.id=oe.employee_id WHERE oe.order_id=:order_id ORDER BY oe.id DESC",
        {"order_id": order_id},
    )


def add_employee_to_order(order_id, employee_id, start_dt, end_dt):
    execute(
        "INSERT INTO service_order_employees (order_id,employee_id,start_datetime,end_datetime,created_at) VALUES (:order_id,:employee_id,:start_datetime,:end_datetime,:created_at)",
        {
            "order_id": order_id,
            "employee_id": employee_id,
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "created_at": now_br(),
        },
    )


def get_order_parts(order_id):
    return fetch_df(
        "SELECT op.id,p.id AS peca_id,p.nome,op.quantidade,p.unidade FROM service_order_parts op INNER JOIN products p ON p.id=op.product_id WHERE op.order_id=:order_id ORDER BY op.id DESC",
        {"order_id": order_id},
    )


def visualizar_ordem_streamlit(row, funcionarios, pecas):
    st.divider()
    st.markdown(f"## Ordem de Serviço #{int(row['id'])}")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(f"**Máquina:** {row.get('maquina', '')}")
        st.markdown(f"**Tipo:** {row.get('tipo', '')}")
        st.markdown(f"**Tipo manutenção:** {row.get('tipo_manutencao', '')}")
        st.markdown(f"**Local do problema:** {row.get('local_problema', '')}")

    with c2:
        st.markdown(f"**Centro de custo:** {row.get('centro_custo', '')}")
        st.markdown(
            f"**Gerou parada:** {'Sim' if int(row.get('gera_parada', 0) or 0) == 1 else 'Não'}"
        )
        st.markdown(f"**Status:** {row.get('status', '')}")
        st.markdown(f"**Aberta por:** {row.get('opened_by', '')}")

    with c3:
        st.markdown(f"**Início:** {format_datetime_br(row.get('start_datetime'))}")
        st.markdown(f"**Fim:** {format_datetime_br(row.get('end_datetime'))}")
        st.markdown(f"**Criada em:** {format_datetime_br(row.get('created_at'))}")
        st.markdown(f"**Atualizada em:** {format_datetime_br(row.get('updated_at'))}")

    st.markdown("## Descrição do Problema")
    st.write(row.get("problem_description", "") or "")

    st.markdown("## Mão de Obra")
    if funcionarios.empty:
        st.info("Nenhum funcionário lançado.")
    else:
        st.dataframe(funcionarios, use_container_width=True, hide_index=True)

    st.markdown("## Peças Utilizadas")
    if pecas.empty:
        st.info("Nenhuma peça lançada.")
    else:
        st.dataframe(pecas, use_container_width=True, hide_index=True)

    st.markdown("## Solução")
    st.write(row.get("solution_description", "") or "")


def add_part_to_order(order_id, product_id, quantidade, usuario_lancamento):
    quantidade = float(quantidade)
    with get_engine().begin() as conn:
        produto = (
            conn.execute(
                text("SELECT id,estoque_atual FROM products WHERE id=:id FOR UPDATE"),
                {"id": product_id},
            )
            .mappings()
            .first()
        )
        novo = float(produto["estoque_atual"]) - quantidade
        if novo < 0:
            raise ValueError("Estoque insuficiente para lançar esta peça.")
        conn.execute(
            text(
                "UPDATE products SET estoque_atual=:estoque, atualizado_em=:agora WHERE id=:id"
            ),
            {"estoque": novo, "agora": now_br(), "id": product_id},
        )
        conn.execute(
            text(
                "INSERT INTO service_order_parts (order_id,product_id,quantidade,created_at) VALUES (:order_id,:product_id,:quantidade,:created_at)"
            ),
            {
                "order_id": order_id,
                "product_id": product_id,
                "quantidade": quantidade,
                "created_at": now_br(),
            },
        )
        conn.execute(
            text(
                "INSERT INTO movements (produto_id,tipo,quantidade,observacao,usuario_lancamento,criado_em) VALUES (:produto_id,'SAIDA',:quantidade,:observacao,:usuario_lancamento,:criado_em)"
            ),
            {
                "produto_id": product_id,
                "quantidade": quantidade,
                "observacao": f"Peça utilizada na ordem {order_id}",
                "usuario_lancamento": usuario_lancamento,
                "criado_em": now_br(),
            },
        )


def delete_employee_from_order(vinculo_id, usuario_lancamento):
    execute(
        "DELETE FROM service_order_employees WHERE id=:id",
        {"id": int(vinculo_id)},
    )
    log_action(
        usuario_lancamento,
        "Removeu funcionário da ordem",
        "service_order_employees",
        vinculo_id,
        "Funcionário desvinculado da OS",
    )


def delete_part_from_order(vinculo_id, usuario_lancamento):
    with get_engine().begin() as conn:
        part = (
            conn.execute(
                text("""
                SELECT id, order_id, product_id, quantidade
                FROM service_order_parts
                WHERE id=:id
            """),
                {"id": int(vinculo_id)},
            )
            .mappings()
            .first()
        )

        if not part:
            return

        product_id = int(part["product_id"])
        quantidade = float(part["quantidade"])
        order_id = int(part["order_id"])

        produto = (
            conn.execute(
                text("SELECT id, estoque_atual FROM products WHERE id=:id FOR UPDATE"),
                {"id": product_id},
            )
            .mappings()
            .first()
        )

        if produto:
            novo_estoque = float(produto["estoque_atual"] or 0) + quantidade

            conn.execute(
                text("""
                    UPDATE products
                    SET estoque_atual=:estoque,
                        atualizado_em=:agora
                    WHERE id=:id
                """),
                {
                    "estoque": novo_estoque,
                    "agora": now_br(),
                    "id": product_id,
                },
            )

            conn.execute(
                text("""
                    INSERT INTO movements
                    (produto_id, tipo, quantidade, observacao, usuario_lancamento, criado_em)
                    VALUES
                    (:produto_id, 'ENTRADA', :quantidade, :observacao, :usuario_lancamento, :criado_em)
                """),
                {
                    "produto_id": product_id,
                    "quantidade": quantidade,
                    "observacao": f"Devolução de peça removida da ordem {order_id}",
                    "usuario_lancamento": usuario_lancamento,
                    "criado_em": now_br(),
                },
            )

        conn.execute(
            text("DELETE FROM service_order_parts WHERE id=:id"),
            {"id": int(vinculo_id)},
        )

    log_action(
        usuario_lancamento,
        "Removeu peça da ordem",
        "service_order_parts",
        vinculo_id,
        f"Peça removida da OS e estoque devolvido: {quantidade}",
    )


if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None
if "planta" not in st.session_state:
    st.session_state.planta = PLANTA_PADRAO
else:
    st.session_state.planta = normalizar_chave_planta(st.session_state.planta)


def logout():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()


def normalizar_perfil(valor):
    perfil = str(valor or "").strip().lower()
    mapa = {
        "administrador": "administrador",
        "admin": "administrador",
        "almoxarifado": "almoxarifado",
        "operador": "operador",
        "aprovador": "aprovador",
        "aprvador": "aprovador",
        "aprovador de compras": "aprovador",
    }
    return mapa.get(perfil, perfil)


def is_admin():
    return normalizar_perfil(user.get("perfil", "")) == "administrador"


def is_almoxarifado():
    return normalizar_perfil(user.get("perfil", "")) == "almoxarifado"


def is_aprovador():
    return normalizar_perfil(user.get("perfil", "")) == "aprovador"


def is_operador():
    return normalizar_perfil(user.get("perfil", "")) == "operador"


def can_manage_master_data():
    return is_admin() or is_almoxarifado()


def can_view_stock():
    return is_admin() or is_almoxarifado() or is_operador()


def can_manage_users():
    return is_admin()


def can_manage_orders():
    return is_admin() or is_almoxarifado() or is_operador()


def require_permission(
    condition, message="Você não tem permissão para acessar esta área."
):
    if not condition:
        st.warning(message)
        st.stop()


if not st.session_state.logged_in:
    opcoes_plantas = list(PLANTAS_DB.keys())
    planta_atual = normalizar_chave_planta(
        st.session_state.get("planta", PLANTA_PADRAO)
    )
    planta_escolhida = st.selectbox(
        "Planta",
        opcoes_plantas,
        index=opcoes_plantas.index(planta_atual),
        format_func=get_planta_label,
        key="planta_login_selectbox",
    )
    if planta_escolhida != st.session_state.get("planta"):
        st.session_state.planta = planta_escolhida
        st.cache_resource.clear()
        try:
            shop_manager.set_database_url(get_current_database_url())
            producao.set_database_url(get_current_database_url())
        except Exception:
            pass
        st.rerun()
    st.session_state.planta = planta_escolhida

try:
    shop_manager.set_database_url(get_current_database_url())
    producao.set_database_url(get_current_database_url())
except Exception:
    pass

init_db()
if count_users() == 0:
    app_header("Primeira configuração", "Crie o primeiro usuário administrador.")
    with st.form("form_primeiro_admin"):
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome")
        usuario = c2.text_input("Usuário")
        c3, c4 = st.columns(2)
        email = c3.text_input("E-mail")
        senha = c4.text_input("Senha", type="password")
        if st.form_submit_button("Criar administrador", use_container_width=True):
            create_user(nome, usuario, email, "Administrador", senha, True)
            st.success("Administrador criado.")
            st.rerun()
    st.stop()
if not st.session_state.logged_in:
    app_header("Acesso ao sistema", APP_SUBTITLE)
    c1, c2, c3 = st.columns([1, 1.1, 1])
    with c2:
        st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
        with st.form("login"):
            st.info(f"Planta selecionada: {get_planta_label()}")
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                u = authenticate_user(usuario, senha)
                if u:
                    st.session_state.logged_in = True
                    st.session_state.user = u
                    log_action(
                        u["usuario"], "Login", "auth", u["id"], "Acesso ao sistema"
                    )
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

user = st.session_state.user
products_df = get_products()
users_df = get_users()
machines_df = get_machines()
employees_df = get_employees()
problem_locations_df = get_problem_locations()
criticos_df = get_critical_products()
os_df = get_orders("CORRETIVA")
pm_df = get_orders("PREVENTIVA")

with st.sidebar:
    if logo_b64:
        st.markdown(
            f"""<div class="hero-card" style="padding:0.9rem 1rem;">
                    <h3 style="text-align:center;font-weight:900;margin:0;">{APP_NAME}</h3>
                    <div class="small-muted" style="text-align:center;">{APP_SUBTITLE}</div>
                </div>""",
            unsafe_allow_html=True,
        )
    st.markdown(f"**{user['nome']}**")
    st.caption(
        f"Planta: {get_planta_label()} | Perfil: {user['perfil']} | {user['usuario']}"
    )
    st.markdown("---")
    common_menu = [
        "Dashboard",
        "Meu painel",
        "Ordem de serviço",
        "Ordem de preventiva",
        "PMOC",
        "Produção",
        "Dashboard executivo",
        "Solicitações de Compras/Serviços",
    ]
    compras_menu = ["Compras", "Serviços"]
    almox_menu = ["Produtos / Estoque"] + compras_menu
    admin_menu = [
        "Produtos / Estoque",
        "Máquinas",
        "Funcionários",
        "Locais do Problema",
        "Usuários",
        "Auditoria",
    ] + compras_menu

    if is_admin():
        menu_options = common_menu + admin_menu
    elif is_almoxarifado():
        menu_options = common_menu + almox_menu
    elif is_aprovador():
        menu_options = ["Compras", "Serviços"]
    else:
        menu_options = common_menu + compras_menu
    if st.button("Sair", use_container_width=True):
        logout()
    menu = st.radio("Menu", menu_options)

app_header(
    "Sistema de controle de estoque e manutenção",
)

st.markdown(
    f"""<div class="section-card" style="padding:0.6rem 1rem;"><div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;"><div><strong>Usuário:</strong> {user["nome"]}</div><div><strong>Planta:</strong> {get_planta_label()}</div><div><strong>Perfil:</strong> {user["perfil"]}</div><div><strong>Turno:</strong> Operação online</div><div><strong>Data/Hora:</strong> {now_br().strftime("%d/%m/%Y %H:%M")}</div></div></div>""",
    unsafe_allow_html=True,
)


def can_manage_purchases():
    return is_admin() or is_almoxarifado()


def can_view_purchases():
    return is_admin() or is_almoxarifado() or is_operador() or is_aprovador()


def preparar_sessao_compras():
    """Adapta o login do StockPro para o módulo Shop Manager."""
    try:
        shop_manager.set_database_url(get_current_database_url())
    except Exception:
        pass
    perfil_stock = normalizar_perfil(user.get("perfil", ""))

    if perfil_stock == "administrador":
        perfil_compras = "admin"
    elif perfil_stock == "almoxarifado":
        perfil_compras = "almoxarifado"
    elif perfil_stock == "aprovador":
        perfil_compras = "aprovador"
    else:
        perfil_compras = "operador"

    st.session_state.usuario = user.get("usuario", "")
    st.session_state.nome = user.get("nome", "")
    st.session_state.perfil = perfil_compras
    st.session_state.logado = True

    if "itens_novo_pedido" not in st.session_state:
        st.session_state.itens_novo_pedido = []


def tela_compras_integrada():
    preparar_sessao_compras()
    shop_manager.criar_tabelas()

    st.subheader("🛒 Compras / Shop Manager")
    st.caption(
        "Módulo integrado ao StockPro usando o mesmo login do sistema principal."
    )

    if shop_manager.email_configurado():
        st.success("E-mail configurado para notificações de compras.")
    else:
        st.info(
            "E-mail não configurado. O módulo funciona normalmente, apenas sem envio automático."
        )

    perfil_txt = {
        "admin": "Administrador de compras",
        "aprovador": "Aprovador / Compras total",
        "operador": "Operador de compras",
    }.get(st.session_state.perfil, st.session_state.perfil)
    st.markdown(f"**Perfil no módulo de compras:** {perfil_txt}")

    menu_compras = st.radio(
        "Menu de compras",
        [
            "Dashboard",
            "Novo Pedido",
            "Pedidos",
            "Notificações",
            "Produtos",
            "Fornecedores",
            "Centro de custo",
            "Configurações",
        ],
        horizontal=True,
    )

    paginas = {
        "Dashboard": shop_manager.tela_dashboard,
        "Novo Pedido": shop_manager.tela_novo_pedido,
        "Pedidos": shop_manager.tela_pedidos,
        "Notificações": shop_manager.tela_notificacoes,
        "Produtos": shop_manager.tela_produtos,
        "Fornecedores": shop_manager.tela_fornecedores,
        "Centro de custo": shop_manager.tela_centros_custo_orcamento,
        "Centro de custo / Orçamento": shop_manager.tela_centros_custo_orcamento,
        "Configurações": shop_manager.tela_configuracoes,
    }
    if menu_compras not in paginas:
        st.error(f"Página de compras não encontrada: {menu_compras}")
        st.stop()
    paginas[menu_compras]()


def tela_servicos_integrada():
    preparar_sessao_compras()
    shop_manager.criar_tabelas()
    shop_manager.tela_servicos_integrada()


if menu == "Serviços":
    require_permission(
        can_view_purchases(), "Você não possui acesso ao módulo Serviços."
    )
    tela_servicos_integrada()

elif menu == "Dashboard":
    os_metrics = prepare_orders_metrics(os_df)
    pm_metrics = prepare_orders_metrics(pm_df)

    abertas_os = len(os_df[os_df["status"].isin(["Aberta", "Em andamento"])])
    abertas_pm = len(pm_df[pm_df["status"].isin(["Aberta", "Em andamento"])])
    mttr_os = calc_mttr(os_df)
    mttr_pm = calc_mttr(pm_df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Produtos", len(products_df))
    c2.metric("Máquinas", len(machines_df))
    c3.metric("Funcionários", len(employees_df))
    c4.metric(
        "Saldo total estoque",
        format_number(
            products_df["estoque_atual"].sum() if not products_df.empty else 0
        ),
    )
    if "valor_unitario" in products_df.columns and not products_df.empty:
        valor_estoque_total = (
            products_df["estoque_atual"].astype(float)
            * products_df["valor_unitario"].astype(float)
        ).sum()
    else:
        valor_estoque_total = 0.0
    st.metric(
        "Valor financeiro do estoque",
        f"R$ {valor_estoque_total:,.2f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", "."),
    )

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("OS abertas", abertas_os)
    c6.metric("Preventivas abertas", abertas_pm)
    c7.metric("MTTR OS (h)", format_number(mttr_os))
    c8.metric("MTTR Preventivas (h)", format_number(mttr_pm))

    st.subheader("Indicadores de manutenção")

    left, right = st.columns(2)

    st.subheader("Resumo operacional")
    r1, r2 = st.columns(2)

    with r1:
        st.markdown("### Itens críticos")
        if criticos_df.empty:
            st.success("Nenhum item abaixo ou igual ao estoque mínimo.")
        else:
            st.dataframe(
                criticos_df.rename(
                    columns={
                        "id": "ID",
                        "nome": "Produto",
                        "unidade": "Unidade",
                        "estoque_atual": "Estoque atual",
                        "estoque_minimo": "Estoque mínimo",
                        "valor_unitario": "Valor unitário",
                        "falta_para_minimo": "Falta para mínimo",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    with r2:
        st.markdown("### Resumo de backlog")
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.write(f"OS corretivas abertas/em andamento: **{abertas_os}**")
        st.write(f"Preventivas abertas/em andamento: **{abertas_pm}**")
        st.write(f"Máquinas cadastradas: **{len(machines_df)}**")
        st.write(f"Usuários cadastrados: **{len(users_df)}**")
        st.write(f"Itens críticos em estoque: **{len(criticos_df)}**")
        st.markdown("</div>", unsafe_allow_html=True)


elif menu == "Meu painel":
    st.subheader("Meu painel")
    minhas_ordens = get_user_opened_orders(user["usuario"])
    meus_logs = get_audit_logs(limit=30, usuario=user["usuario"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Ordens abertas por mim",
        len(
            minhas_ordens[minhas_ordens["status"].isin(["Aberta", "Em andamento"])]
            if not minhas_ordens.empty
            else []
        ),
    )
    c2.metric(
        "Ordens finalizadas por mim",
        len(
            minhas_ordens[minhas_ordens["status"] == "Finalizada"]
            if not minhas_ordens.empty
            else []
        ),
    )
    c3.metric("Ações registradas", len(meus_logs))
    c4.metric("Perfil", user["perfil"])

    if not minhas_ordens.empty:
        minhas_ordens["Tempo total"] = minhas_ordens.apply(
            lambda r: format_duration(r["start_datetime"], r["end_datetime"]), axis=1
        )
        st.markdown("### Minhas ordens")
        st.dataframe(
            minhas_ordens.rename(
                columns={
                    "id": "ID ordem",
                    "tipo": "Tipo",
                    "opened_by": "Aberta por",
                    "machine_id": "ID máquina",
                    "start_datetime": "Início",
                    "end_datetime": "Fim",
                    "problem_description": "Problema",
                    "status": "Status",
                    "solution_description": "Solução",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Você ainda não abriu ordens.")

    st.markdown("### Meu histórico de ações")
    if meus_logs.empty:
        st.info("Sem ações registradas para este usuário.")
    else:
        st.dataframe(
            meus_logs.rename(
                columns={
                    "id": "ID",
                    "usuario": "Usuário",
                    "acao": "Ação",
                    "entidade": "Entidade",
                    "entidade_id": "ID entidade",
                    "detalhes": "Detalhes",
                    "criado_em": "Data/hora",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

elif menu == "PMOC":
    st.subheader("❄️ PMOC")

    pmoc_menu = st.radio(
        "Menu PMOC",
        [
            "Dashboard",
            "Máquinas",
            "Nova preventiva",
            "Preventivas",
            "Corretivas",
        ],
        horizontal=True,
        key="pmoc_menu",
    )

    # =====================================================
    # DASHBOARD PMOC
    # =====================================================
    if pmoc_menu == "Dashboard":
        st.subheader("📊 Dashboard PMOC")

        maquinas = fetch_df("""
            SELECT COUNT(*) total
            FROM pmoc_maquinas
            WHERE status='ATIVA'
        """)

        preventivas_abertas = fetch_df("""
            SELECT COUNT(*) total
            FROM pmoc_preventivas
            WHERE status='ABERTA'
        """)

        preventivas_vencidas = fetch_df("""
            SELECT COUNT(*) total
            FROM pmoc_preventivas
            WHERE status='ABERTA'
            AND data_programada < CURDATE()
        """)

        corretivas_abertas = fetch_df("""
            SELECT COUNT(*) total
            FROM pmoc_corretivas pc
            INNER JOIN service_orders so
                ON so.id=pc.service_order_id
            WHERE so.status<>'Finalizada'
        """)

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Máquinas Ativas", int(maquinas.iloc[0]["total"]))

        c2.metric("Preventivas Abertas", int(preventivas_abertas.iloc[0]["total"]))

        c3.metric("Preventivas Vencidas", int(preventivas_vencidas.iloc[0]["total"]))

        c4.metric("Corretivas Abertas", int(corretivas_abertas.iloc[0]["total"]))

        st.divider()

        # ============================================================
        # PRÓXIMAS PREVENTIVAS
        # ============================================================

        st.markdown("### Próximas preventivas")

        proximas_preventivas = fetch_df("""
            SELECT
                p.id,
                p.numero,
                m.codigo AS maquina,
                m.local,
                p.tipo_servico,
                p.data_programada,
                DATEDIFF(p.data_programada, CURDATE()) AS dias_restantes
            FROM pmoc_preventivas p

            INNER JOIN pmoc_maquinas m
                ON m.id = p.maquina_id

            WHERE p.status = 'ABERTA'
            AND p.data_programada >= CURDATE()

            ORDER BY p.data_programada ASC

            LIMIT 10
            """)

        if proximas_preventivas.empty:
            st.success("Não existem preventivas futuras pendentes.")

        else:
            proximas_exibicao = proximas_preventivas.copy()

            proximas_exibicao["data_programada"] = pd.to_datetime(
                proximas_exibicao["data_programada"],
                errors="coerce",
            ).dt.strftime("%d/%m/%Y")

            proximas_exibicao["situação"] = proximas_exibicao["dias_restantes"].apply(
                lambda dias: (
                    "🔴 Vence hoje"
                    if int(dias or 0) == 0
                    else ("🟡 Próxima" if int(dias or 0) <= 15 else "🟢 Programada")
                )
            )

            st.dataframe(
                proximas_exibicao[
                    [
                        "numero",
                        "maquina",
                        "local",
                        "tipo_servico",
                        "data_programada",
                        "dias_restantes",
                        "situação",
                    ]
                ].rename(
                    columns={
                        "numero": "Preventiva",
                        "maquina": "Máquina",
                        "local": "Local",
                        "tipo_servico": "Tipo",
                        "data_programada": "Data programada",
                        "dias_restantes": "Dias restantes",
                        "situação": "Situação",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

        st.divider()

        # ============================================================
        # PREVENTIVAS VENCIDAS
        # ============================================================

        st.markdown("### Preventivas vencidas")

        preventivas_vencidas_lista = fetch_df("""
            SELECT
                p.id,
                p.numero,
                m.codigo AS maquina,
                m.local,
                p.tipo_servico,
                p.data_programada,
                ABS(DATEDIFF(p.data_programada, CURDATE())) AS dias_atraso
            FROM pmoc_preventivas p

            INNER JOIN pmoc_maquinas m
                ON m.id = p.maquina_id

            WHERE p.status = 'ABERTA'
            AND p.data_programada < CURDATE()

            ORDER BY p.data_programada ASC
            """)

        if preventivas_vencidas_lista.empty:
            st.success("Nenhuma preventiva vencida.")

        else:
            vencidas_exibicao = preventivas_vencidas_lista.copy()

            vencidas_exibicao["data_programada"] = pd.to_datetime(
                vencidas_exibicao["data_programada"],
                errors="coerce",
            ).dt.strftime("%d/%m/%Y")

            vencidas_exibicao["situação"] = "🔴 ATRASADA"

            st.dataframe(
                vencidas_exibicao[
                    [
                        "numero",
                        "maquina",
                        "local",
                        "tipo_servico",
                        "data_programada",
                        "dias_atraso",
                        "situação",
                    ]
                ].rename(
                    columns={
                        "numero": "Preventiva",
                        "maquina": "Máquina",
                        "local": "Local",
                        "tipo_servico": "Tipo",
                        "data_programada": "Data programada",
                        "dias_atraso": "Dias em atraso",
                        "situação": "Situação",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

        st.divider()

        # ============================================================
        # CORRETIVAS ABERTAS
        # ============================================================

        st.markdown("### Corretivas abertas")

        corretivas_abertas_lista = fetch_df("""
            SELECT
                pc.id,
                pc.numero,
                pc.service_order_id,
                m.codigo AS maquina,
                m.local,
                so.status AS status_os,
                so.problem_description,
                so.start_datetime
            FROM pmoc_corretivas pc

            INNER JOIN pmoc_maquinas m
                ON m.id = pc.maquina_id

            INNER JOIN service_orders so
                ON so.id = pc.service_order_id

            WHERE so.status NOT IN ('Finalizada', 'Cancelada')

            ORDER BY so.start_datetime DESC
            """)

        if corretivas_abertas_lista.empty:
            st.success("Nenhuma corretiva PMOC aberta.")

        else:
            corretivas_exibicao = corretivas_abertas_lista.copy()

            corretivas_exibicao["start_datetime"] = pd.to_datetime(
                corretivas_exibicao["start_datetime"],
                errors="coerce",
            ).dt.strftime("%d/%m/%Y %H:%M")

            st.dataframe(
                corretivas_exibicao[
                    [
                        "numero",
                        "service_order_id",
                        "maquina",
                        "local",
                        "start_datetime",
                        "status_os",
                        "problem_description",
                    ]
                ].rename(
                    columns={
                        "numero": "Corretiva PMOC",
                        "service_order_id": "OS",
                        "maquina": "Máquina",
                        "local": "Local",
                        "start_datetime": "Abertura",
                        "status_os": "Status",
                        "problem_description": "Problema",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    elif pmoc_menu == "Máquinas":
        st.markdown("### Máquinas de ar-condicionado")

        tab_nova, tab_editar = st.tabs(
            [
                "Nova máquina",
                "Editar / Excluir",
            ]
        )

        # =====================================================
        # NOVA MÁQUINA
        # =====================================================

        with tab_nova:
            with st.form(
                "form_nova_maquina_pmoc",
                clear_on_submit=True,
            ):
                c1, c2, c3 = st.columns(3)

                codigo = c1.text_input(
                    "Código *",
                    placeholder="Ex.: AC-001",
                )

                marca = c2.text_input(
                    "Marca",
                    placeholder="Ex.: Springer",
                )

                modelo = c3.text_input(
                    "Modelo",
                )

                c4, c5, c6 = st.columns(3)

                capacidade = c4.number_input(
                    "Capacidade",
                    min_value=0,
                    step=1000,
                    value=12000,
                )

                unidade_capacidade = c5.selectbox(
                    "Unidade",
                    ["BTU", "TR", "KW"],
                )

                status = c6.selectbox(
                    "Status",
                    ["ATIVA", "DESATIVADA"],
                )

                c7, c8 = st.columns(2)
                periodicidade_dias = c7.number_input(
                    "Periodicidade preventiva",
                    min_value=1,
                    max_value=365,
                    value=90,
                    step=30,
                )
                local = c8.text_input(
                    "Local *",
                    placeholder="Ex.: Sala elétrica",
                )

                observacao = st.text_area("Observação")

                salvar = st.form_submit_button(
                    "Cadastrar máquina",
                    use_container_width=True,
                )

                if salvar:
                    if not codigo.strip():
                        st.error("Informe o código da máquina.")

                    elif not local.strip():
                        st.error("Informe o local da máquina.")

                    else:
                        try:
                            create_pmoc_maquina(
                                codigo=codigo,
                                marca=marca,
                                modelo=modelo,
                                capacidade=capacidade,
                                unidade_capacidade=unidade_capacidade,
                                local=local,
                                status=status,
                                observacao=observacao,
                                periodicidade_dias=periodicidade_dias,
                            )

                            st.success("Máquina PMOC cadastrada com sucesso.")
                            st.rerun()

                        except Exception as e:
                            st.error(str(e))

        # =====================================================
        # EDITAR / EXCLUIR
        # =====================================================

        with tab_editar:
            maquinas_pmoc = get_pmoc_maquinas()

            if maquinas_pmoc.empty:
                st.info("Nenhuma máquina PMOC cadastrada.")

            else:
                tabela = maquinas_pmoc.copy()

                tabela["capacidade"] = tabela.apply(
                    lambda row: (
                        f"{int(row['capacidade'] or 0)} "
                        f"{row['unidade_capacidade'] or 'BTU'}"
                    ),
                    axis=1,
                )

                st.dataframe(
                    tabela[
                        [
                            "codigo",
                            "marca",
                            "modelo",
                            "capacidade",
                            "local",
                            "status",
                        ]
                    ].rename(
                        columns={
                            "codigo": "Código",
                            "marca": "Marca",
                            "modelo": "Modelo",
                            "capacidade": "Capacidade",
                            "local": "Local",
                            "status": "Status",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                maquina_map = {
                    (
                        f"{r['codigo']} | "
                        f"{r['marca'] or 'Sem marca'} | "
                        f"{r['local'] or 'Sem local'}"
                    ): r
                    for _, r in maquinas_pmoc.iterrows()
                }

                maquina_label = st.selectbox(
                    "Selecione a máquina",
                    list(maquina_map.keys()),
                    key="pmoc_maquina_edicao",
                )

                maquina = maquina_map[maquina_label]
                maquina_id = int(maquina["id"])

                unidades = ["BTU", "TR", "KW"]
                unidade_atual = str(maquina.get("unidade_capacidade") or "BTU").upper()

                if unidade_atual not in unidades:
                    unidade_atual = "BTU"

                status_opcoes = [
                    "ATIVA",
                    "DESATIVADA",
                ]

                status_atual = str(maquina.get("status") or "ATIVA").upper()

                if status_atual not in status_opcoes:
                    status_atual = "ATIVA"
                periodicidades = [30, 60, 90, 120, 180, 365]
                periodicidade_atual = int(maquina.get("periodicidade_dias") or 90)

                if periodicidade_atual not in periodicidades:
                    periodicidades.append(periodicidade_atual)
                    periodicidades.sort()
                with st.form(f"form_editar_maquina_pmoc_{maquina_id}"):
                    c1, c2, c3 = st.columns(3)

                    codigo_edicao = c1.text_input(
                        "Código",
                        value=str(maquina.get("codigo") or ""),
                    )

                    marca_edicao = c2.text_input(
                        "Marca",
                        value=str(maquina.get("marca") or ""),
                    )

                    modelo_edicao = c3.text_input(
                        "Modelo",
                        value=str(maquina.get("modelo") or ""),
                    )

                    c4, c5, c6 = st.columns(3)

                    capacidade_edicao = c4.number_input(
                        "Capacidade",
                        min_value=0,
                        step=1000,
                        value=int(maquina.get("capacidade") or 0),
                    )

                    unidade_edicao = c5.selectbox(
                        "Unidade",
                        unidades,
                        index=unidades.index(unidade_atual),
                    )

                    status_edicao = c6.selectbox(
                        "Status",
                        status_opcoes,
                        index=status_opcoes.index(status_atual),
                    )
                    c7, c8 = st.columns(2)

                    periodicidade_edicao = c7.selectbox(
                        "Periodicidade preventiva",
                        periodicidades,
                        index=periodicidades.index(periodicidade_atual),
                        format_func=lambda dias: f"{dias} dias",
                        key=f"pmoc_periodicidade_edicao_{maquina_id}",
                    )

                    local_edicao = c8.text_input(
                        "Local",
                        value=str(maquina.get("local") or ""),
                    )

                    observacao_edicao = st.text_area(
                        "Observação",
                        value=str(maquina.get("observacao") or ""),
                    )

                    c_salvar, c_excluir = st.columns(2)

                    salvar_edicao = c_salvar.form_submit_button(
                        "Salvar alterações",
                        use_container_width=True,
                    )

                    excluir = c_excluir.form_submit_button(
                        "Excluir máquina",
                        use_container_width=True,
                    )

                if salvar_edicao:
                    try:
                        update_pmoc_maquina(
                            maquina_id=maquina_id,
                            codigo=codigo_edicao,
                            marca=marca_edicao,
                            modelo=modelo_edicao,
                            capacidade=capacidade_edicao,
                            unidade_capacidade=unidade_edicao,
                            local=local_edicao,
                            status=status_edicao,
                            periodicidade_dias=periodicidade_edicao,
                            observacao=observacao_edicao,
                        )

                        st.success("Máquina PMOC atualizada.")
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))

                if excluir:
                    try:
                        delete_pmoc_maquina(maquina_id)

                        st.success("Máquina PMOC excluída.")
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))

            st.divider()
            st.markdown("### Histórico da máquina")

            resumo_preventiva = get_pmoc_ultima_proxima_preventiva(maquina_id)

            ultima_execucao = None
            proxima_programada = None
            preventiva_atrasada = None

            if not resumo_preventiva.empty:
                ultima_execucao = pd.to_datetime(
                    resumo_preventiva.iloc[0].get("ultima_execucao"),
                    errors="coerce",
                )

                proxima_programada = pd.to_datetime(
                    resumo_preventiva.iloc[0].get("proxima_programada"),
                    errors="coerce",
                )

                preventiva_atrasada = pd.to_datetime(
                    resumo_preventiva.iloc[0].get("preventiva_atrasada"),
                    errors="coerce",
                )

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Última preventiva",
                (
                    ultima_execucao.strftime("%d/%m/%Y")
                    if not pd.isna(ultima_execucao)
                    else "Sem registro"
                ),
            )

            c2.metric(
                "Próxima preventiva",
                (
                    proxima_programada.strftime("%d/%m/%Y")
                    if not pd.isna(proxima_programada)
                    else "Não programada"
                ),
            )

            c3.metric(
                "Situação",
                ("ATRASADA" if not pd.isna(preventiva_atrasada) else "EM DIA"),
            )

            historico_preventivas = get_pmoc_historico_preventivas(maquina_id)

            historico_corretivas = get_pmoc_historico_corretivas(maquina_id)

            tab_hist_prev, tab_hist_corr = st.tabs(
                [
                    "Preventivas",
                    "Corretivas",
                ]
            )
            with tab_hist_prev:
                if historico_preventivas.empty:
                    st.info("Nenhuma preventiva registrada para esta máquina.")

                else:
                    tabela_preventivas = historico_preventivas.copy()

                    tabela_preventivas["data_programada"] = pd.to_datetime(
                        tabela_preventivas["data_programada"],
                        errors="coerce",
                    ).dt.strftime("%d/%m/%Y")

                    tabela_preventivas["data_execucao"] = pd.to_datetime(
                        tabela_preventivas["data_execucao"],
                        errors="coerce",
                    ).dt.strftime("%d/%m/%Y")

                    st.dataframe(
                        tabela_preventivas[
                            [
                                "numero",
                                "tipo_servico",
                                "data_programada",
                                "data_execucao",
                                "status",
                                "observacao",
                            ]
                        ].rename(
                            columns={
                                "numero": "Preventiva",
                                "tipo_servico": "Tipo",
                                "data_programada": "Programada",
                                "data_execucao": "Executada",
                                "status": "Status",
                                "observacao": "Observação",
                            }
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
            with tab_hist_corr:
                if historico_corretivas.empty:
                    st.info("Nenhuma corretiva registrada para esta máquina.")

                else:
                    tabela_corretivas = historico_corretivas.copy()

                    tabela_corretivas["start_datetime"] = pd.to_datetime(
                        tabela_corretivas["start_datetime"],
                        errors="coerce",
                    ).dt.strftime("%d/%m/%Y %H:%M")

                    tabela_corretivas["end_datetime"] = pd.to_datetime(
                        tabela_corretivas["end_datetime"],
                        errors="coerce",
                    ).dt.strftime("%d/%m/%Y %H:%M")

                    st.dataframe(
                        tabela_corretivas[
                            [
                                "numero",
                                "service_order_id",
                                "start_datetime",
                                "end_datetime",
                                "status_os",
                                "problem_description",
                                "solution_description",
                            ]
                        ].rename(
                            columns={
                                "numero": "Corretiva PMOC",
                                "service_order_id": "OS",
                                "start_datetime": "Início",
                                "end_datetime": "Fim",
                                "status_os": "Status da OS",
                                "problem_description": "Problema",
                                "solution_description": "Solução",
                            }
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

    elif pmoc_menu == "Nova preventiva":
        st.markdown("### Nova preventiva PMOC")

        maquinas_pmoc = get_pmoc_maquinas(apenas_ativas=True)

        funcionarios_pmoc = get_employees()

        if maquinas_pmoc.empty:
            st.warning("Cadastre pelo menos uma máquina PMOC ativa.")

        elif funcionarios_pmoc.empty:
            st.warning("Cadastre pelo menos um funcionário.")

        else:
            maquina_map = {
                (
                    f"{r['codigo']} | "
                    f"{r['marca'] or 'Sem marca'} | "
                    f"{r['local'] or 'Sem local'}"
                ): int(r["id"])
                for _, r in maquinas_pmoc.iterrows()
            }

            funcionario_map = {
                (f"{r['nome']} | " f"{r.get('funcao') or 'Sem função'}"): int(r["id"])
                for _, r in funcionarios_pmoc.iterrows()
            }

            tipos_servico = [
                "HIGIENIZACAO",
                "LIMPEZA",
                "INSPECAO",
                "TROCA DE FILTRO",
                "OUTRO",
            ]

            with st.form(
                "form_nova_preventiva_pmoc",
                clear_on_submit=True,
            ):
                maquina_label = st.selectbox(
                    "Máquina",
                    list(maquina_map.keys()),
                )

                c1, c2, c3 = st.columns(3)

                tipo_servico = c1.selectbox(
                    "Tipo de serviço",
                    tipos_servico,
                )

                data_programada = c2.date_input(
                    "Data programada",
                    value=date.today(),
                    format="DD/MM/YYYY",
                )

                status = c3.selectbox(
                    "Status",
                    [
                        "ABERTA",
                        "EXECUTADA",
                        "CANCELADA",
                    ],
                )

                data_execucao = None

                if status == "EXECUTADA":
                    data_execucao = st.date_input(
                        "Data da execução",
                        value=date.today(),
                        format="DD/MM/YYYY",
                    )

                executores_labels = st.multiselect(
                    "Executor(es)",
                    list(funcionario_map.keys()),
                )

                observacao = st.text_area("Observação")

                fotos = st.file_uploader(
                    "Fotos da preventiva",
                    type=[
                        "png",
                        "jpg",
                        "jpeg",
                        "webp",
                    ],
                    accept_multiple_files=True,
                    key="fotos_nova_preventiva_pmoc",
                )

                salvar_preventiva = st.form_submit_button(
                    "Cadastrar preventiva",
                    use_container_width=True,
                )

                if salvar_preventiva:
                    if not executores_labels:
                        st.error("Selecione pelo menos um executor.")

                    else:
                        executores_ids = [
                            funcionario_map[label] for label in executores_labels
                        ]

                        try:
                            preventiva_id, numero = create_pmoc_preventiva(
                                maquina_id=maquina_map[maquina_label],
                                tipo_servico=tipo_servico,
                                data_programada=data_programada,
                                status=status,
                                observacao=observacao,
                                executores_ids=executores_ids,
                                fotos=fotos,
                                usuario=user["usuario"],
                                data_execucao=data_execucao,
                            )

                            st.success(f"Preventiva {numero} cadastrada.")
                            st.rerun()

                        except Exception as e:
                            st.error(str(e))

    elif pmoc_menu == "Preventivas":
        st.markdown("### Preventivas PMOC")

        preventivas = get_pmoc_preventivas()

        if preventivas.empty:
            st.info("Nenhuma preventiva PMOC cadastrada.")

        else:
            filtro1, filtro2, filtro3 = st.columns(3)

            status_filtro = filtro1.selectbox(
                "Status",
                [
                    "TODOS",
                    "ABERTA",
                    "EXECUTADA",
                    "CANCELADA",
                ],
                key="pmoc_filtro_status",
            )

            maquinas_filtro = ["TODAS"] + sorted(
                preventivas["maquina_codigo"].dropna().unique().tolist()
            )

            maquina_filtro = filtro2.selectbox(
                "Máquina",
                maquinas_filtro,
                key="pmoc_filtro_maquina",
            )

            tipos_filtro = ["TODOS"] + sorted(
                preventivas["tipo_servico"].dropna().unique().tolist()
            )

            tipo_filtro = filtro3.selectbox(
                "Tipo de serviço",
                tipos_filtro,
                key="pmoc_filtro_tipo",
            )

            c_data1, c_data2 = st.columns(2)

            data_inicio_filtro = c_data1.date_input(
                "Data inicial",
                value=date.today().replace(
                    month=1,
                    day=1,
                ),
                format="DD/MM/YYYY",
                key="pmoc_data_inicio",
            )

            data_fim_filtro = c_data2.date_input(
                "Data final",
                value=date.today(),
                format="DD/MM/YYYY",
                key="pmoc_data_fim",
            )

            filtradas = preventivas.copy()

            filtradas["data_programada_dt"] = pd.to_datetime(
                filtradas["data_programada"],
                errors="coerce",
            )

            filtradas = filtradas[
                (filtradas["data_programada_dt"].dt.date >= data_inicio_filtro)
                & (filtradas["data_programada_dt"].dt.date <= data_fim_filtro)
            ]

            if status_filtro != "TODOS":
                filtradas = filtradas[filtradas["status"] == status_filtro]

            if maquina_filtro != "TODAS":
                filtradas = filtradas[filtradas["maquina_codigo"] == maquina_filtro]

            if tipo_filtro != "TODOS":
                filtradas = filtradas[filtradas["tipo_servico"] == tipo_filtro]

            exibicao = filtradas.copy()

            exibicao["data_programada"] = pd.to_datetime(
                exibicao["data_programada"],
                errors="coerce",
            ).dt.strftime("%d/%m/%Y")

            exibicao["data_execucao"] = pd.to_datetime(
                exibicao["data_execucao"],
                errors="coerce",
            ).dt.strftime("%d/%m/%Y")

            st.dataframe(
                exibicao[
                    [
                        "numero",
                        "maquina_codigo",
                        "local",
                        "tipo_servico",
                        "data_programada",
                        "data_execucao",
                        "status",
                    ]
                ].rename(
                    columns={
                        "numero": "Número",
                        "maquina_codigo": "Máquina",
                        "local": "Local",
                        "tipo_servico": "Tipo",
                        "data_programada": "Programada",
                        "data_execucao": "Executada",
                        "status": "Status",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

            if filtradas.empty:
                st.warning("Nenhuma preventiva encontrada " "com esses filtros.")

            else:
                preventiva_map = {
                    (
                        f"{r['numero']} | " f"{r['maquina_codigo']} | " f"{r['status']}"
                    ): int(r["id"])
                    for _, r in filtradas.iterrows()
                }

                selecionada_label = st.selectbox(
                    "Selecionar preventiva",
                    list(preventiva_map.keys()),
                    key="pmoc_preventiva_selecionada",
                )

                preventiva_id = preventiva_map[selecionada_label]

                preventiva = get_pmoc_preventiva(preventiva_id)

                executores_atuais = get_pmoc_preventiva_executores(preventiva_id)

                fotos_atuais = get_pmoc_preventiva_fotos(preventiva_id)

                try:
                    pdf_pmoc = gerar_laudo_pmoc_pdf(preventiva_id)

                    st.download_button(
                        "📄 Gerar Laudo PMOC",
                        data=pdf_pmoc,
                        file_name=(f"laudo_pmoc_" f"{preventiva['numero']}.pdf"),
                        mime="application/pdf",
                        use_container_width=True,
                        key=f"baixar_laudo_pmoc_{preventiva_id}",
                    )

                except Exception as erro_pdf:
                    st.error(f"Não foi possível gerar o laudo: " f"{erro_pdf}")

                tab_dados, tab_checklist, tab_medicoes, tab_fotos = st.tabs(
                    [
                        "Editar preventiva",
                        "Checklist",
                        "Medições",
                        "Fotos",
                    ]
                )

                with tab_dados:
                    maquinas_pmoc = get_pmoc_maquinas()

                    funcionarios_pmoc = get_employees()

                    maquina_map = {
                        (f"{r['codigo']} | " f"{r['local'] or 'Sem local'}"): int(
                            r["id"]
                        )
                        for _, r in maquinas_pmoc.iterrows()
                    }

                    maquina_atual_label = next(
                        (
                            label
                            for label, maquina_id in maquina_map.items()
                            if int(maquina_id) == int(preventiva["maquina_id"])
                        ),
                        list(maquina_map.keys())[0],
                    )

                    funcionario_map = {
                        (f"{r['nome']} | " f"{r.get('funcao') or 'Sem função'}"): int(
                            r["id"]
                        )
                        for _, r in funcionarios_pmoc.iterrows()
                    }

                    executores_ids_atuais = set(
                        executores_atuais["funcionario_id"].astype(int).tolist()
                    )

                    executores_labels_atuais = [
                        label
                        for label, funcionario_id in funcionario_map.items()
                        if int(funcionario_id) in executores_ids_atuais
                    ]

                    status_opcoes = [
                        "ABERTA",
                        "EXECUTADA",
                        "CANCELADA",
                    ]

                    status_atual = str(preventiva.get("status") or "ABERTA")

                    tipos_servico = [
                        "HIGIENIZACAO",
                        "LIMPEZA",
                        "INSPECAO",
                        "TROCA DE FILTRO",
                        "OUTRO",
                    ]

                    tipo_atual = str(preventiva.get("tipo_servico") or "HIGIENIZACAO")

                    data_programada_atual = pd.to_datetime(
                        preventiva.get("data_programada"),
                        errors="coerce",
                    )

                    if pd.isna(data_programada_atual):
                        data_programada_atual = date.today()
                    else:
                        data_programada_atual = data_programada_atual.date()

                    data_execucao_atual = pd.to_datetime(
                        preventiva.get("data_execucao"),
                        errors="coerce",
                    )

                    if pd.isna(data_execucao_atual):
                        data_execucao_atual = date.today()
                    else:
                        data_execucao_atual = data_execucao_atual.date()

                    with st.form(f"editar_pmoc_{preventiva_id}"):
                        maquina_edicao = st.selectbox(
                            "Máquina",
                            list(maquina_map.keys()),
                            index=list(maquina_map.keys()).index(maquina_atual_label),
                        )

                        c1, c2, c3 = st.columns(3)

                        tipo_edicao = c1.selectbox(
                            "Tipo de serviço",
                            tipos_servico,
                            index=(
                                tipos_servico.index(tipo_atual)
                                if tipo_atual in tipos_servico
                                else 0
                            ),
                        )

                        data_programada_edicao = c2.date_input(
                            "Data programada",
                            value=(data_programada_atual),
                            format="DD/MM/YYYY",
                        )

                        status_edicao = c3.selectbox(
                            "Status",
                            status_opcoes,
                            index=(
                                status_opcoes.index(status_atual)
                                if status_atual in status_opcoes
                                else 0
                            ),
                        )

                        data_execucao_edicao = st.date_input(
                            "Data de execução",
                            value=data_execucao_atual,
                            format="DD/MM/YYYY",
                        )

                        executores_edicao = st.multiselect(
                            "Executor(es)",
                            list(funcionario_map.keys()),
                            default=(executores_labels_atuais),
                        )

                        observacao_edicao = st.text_area(
                            "Observação",
                            value=str(preventiva.get("observacao") or ""),
                        )

                        c_salvar, c_excluir = st.columns(2)

                        salvar = c_salvar.form_submit_button(
                            "Salvar alterações",
                            use_container_width=True,
                        )

                        excluir = c_excluir.form_submit_button(
                            "Excluir preventiva",
                            use_container_width=True,
                        )

                    if salvar:
                        if not executores_edicao:
                            st.error("Selecione pelo menos " "um executor.")

                        else:
                            data_execucao_salvar = (
                                data_execucao_edicao
                                if status_edicao == "EXECUTADA"
                                else None
                            )

                            update_pmoc_preventiva(
                                preventiva_id=preventiva_id,
                                maquina_id=maquina_map[maquina_edicao],
                                tipo_servico=tipo_edicao,
                                data_programada=(data_programada_edicao),
                                data_execucao=(data_execucao_salvar),
                                status=status_edicao,
                                observacao=(observacao_edicao),
                                executores_ids=[
                                    funcionario_map[label]
                                    for label in executores_edicao
                                ],
                            )
                            proxima_preventiva = None

                            if status_edicao == "EXECUTADA":
                                proxima_preventiva = gerar_proxima_preventiva_pmoc(
                                    preventiva_id=preventiva_id,
                                    usuario=user["usuario"],
                                )

                            if proxima_preventiva:
                                _, novo_numero, proxima_data = proxima_preventiva

                                st.success(
                                    f"Preventiva atualizada. Próxima preventiva "
                                    f"{novo_numero} criada para "
                                    f"{proxima_data.strftime('%d/%m/%Y')}."
                                )
                            else:
                                st.success("Preventiva atualizada.")
                            st.rerun()

                    if excluir:
                        try:
                            delete_pmoc_preventiva(preventiva_id)

                            st.success("Preventiva excluída.")
                            st.rerun()

                        except Exception as e:
                            st.error(str(e))

                with tab_checklist:
                    garantir_pmoc_checklist(preventiva_id)

                    checklist = get_pmoc_checklist(preventiva_id)

                    if checklist.empty:
                        st.info("Checklist não disponível.")
                    else:
                        respostas_checklist = []

                        with st.form(f"form_checklist_pmoc_{preventiva_id}"):
                            for grupo in checklist["grupo"].drop_duplicates():
                                st.markdown(f"### {grupo}")

                                itens_grupo = checklist[checklist["grupo"] == grupo]

                                for _, item_row in itens_grupo.iterrows():
                                    item_id = int(item_row["id"])

                                    c1, c2 = st.columns([1, 3])

                                    executado = c1.checkbox(
                                        "OK",
                                        value=bool(int(item_row["executado"] or 0)),
                                        key=f"pmoc_check_ok_{item_id}",
                                    )

                                    observacao_item = c2.text_input(
                                        str(item_row["item"]),
                                        value=str(item_row["observacao"] or ""),
                                        key=f"pmoc_check_obs_{item_id}",
                                    )

                                    respostas_checklist.append(
                                        {
                                            "id": item_id,
                                            "executado": executado,
                                            "observacao": observacao_item,
                                        }
                                    )

                                st.divider()

                            salvar_checklist = st.form_submit_button(
                                "Salvar checklist",
                                use_container_width=True,
                            )

                        if salvar_checklist:
                            salvar_pmoc_checklist(
                                preventiva_id=preventiva_id,
                                respostas=respostas_checklist,
                            )

                            st.success("Checklist salvo com sucesso.")
                            st.rerun()
                with tab_medicoes:
                    st.markdown("### Medições da preventiva")

                    medicao_atual = get_pmoc_medicao(preventiva_id)

                    retorno_atual = 0.0
                    insuflada_atual = 0.0
                    corrente_atual = 0.0
                    tensao_atual = 0.0
                    pressao_alta_atual = 0.0
                    pressao_baixa_atual = 0.0
                    observacao_medicao_atual = ""

                    if medicao_atual is not None:
                        retorno_atual = float(
                            medicao_atual.get("temperatura_retorno") or 0
                        )

                        insuflada_atual = float(
                            medicao_atual.get("temperatura_insuflada") or 0
                        )

                        corrente_atual = float(medicao_atual.get("corrente") or 0)

                        tensao_atual = float(medicao_atual.get("tensao") or 0)

                        pressao_alta_atual = float(
                            medicao_atual.get("pressao_alta") or 0
                        )

                        pressao_baixa_atual = float(
                            medicao_atual.get("pressao_baixa") or 0
                        )

                        observacao_medicao_atual = str(
                            medicao_atual.get("observacao") or ""
                        )

                    with st.form(f"form_medicoes_pmoc_{preventiva_id}"):
                        c1, c2 = st.columns(2)

                        temperatura_retorno = c1.number_input(
                            "Temperatura de retorno (°C)",
                            min_value=-50.0,
                            max_value=100.0,
                            value=retorno_atual,
                            step=0.1,
                            format="%.1f",
                            key=f"pmoc_temp_retorno_{preventiva_id}",
                        )

                        temperatura_insuflada = c2.number_input(
                            "Temperatura insuflada (°C)",
                            min_value=-50.0,
                            max_value=100.0,
                            value=insuflada_atual,
                            step=0.1,
                            format="%.1f",
                            key=f"pmoc_temp_insuflada_{preventiva_id}",
                        )

                        delta_t = float(temperatura_retorno) - float(
                            temperatura_insuflada
                        )

                        c_delta, c_situacao = st.columns(2)

                        c_delta.metric(
                            "ΔT",
                            f"{delta_t:.1f} °C",
                        )

                        if temperatura_retorno == 0 and temperatura_insuflada == 0:
                            situacao_delta = "Não informado"

                        elif delta_t > 18:
                            situacao_delta = "🟡 Verificar vazão de ar ou medição"

                        elif delta_t >= 12:
                            situacao_delta = "🟢 Excelente"

                        elif delta_t >= 10:
                            situacao_delta = "🟢 Muito boa"

                        elif delta_t >= 8:
                            situacao_delta = "🟡 Atenção"

                        elif delta_t >= 6:
                            situacao_delta = "🟠 Verificar equipamento"

                        else:
                            situacao_delta = "🔴 Baixa eficiência"

                        c_situacao.metric(
                            "Avaliação térmica",
                            situacao_delta,
                        )

                        st.divider()

                        c3, c4 = st.columns(2)

                        corrente = c3.number_input(
                            "Corrente do equipamento (A)",
                            min_value=0.0,
                            value=corrente_atual,
                            step=0.1,
                            format="%.2f",
                            key=f"pmoc_corrente_{preventiva_id}",
                        )

                        tensao = c4.number_input(
                            "Tensão de alimentação (V)",
                            min_value=0.0,
                            value=tensao_atual,
                            step=1.0,
                            format="%.1f",
                            key=f"pmoc_tensao_{preventiva_id}",
                        )

                        c5, c6 = st.columns(2)

                        pressao_alta = c5.number_input(
                            "Pressão alta",
                            min_value=0.0,
                            value=pressao_alta_atual,
                            step=1.0,
                            format="%.2f",
                            key=f"pmoc_pressao_alta_{preventiva_id}",
                        )

                        pressao_baixa = c6.number_input(
                            "Pressão baixa",
                            min_value=0.0,
                            value=pressao_baixa_atual,
                            step=1.0,
                            format="%.2f",
                            key=f"pmoc_pressao_baixa_{preventiva_id}",
                        )

                        observacao_medicao = st.text_area(
                            "Observações das medições",
                            value=observacao_medicao_atual,
                            key=f"pmoc_obs_medicao_{preventiva_id}",
                        )

                        salvar_medicoes = st.form_submit_button(
                            "Salvar medições",
                            use_container_width=True,
                        )

                    if salvar_medicoes:
                        salvar_pmoc_medicao(
                            preventiva_id=preventiva_id,
                            retorno=temperatura_retorno,
                            insuflada=temperatura_insuflada,
                            corrente=corrente,
                            tensao=tensao,
                            pressao_alta=pressao_alta,
                            pressao_baixa=pressao_baixa,
                            observacao=observacao_medicao,
                        )

                        st.success("Medições salvas com sucesso.")
                        st.rerun()
                with tab_fotos:
                    novas_fotos = st.file_uploader(
                        "Adicionar novas fotos",
                        type=[
                            "png",
                            "jpg",
                            "jpeg",
                            "webp",
                        ],
                        accept_multiple_files=True,
                        key=f"pmoc_novas_fotos_{preventiva_id}",
                    )

                    if st.button(
                        "Salvar novas fotos",
                        key=f"pmoc_salvar_fotos_{preventiva_id}",
                        use_container_width=True,
                    ):
                        if not novas_fotos:
                            st.warning("Selecione pelo menos uma foto.")
                        else:
                            salvar_fotos_pmoc(
                                preventiva_id=preventiva_id,
                                numero=preventiva["numero"],
                                fotos=novas_fotos,
                                usuario=user["usuario"],
                            )

                            st.success("Fotos adicionadas.")
                            st.rerun()

                    if fotos_atuais.empty:
                        st.info("Nenhuma foto cadastrada.")

                    else:
                        for _, foto in fotos_atuais.iterrows():
                            caminho = Path(str(foto["caminho"]))

                            st.markdown(f"**{foto['nome_arquivo']}**")

                            if caminho.exists():
                                st.image(
                                    str(caminho),
                                    width=350,
                                )

                            if st.button(
                                "Excluir foto",
                                key=(f"excluir_foto_pmoc_" f"{int(foto['id'])}"),
                            ):
                                delete_pmoc_foto(int(foto["id"]))

                                st.success("Foto excluída.")
                                st.rerun()

                            st.divider()

    elif pmoc_menu == "Corretivas":
        st.markdown("### Corretivas PMOC")

        corretivas = fetch_df("""
            SELECT
                pc.id,
                pc.numero,
                pc.maquina_id,
                pm.codigo AS maquina_codigo,
                pm.marca,
                pm.modelo,
                pm.local,
                pc.service_order_id,
                so.status AS status_os,
                so.problem_description,
                so.solution_description,
                so.start_datetime,
                so.end_datetime,
                pc.status AS status_pmoc,
                pc.observacao,
                pc.created_at,
                pc.updated_at

            FROM pmoc_corretivas pc

            LEFT JOIN pmoc_maquinas pm
                ON pm.id = pc.maquina_id

            LEFT JOIN service_orders so
                ON so.id = pc.service_order_id

            ORDER BY pc.id DESC
            """)

        if corretivas.empty:
            st.info("Nenhuma corretiva PMOC vinculada.")

        else:
            c1, c2 = st.columns(2)

            status_filtro = c1.selectbox(
                "Status da ordem",
                [
                    "TODOS",
                    "Aberta",
                    "Em andamento",
                    "Finalizada",
                    "Cancelada",
                ],
                key="pmoc_corretiva_filtro_status",
            )

            maquinas_opcoes = ["TODAS"] + sorted(
                corretivas["maquina_codigo"].dropna().astype(str).unique().tolist()
            )

            maquina_filtro = c2.selectbox(
                "Máquina",
                maquinas_opcoes,
                key="pmoc_corretiva_filtro_maquina",
            )

            filtradas = corretivas.copy()

            if status_filtro != "TODOS":
                filtradas = filtradas[filtradas["status_os"] == status_filtro]

            if maquina_filtro != "TODAS":
                filtradas = filtradas[filtradas["maquina_codigo"] == maquina_filtro]

            st.dataframe(
                filtradas[
                    [
                        "numero",
                        "service_order_id",
                        "maquina_codigo",
                        "local",
                        "status_os",
                        "problem_description",
                    ]
                ].rename(
                    columns={
                        "numero": "Corretiva PMOC",
                        "service_order_id": "Código da OS",
                        "maquina_codigo": "Máquina",
                        "local": "Local",
                        "status_os": "Status da OS",
                        "problem_description": "Problema",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

            if filtradas.empty:
                st.warning("Nenhuma corretiva encontrada com os filtros selecionados.")

            else:
                corretiva_map = {
                    (
                        f"{r['numero']} | "
                        f"OS {int(r['service_order_id'])} | "
                        f"{r['maquina_codigo'] or 'Sem máquina'}"
                    ): r
                    for _, r in filtradas.iterrows()
                }

                selecionada = st.selectbox(
                    "Visualizar corretiva",
                    list(corretiva_map.keys()),
                    key="pmoc_corretiva_selecionada",
                )

                row = corretiva_map[selecionada]

                st.divider()
                st.markdown(f"#### {row['numero']}")

                c1, c2, c3 = st.columns(3)

                c1.markdown(
                    f"**Ordem vinculada:** " f"OS {int(row['service_order_id'])}"
                )

                c2.markdown(f"**Máquina:** " f"{row['maquina_codigo'] or ''}")

                c3.markdown(f"**Status da OS:** " f"{row['status_os'] or ''}")

                st.markdown(
                    f"**Marca/Modelo:** "
                    f"{row['marca'] or ''} "
                    f"{row['modelo'] or ''}"
                )

                st.markdown(f"**Local:** " f"{row['local'] or ''}")

                st.markdown("**Descrição do problema**")
                st.write(row["problem_description"] or "")

                st.markdown("**Solução registrada na OS**")
                st.write(row["solution_description"] or "Ainda não informada.")

                st.markdown("**Observação PMOC**")
                st.write(row["observacao"] or "")

                inicio = pd.to_datetime(
                    row.get("start_datetime"),
                    errors="coerce",
                )

                fim = pd.to_datetime(
                    row.get("end_datetime"),
                    errors="coerce",
                )

                c4, c5 = st.columns(2)

                c4.markdown(
                    "**Início:** "
                    + (inicio.strftime("%d/%m/%Y %H:%M") if not pd.isna(inicio) else "")
                )

                c5.markdown(
                    "**Fim:** "
                    + (fim.strftime("%d/%m/%Y %H:%M") if not pd.isna(fim) else "")
                )


elif menu == "Produção":
    try:
        producao.set_database_url(get_current_database_url())
        producao.tela_producao(
            usuario=user.get("nome", "Sistema"), planta_label=get_planta_label()
        )
    except Exception as erro:
        st.error(f"Erro ao abrir módulo de produção: {erro}")

elif menu == "Solicitações de Compras/Serviços":
    require_permission(
        can_view_purchases(),
        "Você não possui acesso ao módulo Solicitações.",
    )

    preparar_sessao_compras()
    shop_manager.criar_tabelas()

    st.subheader("📥 Solicitações de Compras/Serviços")
    st.caption(
        "Solicitações de materiais e serviços para análise " "e conversão em pedidos."
    )

    shop_manager.tela_solicitacoes()

elif menu == "Compras":
    require_permission(
        can_view_purchases(), "Você não possui acesso ao módulo Compras."
    )
    tela_compras_integrada()

elif menu == "Produtos / Estoque":
    require_permission(
        can_view_stock(),
        "Somente Administrador, Almoxarifado ou Operador pode acessar Produtos / Estoque.",
    )
    st.subheader("Produtos / Estoque")
    t1, t2, t3, t4, t5 = st.tabs(
        ["Novo produto", "Editar / Excluir", "Entrada/Saída", "Consulta", "Histórico"]
    )

    with t1:
        if is_operador():
            st.info("Operador possui acesso somente para consulta de estoque.")
        else:
            with st.form("novo_produto", clear_on_submit=True):
                c1, c2, c3 = st.columns(3)
                nome = c1.text_input("Nome")
                unidade = c2.selectbox("Unidade", ["UN", "KG", "PC", "M", "L"])
                estoque_inicial = c3.number_input(
                    "Estoque inicial", min_value=0.0, value=0.0
                )

                c4, c5 = st.columns([1, 2])
                estoque_minimo = c4.number_input(
                    "Estoque mínimo", min_value=0.0, value=0.0
                )
                descricao = c5.text_area("Descrição")

                valor_unitario = st.number_input(
                    "Valor unitário inicial",
                    min_value=0.0,
                    value=0.0,
                    step=0.01,
                )

                centro_custo_id = select_cost_center(
                    "Centro de custo do produto",
                    key="cc_prod_novo",
                )

                if st.form_submit_button("Salvar produto", use_container_width=True):
                    create_product(
                        nome,
                        descricao,
                        unidade,
                        estoque_inicial,
                        estoque_minimo,
                        centro_custo_id,
                        valor_unitario,
                    )
                    st.success("Produto cadastrado.")
                    st.rerun()

    with t2:
        if is_operador():
            st.info("Operador possui acesso somente para consulta de estoque.")
        elif products_df.empty:
            st.info("Nenhum produto cadastrado.")
        else:
            prod_map = {
                f"ID {int(r['id'])} - {r['nome']}": r for _, r in products_df.iterrows()
            }

            sel = st.selectbox("Selecionar produto", list(prod_map.keys()))
            row = prod_map[sel]

            unidades = ["UN", "KG", "PC", "M", "L"]
            unidade_atual = row["unidade"] if row["unidade"] in unidades else "UN"

            with st.form("editar_produto"):
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome", value=str(row["nome"]))
                unidade = c2.selectbox(
                    "Unidade",
                    unidades,
                    index=unidades.index(unidade_atual),
                )

                c3, c4 = st.columns(2)
                c3.number_input(
                    "Estoque atual",
                    value=float(row["estoque_atual"] or 0),
                    disabled=True,
                )
                estoque_minimo = c4.number_input(
                    "Estoque mínimo",
                    min_value=0.0,
                    value=float(row["estoque_minimo"] or 0),
                )

                valor_unitario = st.number_input(
                    "Valor unitário médio atual",
                    min_value=0.0,
                    value=float(row.get("valor_unitario", 0) or 0),
                    step=0.01,
                )

                descricao = st.text_area(
                    "Descrição",
                    value="" if pd.isna(row["descricao"]) else str(row["descricao"]),
                )

                centro_custo_id = select_cost_center_with_current(
                    "Centro de custo do produto",
                    row.get("centro_custo_id", None),
                    key=f"cc_prod_edit_{int(row['id'])}",
                )

                b1, b2 = st.columns(2)

                with b1:
                    salvar = st.form_submit_button(
                        "Atualizar produto",
                        use_container_width=True,
                    )

                with b2:
                    excluir = st.form_submit_button(
                        "Excluir produto",
                        use_container_width=True,
                    )

                if salvar:
                    update_product_record(
                        int(row["id"]),
                        nome,
                        descricao,
                        unidade,
                        estoque_minimo,
                        centro_custo_id,
                        valor_unitario,
                    )
                    st.success("Produto atualizado.")
                    st.rerun()

                if excluir:
                    try:
                        delete_product_record(int(row["id"]))
                        st.success("Produto excluído.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

    with t3:
        if is_operador():
            st.info("Operador não pode lançar movimentações de estoque.")
        else:
            if products_df.empty:
                st.info("Cadastre produtos primeiro.")
            else:
                with st.form("mov_estoque", clear_on_submit=True):
                    produto_map = {
                        f"ID {int(r['id'])} - {r['nome']} | saldo: {r['estoque_atual']} {r['unidade']}": int(
                            r["id"]
                        )
                        for _, r in products_df.iterrows()
                    }

                    produto = st.selectbox("Produto", list(produto_map.keys()))
                    tipo = st.selectbox("Tipo", ["ENTRADA", "SAIDA"])
                    quantidade = st.number_input(
                        "Quantidade", min_value=0.01, value=1.0
                    )

                    valor_unitario_entrada = 0.0
                    if tipo == "ENTRADA":
                        valor_unitario_entrada = st.number_input(
                            "Valor unitário da entrada",
                            min_value=0.0,
                            value=0.0,
                            step=0.01,
                        )

                    observacao = st.text_input("Observação")

                    if st.form_submit_button("Lançar", use_container_width=True):
                        register_stock_movement(
                            produto_map[produto],
                            tipo,
                            quantidade,
                            observacao,
                            user["usuario"],
                            valor_unitario_entrada,
                        )
                        st.success("Movimentação registrada.")
                        st.rerun()

    with t4:
        if products_df.empty:
            st.info("Nenhum produto cadastrado.")
        else:
            df_view = products_df.copy()
            if "valor_unitario" in df_view.columns:
                df_view["valor_total"] = df_view["estoque_atual"].astype(
                    float
                ) * df_view["valor_unitario"].astype(float)

            st.dataframe(
                df_view.rename(
                    columns={
                        "id": "ID",
                        "nome": "Produto",
                        "descricao": "Descrição",
                        "unidade": "Unidade",
                        "estoque_atual": "Estoque atual",
                        "estoque_minimo": "Estoque mínimo",
                        "valor_unitario": "Valor unitário",
                        "valor_total": "Valor total",
                        "centro_custo": "Centro de custo",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    with t5:
        mov_df = get_movements()
        if mov_df.empty:
            st.info("Nenhuma movimentação registrada.")
        else:
            st.dataframe(
                mov_df.rename(
                    columns={
                        "id": "ID",
                        "produto_id": "ID produto",
                        "produto": "Produto",
                        "tipo": "Tipo",
                        "quantidade": "Quantidade",
                        "unidade": "Unidade",
                        "usuario_lancamento": "Usuário",
                        "observacao": "Observação",
                        "criado_em": "Data/hora",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

elif menu == "Máquinas":
    require_permission(
        can_manage_master_data(),
        "Somente Administrador ou Almoxarifado pode acessar Máquinas.",
    )
    st.subheader("Máquinas")
    t1, t2 = st.tabs(["Nova máquina", "Editar / Excluir"])

    with t1:
        with st.form("nova_maquina", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome da máquina")
            status = c2.selectbox(
                "Status", ["Ativa", "Parada", "Em manutenção", "Inativa"]
            )
            if st.form_submit_button("Salvar máquina", use_container_width=True):
                create_machine(nome, status)
                st.success("Máquina cadastrada.")
                st.rerun()

    with t2:
        if machines_df.empty:
            st.info("Nenhuma máquina cadastrada.")
        else:
            maq_map = {
                f"ID {int(r['id'])} - {r['nome']}": r for _, r in machines_df.iterrows()
            }
            sel = st.selectbox("Selecionar máquina", list(maq_map.keys()))
            row = maq_map[sel]
            with st.form("editar_maquina"):
                nome = st.text_input("Nome", value=str(row["nome"]))
                opts = ["Ativa", "Parada", "Em manutenção", "Inativa"]
                status = st.selectbox(
                    "Status",
                    opts,
                    index=opts.index(row["status"]) if row["status"] in opts else 0,
                )
                b1, b2 = st.columns(2)
                with b1:
                    salvar = st.form_submit_button(
                        "Atualizar máquina", use_container_width=True
                    )
                with b2:
                    excluir = st.form_submit_button(
                        "Excluir máquina", use_container_width=True
                    )
                if salvar:
                    update_machine(int(row["id"]), nome, status)
                    st.success("Máquina atualizada.")
                    st.rerun()
                if excluir:
                    try:
                        delete_machine_record(int(row["id"]))
                        st.success("Máquina excluída.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

elif menu == "Locais do Problema":
    require_permission(
        can_manage_master_data(),
        "Somente Administrador ou Almoxarifado pode acessar Locais do Problema.",
    )

    st.subheader("Locais do Problema")

    t1, t2 = st.tabs(["Novo local", "Editar / Excluir"])

    with t1:
        with st.form("novo_local_problema", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            nome = c1.text_input("Nome do local / componente")
            ativo = c2.checkbox("Ativo", value=True)
            descricao = st.text_area("Descrição")

            if st.form_submit_button("Salvar local", use_container_width=True):
                if not str(nome or "").strip():
                    st.error("Informe o nome do local do problema.")
                else:
                    create_problem_location(nome, descricao, ativo)
                    st.success("Local do problema cadastrado.")
                    st.rerun()

    with t2:
        locais = get_problem_locations()

        if locais.empty:
            st.info("Nenhum local do problema cadastrado.")
        else:
            view = locais.copy()
            view["ativo"] = view["ativo"].apply(
                lambda x: "Ativo" if int(x or 0) == 1 else "Inativo"
            )

            st.dataframe(
                view.rename(
                    columns={
                        "id": "ID",
                        "nome": "Nome",
                        "descricao": "Descrição",
                        "ativo": "Status",
                        "created_at": "Criado em",
                        "updated_at": "Atualizado em",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

            loc_map = {
                f"ID {int(r['id'])} - {r['nome']}": r for _, r in locais.iterrows()
            }

            sel = st.selectbox("Selecionar local", list(loc_map.keys()))
            row = loc_map[sel]

            with st.form("editar_local_problema"):
                c1, c2 = st.columns([2, 1])
                nome = c1.text_input("Nome", value=str(row["nome"]))
                ativo = c2.checkbox("Ativo", value=bool(int(row["ativo"] or 0)))
                descricao = st.text_area(
                    "Descrição",
                    value=(
                        "" if pd.isna(row["descricao"]) else str(row["descricao"] or "")
                    ),
                )

                b1, b2 = st.columns(2)

                with b1:
                    salvar = st.form_submit_button(
                        "Atualizar local", use_container_width=True
                    )

                with b2:
                    excluir = st.form_submit_button(
                        "Excluir local", use_container_width=True
                    )

                if salvar:
                    update_problem_location(int(row["id"]), nome, descricao, ativo)
                    st.success("Local do problema atualizado.")
                    st.rerun()

                if excluir:
                    try:
                        delete_problem_location(int(row["id"]))
                        st.success("Local do problema excluído.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

elif menu == "Funcionários":
    require_permission(
        can_manage_master_data(),
        "Somente Administrador ou Almoxarifado pode acessar Funcionários.",
    )
    st.subheader("Funcionários")
    t1, t2 = st.tabs(["Novo funcionário", "Editar / Excluir"])

    with t1:
        with st.form("novo_funcionario", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            nome = c1.text_input("Nome")
            setor = c2.text_input("Setor")
            funcao = c3.text_input("Função")
            if st.form_submit_button("Salvar funcionário", use_container_width=True):
                create_employee(nome, setor, funcao)
                st.success("Funcionário cadastrado.")
                st.rerun()

    with t2:
        if employees_df.empty:
            st.info("Nenhum funcionário cadastrado.")
        else:
            emp_map = {
                f"ID {int(r['id'])} - {r['nome']}": r
                for _, r in employees_df.iterrows()
            }
            sel = st.selectbox("Selecionar funcionário", list(emp_map.keys()))
            row = emp_map[sel]
            with st.form("editar_funcionario"):
                c1, c2, c3 = st.columns(3)
                nome = c1.text_input("Nome", value=str(row["nome"]))
                setor = c2.text_input(
                    "Setor", value="" if pd.isna(row["setor"]) else str(row["setor"])
                )
                funcao = c3.text_input(
                    "Função", value="" if pd.isna(row["funcao"]) else str(row["funcao"])
                )
                b1, b2 = st.columns(2)
                with b1:
                    salvar = st.form_submit_button(
                        "Atualizar funcionário", use_container_width=True
                    )
                with b2:
                    excluir = st.form_submit_button(
                        "Excluir funcionário", use_container_width=True
                    )
                if salvar:
                    update_employee(int(row["id"]), nome, setor, funcao)
                    st.success("Funcionário atualizado.")
                    st.rerun()
                if excluir:
                    try:
                        delete_employee_record(int(row["id"]))
                        st.success("Funcionário excluído.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


def order_page(tipo, titulo):
    st.subheader(titulo)

    state_key = f"selected_order_{tipo}"
    if state_key not in st.session_state:
        st.session_state[state_key] = None

    df_all = get_orders(tipo)

    tabs = st.tabs(["Nova ordem", "Editar ordem", "Consulta", "Excluir ordem"])

    with tabs[0]:
        if machines_df.empty:
            st.warning("Cadastre máquinas antes de abrir ordens.")

        else:
            # =====================================================
            # VÍNCULO COM PMOC
            # Precisa ficar fora do formulário para atualizar a tela.
            # =====================================================

            vincular_pmoc = False
            pmoc_maquina_id = None

            if str(tipo).upper() == "CORRETIVA":
                vincular_pmoc = st.checkbox(
                    "Esta ordem é para uma máquina de ar-condicionado?",
                    key=f"nova_os_pmoc_{tipo}",
                )

                if vincular_pmoc:
                    maquinas_pmoc_ativas = get_pmoc_maquinas(apenas_ativas=True)

                    if maquinas_pmoc_ativas.empty:
                        st.warning(
                            "Não existem máquinas de ar-condicionado "
                            "ativas cadastradas no PMOC."
                        )

                    else:
                        pmoc_maquina_map = {
                            (
                                f"{r['codigo']} | "
                                f"{r['marca'] or 'Sem marca'} | "
                                f"{r['local'] or 'Sem local'}"
                            ): int(r["id"])
                            for _, r in maquinas_pmoc_ativas.iterrows()
                        }

                        pmoc_maquina_label = st.selectbox(
                            "Máquina de ar-condicionado",
                            list(pmoc_maquina_map.keys()),
                            key=f"nova_os_pmoc_maquina_{tipo}",
                        )

                        pmoc_maquina_id = pmoc_maquina_map[pmoc_maquina_label]

            with st.form(
                f"nova_ordem_{tipo}",
                clear_on_submit=True,
            ):
                maq_map = {
                    f"ID {int(r['id'])} - {r['nome']}": int(r["id"])
                    for _, r in machines_df.iterrows()
                }
                maquina = st.selectbox("Máquina", list(maq_map.keys()))

                tipo_manutencao = st.selectbox(
                    "Tipo da manutenção",
                    TIPOS_MANUTENCAO,
                    key=f"novo_tipo_manutencao_{tipo}",
                )
                problem_location_id = select_problem_location(
                    "Local do problema",
                    key=f"novo_local_problema_{tipo}",
                )
                c1, c2 = st.columns(2)
                data_inicio = c1.date_input(
                    "Data início", value=date.today(), key=f"di_{tipo}"
                )
                hora_inicio = c2.time_input("Hora início", key=f"hi_{tipo}")
                c3, c4 = st.columns(2)
                data_fim = c3.date_input(
                    "Data fim", value=date.today(), key=f"df_{tipo}"
                )
                hora_fim = c4.time_input("Hora fim", key=f"hf_{tipo}")
                problem_description = st.text_area("Descrição do problema")
                gera_parada = st.checkbox(
                    "Gerou parada de máquina?",
                    value=True,
                    help="Marque Sim quando a máquina ficou parada por causa desta OS.",
                )
                centro_custo_id = select_cost_center(
                    "Centro de custo da ordem", key=f"cc_ordem_{tipo}"
                )
                status = st.selectbox(
                    "Status",
                    ["Aberta", "Em andamento", "Finalizada", "Cancelada"],
                    key=f"st_{tipo}",
                )
                solution_description = st.text_area("Descrição da solução")
                if st.form_submit_button("Salvar ordem", use_container_width=True):
                    if vincular_pmoc and pmoc_maquina_id is None:
                        st.error("Selecione uma máquina de ar-condicionado.")
                        st.stop()
                    start_dt = combine_date_time(data_inicio, hora_inicio)
                    end_dt = combine_date_time(data_fim, hora_fim)
                    machine_id_salvar = maq_map[maquina]
                    if vincular_pmoc:
                        maquina_pmoc_generica = machines_df[
                            machines_df["nome"].astype(str).str.strip().str.upper()
                            == "AR-CONDICIONADO / PMOC"
                        ]

                        if maquina_pmoc_generica.empty:
                            st.error(
                                "Cadastre uma máquina comum com o nome "
                                "'AR-CONDICIONADO / PMOC' antes de abrir "
                                "uma corretiva PMOC."
                            )
                            st.stop()

                        machine_id_salvar = int(maquina_pmoc_generica.iloc[0]["id"])

                    order_id = create_order(
                        tipo=tipo,
                        opened_by=user["usuario"],
                        machine_id=machine_id_salvar,
                        start_dt=combine_date_time(data_inicio, hora_inicio),
                        end_dt=combine_date_time(data_fim, hora_fim),
                        problem_description=problem_description,
                        status=status,
                        solution_description=solution_description,
                        centro_custo_id=centro_custo_id,
                        gera_parada=gera_parada,
                        tipo_manutencao=tipo_manutencao,
                        problem_location_id=problem_location_id,
                    )

                    numero_pmoc = None
                    if vincular_pmoc and order_id:
                        _, numero_pmoc = create_pmoc_corretiva(
                            maquina_id=pmoc_maquina_id,
                            service_order_id=order_id,
                            status="ABERTA",
                            observacao=(
                                f"Corretiva PMOC vinculada à OS {order_id}. "
                                f"Problema: {problem_description}"
                            ),
                        )
                    if vincular_pmoc:
                        maquina_nome = pmoc_maquina_label
                    else:
                        maquina_nome = (
                            maquina.split(" - ", 1)[1] if " - " in maquina else maquina
                        )
                    centro_custo_nome = get_cost_center_name_by_id(centro_custo_id)
                    if order_id:
                        notificar_telegram_nova_ordem(
                            order_id,
                            tipo,
                            user["usuario"],
                            maquina_nome,
                            centro_custo_nome,
                            start_dt,
                            end_dt,
                            problem_description,
                            status,
                            solution_description,
                            planta=st.session_state.get("planta", PLANTA_PADRAO),
                        )
                    st.success("Ordem cadastrada.")
                    st.rerun()

    with tabs[1]:
        df = get_orders(tipo)
        if df.empty:
            st.info("Nenhuma ordem cadastrada.")
        elif machines_df.empty:
            st.warning("Cadastre máquinas antes de editar ordens.")
        else:
            ord_map = {
                f"Ordem {int(r['id'])} - {r['maquina']} - {r['status']}": r
                for _, r in df.iterrows()
            }
            labels = list(ord_map.keys())

            default_index = 0
            selected_id = st.session_state.get(state_key)
            if selected_id is not None:
                for i, (_, r) in enumerate(ord_map.items()):
                    try:
                        if int(r["id"]) == int(selected_id):
                            default_index = i
                            break
                    except Exception:
                        pass

            sel = st.selectbox(
                "Selecione a ordem",
                labels,
                index=default_index,
                key=f"ed_{tipo}",
            )
            row = ord_map[sel]
            order_id_atual = int(row["id"])
            st.session_state[state_key] = order_id_atual

            maq_map = {
                f"ID {int(r['id'])} - {r['nome']}": int(r["id"])
                for _, r in machines_df.iterrows()
            }

            machine_label = next(
                (k for k, v in maq_map.items() if int(v) == int(row["machine_id"])),
                list(maq_map.keys())[0],
            )

            tipo_manutencao_atual = str(row.get("tipo_manutencao") or "Corretiva")

            tipo_manutencao = st.selectbox(
                "Tipo da manutenção",
                TIPOS_MANUTENCAO,
                index=(
                    TIPOS_MANUTENCAO.index(tipo_manutencao_atual)
                    if tipo_manutencao_atual in TIPOS_MANUTENCAO
                    else 0
                ),
                key=f"edi_{tipo}_{order_id_atual}_tipo_manutencao",
            )

            problem_location_id = select_problem_location(
                "Local do problema",
                current_id=row.get("problem_location_id", None),
                key=f"edi_{tipo}_{order_id_atual}_local_problema",
            )

            start_dt = pd.to_datetime(row.get("start_datetime"), errors="coerce")
            end_dt = pd.to_datetime(row.get("end_datetime"), errors="coerce")

            if pd.isna(start_dt):
                data_inicio_atual = date.today()
                hora_inicio_atual = now_br().time().replace(second=0, microsecond=0)
            else:
                data_inicio_atual = start_dt.date()
                hora_inicio_atual = start_dt.time().replace(second=0, microsecond=0)

            if pd.isna(end_dt):
                data_fim_atual = date.today()
                hora_fim_atual = now_br().time().replace(second=0, microsecond=0)
            else:
                data_fim_atual = end_dt.date()
                hora_fim_atual = end_dt.time().replace(second=0, microsecond=0)

            with st.form(f"editar_ordem_{tipo}_{order_id_atual}"):
                maquina = st.selectbox(
                    "Máquina",
                    list(maq_map.keys()),
                    index=list(maq_map.keys()).index(machine_label),
                    key=f"edi_{tipo}_{order_id_atual}_maquina",
                )

                c1, c2 = st.columns(2)
                data_inicio = c1.date_input(
                    "Data início",
                    value=data_inicio_atual,
                    format="DD/MM/YYYY",
                    key=f"edi_{tipo}_{order_id_atual}_data_inicio",
                )
                hora_inicio = c2.time_input(
                    "Hora início",
                    value=hora_inicio_atual,
                    key=f"edi_{tipo}_{order_id_atual}_hora_inicio",
                )

                c3, c4 = st.columns(2)
                data_fim = c3.date_input(
                    "Data fim",
                    value=data_fim_atual,
                    format="DD/MM/YYYY",
                    key=f"edi_{tipo}_{order_id_atual}_data_fim",
                )
                hora_fim = c4.time_input(
                    "Hora fim",
                    value=hora_fim_atual,
                    key=f"edi_{tipo}_{order_id_atual}_hora_fim",
                )

                gera_parada_banco = row.get("gera_parada", 0)

                try:
                    gera_parada_atual = int(gera_parada_banco or 0) == 1
                except Exception:
                    gera_parada_atual = False

                gera_parada = st.checkbox(
                    "Gerou parada de máquina?",
                    value=gera_parada_atual,
                    key=f"edit_gera_parada_{tipo}_{order_id_atual}_{int(gera_parada_atual)}",
                )

                problem_description = st.text_area(
                    "Descrição do problema",
                    value=(
                        ""
                        if pd.isna(row.get("problem_description"))
                        else str(row.get("problem_description") or "")
                    ),
                    key=f"edi_{tipo}_{order_id_atual}_problema",
                )

                centro_custo_id = select_cost_center_with_current(
                    "Centro de custo da ordem",
                    row.get("centro_custo_id", None),
                    key=f"edi_{tipo}_{order_id_atual}_cc",
                )

                status_opts = ["Aberta", "Em andamento", "Finalizada", "Cancelada"]
                status_atual = str(row.get("status") or "Aberta")
                status = st.selectbox(
                    "Status",
                    status_opts,
                    index=(
                        status_opts.index(status_atual)
                        if status_atual in status_opts
                        else 0
                    ),
                    key=f"edi_{tipo}_{order_id_atual}_status",
                )

                solution_description = st.text_area(
                    "Descrição da solução",
                    value=(
                        ""
                        if pd.isna(row.get("solution_description"))
                        else str(row.get("solution_description") or "")
                    ),
                    key=f"edi_{tipo}_{order_id_atual}_solucao",
                )

                if st.form_submit_button("Atualizar ordem", use_container_width=True):
                    start_dt_salvar = combine_date_time(data_inicio, hora_inicio)
                    end_dt_salvar = combine_date_time(data_fim, hora_fim)

                    update_order(
                        order_id=int(row["id"]),
                        machine_id=maq_map[maquina],
                        start_dt=combine_date_time(data_inicio, hora_inicio),
                        end_dt=combine_date_time(data_fim, hora_fim),
                        problem_description=problem_description,
                        status=status,
                        solution_description=solution_description,
                        centro_custo_id=centro_custo_id,
                        gera_parada=gera_parada,
                        tipo_manutencao=tipo_manutencao,
                        problem_location_id=problem_location_id,
                    )

                    log_action(
                        user["usuario"],
                        "Atualizou ordem",
                        "service_orders",
                        order_id_atual,
                        f"Status: {status}",
                    )

                    st.success("Ordem atualizada.")
                    st.rerun()

            st.divider()
            st.markdown("## Equipe e Peças da Ordem")

            ca, cb = st.columns(2)

            with ca:
                st.markdown("### Funcionários")

                if employees_df.empty:
                    st.info("Nenhum funcionário cadastrado.")
                else:
                    with st.form(
                        f"func_ordem_edit_{tipo}_{order_id_atual}", clear_on_submit=True
                    ):
                        emp_map = {
                            f"ID {int(r['id'])} - {r['nome']}": int(r["id"])
                            for _, r in employees_df.iterrows()
                        }

                        emp = st.selectbox(
                            "Funcionário",
                            list(emp_map.keys()),
                            key=f"emp_edit_{tipo}_{order_id_atual}",
                        )

                        c1, c2 = st.columns(2)
                        di = c1.date_input(
                            "Data início",
                            value=date.today(),
                            key=f"empdi_edit_{tipo}_{order_id_atual}",
                        )
                        hi = c2.time_input(
                            "Hora início",
                            key=f"emphi_edit_{tipo}_{order_id_atual}",
                        )

                        c3, c4 = st.columns(2)
                        dfim = c3.date_input(
                            "Data fim",
                            value=date.today(),
                            key=f"empdf_edit_{tipo}_{order_id_atual}",
                        )
                        hfim = c4.time_input(
                            "Hora fim",
                            key=f"emphf_edit_{tipo}_{order_id_atual}",
                        )

                        if st.form_submit_button(
                            "Adicionar funcionário", use_container_width=True
                        ):
                            add_employee_to_order(
                                order_id_atual,
                                emp_map[emp],
                                combine_date_time(di, hi),
                                combine_date_time(dfim, hfim),
                            )
                            st.success("Funcionário vinculado.")
                            st.rerun()

                order_emp = get_order_employees(order_id_atual)

                if order_emp.empty:
                    st.info("Nenhum funcionário vinculado a esta ordem.")
                else:
                    order_emp["Tempo"] = order_emp.apply(
                        lambda r: format_duration(
                            r["start_datetime"], r["end_datetime"]
                        ),
                        axis=1,
                    )

                    st.dataframe(
                        order_emp.rename(
                            columns={
                                "id": "ID vínculo",
                                "funcionario_id": "ID funcionário",
                                "nome": "Nome",
                                "setor": "Setor",
                                "funcao": "Função",
                                "start_datetime": "Início",
                                "end_datetime": "Fim",
                            }
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

                    emp_del_map = {
                        f"ID vínculo {int(r['id'])} - {r['nome']}": int(r["id"])
                        for _, r in order_emp.iterrows()
                    }

                    emp_del = st.selectbox(
                        "Funcionário para remover",
                        list(emp_del_map.keys()),
                        key=f"del_emp_edit_{tipo}_{order_id_atual}",
                    )

                    if st.button(
                        "Remover funcionário desta ordem",
                        key=f"btn_del_emp_edit_{tipo}_{order_id_atual}",
                        use_container_width=True,
                    ):
                        delete_employee_from_order(
                            emp_del_map[emp_del], user["usuario"]
                        )
                        st.success("Funcionário removido da ordem.")
                        st.rerun()

            with cb:
                st.markdown("### Peças utilizadas")

                if products_df.empty:
                    st.info("Nenhuma peça cadastrada no estoque.")
                else:
                    with st.form(
                        f"peca_ordem_edit_{tipo}_{order_id_atual}", clear_on_submit=True
                    ):
                        part_map = {
                            f"ID {int(r['id'])} - {r['nome']} | saldo: {r['estoque_atual']} {r['unidade']}": int(
                                r["id"]
                            )
                            for _, r in products_df.iterrows()
                        }

                        peca = st.selectbox(
                            "Peça",
                            list(part_map.keys()),
                            key=f"peca_edit_{tipo}_{order_id_atual}",
                        )

                        quantidade = st.number_input(
                            "Quantidade",
                            min_value=0.01,
                            value=1.0,
                            key=f"qtd_edit_{tipo}_{order_id_atual}",
                        )

                        if st.form_submit_button(
                            "Adicionar peça e baixar estoque", use_container_width=True
                        ):
                            add_part_to_order(
                                order_id_atual,
                                part_map[peca],
                                quantidade,
                                user["usuario"],
                            )
                            st.success("Peça lançada na ordem.")
                            st.rerun()

                order_parts = get_order_parts(order_id_atual)

                if order_parts.empty:
                    st.info("Nenhuma peça lançada nesta ordem.")
                else:
                    st.dataframe(
                        order_parts.rename(
                            columns={
                                "id": "ID vínculo",
                                "peca_id": "ID peça",
                                "nome": "Peça",
                                "quantidade": "Quantidade",
                                "unidade": "Unidade",
                            }
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

                    part_del_map = {
                        f"ID vínculo {int(r['id'])} - {r['nome']} | {r['quantidade']} {r['unidade']}": int(
                            r["id"]
                        )
                        for _, r in order_parts.iterrows()
                    }

                    part_del = st.selectbox(
                        "Peça para remover",
                        list(part_del_map.keys()),
                        key=f"del_part_edit_{tipo}_{order_id_atual}",
                    )

                    if st.button(
                        "Remover peça e devolver ao estoque",
                        key=f"btn_del_part_edit_{tipo}_{order_id_atual}",
                        use_container_width=True,
                    ):
                        delete_part_from_order(part_del_map[part_del], user["usuario"])
                        st.success("Peça removida e estoque devolvido.")
                        st.rerun()

    with tabs[2]:
        st.markdown("### Filtros")
        c1, c2, c3, c4 = st.columns(4)
        machine_id = None
        if not machines_df.empty:
            maq_labels = ["TODAS"] + [
                f"ID {int(r['id'])} - {r['nome']}" for _, r in machines_df.iterrows()
            ]
            maq_sel = c1.selectbox("Máquina", maq_labels, key=f"fmaq_{tipo}")
            if maq_sel != "TODAS":
                machine_id = int(maq_sel.split(" - ")[0].replace("ID ", ""))
        status = c2.selectbox(
            "Status",
            ["TODOS", "Aberta", "Em andamento", "Finalizada", "Cancelada"],
            key=f"fstatus_{tipo}",
        )
        d_ini = c3.date_input(
            "De", value=date.today() - timedelta(days=30), key=f"fdi_{tipo}"
        )
        d_fim = c4.date_input("Até", value=date.today(), key=f"fdf_{tipo}")

        df = get_orders_filtered(
            tipo, machine_id=machine_id, status=status, date_from=d_ini, date_to=d_fim
        )
        if not df.empty:
            df["Tempo total"] = df.apply(
                lambda r: format_duration(r["start_datetime"], r["end_datetime"]),
                axis=1,
            )
            df_view = df.copy()
            for col in ["created_at", "updated_at"]:
                if col in df_view.columns:
                    df_view[col] = df_view[col].apply(format_datetime_br)
            st.dataframe(
                df_view.rename(
                    columns={
                        "id": "ID ordem",
                        "opened_by": "Aberta por",
                        "maquina": "Máquina",
                        "centro_custo": "Centro de custo",
                        "start_datetime": "Início",
                        "end_datetime": "Fim",
                        "problem_description": "Problema",
                        "status": "Status",
                        "solution_description": "Solução",
                        "created_at": "Criado em",
                        "updated_at": "Atualizado em",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

            ordem_escolhida = st.selectbox(
                "Selecione uma ordem da consulta para editar",
                [f"Ordem {int(r['id'])} - {r['maquina']}" for _, r in df.iterrows()],
                key=f"consulta_select_{tipo}",
            )
            if st.button(
                "Visualizar ordem",
                key=f"visualizar_os_{tipo}",
                use_container_width=True,
            ):
                order_id = int(ordem_escolhida.split(" - ")[0].replace("Ordem ", ""))

                row_view = df[df["id"].astype(int) == order_id].iloc[0]
                funcionarios = get_order_employees(order_id)
                pecas = get_order_parts(order_id)

                visualizar_ordem_streamlit(row_view, funcionarios, pecas)
            else:
                st.info("Nenhuma ordem encontrada com os filtros.")

    with tabs[3]:
        df = get_orders(tipo)
        if df.empty:
            st.info("Nenhuma ordem cadastrada.")
        else:
            ord_map = {
                f"Ordem {int(r['id'])} - {r['maquina']}": int(r["id"])
                for _, r in df.iterrows()
            }
            order_label = st.selectbox(
                "Selecione a ordem para excluir",
                list(ord_map.keys()),
                key=f"del_{tipo}",
            )
            st.warning(
                "Ao excluir a ordem, os funcionários vinculados e peças lançadas serão removidos. As peças usadas voltarão ao estoque."
            )
            if st.button(
                "Excluir ordem selecionada",
                type="primary",
                key=f"btn_del_{tipo}",
                use_container_width=True,
            ):
                delete_order_cascade(ord_map[order_label], user["usuario"])
                if st.session_state.get(state_key) == ord_map[order_label]:
                    st.session_state[state_key] = None
                st.success("Ordem excluída com sucesso e estoque revertido.")
                st.rerun()


if menu == "Ordem de serviço":
    require_permission(
        can_manage_orders(), "Você não tem permissão para acessar Ordens de serviço."
    )
    order_page("CORRETIVA", "Ordem de serviço")
elif menu == "Ordem de preventiva":
    require_permission(
        can_manage_orders(), "Você não tem permissão para acessar Ordens preventivas."
    )
    order_page("PREVENTIVA", "Ordem de preventiva")


elif menu == "Usuários":
    require_permission(
        can_manage_users(), "Somente Administrador pode acessar Usuários."
    )
    st.subheader("Usuários")
    users_df = get_users()
    t1, t2 = st.tabs(["Novo usuário", "Editar / Excluir"])
    with t1:
        with st.form("novo_usuario", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome")
            usuario_login = c2.text_input("Usuário")
            c3, c4 = st.columns(2)
            email = c3.text_input("E-mail")
            senha = c4.text_input("Senha", type="password")
            perfil = st.selectbox(
                "Perfil", ["Administrador", "Almoxarifado", "Operador", "Aprovador"]
            )
            ativo = st.checkbox("Ativo", value=True)
            if st.form_submit_button("Criar usuário", use_container_width=True):
                create_user(nome, usuario_login, email, perfil, senha, ativo)
                st.success("Usuário criado com sucesso.")
                st.rerun()
    with t2:
        if users_df.empty:
            st.info("Nenhum usuário cadastrado.")
        else:
            user_map = {
                f'ID {int(r["id"])} - {r["nome"]} ({r["usuario"]})': r
                for _, r in users_df.iterrows()
            }
            selected = st.selectbox("Selecionar usuário", list(user_map.keys()))
            row = user_map[selected]
            with st.form("editar_usuario"):
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome", value=row["nome"])
                usuario_login = c2.text_input("Usuário", value=row["usuario"])
                c3, c4 = st.columns(2)
                email = c3.text_input(
                    "E-mail", value="" if pd.isna(row["email"]) else str(row["email"])
                )
                senha = c4.text_input("Nova senha (opcional)", type="password")
                perfil_opts = ["Administrador", "Almoxarifado", "Operador", "Aprovador"]
                perfil = st.selectbox(
                    "Perfil",
                    perfil_opts,
                    index=(
                        perfil_opts.index(row["perfil"])
                        if row["perfil"] in perfil_opts
                        else 1
                    ),
                )
                ativo = st.checkbox("Ativo", value=bool(row["ativo"]))
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button(
                        "Atualizar usuário", use_container_width=True
                    ):
                        update_user_record(
                            int(row["id"]), nome, usuario_login, email, perfil, ativo
                        )
                        if senha:
                            update_user_password(int(row["id"]), senha)
                        log_action(
                            user["usuario"],
                            "Atualizou usuário",
                            "users",
                            row["id"],
                            usuario_login,
                        )
                        st.success("Usuário atualizado.")
                        st.rerun()
                with col2:
                    if st.form_submit_button(
                        "Excluir usuário", use_container_width=True
                    ):
                        if int(row["id"]) == int(user["id"]):
                            st.error("Você não pode excluir o próprio usuário logado.")
                        else:
                            delete_user_record(int(row["id"]))
                            log_action(
                                user["usuario"],
                                "Excluiu usuário",
                                "users",
                                row["id"],
                                usuario_login,
                            )
                            st.success("Usuário excluído.")
                            st.rerun()

elif menu == "Auditoria":
    require_permission(
        can_manage_users(), "Somente Administrador pode acessar Auditoria."
    )
    st.subheader("Histórico de ações")
    logs_df = get_audit_logs(limit=500)
    if logs_df.empty:
        st.info("Nenhum log registrado.")
    else:
        st.dataframe(
            logs_df.rename(
                columns={
                    "id": "ID",
                    "usuario": "Usuário",
                    "acao": "Ação",
                    "entidade": "Entidade",
                    "entidade_id": "ID entidade",
                    "detalhes": "Detalhes",
                    "criado_em": "Data/hora",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

elif menu == "Dashboard executivo":
    st.subheader("Dashboard executivo")
    st.markdown(
        """
        <style>
        div[data-testid="stMetric"] {
            padding: 0px !important;
        }

        div[data-testid="stMetricLabel"] p {
            font-size: 11px !important;
            font-weight: 600 !important;
        }

        div[data-testid="stMetricValue"] {
            font-size: 16px !important;
            font-weight: 700 !important;
        }

        div[data-testid="stMetricDelta"] {
            font-size: 10px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    os_metrics = prepare_orders_metrics(os_df)
    pm_metrics = prepare_orders_metrics(pm_df)
    mttr_os = calc_mttr(os_df)
    mttr_pm = calc_mttr(pm_df)
    mtbf_os = calc_mtbf(os_df)
    mtbf_pm = calc_mtbf(pm_df)

    top_maquinas = pd.DataFrame()
    if not os_df.empty:
        top_maquinas = (
            os_df.groupby("maquina", dropna=False)
            .size()
            .reset_index(name="quebras")
            .sort_values("quebras", ascending=False)
            .head(5)
        )

    top_itens = get_top_used_parts(10)
    top_func = get_top_employees_called(10)
    audit_recent = get_audit_logs(limit=12)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("MTTR OS (h)", format_number(mttr_os))
    c2.metric("MTBF OS (h)", format_number(mtbf_os))
    c3.metric("MTTR Preventivas (h)", format_number(mttr_pm))
    c4.metric("MTBF Preventivas (h)", format_number(mtbf_pm))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric(
        "OS abertas", len(os_df[os_df["status"].isin(["Aberta", "Em andamento"])])
    )
    c6.metric(
        "Preventivas abertas",
        len(pm_df[pm_df["status"].isin(["Aberta", "Em andamento"])]),
    )
    c7.metric("Máquinas cadastradas", len(machines_df))
    c8.metric("Itens críticos", len(criticos_df))

    st.markdown("### Top 5 máquinas que mais quebram")
    if top_maquinas.empty:
        st.info("Sem ordens de serviço suficientes para calcular.")
    else:
        cols = st.columns(min(5, len(top_maquinas)))
        for i, (_, row) in enumerate(top_maquinas.iterrows()):
            with cols[i]:
                st.markdown('<div class="section-card">', unsafe_allow_html=True)
                st.metric(
                    f"{i+1}º lugar", row["maquina"], delta=f'{int(row["quebras"])} OS'
                )
                st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### Top 10 itens mais usados")
    if top_itens.empty:
        st.info("Nenhuma peça foi usada em ordens ainda.")
    else:
        for start in range(0, len(top_itens), 5):
            row_items = top_itens.iloc[start : start + 5]
            cols = st.columns(len(row_items))
            for i, (_, item) in enumerate(row_items.iterrows()):
                with cols[i]:
                    st.markdown('<div class="section-card">', unsafe_allow_html=True)
                    st.metric(
                        f'ID {int(item["produto_id"])}',
                        item["nome"],
                        delta=f'{format_number(item["total_usado"])} {item["unidade"]}',
                    )
                    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### Top 10 funcionários mais acionados")
    if top_func.empty:
        st.info("Nenhum funcionário foi apontado em ordens ainda.")
    else:
        for start in range(0, len(top_func), 5):
            row_items = top_func.iloc[start : start + 5]
            cols = st.columns(len(row_items))
            for i, (_, item) in enumerate(row_items.iterrows()):
                with cols[i]:
                    st.markdown('<div class="section-card">', unsafe_allow_html=True)
                    st.metric(
                        f'ID {int(item["funcionario_id"])}',
                        item["nome"],
                        delta=f'{int(item["total_acionamentos"])} acionamentos',
                    )
                    st.markdown("</div>", unsafe_allow_html=True)

    c9, c10, c11, c12 = st.columns(4)
    with c9:
        st.markdown("### OS por máquina")
        if not os_df.empty:
            os_por_maquina = (
                os_df.groupby("maquina", dropna=False)
                .size()
                .reset_index(name="total_os")
                .sort_values("total_os", ascending=False)
                .head(10)
                .set_index("maquina")
            )
            st.bar_chart(os_por_maquina)
        else:
            st.info("Sem dados para exibir.")
    with c10:
        st.markdown("### Máquinas x paradas")
        if not os_df.empty:
            paradas = (
                os_df[os_df["status"].isin(["Aberta", "Em andamento", "Finalizada"])]
                .groupby("maquina", dropna=False)
                .size()
                .reset_index(name="paradas")
                .sort_values("paradas", ascending=False)
                .head(10)
                .set_index("maquina")
            )
            st.bar_chart(paradas)
        else:
            st.info("Sem dados para exibir.")

    with c11:
        st.markdown("### Preventivas")
        if not pm_df.empty:
            status_pm = (
                pm_df.groupby("status", dropna=False)
                .size()
                .reset_index(name="total")
                .set_index("status")
            )
            st.bar_chart(status_pm)
        else:
            st.info("Sem preventivas cadastradas.")
    with c12:
        st.markdown("### Maior tempo Parada")
        if not os_metrics.empty:
            tempo_por_maquina = (
                os_metrics[os_metrics["duracao_horas"] > 0]
                .groupby("maquina", dropna=False)["duracao_horas"]
                .sum()
                .reset_index()
                .sort_values("duracao_horas", ascending=False)
                .head(10)
                .set_index("maquina")
            )
            if tempo_por_maquina.empty:
                st.info("Sem dados para exibir.")
            else:
                st.bar_chart(tempo_por_maquina)
        else:
            st.info("Sem dados para exibir.")

    st.markdown("### Últimas ações registradas")
    if audit_recent.empty:
        st.info("Sem ações registradas.")
    else:
        st.dataframe(
            audit_recent.rename(
                columns={
                    "id": "ID",
                    "usuario": "Usuário",
                    "acao": "Ação",
                    "entidade": "Entidade",
                    "entidade_id": "ID entidade",
                    "detalhes": "Detalhes",
                    "criado_em": "Data/hora",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
