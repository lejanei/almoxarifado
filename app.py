import os, io, base64, hashlib
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

DEFAULT_DB_URL = "mysql+pymysql://ljsyst02_adm:vinimalu121924@ljsystem.com.br/ljsyst02_almoxarifado?charset=utf8mb4"
APP_NAME = "StockPro Manutenção"
APP_SUBTITLE = "Controle de Estoque e Manutenção"
LOGO_PATH = Path(__file__).parent / "assets" / "logo_stockpro.svg"


def get_database_url():
    v = os.getenv("ALMOXARIFADO_URL")
    if v:
        return v
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
def get_engine():
    return create_engine(
        DATABASE_URL, pool_pre_ping=True, pool_recycle=3600, future=True
    )


def init_db():
    ddls = [
        """CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY,nome VARCHAR(150) NOT NULL,usuario VARCHAR(80) NOT NULL UNIQUE,email VARCHAR(150),perfil VARCHAR(50),senha_hash VARCHAR(64),ativo TINYINT(1) NOT NULL DEFAULT 1,criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS products (id INT AUTO_INCREMENT PRIMARY KEY,codigo VARCHAR(80) NULL UNIQUE,nome VARCHAR(150) NOT NULL,descricao TEXT,unidade VARCHAR(20) NOT NULL DEFAULT 'UN',estoque_atual DECIMAL(18,3) NOT NULL DEFAULT 0,estoque_minimo DECIMAL(18,3) NOT NULL DEFAULT 0,criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS movements (id INT AUTO_INCREMENT PRIMARY KEY,produto_id INT NOT NULL,tipo VARCHAR(30) NOT NULL,quantidade DECIMAL(18,3) NOT NULL,observacao TEXT,usuario_lancamento VARCHAR(150),criado_em DATETIME NOT NULL,CONSTRAINT fk_movements_product FOREIGN KEY (produto_id) REFERENCES products(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS machines (id INT AUTO_INCREMENT PRIMARY KEY,nome VARCHAR(150) NOT NULL,status VARCHAR(50) NOT NULL DEFAULT 'Ativa',criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY,nome VARCHAR(150) NOT NULL,setor VARCHAR(100),funcao VARCHAR(100),criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS service_orders (id INT AUTO_INCREMENT PRIMARY KEY,tipo VARCHAR(20) NOT NULL,opened_by VARCHAR(150) NOT NULL,machine_id INT NOT NULL,start_datetime DATETIME NOT NULL,end_datetime DATETIME NULL,problem_description TEXT,status VARCHAR(50) NOT NULL DEFAULT 'Aberta',solution_description TEXT,created_at DATETIME NOT NULL,updated_at DATETIME NULL,CONSTRAINT fk_so_machine FOREIGN KEY (machine_id) REFERENCES machines(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS service_order_employees (id INT AUTO_INCREMENT PRIMARY KEY,order_id INT NOT NULL,employee_id INT NOT NULL,start_datetime DATETIME NOT NULL,end_datetime DATETIME NULL,created_at DATETIME NOT NULL,CONSTRAINT fk_soe_order FOREIGN KEY (order_id) REFERENCES service_orders(id),CONSTRAINT fk_soe_employee FOREIGN KEY (employee_id) REFERENCES employees(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        
        """CREATE TABLE IF NOT EXISTS audit_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario VARCHAR(150) NOT NULL,
            acao VARCHAR(150) NOT NULL,
            entidade VARCHAR(100),
            entidade_id VARCHAR(100),
            detalhes TEXT,
            criado_em DATETIME NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS service_order_parts (id INT AUTO_INCREMENT PRIMARY KEY,order_id INT NOT NULL,product_id INT NOT NULL,quantidade DECIMAL(18,3) NOT NULL,created_at DATETIME NOT NULL,CONSTRAINT fk_sop_order FOREIGN KEY (order_id) REFERENCES service_orders(id),CONSTRAINT fk_sop_product FOREIGN KEY (product_id) REFERENCES products(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    ]
    with get_engine().begin() as conn:
        for ddl in ddls:
            conn.execute(text(ddl))


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
                "criado_em": datetime.now(),
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
        "SELECT id, tipo, opened_by, machine_id, start_datetime, end_datetime, problem_description, status, solution_description, created_at, updated_at FROM service_orders WHERE opened_by = :username ORDER BY id DESC",
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
            "atualizado_em": datetime.now(),
        },
    )

def update_user_password(user_id, senha):
    execute(
        "UPDATE users SET senha_hash=:senha_hash, atualizado_em=:agora WHERE id=:id",
        {"id": int(user_id), "senha_hash": hash_password(senha), "agora": datetime.now()},
    )

def delete_user_record(user_id):
    execute("DELETE FROM users WHERE id = :id", {"id": int(user_id)})

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
            "criado_em": datetime.now(),
            "atualizado_em": datetime.now(),
        },
    )
    log_action(st.session_state.get("user", {}).get("usuario", "sistema"), "Criou usuário", "users", usuario.strip(), f"Perfil: {perfil}")


def get_products():
    return fetch_df(
        "SELECT id,nome,descricao,unidade,estoque_atual,estoque_minimo,criado_em,atualizado_em FROM products ORDER BY nome"
    )


