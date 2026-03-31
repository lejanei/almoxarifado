import os
import io
import base64
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


DEFAULT_DB_URL = "mysql+pymysql://ljsyst02_adm:vinimalu121924@ljsystem.com.br/ljsyst02_almoxarifado?charset=utf8mb4"
APP_NAME = "StockPro Almoxarifado"
APP_SUBTITLE = "Controle de Estoque"
LOGO_PATH = Path(__file__).parent / "assets" / "logo_stockpro.svg"


def get_database_url() -> str:
    env_url = os.getenv("ALMOXARIFADO_URL")
    if env_url:
        return env_url

    try:
        if "ALMOXARIFADO_URL" in st.secrets:
            return st.secrets["ALMOXARIFADO_URL"]
    except Exception:
        pass

    return DEFAULT_DB_URL


DATABASE_URL = get_database_url()


st.set_page_config(page_title=APP_NAME, page_icon="📦", layout="wide")


def load_logo_base64():
    try:
        return base64.b64encode(LOGO_PATH.read_bytes()).decode("utf-8")
    except Exception:
        return ""


logo_b64 = load_logo_base64()

st.markdown("""
<style>
:root {
    --bg: #0b1220;
    --panel: #111827;
    --panel-2: #0f172a;
    --card: #1f2937;
    --card-soft: #243244;
    --border: rgba(148, 163, 184, 0.18);
    --text: #e5e7eb;
    --muted: #94a3b8;
    --brand: #0ea5a4;
    --brand-2: #14b8a6;
    --success: #22c55e;
    --danger: #ef4444;
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background: linear-gradient(180deg, #0b1220 0%, #0a0f1c 100%);
    color: var(--text);
}

.block-container {
    padding-top: 1rem;
    padding-bottom: 1rem;
}

header[data-testid="stHeader"] {
    background: transparent;
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
    border-right: 1px solid var(--border);
}

section[data-testid="stSidebar"] * {
    color: var(--text) !important;
}

.hero-card {
    padding: 1.2rem 1.3rem;
    border: 1px solid rgba(20, 184, 166, 0.22);
    border-radius: 22px;
    background: linear-gradient(135deg, rgba(17,24,39,0.96) 0%, rgba(15,23,42,0.96) 100%);
    margin-bottom: 1rem;
    box-shadow: 0 16px 36px rgba(0,0,0,0.22);
}

.brand-chip {
    display: inline-block;
    padding: 0.34rem 0.78rem;
    border-radius: 999px;
    background: rgba(20,184,166,0.14);
    color: #99f6e4 !important;
    font-size: 0.84rem;
    font-weight: 700;
    margin-bottom: 0.45rem;
    border: 1px solid rgba(20,184,166,0.18);
}

.brand-title {
    font-size: 1.7rem;
    font-weight: 1200;
    color: #f8fafc !important;
    margin: 0;
}

.brand-subtitle {
    color: var(--muted) !important;
    margin-top: 0.18rem;
    margin-bottom: 0;
}

.small-muted {
    color: var(--muted) !important;
    font-size: 0.92rem;
}

.sidebar-brand {
    padding: 0.9rem 1rem;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(30,41,59,0.65) 0%, rgba(15,23,42,0.55) 100%);
    margin-bottom: 0.9rem;
}

.login-wrap,
.section-card,
div[data-testid="stMetric"],
div[data-testid="stDataFrame"] {
    background: linear-gradient(180deg, rgba(31,41,55,0.96) 0%, rgba(17,24,39,0.96) 100%) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    box-shadow: 0 14px 30px rgba(0,0,0,0.18);
}

.login-wrap {
    border-radius: 22px;
    padding: 1.2rem;
}

.section-card {
    padding: 1rem 1.1rem;
    border-radius: 18px;
    margin-bottom: 1rem;
}

div[data-testid="stMetric"] {
    padding: 14px 16px;
    border-radius: 18px;
}

div[data-testid="stMetric"] * {
    color: var(--text) !important;
}

div[data-testid="stMetricLabel"] p,
div[data-testid="stMetricLabel"] label {
    color: var(--muted) !important;
}

div[data-testid="stDataFrame"] {
    border-radius: 14px;
    overflow: hidden;
}

h1, h2, h3, h4, h5, h6,
p, li, label, span, div,
[data-testid="stMarkdownContainer"] * {
    color: var(--text);
}

.stAlert {
    border-radius: 14px;
    border: 1px solid var(--border);
}

.stButton > button, .stDownloadButton > button {
    border-radius: 12px;
    font-weight: 700;
    border: 1px solid rgba(20,184,166,0.22);
    background: linear-gradient(90deg, var(--brand) 0%, var(--brand-2) 100%);
    color: white !important;
}

.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
div[data-baseweb="select"] > div,
[data-testid="stDateInputField"] {
    background: rgba(15,23,42,0.85) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
}

[data-baseweb="select"] * {
    color: var(--text) !important;
}

[data-testid="stRadio"] label,
[data-testid="stCheckbox"] label {
    color: var(--text) !important;
}
</style>
""", unsafe_allow_html=True)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def format_number(value):
    try:
        return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return value


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def df_to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name[:31])
    return buffer.getvalue()


def badge_perfil(perfil: str) -> str:
    if perfil == "Administrador":
        return "🛡️ Administrador"
    if perfil == "Almoxarifado":
        return "📦 Almoxarifado"
    return "👤 Operador"