def create_product(nome, descricao, unidade, estoque_inicial, estoque_minimo):
    execute(
        "INSERT INTO products (codigo,nome,descricao,unidade,estoque_atual,estoque_minimo,criado_em,atualizado_em) VALUES (NULL,:nome,:descricao,:unidade,:estoque_atual,:estoque_minimo,:criado_em,:atualizado_em)",
        {
            "nome": nome.strip(),
            "descricao": descricao.strip(),
            "unidade": unidade,
            "estoque_atual": float(estoque_inicial),
            "estoque_minimo": float(estoque_minimo),
            "criado_em": datetime.now(),
            "atualizado_em": datetime.now(),
        },
    )
    log_action(st.session_state.get("user", {}).get("usuario", "sistema"), "Criou produto", "products", nome.strip(), f"Estoque inicial: {estoque_inicial}")


def register_stock_movement(
    produto_id, tipo, quantidade, observacao, usuario_lancamento
):
    quantidade = float(quantidade)
    with get_engine().begin() as conn:
        produto = (
            conn.execute(
                text("SELECT id,estoque_atual FROM products WHERE id=:id FOR UPDATE"),
                {"id": produto_id},
            )
            .mappings()
            .first()
        )
        atual = float(produto["estoque_atual"])
        novo = atual + quantidade if tipo == "ENTRADA" else atual - quantidade
        if novo < 0:
            raise ValueError("Estoque insuficiente.")
        conn.execute(
            text(
                "UPDATE products SET estoque_atual=:estoque, atualizado_em=:agora WHERE id=:id"
            ),
            {"estoque": novo, "agora": datetime.now(), "id": produto_id},
        )
        conn.execute(
            text(
                "INSERT INTO movements (produto_id,tipo,quantidade,observacao,usuario_lancamento,criado_em) VALUES (:produto_id,:tipo,:quantidade,:observacao,:usuario_lancamento,:criado_em)"
            ),
            {
                "produto_id": produto_id,
                "tipo": tipo,
                "quantidade": quantidade,
                "observacao": observacao,
                "usuario_lancamento": usuario_lancamento,
                "criado_em": datetime.now(),
            },
        )


def update_product_record(product_id, nome, descricao, unidade, estoque_minimo):
    execute(
        "UPDATE products SET nome=:nome, descricao=:descricao, unidade=:unidade, estoque_minimo=:estoque_minimo, atualizado_em=:agora WHERE id=:id",
        {
            "id": int(product_id),
            "nome": nome.strip(),
            "descricao": descricao.strip(),
            "unidade": unidade,
            "estoque_minimo": float(estoque_minimo),
            "agora": datetime.now(),
        },
    )

def delete_product_record(product_id):
    mov = fetch_df("SELECT COUNT(*) AS total FROM movements WHERE produto_id = :id", {"id": int(product_id)})
    if not mov.empty and int(mov.iloc[0]["total"]) > 0:
        raise ValueError("Este produto possui movimentações e não pode ser excluído.")
    uso = fetch_df("SELECT COUNT(*) AS total FROM service_order_parts WHERE product_id = :id", {"id": int(product_id)})
    if not uso.empty and int(uso.iloc[0]["total"]) > 0:
        raise ValueError("Este produto já foi utilizado em ordens e não pode ser excluído.")
    execute("DELETE FROM products WHERE id = :id", {"id": int(product_id)})

def get_movements(limit=200):
    return fetch_df(
        "SELECT m.id,p.id AS produto_id,p.nome AS produto,m.tipo,m.quantidade,p.unidade,m.usuario_lancamento,m.observacao,m.criado_em FROM movements m INNER JOIN products p ON p.id=m.produto_id ORDER BY m.id DESC LIMIT :limite",
        
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
            "criado_em": datetime.now(),
            "atualizado_em": datetime.now(),
        },
    )


def update_machine(machine_id, nome, status):
    execute(
        "UPDATE machines SET nome=:nome,status=:status,atualizado_em=:agora WHERE id=:id",
        {
            "id": machine_id,
            "nome": nome.strip(),
            "status": status,
            "agora": datetime.now(),
        },
    )
    log_action(st.session_state.get("user", {}).get("usuario", "sistema"), "Atualizou máquina", "machines", machine_id, nome.strip())


def delete_machine_record(machine_id):
    uso = fetch_df("SELECT COUNT(*) AS total FROM service_orders WHERE machine_id = :id", {"id": int(machine_id)})
    if not uso.empty and int(uso.iloc[0]["total"]) > 0:
        raise ValueError("Esta máquina possui ordens vinculadas e não pode ser excluída.")
    execute("DELETE FROM machines WHERE id = :id", {"id": int(machine_id)})

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
            "criado_em": datetime.now(),
            "atualizado_em": datetime.now(),
        },
    )
    log_action(st.session_state.get("user", {}).get("usuario", "sistema"), "Criou funcionário", "employees", nome.strip(), f"Setor: {setor}")


def update_employee(emp_id, nome, setor, funcao):
    execute(
        "UPDATE employees SET nome=:nome,setor=:setor,funcao=:funcao,atualizado_em=:agora WHERE id=:id",
        {
            "id": emp_id,
            "nome": nome.strip(),
            "setor": setor.strip(),
            "funcao": funcao.strip(),
            "agora": datetime.now(),
        },
    )
    log_action(st.session_state.get("user", {}).get("usuario", "sistema"), "Atualizou funcionário", "employees", emp_id, nome.strip())


def delete_employee_record(emp_id):
    uso = fetch_df("SELECT COUNT(*) AS total FROM service_order_employees WHERE employee_id = :id", {"id": int(emp_id)})
    if not uso.empty and int(uso.iloc[0]["total"]) > 0:
        raise ValueError("Este funcionário possui apontamentos em ordens e não pode ser excluído.")
    execute("DELETE FROM employees WHERE id = :id", {"id": int(emp_id)})

def get_orders(tipo):
    return fetch_df(
        "SELECT so.id,so.tipo,so.opened_by,m.nome AS maquina,so.machine_id,so.start_datetime,so.end_datetime,so.problem_description,so.status,so.solution_description,so.created_at,so.updated_at FROM service_orders so INNER JOIN machines m ON m.id=so.machine_id WHERE so.tipo=:tipo ORDER BY so.id DESC",
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
    finalizadas["start_datetime"] = pd.to_datetime(finalizadas["start_datetime"], errors="coerce")
    finalizadas = finalizadas.dropna(subset=["start_datetime"]).sort_values("start_datetime")
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
        parts = conn.execute(
            text("SELECT product_id, quantidade FROM service_order_parts WHERE order_id = :order_id"),
            {"order_id": order_id},
        ).mappings().all()

        for part in parts:
            product_id = int(part["product_id"])
            quantidade = float(part["quantidade"])
            produto = conn.execute(
                text("SELECT id, estoque_atual FROM products WHERE id = :id FOR UPDATE"),
                {"id": product_id},
            ).mappings().first()

            if produto:
                novo_estoque = float(produto["estoque_atual"]) + quantidade
                conn.execute(
                    text("UPDATE products SET estoque_atual = :estoque, atualizado_em = :agora WHERE id = :id"),
                    {"estoque": novo_estoque, "agora": datetime.now(), "id": product_id},
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
                        "criado_em": datetime.now(),
                    },
                )

        conn.execute(text("DELETE FROM service_order_parts WHERE order_id = :order_id"), {"order_id": order_id})
        conn.execute(text("DELETE FROM service_order_employees WHERE order_id = :order_id"), {"order_id": order_id})
        conn.execute(text("DELETE FROM service_orders WHERE id = :order_id"), {"order_id": order_id})
    log_action(usuario_lancamento, "Excluiu ordem", "service_orders", order_id, "Exclusão em cascata com devolução de peças")


def get_orders_filtered(
    tipo, machine_id=None, status=None, date_from=None, date_to=None
):
    params = {"tipo": tipo}
    sql = "SELECT so.id,so.tipo,so.opened_by,m.nome AS maquina,so.machine_id,so.start_datetime,so.end_datetime,so.problem_description,so.status,so.solution_description,so.created_at,so.updated_at FROM service_orders so INNER JOIN machines m ON m.id=so.machine_id WHERE so.tipo=:tipo"
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
):
    execute(
        "INSERT INTO service_orders (tipo,opened_by,machine_id,start_datetime,end_datetime,problem_description,status,solution_description,created_at,updated_at) VALUES (:tipo,:opened_by,:machine_id,:start_datetime,:end_datetime,:problem_description,:status,:solution_description,:created_at,:updated_at)",
        {
            "tipo": tipo,
            "opened_by": opened_by,
            "machine_id": machine_id,
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "problem_description": problem_description.strip(),
            "status": status,
            "solution_description": solution_description.strip(),
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        },
    )


def update_order(
    order_id,
    machine_id,
    start_dt,
    end_dt,
    problem_description,
    status,
    solution_description,
):
    execute(
        "UPDATE service_orders SET machine_id=:machine_id,start_datetime=:start_datetime,end_datetime=:end_datetime,problem_description=:problem_description,status=:status,solution_description=:solution_description,updated_at=:updated_at WHERE id=:id",
        {
            "id": order_id,
            "machine_id": machine_id,
            "start_datetime": start_dt,
            "end_datetime": end_dt,
            "problem_description": problem_description.strip(),
            "status": status,
            "solution_description": solution_description.strip(),
            "updated_at": datetime.now(),
        },
    )


def close_order(order_id, solution_description, end_dt):
    execute(
        "UPDATE service_orders SET status='Finalizada',solution_description=:solution_description,end_datetime=:end_datetime,updated_at=:updated_at WHERE id=:id",
        {
            "id": order_id,
            "solution_description": solution_description.strip(),
            "end_datetime": end_dt,
            "updated_at": datetime.now(),
        },
    )
    log_action(st.session_state.get("user", {}).get("usuario", "sistema"), "Fechou ordem", "service_orders", order_id, "Finalizada")


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
            "created_at": datetime.now(),
        },
    )


def get_order_parts(order_id):
    return fetch_df(
        "SELECT op.id,p.id AS peca_id,p.nome,op.quantidade,p.unidade FROM service_order_parts op INNER JOIN products p ON p.id=op.product_id WHERE op.order_id=:order_id ORDER BY op.id DESC",
        {"order_id": order_id},
    )


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
            {"estoque": novo, "agora": datetime.now(), "id": product_id},
        )
        conn.execute(
            text(
                "INSERT INTO service_order_parts (order_id,product_id,quantidade,created_at) VALUES (:order_id,:product_id,:quantidade,:created_at)"
            ),
            {
                "order_id": order_id,
                "product_id": product_id,
                "quantidade": quantidade,
                "created_at": datetime.now(),
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
                "criado_em": datetime.now(),
            },
        )


if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None


def logout():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()