def app_header(title: str, subtitle: str = ""):
    #logo_html = f'<img src="data:image/svg+xml;base64,{logo_b64}" style="height:66px;">' if logo_b64 else '<div style="font-size:48px;">📦</div>'
    st.markdown(
        f"""
        <div class="hero-card">
            <div style="display:flex; align-items:center; gap:16px;">                
                <div>                   
                    <h1 class="brand-title">{title}</h1>
                    <p class="brand-subtitle">{subtitle or APP_SUBTITLE}</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600, future=True)


def init_db():
    engine = get_engine()
    ddl_users = """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nome VARCHAR(150) NOT NULL,
        usuario VARCHAR(80) NOT NULL UNIQUE,
        email VARCHAR(150),
        perfil VARCHAR(50),
        criado_em DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    ddl_products = """
    CREATE TABLE IF NOT EXISTS products (
        id INT AUTO_INCREMENT PRIMARY KEY,
        codigo VARCHAR(80) NULL UNIQUE,
        nome VARCHAR(150) NOT NULL,
        descricao TEXT,
        unidade VARCHAR(20) NOT NULL DEFAULT 'UN',
        estoque_atual DECIMAL(18,3) NOT NULL DEFAULT 0,
        estoque_minimo DECIMAL(18,3) NOT NULL DEFAULT 0,
        criado_em DATETIME NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    ddl_movements = """
    CREATE TABLE IF NOT EXISTS movements (
        id INT AUTO_INCREMENT PRIMARY KEY,
        produto_id INT NOT NULL,
        tipo VARCHAR(20) NOT NULL,
        quantidade DECIMAL(18,3) NOT NULL,
        observacao TEXT,
        usuario_lancamento VARCHAR(150),
        criado_em DATETIME NOT NULL,
        CONSTRAINT fk_movements_product FOREIGN KEY (produto_id) REFERENCES products(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    with engine.begin() as conn:
        conn.execute(text(ddl_users))
        conn.execute(text(ddl_products))
        conn.execute(text(ddl_movements))
        for ddl in [
            "ALTER TABLE users ADD COLUMN senha_hash VARCHAR(64) NULL",
            "ALTER TABLE users ADD COLUMN ativo TINYINT(1) NOT NULL DEFAULT 1",
            "ALTER TABLE users ADD COLUMN atualizado_em DATETIME NULL",
        ]:
            try:
                conn.execute(text(ddl))
            except Exception:
                pass
        for ddl in [
            "ALTER TABLE products MODIFY COLUMN codigo VARCHAR(80) NULL",
            "ALTER TABLE products ADD COLUMN atualizado_em DATETIME NULL",
        ]:
            try:
                conn.execute(text(ddl))
            except Exception:
                pass
        try:
            conn.execute(text("UPDATE users SET ativo = 1 WHERE ativo IS NULL"))
        except Exception:
            pass
        try:
            conn.execute(text("UPDATE users SET senha_hash = '' WHERE senha_hash IS NULL"))
        except Exception:
            pass


def fetch_df(query: str, params: dict | None = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(query), conn, params=params or {})


def execute(query: str, params: dict | None = None):
    with get_engine().begin() as conn:
        return conn.execute(text(query), params or {})


def can_manage_users() -> bool:
    return st.session_state.user["perfil"] == "Administrador"


def can_manage_products() -> bool:
    return st.session_state.user["perfil"] in ["Administrador", "Almoxarifado"]


def can_move_stock() -> bool:
    return st.session_state.user["perfil"] in ["Administrador", "Almoxarifado", "Operador"]


def can_adjust_inventory() -> bool:
    return st.session_state.user["perfil"] in ["Administrador", "Almoxarifado"]


def deny_access(msg="Você não tem permissão para acessar esta área."):
    st.warning(msg)
    st.stop()


def get_users() -> pd.DataFrame:
    return fetch_df("SELECT id, nome, usuario, email, perfil, ativo, criado_em, atualizado_em FROM users ORDER BY nome")


def count_users() -> int:
    df = fetch_df("SELECT COUNT(*) AS total FROM users")
    return int(df.iloc[0]["total"]) if not df.empty else 0


def authenticate_user(usuario: str, senha: str):
    df = fetch_df("SELECT id, nome, usuario, email, perfil, ativo, senha_hash FROM users WHERE usuario = :usuario LIMIT 1", {"usuario": usuario.strip()})
    if df.empty:
        return None
    row = df.iloc[0]
    if int(row["ativo"]) != 1:
        return None
    if (row["senha_hash"] or "") != hash_password(senha):
        return None
    return {"id": int(row["id"]), "nome": row["nome"], "usuario": row["usuario"], "email": row["email"], "perfil": row["perfil"]}


def create_user(nome: str, usuario: str, email: str, perfil: str, senha: str, ativo: bool = True):
    execute(
        "INSERT INTO users (nome, usuario, email, perfil, senha_hash, ativo, criado_em, atualizado_em) VALUES (:nome, :usuario, :email, :perfil, :senha_hash, :ativo, :criado_em, :atualizado_em)",
        {"nome": nome.strip(), "usuario": usuario.strip(), "email": email.strip(), "perfil": perfil, "senha_hash": hash_password(senha), "ativo": 1 if ativo else 0, "criado_em": datetime.now(), "atualizado_em": datetime.now()},
    )


def update_user(user_id: int, nome: str, usuario: str, email: str, perfil: str, ativo: bool):
    execute(
        "UPDATE users SET nome=:nome, usuario=:usuario, email=:email, perfil=:perfil, ativo=:ativo, atualizado_em=:atualizado_em WHERE id=:id",
        {"id": user_id, "nome": nome.strip(), "usuario": usuario.strip(), "email": email.strip(), "perfil": perfil, "ativo": 1 if ativo else 0, "atualizado_em": datetime.now()},
    )


def update_user_password(user_id: int, nova_senha: str):
    execute(
        "UPDATE users SET senha_hash=:senha_hash, atualizado_em=:atualizado_em WHERE id=:id",
        {"id": user_id, "senha_hash": hash_password(nova_senha), "atualizado_em": datetime.now()},
    )


def delete_user(user_id: int):
    df = fetch_df("SELECT COUNT(*) AS total FROM movements WHERE usuario_lancamento = (SELECT usuario FROM users WHERE id = :id)", {"id": user_id})
    total = int(df.iloc[0]["total"]) if not df.empty else 0
    if total > 0:
        raise ValueError("Este usuário possui movimentações vinculadas. Desative em vez de excluir.")
    execute("DELETE FROM users WHERE id = :id", {"id": user_id})


def get_products() -> pd.DataFrame:
    return fetch_df("SELECT id, nome, descricao, unidade, estoque_atual, estoque_minimo, criado_em, atualizado_em FROM products ORDER BY nome")


def get_critical_products() -> pd.DataFrame:
    return fetch_df("SELECT id, nome, unidade, estoque_atual, estoque_minimo, (estoque_minimo - estoque_atual) AS falta_para_minimo FROM products WHERE estoque_atual <= estoque_minimo ORDER BY falta_para_minimo DESC, nome")


def create_product(nome: str, descricao: str, unidade: str, estoque_inicial: float, estoque_minimo: float):
    execute(
        "INSERT INTO products (codigo, nome, descricao, unidade, estoque_atual, estoque_minimo, criado_em, atualizado_em) VALUES (NULL, :nome, :descricao, :unidade, :estoque_atual, :estoque_minimo, :criado_em, :atualizado_em)",
        {"nome": nome.strip(), "descricao": descricao.strip(), "unidade": unidade, "estoque_atual": float(estoque_inicial), "estoque_minimo": float(estoque_minimo), "criado_em": datetime.now(), "atualizado_em": datetime.now()},
    )


def update_product(product_id: int, nome: str, descricao: str, unidade: str, estoque_minimo: float):
    execute(
        "UPDATE products SET nome=:nome, descricao=:descricao, unidade=:unidade, estoque_minimo=:estoque_minimo, atualizado_em=:atualizado_em WHERE id=:id",
        {"id": product_id, "nome": nome.strip(), "descricao": descricao.strip(), "unidade": unidade, "estoque_minimo": float(estoque_minimo), "atualizado_em": datetime.now()},
    )


def delete_product(product_id: int):
    df = fetch_df("SELECT COUNT(*) AS total FROM movements WHERE produto_id = :id", {"id": product_id})
    total = int(df.iloc[0]["total"]) if not df.empty else 0
    if total > 0:
        raise ValueError("Este produto possui movimentações e não pode ser excluído.")
    execute("DELETE FROM products WHERE id = :id", {"id": product_id})


def normalize_movement_type(tipo: str) -> str:
    if tipo in ["ENTRADA", "AJUSTE_ENTRADA"]:
        return "ENTRADA"
    if tipo in ["SAIDA", "AJUSTE_SAIDA"]:
        return "SAIDA"
    return tipo


def registrar_movimento(produto_id: int, tipo: str, quantidade: float, observacao: str, usuario_lancamento: str):
    quantidade = float(quantidade)
    if quantidade <= 0:
        raise ValueError("A quantidade deve ser maior que zero.")
    with get_engine().begin() as conn:
        produto = conn.execute(text("SELECT id, estoque_atual FROM products WHERE id = :id FOR UPDATE"), {"id": produto_id}).mappings().first()
        if not produto:
            raise ValueError("Produto não encontrado.")
        estoque_atual = float(produto["estoque_atual"])
        novo_estoque = estoque_atual + quantidade if tipo in ["ENTRADA", "AJUSTE_ENTRADA"] else estoque_atual - quantidade
        if novo_estoque < 0:
            raise ValueError("Operação resultaria em estoque negativo.")
        conn.execute(text("UPDATE products SET estoque_atual=:estoque, atualizado_em=:atualizado_em WHERE id=:id"), {"estoque": novo_estoque, "atualizado_em": datetime.now(), "id": produto_id})
        conn.execute(text("INSERT INTO movements (produto_id, tipo, quantidade, observacao, usuario_lancamento, criado_em) VALUES (:produto_id, :tipo, :quantidade, :observacao, :usuario_lancamento, :criado_em)"), {"produto_id": produto_id, "tipo": tipo, "quantidade": quantidade, "observacao": observacao.strip(), "usuario_lancamento": usuario_lancamento.strip(), "criado_em": datetime.now()})


def ajustar_estoque_para_valor(produto_id: int, estoque_desejado: float, motivo: str, usuario_lancamento: str):
    estoque_desejado = float(estoque_desejado)
    if estoque_desejado < 0:
        raise ValueError("O estoque desejado não pode ser negativo.")
    with get_engine().begin() as conn:
        produto = conn.execute(text("SELECT id, estoque_atual FROM products WHERE id = :id FOR UPDATE"), {"id": produto_id}).mappings().first()
        if not produto:
            raise ValueError("Produto não encontrado.")
        estoque_atual = float(produto["estoque_atual"])
        diferenca = estoque_desejado - estoque_atual
        if diferenca == 0:
            raise ValueError("O estoque informado é igual ao estoque atual. Nenhum ajuste necessário.")
        tipo = "AJUSTE_ENTRADA" if diferenca > 0 else "AJUSTE_SAIDA"
        quantidade = abs(diferenca)
        conn.execute(text("UPDATE products SET estoque_atual=:estoque, atualizado_em=:atualizado_em WHERE id=:id"), {"estoque": estoque_desejado, "atualizado_em": datetime.now(), "id": produto_id})
        obs = f"AJUSTE DE INVENTÁRIO | {motivo.strip()} | estoque anterior: {estoque_atual} | novo estoque: {estoque_desejado}"
        conn.execute(text("INSERT INTO movements (produto_id, tipo, quantidade, observacao, usuario_lancamento, criado_em) VALUES (:produto_id, :tipo, :quantidade, :observacao, :usuario_lancamento, :criado_em)"), {"produto_id": produto_id, "tipo": tipo, "quantidade": quantidade, "observacao": obs, "usuario_lancamento": usuario_lancamento.strip(), "criado_em": datetime.now()})


def get_movements_filtered(data_ini: date, data_fim: date, tipo: str, produto_id: int | None):
    params = {"data_ini": f"{data_ini.strftime('%Y-%m-%d')} 00:00:00", "data_fim": f"{data_fim.strftime('%Y-%m-%d')} 23:59:59"}
    sql = "SELECT m.id, p.id AS produto_id, p.nome AS produto, m.tipo, m.quantidade, p.unidade, m.usuario_lancamento, m.observacao, m.criado_em FROM movements m INNER JOIN products p ON p.id = m.produto_id WHERE m.criado_em BETWEEN :data_ini AND :data_fim"
    if tipo != "TODOS":
        if tipo == "ENTRADA":
            sql += " AND m.tipo IN ('ENTRADA', 'AJUSTE_ENTRADA') "
        elif tipo == "SAIDA":
            sql += " AND m.tipo IN ('SAIDA', 'AJUSTE_SAIDA') "
        elif tipo == "AJUSTE":
            sql += " AND m.tipo IN ('AJUSTE_ENTRADA', 'AJUSTE_SAIDA') "
    if produto_id is not None:
        sql += " AND p.id = :produto_id "
        params["produto_id"] = produto_id
    sql += " ORDER BY m.id DESC "
    return fetch_df(sql, params)


def get_movement_reason_options(tipo: str):
    if tipo == "ENTRADA":
        return ["Compra", "Retorno de produção", "Devolução", "Transferência recebida", "Reposição interna", "Outros"]
    return ["Consumo interno", "Produção", "Perda", "Quebra/avaria", "Transferência enviada", "Outros"]


if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None


def logout():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()


try:
    init_db()
except Exception as e:
    st.error("Não foi possível conectar/inicializar o banco de dados.")
    st.exception(e)
    st.stop()


if count_users() == 0:
    app_header("Primeira configuração", "Crie o primeiro usuário administrador para liberar o sistema.")
    with st.form("form_primeiro_admin"):
        col1, col2 = st.columns(2)
        nome = col1.text_input("Nome")
        usuario = col2.text_input("Usuário")
        col3, col4 = st.columns(2)
        email = col3.text_input("E-mail")
        senha = col4.text_input("Senha", type="password")
        salvar = st.form_submit_button("Criar administrador", use_container_width=True)
        if salvar:
            if not nome.strip() or not usuario.strip() or not senha.strip():
                st.error("Preencha nome, usuário e senha.")
            else:
                try:
                    create_user(nome=nome, usuario=usuario, email=email, perfil="Administrador", senha=senha, ativo=True)
                    st.success("Administrador criado com sucesso. Faça login.")
                    st.rerun()
                except IntegrityError:
                    st.error("Já existe um usuário com esse login.")
                except Exception as e:
                    st.error(f"Erro ao criar administrador: {e}")
    st.stop()


if not st.session_state.logged_in:
    app_header("Acesso ao sistema", APP_SUBTITLE)
    c1, c2, c3 = st.columns([1, 1.1, 1])
    with c2:
        st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
        st.markdown("### Entrar")
        with st.form("form_login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True)
            if entrar:
                user = authenticate_user(usuario, senha)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.success(f"Bem-vindo, {user['nome']}.")
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


user = st.session_state.user
products_df = get_products()
users_df = get_users()
criticos_df = get_critical_products()

with st.sidebar:
    if logo_b64:
        st.markdown(f"""
        <div class="sidebar-brand">                      
            <div style="text-align:center; font-weight:2000;">{APP_NAME}</div>
            <div class="small-muted" style="text-align:center;">{APP_SUBTITLE}</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown(f"**{user['nome']}**")
    st.caption(f"{badge_perfil(user['perfil'])} • {user['usuario']}")
    if st.button("Sair", use_container_width=True):
        logout()
    menu = st.radio("Menu", ["Dashboard", "Cadastro de produtos", "Cadastro de usuários", "Consulta de estoque", "Lançamento de entrada", "Lançamento de saída", "Ajuste de inventário", "Peças críticas", "Histórico", "Relatórios"])

app_header("StockPro Almoxariifado", "Sistema de Controle de Estoque Inteligente")
st.info(f"Banco em uso: {'Secret/variável configurada' if DATABASE_URL != DEFAULT_DB_URL else 'URL padrão do app'}")


if menu == "Dashboard":
    total_itens = len(products_df)
    total_usuarios = len(users_df)
    total_criticos = len(criticos_df)
    saldo_total = float(products_df["estoque_atual"].sum()) if not products_df.empty else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Produtos cadastrados", total_itens)
    c2.metric("Usuários cadastrados", total_usuarios)
    c3.metric("Itens críticos", total_criticos)
    c4.metric("Saldo total em estoque", format_number(saldo_total))
    a, b = st.columns([1.25, 1])
    with a:
        st.subheader("Itens em situação crítica")
        if criticos_df.empty:
            st.success("Nenhum item abaixo ou igual ao estoque mínimo.")
        else:
            view = criticos_df.rename(columns={"id": "ID", "nome": "Produto", "unidade": "Unidade", "estoque_atual": "Estoque atual", "estoque_minimo": "Estoque mínimo", "falta_para_minimo": "Falta para mínimo"})
            st.dataframe(view, use_container_width=True, hide_index=True)
    with b:
        #st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Resumo de acesso")
        st.markdown(f"- Perfil atual: **{user['perfil']}**")
        st.markdown(f"- Pode movimentar estoque: **{'Sim' if can_move_stock() else 'Não'}**")
        st.markdown(f"- Pode gerenciar produtos: **{'Sim' if can_manage_products() else 'Não'}**")
        st.markdown(f"- Pode gerenciar usuários: **{'Sim' if can_manage_users() else 'Não'}**")
        st.markdown(f"- Pode ajustar inventário: **{'Sim' if can_adjust_inventory() else 'Não'}**")
        st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("Gráficos")
    g1, g2 = st.columns(2)
    with g1:
        if not criticos_df.empty:
            top_criticos = criticos_df.sort_values("falta_para_minimo", ascending=False).head(10)
            st.bar_chart(top_criticos.set_index("nome")[["falta_para_minimo"]])
        else:
            st.info("Sem itens críticos para exibir.")
    with g2:
        if not products_df.empty:
            comp = products_df[["nome", "estoque_atual", "estoque_minimo"]].copy().head(15).set_index("nome")
            st.bar_chart(comp)
        else:
            st.info("Sem produtos cadastrados.")

elif menu == "Cadastro de produtos":
    if not can_manage_products():
        deny_access("Somente Administrador e Almoxarifado podem gerenciar produtos.")
    st.subheader("Cadastro de produtos")
    st.caption("O sistema usa o ID automático do banco como identificador único.")
    aba1, aba2, aba3 = st.tabs(["Novo produto", "Editar produto", "Excluir produto"])
    with aba1:
        with st.form("form_produto_novo", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            nome = col1.text_input("Nome do produto")
            unidade = col2.selectbox("Unidade", ["UN", "KG", "PC", "M", "L"])
            estoque_inicial = col3.number_input("Estoque inicial", min_value=0.0, step=1.0, value=0.0)
            col4, col5 = st.columns([1, 2])
            estoque_minimo = col4.number_input("Estoque mínimo", min_value=0.0, step=1.0, value=0.0)
            descricao = col5.text_area("Descrição")
            salvar = st.form_submit_button("Salvar produto", use_container_width=True)
            if salvar:
                if not nome.strip():
                    st.error("Informe o nome do produto.")
                else:
                    try:
                        create_product(nome, descricao, unidade, estoque_inicial, estoque_minimo)
                        st.success("Produto cadastrado com sucesso.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar produto: {e}")
    with aba2:
        if products_df.empty:
            st.info("Nenhum produto cadastrado.")
        else:
            opcoes = {f"ID {int(r['id'])} - {r['nome']}": r for _, r in products_df.iterrows()}
            selecionado = st.selectbox("Selecione o produto para editar", list(opcoes.keys()))
            row = opcoes[selecionado]
            with st.form("form_produto_editar"):
                st.markdown(f"**ID do produto:** {int(row['id'])}")
                col1, col2 = st.columns(2)
                novo_nome = col1.text_input("Nome", value=str(row["nome"]))
                nova_unidade = col2.selectbox("Unidade", ["UN", "KG", "PC", "M", "L"], index=["UN", "KG", "PC", "M", "L"].index(row["unidade"]) if row["unidade"] in ["UN", "KG", "PC", "M", "L"] else 0)
                col3, col4 = st.columns(2)
                col3.number_input("Estoque atual", value=float(row["estoque_atual"]), disabled=True)
                novo_minimo = col4.number_input("Estoque mínimo", min_value=0.0, step=1.0, value=float(row["estoque_minimo"]))
                nova_descricao = st.text_area("Descrição", value="" if pd.isna(row["descricao"]) else str(row["descricao"]))
                salvar_edicao = st.form_submit_button("Salvar alterações", use_container_width=True)
                if salvar_edicao:
                    try:
                        update_product(int(row["id"]), novo_nome, nova_descricao, nova_unidade, novo_minimo)
                        st.success("Produto atualizado com sucesso.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao atualizar produto: {e}")
    with aba3:
        if products_df.empty:
            st.info("Nenhum produto cadastrado.")
        else:
            opcoes = {f"ID {int(r['id'])} - {r['nome']}": int(r["id"]) for _, r in products_df.iterrows()}
            excluir = st.selectbox("Selecione o produto para excluir", list(opcoes.keys()), key="select_excluir_produto")
            if st.button("Excluir produto selecionado", type="primary", use_container_width=True):
                try:
                    delete_product(opcoes[excluir])
                    st.success("Produto excluído com sucesso.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    if not products_df.empty:
        view = products_df.rename(columns={"id": "ID", "nome": "Nome", "descricao": "Descrição", "unidade": "Unidade", "estoque_atual": "Estoque atual", "estoque_minimo": "Estoque mínimo", "criado_em": "Criado em", "atualizado_em": "Atualizado em"})
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.download_button("Baixar produtos (CSV)", data=df_to_csv_bytes(view), file_name="produtos.csv", mime="text/csv")

elif menu == "Cadastro de usuários":
    if not can_manage_users():
        deny_access("Somente Administrador pode gerenciar usuários.")
    st.subheader("Cadastro de usuários")
    aba1, aba2, aba3 = st.tabs(["Novo usuário", "Editar usuário", "Excluir usuário"])
    with aba1:
        with st.form("form_usuario_novo", clear_on_submit=True):
            col1, col2 = st.columns(2)
            nome = col1.text_input("Nome completo")
            usuario = col2.text_input("Usuário")
            col3, col4 = st.columns(2)
            email = col3.text_input("E-mail")
            perfil = col4.selectbox("Perfil", ["Administrador", "Almoxarifado", "Operador"])
            col5, col6 = st.columns(2)
            senha = col5.text_input("Senha", type="password")
            ativo = col6.checkbox("Usuário ativo", value=True)
            salvar = st.form_submit_button("Salvar usuário", use_container_width=True)
            if salvar:
                if not nome.strip() or not usuario.strip() or not senha.strip():
                    st.error("Informe nome, usuário e senha.")
                else:
                    try:
                        create_user(nome, usuario, email, perfil, senha, ativo)
                        st.success("Usuário cadastrado com sucesso.")
                        st.rerun()
                    except IntegrityError:
                        st.error("Já existe um usuário com esse login.")
                    except Exception as e:
                        st.error(f"Erro ao salvar usuário: {e}")
    with aba2:
        if users_df.empty:
            st.info("Nenhum usuário cadastrado.")
        else:
            opcoes = {f"{r['nome']} ({r['usuario']})": r for _, r in users_df.iterrows()}
            selecionado = st.selectbox("Selecione o usuário para editar", list(opcoes.keys()))
            row = opcoes[selecionado]
            with st.form("form_usuario_editar"):
                col1, col2 = st.columns(2)
                edit_nome = col1.text_input("Nome", value=str(row["nome"]))
                edit_usuario = col2.text_input("Usuário", value=str(row["usuario"]))
                col3, col4 = st.columns(2)
                edit_email = col3.text_input("E-mail", value="" if pd.isna(row["email"]) else str(row["email"]))
                perfis = ["Administrador", "Almoxarifado", "Operador"]
                edit_perfil = col4.selectbox("Perfil", perfis, index=perfis.index(row["perfil"]) if row["perfil"] in perfis else 0)
                edit_ativo = st.checkbox("Usuário ativo", value=bool(row["ativo"]))
                nova_senha = st.text_input("Nova senha (opcional)", type="password")
                salvar_edicao = st.form_submit_button("Salvar alterações", use_container_width=True)
                if salvar_edicao:
                    try:
                        update_user(int(row["id"]), edit_nome, edit_usuario, edit_email, edit_perfil, edit_ativo)
                        if nova_senha.strip():
                            update_user_password(int(row["id"]), nova_senha.strip())
                        st.success("Usuário atualizado com sucesso.")
                        st.rerun()
                    except IntegrityError:
                        st.error("Já existe outro usuário com esse login.")
                    except Exception as e:
                        st.error(f"Erro ao atualizar usuário: {e}")
    with aba3:
        if users_df.empty:
            st.info("Nenhum usuário cadastrado.")
        else:
            opcoes = {f"{r['nome']} ({r['usuario']})": int(r["id"]) for _, r in users_df.iterrows()}
            excluir = st.selectbox("Selecione o usuário para excluir", list(opcoes.keys()), key="select_excluir_usuario")
            if st.button("Excluir usuário selecionado", type="primary", use_container_width=True):
                try:
                    delete_user(opcoes[excluir])
                    st.success("Usuário excluído com sucesso.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    if not users_df.empty:
        view = users_df.rename(columns={"id": "ID", "nome": "Nome", "usuario": "Usuário", "email": "E-mail", "perfil": "Perfil", "ativo": "Ativo", "criado_em": "Criado em", "atualizado_em": "Atualizado em"})
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.download_button("Baixar usuários (CSV)", data=df_to_csv_bytes(view), file_name="usuarios.csv", mime="text/csv")

elif menu == "Consulta de estoque":
    st.subheader("Consulta dos produtos em estoque")
    col1, col2 = st.columns([2, 1])
    filtro = col1.text_input("Pesquisar por ID ou nome")
    somente_criticos = col2.checkbox("Mostrar apenas críticos")
    consulta_df = products_df.copy()
    if filtro.strip():
        termo = filtro.strip().lower()
        consulta_df = consulta_df[consulta_df["id"].astype(str).str.lower().str.contains(termo, na=False) | consulta_df["nome"].astype(str).str.lower().str.contains(termo, na=False)]
    if somente_criticos and not consulta_df.empty:
        consulta_df = consulta_df[consulta_df["estoque_atual"] <= consulta_df["estoque_minimo"]]
    if consulta_df.empty:
        st.warning("Nenhum produto encontrado.")
    else:
        view = consulta_df.rename(columns={"id": "ID", "nome": "Produto", "descricao": "Descrição", "unidade": "Unidade", "estoque_atual": "Estoque atual", "estoque_minimo": "Estoque mínimo", "criado_em": "Criado em", "atualizado_em": "Atualizado em"})
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.download_button("Baixar consulta (CSV)", data=df_to_csv_bytes(view), file_name="consulta_estoque.csv", mime="text/csv")

elif menu == "Lançamento de entrada":
    if not can_move_stock():
        deny_access("Você não tem permissão para lançar entrada.")
    st.subheader("Lançamento de entrada")
    if products_df.empty:
        st.warning("Cadastre ao menos um produto antes de lançar entrada.")
    else:
        with st.form("form_entrada", clear_on_submit=True):
            produto_map = {f"ID {int(r['id'])} - {r['nome']}": int(r["id"]) for _, r in products_df.iterrows()}
            produto = st.selectbox("Produto", list(produto_map.keys()))
            quantidade = st.number_input("Quantidade de entrada", min_value=0.01, step=1.0, value=1.0)
            motivo = st.selectbox("Motivo da entrada", get_movement_reason_options("ENTRADA"))
            detalhe = st.text_input("Detalhe complementar")
            obs = f"Motivo: {motivo}" + (f" | {detalhe.strip()}" if detalhe.strip() else "")
            salvar = st.form_submit_button("Registrar entrada", use_container_width=True)
            if salvar:
                try:
                    registrar_movimento(produto_map[produto], "ENTRADA", quantidade, obs, user["usuario"])
                    st.success("Entrada registrada com sucesso.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

elif menu == "Lançamento de saída":
    if not can_move_stock():
        deny_access("Você não tem permissão para lançar saída.")
    st.subheader("Lançamento de saída")
    if products_df.empty:
        st.warning("Cadastre ao menos um produto antes de lançar saída.")
    else:
        with st.form("form_saida", clear_on_submit=True):
            produto_map = {f"ID {int(r['id'])} - {r['nome']} | estoque atual: {r['estoque_atual']} {r['unidade']}": int(r["id"]) for _, r in products_df.iterrows()}
            produto = st.selectbox("Produto", list(produto_map.keys()))
            quantidade = st.number_input("Quantidade de saída", min_value=0.01, step=1.0, value=1.0)
            motivo = st.selectbox("Motivo da saída", get_movement_reason_options("SAIDA"))
            detalhe = st.text_input("Detalhe complementar")
            obs = f"Motivo: {motivo}" + (f" | {detalhe.strip()}" if detalhe.strip() else "")
            salvar = st.form_submit_button("Registrar saída", use_container_width=True)
            if salvar:
                try:
                    registrar_movimento(produto_map[produto], "SAIDA", quantidade, obs, user["usuario"])
                    st.success("Saída registrada com sucesso.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

elif menu == "Ajuste de inventário":
    if not can_adjust_inventory():
        deny_access("Somente Administrador e Almoxarifado podem ajustar inventário.")
    st.subheader("Ajuste de inventário")
    if products_df.empty:
        st.warning("Cadastre ao menos um produto antes de ajustar inventário.")
    else:
        with st.form("form_ajuste", clear_on_submit=True):
            produto_map = {f"ID {int(r['id'])} - {r['nome']} | atual: {r['estoque_atual']} {r['unidade']}": r for _, r in products_df.iterrows()}
            produto_sel = st.selectbox("Produto", list(produto_map.keys()))
            row = produto_map[produto_sel]
            estoque_real = st.number_input("Estoque real contado", min_value=0.0, step=1.0, value=float(row["estoque_atual"]))
            motivo = st.selectbox("Motivo do ajuste", ["Inventário periódico", "Correção de divergência", "Perda não lançada", "Sobra não lançada", "Outros"])
            detalhe = st.text_input("Detalhe complementar")
            confirmar = st.form_submit_button("Aplicar ajuste", use_container_width=True)
            if confirmar:
                try:
                    motivo_texto = motivo + (f" | {detalhe.strip()}" if detalhe.strip() else "")
                    ajustar_estoque_para_valor(int(row["id"]), float(estoque_real), motivo_texto, user["usuario"])
                    st.success("Ajuste de inventário aplicado com sucesso.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

elif menu == "Peças críticas":
    st.subheader("Listagem de peças em situação crítica")
    if criticos_df.empty:
        st.success("Nenhum item está abaixo ou igual ao estoque mínimo.")
    else:
        view = criticos_df.rename(columns={"id": "ID", "nome": "Produto", "unidade": "Unidade", "estoque_atual": "Estoque atual", "estoque_minimo": "Estoque mínimo", "falta_para_minimo": "Falta para mínimo"})
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.download_button("Baixar lista crítica (CSV)", data=df_to_csv_bytes(view), file_name="pecas_criticas.csv", mime="text/csv")

elif menu == "Histórico":
    st.subheader("Histórico de movimentações")
    col1, col2, col3, col4 = st.columns(4)
    data_ini = col1.date_input("Data inicial", value=date.today() - timedelta(days=30))
    data_fim = col2.date_input("Data final", value=date.today())
    tipo = col3.selectbox("Tipo", ["TODOS", "ENTRADA", "SAIDA", "AJUSTE"])
    produto_id = None
    produto_label = col4.selectbox("Produto", ["TODOS"] + [f"ID {int(r['id'])} - {r['nome']}" for _, r in products_df.iterrows()])
    if produto_label != "TODOS":
        produto_row = products_df[("ID " + products_df["id"].astype(int).astype(str) + " - " + products_df["nome"].astype(str)) == produto_label]
        if not produto_row.empty:
            produto_id = int(produto_row.iloc[0]["id"])
    if data_fim < data_ini:
        st.error("A data final não pode ser menor que a data inicial.")
    else:
        mov_df = get_movements_filtered(data_ini, data_fim, tipo, produto_id)
        if mov_df.empty:
            st.info("Nenhuma movimentação encontrada.")
        else:
            mov_df["grupo_tipo"] = mov_df["tipo"].apply(normalize_movement_type)
            view = mov_df.rename(columns={"id": "ID movimento", "produto_id": "ID produto", "produto": "Produto", "tipo": "Tipo", "quantidade": "Quantidade", "unidade": "Unidade", "usuario_lancamento": "Usuário", "observacao": "Observação", "criado_em": "Data/hora"})
            st.dataframe(view.drop(columns=["grupo_tipo"]), use_container_width=True, hide_index=True)
            total_entradas = float(mov_df.loc[mov_df["grupo_tipo"] == "ENTRADA", "quantidade"].sum()) if not mov_df.empty else 0
            total_saidas = float(mov_df.loc[mov_df["grupo_tipo"] == "SAIDA", "quantidade"].sum()) if not mov_df.empty else 0
            c1, c2 = st.columns(2)
            c1.metric("Total de entradas", format_number(total_entradas))
            c2.metric("Total de saídas", format_number(total_saidas))
            st.download_button("Baixar movimentações (CSV)", data=df_to_csv_bytes(view.drop(columns=["grupo_tipo"])), file_name="movimentacoes_filtradas.csv", mime="text/csv")

elif menu == "Relatórios":
    #st.subheader("Relatórios")
    col1, col2 = st.columns(2)
    with col1:
        #st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Relatório geral do sistema")
        mov_30 = get_movements_filtered(date.today() - timedelta(days=30), date.today(), "TODOS", None)
        if not mov_30.empty:
            mov_30["grupo_tipo"] = mov_30["tipo"].apply(normalize_movement_type)
            mov_30 = mov_30.drop(columns=["grupo_tipo"])
        produtos_view = products_df.rename(columns={"id": "ID", "nome": "Nome", "descricao": "Descrição", "unidade": "Unidade", "estoque_atual": "Estoque atual", "estoque_minimo": "Estoque mínimo", "criado_em": "Criado em", "atualizado_em": "Atualizado em"})
        usuarios_view = users_df.rename(columns={"id": "ID", "nome": "Nome", "usuario": "Usuário", "email": "E-mail", "perfil": "Perfil", "ativo": "Ativo", "criado_em": "Criado em", "atualizado_em": "Atualizado em"})
        criticos_view = criticos_df.rename(columns={"id": "ID", "nome": "Produto", "unidade": "Unidade", "estoque_atual": "Estoque atual", "estoque_minimo": "Estoque mínimo", "falta_para_minimo": "Falta para mínimo"})
        mov_view = mov_30.rename(columns={"id": "ID movimento", "produto_id": "ID produto", "produto": "Produto", "tipo": "Tipo", "quantidade": "Quantidade", "unidade": "Unidade", "usuario_lancamento": "Usuário", "observacao": "Observação", "criado_em": "Data/hora"})
        excel = df_to_excel_bytes({"Produtos": produtos_view, "Usuarios": usuarios_view, "Criticos": criticos_view, "Mov_30_dias": mov_view})
        st.download_button("Baixar relatório geral.xlsx", data=excel, file_name="relatorio_geral_estoque.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with col2:
        #st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Relatório de estoque atual")
        if not products_df.empty:
            estoque_view = products_df.rename(columns={"id": "ID", "nome": "Produto", "descricao": "Descrição", "unidade": "Unidade", "estoque_atual": "Estoque atual", "estoque_minimo": "Estoque mínimo", "criado_em": "Criado em", "atualizado_em": "Atualizado em"})
            excel = df_to_excel_bytes({"Estoque_atual": estoque_view})
            st.download_button("Baixar estoque atual.xlsx", data=excel, file_name="estoque_atual.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        else:
            st.info("Não há produtos cadastrados.")
        st.markdown('</div>', unsafe_allow_html=True)