def is_admin():
    return str(user.get("perfil", "")).lower() == "administrador"

def is_almoxarifado():
    return str(user.get("perfil", "")).lower() == "almoxarifado"

def is_operador():
    return str(user.get("perfil", "")).lower() == "operador"

def can_manage_master_data():
    return is_admin() or is_almoxarifado()

def can_view_stock():
    return is_admin() or is_almoxarifado() or is_operador()

def can_manage_users():
    return is_admin()

def can_manage_orders():
    return is_admin() or is_almoxarifado() or is_operador()

def require_permission(condition, message="Você não tem permissão para acessar esta área."):
    if not condition:
        st.warning(message)
        st.stop()


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
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                u = authenticate_user(usuario, senha)
                if u:
                    st.session_state.logged_in = True
                    st.session_state.user = u
                    log_action(u["usuario"], "Login", "auth", u["id"], "Acesso ao sistema")
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
    st.caption(f"Perfil: {user['perfil']} | {user['usuario']}")
    st.markdown("---")
    common_menu = ["Dashboard", "Meu painel", "Ordem de serviço", "Ordem de preventiva", "Dashboard executivo","Produtos / Estoque"]
    almox_menu = []
    admin_menu = ["Máquinas", "Funcionários", "Usuários", "Auditoria"]

    if is_admin():
        menu_options = common_menu + admin_menu
    elif is_almoxarifado():
        menu_options = common_menu + almox_menu
    else:
        menu_options = common_menu
    if st.button("Sair", use_container_width=True):
        logout()
    menu = st.radio("Menu", menu_options)

app_header(
    "Sistema de controle de estoque e manutenção",
    "Estoque + máquinas + OS + preventivas + funcionários",
)

st.markdown(f"""<div class="section-card" style="padding:0.6rem 1rem;"><div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;"><div><strong>Usuário:</strong> {user["nome"]}</div><div><strong>Perfil:</strong> {user["perfil"]}</div><div><strong>Turno:</strong> Operação online</div><div><strong>Data/Hora:</strong> {datetime.now().strftime("%d/%m/%Y %H:%M")}</div></div></div>""", unsafe_allow_html=True)

if menu == "Dashboard":
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
    c1.metric("Ordens abertas por mim", len(minhas_ordens[minhas_ordens["status"].isin(["Aberta", "Em andamento"])] if not minhas_ordens.empty else []))
    c2.metric("Ordens finalizadas por mim", len(minhas_ordens[minhas_ordens["status"] == "Finalizada"] if not minhas_ordens.empty else []))
    c3.metric("Ações registradas", len(meus_logs))
    c4.metric("Perfil", user["perfil"])

    if not minhas_ordens.empty:
        minhas_ordens["Tempo total"] = minhas_ordens.apply(lambda r: format_duration(r["start_datetime"], r["end_datetime"]), axis=1)
        st.markdown("### Minhas ordens")
        st.dataframe(
            minhas_ordens.rename(columns={
                "id": "ID ordem",
                "tipo": "Tipo",
                "opened_by": "Aberta por",
                "machine_id": "ID máquina",
                "start_datetime": "Início",
                "end_datetime": "Fim",
                "problem_description": "Problema",
                "status": "Status",
                "solution_description": "Solução",
            }),
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
            meus_logs.rename(columns={
                "id": "ID",
                "usuario": "Usuário",
                "acao": "Ação",
                "entidade": "Entidade",
                "entidade_id": "ID entidade",
                "detalhes": "Detalhes",
                "criado_em": "Data/hora",
            }),
            use_container_width=True,
            hide_index=True,
        )

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
                estoque_inicial = c3.number_input("Estoque inicial", min_value=0.0, value=0.0)
                c4, c5 = st.columns([1, 2])
                estoque_minimo = c4.number_input("Estoque mínimo", min_value=0.0, value=0.0)
                descricao = c5.text_area("Descrição")
                if st.form_submit_button("Salvar produto", use_container_width=True):
                    create_product(nome, descricao, unidade, estoque_inicial, estoque_minimo)
                    st.success("Produto cadastrado.")
                    st.rerun()

    with t2:
        if is_operador():
            st.info("Operador possui acesso somente para consulta de estoque.")
        elif products_df.empty:
            st.info("Nenhum produto cadastrado.")
        else:
            prod_map = {f"ID {int(r['id'])} - {r['nome']}": r for _, r in products_df.iterrows()}
            sel = st.selectbox("Selecionar produto", list(prod_map.keys()))
            row = prod_map[sel]
            unidades = ["UN", "KG", "PC", "M", "L"]
            unidade_atual = row["unidade"] if row["unidade"] in unidades else "UN"
            with st.form("editar_produto"):
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome", value=str(row["nome"]))
                unidade = c2.selectbox("Unidade", unidades, index=unidades.index(unidade_atual))
                c3, c4 = st.columns(2)
                c3.number_input("Estoque atual", value=float(row["estoque_atual"]), disabled=True)
                estoque_minimo = c4.number_input("Estoque mínimo", min_value=0.0, value=float(row["estoque_minimo"]))
                descricao = st.text_area("Descrição", value="" if pd.isna(row["descricao"]) else str(row["descricao"]))
                b1, b2 = st.columns(2)
                with b1:
                    salvar = st.form_submit_button("Atualizar produto", use_container_width=True)
                with b2:
                    excluir = st.form_submit_button("Excluir produto", use_container_width=True)
                if salvar:
                    update_product_record(int(row["id"]), nome, descricao, unidade, estoque_minimo)
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
                        f"ID {int(r['id'])} - {r['nome']} | saldo: {r['estoque_atual']} {r['unidade']}": int(r["id"])
                        for _, r in products_df.iterrows()
                    }
                    produto = st.selectbox("Produto", list(produto_map.keys()))
                    tipo = st.selectbox("Tipo", ["ENTRADA", "SAIDA"])
                    quantidade = st.number_input("Quantidade", min_value=0.01, value=1.0)
                    observacao = st.text_input("Observação")
                    if st.form_submit_button("Lançar", use_container_width=True):
                        register_stock_movement(produto_map[produto], tipo, quantidade, observacao, user["usuario"])
                        st.success("Movimentação registrada.")
                        st.rerun()

    with t4:
        if products_df.empty:
            st.info("Nenhum produto cadastrado.")
        else:
            st.dataframe(
                products_df.rename(columns={"id": "ID", "nome": "Produto", "descricao": "Descrição", "unidade": "Unidade", "estoque_atual": "Estoque atual", "estoque_minimo": "Estoque mínimo"}),
                use_container_width=True,
                hide_index=True,
            )

    with t5:
        mov_df = get_movements()
        if mov_df.empty:
            st.info("Nenhuma movimentação registrada.")
        else:
            st.dataframe(
                mov_df.rename(columns={"id": "ID", "produto_id": "ID produto", "produto": "Produto", "tipo": "Tipo", "quantidade": "Quantidade", "unidade": "Unidade", "usuario_lancamento": "Usuário", "observacao": "Observação", "criado_em": "Data/hora"}),
                use_container_width=True,
                hide_index=True,
            )

elif menu == "Máquinas":
    require_permission(can_manage_master_data(), "Somente Administrador ou Almoxarifado pode acessar Máquinas.")
    st.subheader("Máquinas")
    t1, t2 = st.tabs(["Nova máquina", "Editar / Excluir"])

    with t1:
        with st.form("nova_maquina", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome da máquina")
            status = c2.selectbox("Status", ["Ativa", "Parada", "Em manutenção", "Inativa"])
            if st.form_submit_button("Salvar máquina", use_container_width=True):
                create_machine(nome, status)
                st.success("Máquina cadastrada.")
                st.rerun()

    with t2:
        if machines_df.empty:
            st.info("Nenhuma máquina cadastrada.")
        else:
            maq_map = {f"ID {int(r['id'])} - {r['nome']}": r for _, r in machines_df.iterrows()}
            sel = st.selectbox("Selecionar máquina", list(maq_map.keys()))
            row = maq_map[sel]
            with st.form("editar_maquina"):
                nome = st.text_input("Nome", value=str(row["nome"]))
                opts = ["Ativa", "Parada", "Em manutenção", "Inativa"]
                status = st.selectbox("Status", opts, index=opts.index(row["status"]) if row["status"] in opts else 0)
                b1, b2 = st.columns(2)
                with b1:
                    salvar = st.form_submit_button("Atualizar máquina", use_container_width=True)
                with b2:
                    excluir = st.form_submit_button("Excluir máquina", use_container_width=True)
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

elif menu == "Funcionários":
    require_permission(can_manage_master_data(), "Somente Administrador ou Almoxarifado pode acessar Funcionários.")
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
            emp_map = {f"ID {int(r['id'])} - {r['nome']}": r for _, r in employees_df.iterrows()}
            sel = st.selectbox("Selecionar funcionário", list(emp_map.keys()))
            row = emp_map[sel]
            with st.form("editar_funcionario"):
                c1, c2, c3 = st.columns(3)
                nome = c1.text_input("Nome", value=str(row["nome"]))
                setor = c2.text_input("Setor", value="" if pd.isna(row["setor"]) else str(row["setor"]))
                funcao = c3.text_input("Função", value="" if pd.isna(row["funcao"]) else str(row["funcao"]))
                b1, b2 = st.columns(2)
                with b1:
                    salvar = st.form_submit_button("Atualizar funcionário", use_container_width=True)
                with b2:
                    excluir = st.form_submit_button("Excluir funcionário", use_container_width=True)
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

    tabs = st.tabs(["Nova ordem", "Editar ordem", "Fechamento", "Equipe / Peças", "Consulta", "Excluir ordem"])

    with tabs[0]:
        if machines_df.empty:
            st.warning("Cadastre máquinas antes de abrir ordens.")
        else:
            with st.form(f"nova_ordem_{tipo}", clear_on_submit=True):
                maq_map = {f"ID {int(r['id'])} - {r['nome']}": int(r["id"]) for _, r in machines_df.iterrows()}
                maquina = st.selectbox("Máquina", list(maq_map.keys()))
                c1, c2 = st.columns(2)
                data_inicio = c1.date_input("Data início", value=date.today(), key=f"di_{tipo}")
                hora_inicio = c2.time_input("Hora início", key=f"hi_{tipo}")
                c3, c4 = st.columns(2)
                data_fim = c3.date_input("Data fim", value=date.today(), key=f"df_{tipo}")
                hora_fim = c4.time_input("Hora fim", key=f"hf_{tipo}")
                problema = st.text_area("Descrição do problema")
                status = st.selectbox("Status", ["Aberta", "Em andamento", "Finalizada", "Cancelada"], key=f"st_{tipo}")
                solucao = st.text_area("Descrição da solução")
                if st.form_submit_button("Salvar ordem", use_container_width=True):
                    create_order(
                        tipo,
                        user["usuario"],
                        maq_map[maquina],
                        combine_date_time(data_inicio, hora_inicio),
                        combine_date_time(data_fim, hora_fim),
                        problema,
                        status,
                        solucao,
                    )
                    st.success("Ordem cadastrada.")
                    st.rerun()

    with tabs[1]:
        df = get_orders(tipo)
        if df.empty:
            st.info("Nenhuma ordem cadastrada.")
        else:
            ord_map = {f"Ordem {int(r['id'])} - {r['maquina']}": r for _, r in df.iterrows()}
            labels = list(ord_map.keys())

            default_index = 0
            selected_id = st.session_state.get(state_key)
            if selected_id is not None:
                for i, (_, r) in enumerate(ord_map.items()):
                    if int(r["id"]) == int(selected_id):
                        default_index = i
                        break

            sel = st.selectbox("Selecione a ordem", labels, index=default_index, key=f"ed_{tipo}")
            row = ord_map[sel]

            maq_map = {f"ID {int(r['id'])} - {r['nome']}": int(r["id"]) for _, r in machines_df.iterrows()}
            machine_label = next((k for k, v in maq_map.items() if v == int(row["machine_id"])), list(maq_map.keys())[0])

            with st.form(f"editar_ordem_{tipo}"):
                maquina = st.selectbox("Máquina", list(maq_map.keys()), index=list(maq_map.keys()).index(machine_label))
                start_dt = pd.to_datetime(row["start_datetime"])
                end_dt = pd.to_datetime(row["end_datetime"]) if pd.notna(row["end_datetime"]) else pd.Timestamp.now()

                c1, c2 = st.columns(2)
                data_inicio = c1.date_input("Data início", value=start_dt.date(), key=f"edi_{tipo}_1")
                hora_inicio = c2.time_input("Hora início", value=start_dt.time(), key=f"edi_{tipo}_2")

                c3, c4 = st.columns(2)
                data_fim = c3.date_input("Data fim", value=end_dt.date(), key=f"edi_{tipo}_3")
                hora_fim = c4.time_input("Hora fim", value=end_dt.time(), key=f"edi_{tipo}_4")

                problema = st.text_area("Descrição do problema", value="" if pd.isna(row["problem_description"]) else str(row["problem_description"]))
                status_opts = ["Aberta", "Em andamento", "Finalizada", "Cancelada"]
                status = st.selectbox("Status", status_opts, index=status_opts.index(row["status"]) if row["status"] in status_opts else 0, key=f"edi_{tipo}_5")
                solucao = st.text_area("Descrição da solução", value="" if pd.isna(row["solution_description"]) else str(row["solution_description"]))

                if st.form_submit_button("Atualizar ordem", use_container_width=True):
                    update_order(
                        int(row["id"]),
                        maq_map[maquina],
                        combine_date_time(data_inicio, hora_inicio),
                        combine_date_time(data_fim, hora_fim),
                        problema,
                        status,
                        solucao,
                    )
                    st.success("Ordem atualizada.")
                    st.rerun()

    with tabs[2]:
        df_close = get_orders_filtered(tipo, status="TODOS")
        if not df_close.empty:
            df_close = df_close[df_close["status"].isin(["Aberta", "Em andamento"])]
        if df_close.empty:
            st.info("Nenhuma ordem aberta ou em andamento para fechamento.")
        else:
            ord_map = {f"Ordem {int(r['id'])} - {r['maquina']} - {r['status']}": r for _, r in df_close.iterrows()}
            sel = st.selectbox("Selecione a ordem para fechar", list(ord_map.keys()), key=f"close_{tipo}")
            row = ord_map[sel]
            with st.form(f"fechar_ordem_{tipo}"):
                c1, c2 = st.columns(2)
                data_fim = c1.date_input("Data final", value=date.today(), key=f"fech_df_{tipo}")
                hora_fim = c2.time_input("Hora final", key=f"fech_hf_{tipo}")
                solucao = st.text_area("Descrição final da solução", value="" if pd.isna(row["solution_description"]) else str(row["solution_description"]))
                if st.form_submit_button("Fechar ordem", use_container_width=True):
                    close_order(int(row["id"]), solucao, combine_date_time(data_fim, hora_fim))
                    st.success("Ordem finalizada com sucesso.")
                    st.rerun()

    with tabs[3]:
        df = get_orders(tipo)
        if df.empty:
            st.info("Nenhuma ordem cadastrada.")
        else:
            ord_map = {f"Ordem {int(r['id'])} - {r['maquina']}": int(r["id"]) for _, r in df.iterrows()}
            order_label = st.selectbox("Ordem", list(ord_map.keys()), key=f"ges_{tipo}")
            order_id = ord_map[order_label]

            ca, cb = st.columns(2)

            with ca:
                st.markdown("### Funcionários")
                if not employees_df.empty:
                    with st.form(f"func_ordem_{tipo}", clear_on_submit=True):
                        emp_map = {f"ID {int(r['id'])} - {r['nome']}": int(r["id"]) for _, r in employees_df.iterrows()}
                        emp = st.selectbox("Funcionário", list(emp_map.keys()), key=f"emp_{tipo}")
                        c1, c2 = st.columns(2)
                        di = c1.date_input("Data início", value=date.today(), key=f"empdi_{tipo}")
                        hi = c2.time_input("Hora início", key=f"emphi_{tipo}")
                        c3, c4 = st.columns(2)
                        dfim = c3.date_input("Data fim", value=date.today(), key=f"empdf_{tipo}")
                        hfim = c4.time_input("Hora fim", key=f"emphf_{tipo}")
                        if st.form_submit_button("Adicionar funcionário", use_container_width=True):
                            add_employee_to_order(order_id, emp_map[emp], combine_date_time(di, hi), combine_date_time(dfim, hfim))
                            st.success("Funcionário vinculado.")
                            st.rerun()
                order_emp = get_order_employees(order_id)
                if not order_emp.empty:
                    order_emp["Tempo"] = order_emp.apply(lambda r: format_duration(r["start_datetime"], r["end_datetime"]), axis=1)
                    st.dataframe(order_emp.rename(columns={"id":"ID vínculo","funcionario_id":"ID funcionário","nome":"Nome","setor":"Setor","funcao":"Função","start_datetime":"Início","end_datetime":"Fim"}), use_container_width=True, hide_index=True)

            with cb:
                st.markdown("### Peças utilizadas")
                if not products_df.empty:
                    with st.form(f"peca_ordem_{tipo}", clear_on_submit=True):
                        part_map = {f"ID {int(r['id'])} - {r['nome']} | saldo: {r['estoque_atual']} {r['unidade']}": int(r["id"]) for _, r in products_df.iterrows()}
                        peca = st.selectbox("Peça", list(part_map.keys()), key=f"peca_{tipo}")
                        quantidade = st.number_input("Quantidade", min_value=0.01, value=1.0, key=f"qtd_{tipo}")
                        if st.form_submit_button("Adicionar peça e baixar estoque", use_container_width=True):
                            add_part_to_order(order_id, part_map[peca], quantidade, user["usuario"])
                            st.success("Peça lançada na ordem.")
                            st.rerun()
                order_parts = get_order_parts(order_id)
                if not order_parts.empty:
                    st.dataframe(order_parts.rename(columns={"id":"ID vínculo","peca_id":"ID peça","nome":"Peça","quantidade":"Quantidade","unidade":"Unidade"}), use_container_width=True, hide_index=True)

    with tabs[4]:
        st.markdown("### Filtros")
        c1, c2, c3, c4 = st.columns(4)
        machine_id = None
        if not machines_df.empty:
            maq_labels = ["TODAS"] + [f"ID {int(r['id'])} - {r['nome']}" for _, r in machines_df.iterrows()]
            maq_sel = c1.selectbox("Máquina", maq_labels, key=f"fmaq_{tipo}")
            if maq_sel != "TODAS":
                machine_id = int(maq_sel.split(" - ")[0].replace("ID ", ""))
        status = c2.selectbox("Status", ["TODOS", "Aberta", "Em andamento", "Finalizada", "Cancelada"], key=f"fstatus_{tipo}")
        d_ini = c3.date_input("De", value=date.today() - timedelta(days=30), key=f"fdi_{tipo}")
        d_fim = c4.date_input("Até", value=date.today(), key=f"fdf_{tipo}")

        df = get_orders_filtered(tipo, machine_id=machine_id, status=status, date_from=d_ini, date_to=d_fim)
        if not df.empty:
            df["Tempo total"] = df.apply(lambda r: format_duration(r["start_datetime"], r["end_datetime"]), axis=1)
            st.dataframe(df.rename(columns={"id":"ID ordem","opened_by":"Aberta por","maquina":"Máquina","start_datetime":"Início","end_datetime":"Fim","problem_description":"Problema","status":"Status","solution_description":"Solução"}), use_container_width=True, hide_index=True)

            ordem_escolhida = st.selectbox(
                "Selecione uma ordem da consulta para editar",
                [f"Ordem {int(r['id'])} - {r['maquina']}" for _, r in df.iterrows()],
                key=f"consulta_select_{tipo}",
            )
            if st.button("Carregar esta ordem na aba Editar", key=f"carregar_edit_{tipo}", use_container_width=True):
                order_id = int(ordem_escolhida.split(" - ")[0].replace("Ordem ", ""))
                st.session_state[state_key] = order_id
                st.success("Ordem carregada. Agora clique na aba 'Editar ordem'.")
        else:
            st.info("Nenhuma ordem encontrada com os filtros.")

    with tabs[5]:
        df = get_orders(tipo)
        if df.empty:
            st.info("Nenhuma ordem cadastrada.")
        else:
            ord_map = {f"Ordem {int(r['id'])} - {r['maquina']}": int(r["id"]) for _, r in df.iterrows()}
            order_label = st.selectbox("Selecione a ordem para excluir", list(ord_map.keys()), key=f"del_{tipo}")
            st.warning("Ao excluir a ordem, os funcionários vinculados e peças lançadas serão removidos. As peças usadas voltarão ao estoque.")
            if st.button("Excluir ordem selecionada", type="primary", key=f"btn_del_{tipo}", use_container_width=True):
                delete_order_cascade(ord_map[order_label], user["usuario"])
                if st.session_state.get(state_key) == ord_map[order_label]:
                    st.session_state[state_key] = None
                st.success("Ordem excluída com sucesso e estoque revertido.")
                st.rerun()

if menu == "Ordem de serviço":
    require_permission(can_manage_orders(), "Você não tem permissão para acessar Ordens de serviço.")
    order_page("CORRETIVA", "Ordem de serviço")
elif menu == "Ordem de preventiva":
    require_permission(can_manage_orders(), "Você não tem permissão para acessar Ordens preventivas.")
    order_page("PREVENTIVA", "Ordem de preventiva")


elif menu == "Usuários":
    require_permission(can_manage_users(), "Somente Administrador pode acessar Usuários.")
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
            perfil = st.selectbox("Perfil", ["Administrador", "Almoxarifado", "Operador"])
            ativo = st.checkbox("Ativo", value=True)
            if st.form_submit_button("Criar usuário", use_container_width=True):
                create_user(nome, usuario_login, email, perfil, senha, ativo)
                st.success("Usuário criado com sucesso.")
                st.rerun()
    with t2:
        if users_df.empty:
            st.info("Nenhum usuário cadastrado.")
        else:
            user_map = {f'ID {int(r["id"])} - {r["nome"]} ({r["usuario"]})': r for _, r in users_df.iterrows()}
            selected = st.selectbox("Selecionar usuário", list(user_map.keys()))
            row = user_map[selected]
            with st.form("editar_usuario"):
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome", value=row["nome"])
                usuario_login = c2.text_input("Usuário", value=row["usuario"])
                c3, c4 = st.columns(2)
                email = c3.text_input("E-mail", value="" if pd.isna(row["email"]) else str(row["email"]))
                senha = c4.text_input("Nova senha (opcional)", type="password")
                perfil_opts = ["Administrador", "Operador"]
                perfil = st.selectbox("Perfil", perfil_opts, index=perfil_opts.index(row["perfil"]) if row["perfil"] in perfil_opts else 1)
                ativo = st.checkbox("Ativo", value=bool(row["ativo"]))
                col1, col2 = st.columns(2)
                with col1:
                    if st.form_submit_button("Atualizar usuário", use_container_width=True):
                        update_user_record(int(row["id"]), nome, usuario_login, email, perfil, ativo)
                        if senha:
                            update_user_password(int(row["id"]), senha)
                        log_action(user["usuario"], "Atualizou usuário", "users", row["id"], usuario_login)
                        st.success("Usuário atualizado.")
                        st.rerun()
                with col2:
                    if st.form_submit_button("Excluir usuário", use_container_width=True):
                        if int(row["id"]) == int(user["id"]):
                            st.error("Você não pode excluir o próprio usuário logado.")
                        else:
                            delete_user_record(int(row["id"]))
                            log_action(user["usuario"], "Excluiu usuário", "users", row["id"], usuario_login)
                            st.success("Usuário excluído.")
                            st.rerun()

elif menu == "Auditoria":
    require_permission(can_manage_users(), "Somente Administrador pode acessar Auditoria.")
    st.subheader("Histórico de ações")
    logs_df = get_audit_logs(limit=500)
    if logs_df.empty:
        st.info("Nenhum log registrado.")
    else:
        st.dataframe(
            logs_df.rename(columns={
                "id": "ID",
                "usuario": "Usuário",
                "acao": "Ação",
                "entidade": "Entidade",
                "entidade_id": "ID entidade",
                "detalhes": "Detalhes",
                "criado_em": "Data/hora",
            }),
            use_container_width=True,
            hide_index=True,
        )

elif menu == "Dashboard executivo":
    st.subheader("Dashboard executivo")

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
    c5.metric("OS abertas", len(os_df[os_df["status"].isin(["Aberta", "Em andamento"])]))
    c6.metric("Preventivas abertas", len(pm_df[pm_df["status"].isin(["Aberta", "Em andamento"])]))
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
                st.metric(f"{i+1}º lugar", row["maquina"], delta=f'{int(row["quebras"])} OS')
                st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("### Top 10 itens mais usados")
    if top_itens.empty:
        st.info("Nenhuma peça foi usada em ordens ainda.")
    else:
        for start in range(0, len(top_itens), 5):
            row_items = top_itens.iloc[start:start+5]
            cols = st.columns(len(row_items))
            for i, (_, item) in enumerate(row_items.iterrows()):
                with cols[i]:
                    st.markdown('<div class="section-card">', unsafe_allow_html=True)
                    st.metric(
                        f'ID {int(item["produto_id"])}',
                        item["nome"],
                        delta=f'{format_number(item["total_usado"])} {item["unidade"]}',
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("### Top 10 funcionários mais acionados")
    if top_func.empty:
        st.info("Nenhum funcionário foi apontado em ordens ainda.")
    else:
        for start in range(0, len(top_func), 5):
            row_items = top_func.iloc[start:start+5]
            cols = st.columns(len(row_items))
            for i, (_, item) in enumerate(row_items.iterrows()):
                with cols[i]:
                    st.markdown('<div class="section-card">', unsafe_allow_html=True)
                    st.metric(
                        f'ID {int(item["funcionario_id"])}',
                        item["nome"],
                        delta=f'{int(item["total_acionamentos"])} acionamentos',
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
    
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
            audit_recent.rename(columns={
                "id": "ID",
                "usuario": "Usuário",
                "acao": "Ação",
                "entidade": "Entidade",
                "entidade_id": "ID entidade",
                "detalhes": "Detalhes",
                "criado_em": "Data/hora",
            }),
            use_container_width=True,
            hide_index=True,
        )


