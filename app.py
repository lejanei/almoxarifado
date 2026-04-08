import os, io, base64, hashlib
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

DEFAULT_DB_URL = "mysql+pymysql://ljsyst02_adm:vinimalu121924@ljsystem.com.br/ljsyst02_almoxarifado?charset=utf8mb4"
APP_NAME = "StockPro Almoxarifado"
APP_SUBTITLE = "Estoque, manutenção corretiva e preventiva"
LOGO_PATH = Path(__file__).parent / "assets" / "logo_stockpro.svg"

def get_database_url():
    v = os.getenv("ALMOXARIFADO_URL")
    if v: return v
    try:
        if "ALMOXARIFADO_URL" in st.secrets: return st.secrets["ALMOXARIFADO_URL"]
    except Exception:
        pass
    return DEFAULT_DB_URL

DATABASE_URL = get_database_url()
st.set_page_config(page_title=APP_NAME, page_icon="📦", layout="wide")

def load_logo_base64():
    try: return base64.b64encode(LOGO_PATH.read_bytes()).decode("utf-8")
    except Exception: return ""
logo_b64 = load_logo_base64()

st.markdown("""
<style>
:root { --border: rgba(148,163,184,.18); --text:#e5e7eb; --muted:#94a3b8; --brand:#0ea5a4; --brand2:#14b8a6; }
html,body,[data-testid="stAppViewContainer"],[data-testid="stApp"]{background:linear-gradient(180deg,#0b1220 0%,#0a0f1c 100%);color:var(--text);}
.block-container{padding-top:1rem;padding-bottom:1rem;} header[data-testid="stHeader"]{background:transparent;}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#0f172a 0%,#111827 100%);border-right:1px solid var(--border);}
section[data-testid="stSidebar"] *{color:var(--text)!important;}
.hero-card,.section-card,.login-wrap,div[data-testid="stMetric"],div[data-testid="stDataFrame"]{background:linear-gradient(180deg,rgba(31,41,55,.96) 0%,rgba(17,24,39,.96) 100%)!important;border:1px solid var(--border)!important;color:var(--text)!important;border-radius:18px;box-shadow:0 14px 30px rgba(0,0,0,.18);}
.hero-card{padding:1.2rem 1.3rem;border-radius:22px;margin-bottom:1rem;}
.brand-chip{display:inline-block;padding:.34rem .78rem;border-radius:999px;background:rgba(20,184,166,.14);color:#99f6e4!important;font-size:.84rem;font-weight:700;margin-bottom:.45rem;border:1px solid rgba(20,184,166,.18);}
.brand-title{font-size:1.7rem;font-weight:800;color:#f8fafc!important;margin:0;}
.brand-subtitle,.small-muted{color:var(--muted)!important;}
.sidebar-brand{padding:.9rem 1rem;border:1px solid rgba(255,255,255,.08);border-radius:18px;background:linear-gradient(180deg,rgba(30,41,59,.65) 0%,rgba(15,23,42,.55) 100%);margin-bottom:.9rem;}
.stButton > button,.stDownloadButton > button{border-radius:12px;font-weight:700;border:1px solid rgba(20,184,166,.22);background:linear-gradient(90deg,var(--brand) 0%,var(--brand2) 100%);color:white!important;}
.stTextInput input,.stTextArea textarea,.stNumberInput input,div[data-baseweb="select"] > div,[data-testid="stDateInputField"]{background:rgba(15,23,42,.85)!important;color:var(--text)!important;border:1px solid var(--border)!important;border-radius:10px!important;}
[data-baseweb="select"] *{color:var(--text)!important;}
</style>
""", unsafe_allow_html=True)

def hash_password(password): return hashlib.sha256(password.encode("utf-8")).hexdigest()
def format_number(v):
    try: return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return v
def df_to_excel_bytes(sheets):
    b = io.BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as w:
        for n, df in sheets.items(): df.to_excel(w, index=False, sheet_name=n[:31])
    return b.getvalue()
def app_header(title, subtitle=""):
    logo_html = f'<img src="data:image/svg+xml;base64,{logo_b64}" style="height:66px;">' if logo_b64 else "📦"
    st.markdown(f"""<div class="hero-card">            
            <h1 class="brand-title">{APP_NAME}</h1>
            <h3 class="brand-title">{title}</h3>
            <p class="brand-subtitle">{subtitle or APP_SUBTITLE}</p></div></div></div>""",
            unsafe_allow_html=True,)

def combine_date_time(d, t): return datetime.combine(d, t)
def format_duration(start_dt, end_dt):
    if pd.isna(start_dt) or pd.isna(end_dt): return ""
    delta = pd.to_datetime(end_dt) - pd.to_datetime(start_dt)
    mins = int(delta.total_seconds()//60)
    if mins < 0: return ""
    return f"{mins//60}h {mins%60}min"

@st.cache_resource
def get_engine(): return create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600, future=True)

def init_db():
    ddls = [
    """CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY,nome VARCHAR(150) NOT NULL,usuario VARCHAR(80) NOT NULL UNIQUE,email VARCHAR(150),perfil VARCHAR(50),senha_hash VARCHAR(64),ativo TINYINT(1) NOT NULL DEFAULT 1,criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS products (id INT AUTO_INCREMENT PRIMARY KEY,codigo VARCHAR(80) NULL UNIQUE,nome VARCHAR(150) NOT NULL,descricao TEXT,unidade VARCHAR(20) NOT NULL DEFAULT 'UN',estoque_atual DECIMAL(18,3) NOT NULL DEFAULT 0,estoque_minimo DECIMAL(18,3) NOT NULL DEFAULT 0,criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS movements (id INT AUTO_INCREMENT PRIMARY KEY,produto_id INT NOT NULL,tipo VARCHAR(30) NOT NULL,quantidade DECIMAL(18,3) NOT NULL,observacao TEXT,usuario_lancamento VARCHAR(150),criado_em DATETIME NOT NULL,CONSTRAINT fk_movements_product FOREIGN KEY (produto_id) REFERENCES products(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS machines (id INT AUTO_INCREMENT PRIMARY KEY,nome VARCHAR(150) NOT NULL,status VARCHAR(50) NOT NULL DEFAULT 'Ativa',criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS employees (id INT AUTO_INCREMENT PRIMARY KEY,nome VARCHAR(150) NOT NULL,setor VARCHAR(100),funcao VARCHAR(100),criado_em DATETIME NOT NULL,atualizado_em DATETIME NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS service_orders (id INT AUTO_INCREMENT PRIMARY KEY,tipo VARCHAR(20) NOT NULL,opened_by VARCHAR(150) NOT NULL,machine_id INT NOT NULL,start_datetime DATETIME NOT NULL,end_datetime DATETIME NULL,problem_description TEXT,status VARCHAR(50) NOT NULL DEFAULT 'Aberta',solution_description TEXT,created_at DATETIME NOT NULL,updated_at DATETIME NULL,CONSTRAINT fk_so_machine FOREIGN KEY (machine_id) REFERENCES machines(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS service_order_employees (id INT AUTO_INCREMENT PRIMARY KEY,order_id INT NOT NULL,employee_id INT NOT NULL,start_datetime DATETIME NOT NULL,end_datetime DATETIME NULL,created_at DATETIME NOT NULL,CONSTRAINT fk_soe_order FOREIGN KEY (order_id) REFERENCES service_orders(id),CONSTRAINT fk_soe_employee FOREIGN KEY (employee_id) REFERENCES employees(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS service_order_parts (id INT AUTO_INCREMENT PRIMARY KEY,order_id INT NOT NULL,product_id INT NOT NULL,quantidade DECIMAL(18,3) NOT NULL,created_at DATETIME NOT NULL,CONSTRAINT fk_sop_order FOREIGN KEY (order_id) REFERENCES service_orders(id),CONSTRAINT fk_sop_product FOREIGN KEY (product_id) REFERENCES products(id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
    ]
    with get_engine().begin() as conn:
        for ddl in ddls: conn.execute(text(ddl))

def fetch_df(q, p=None):
    with get_engine().connect() as conn: return pd.read_sql(text(q), conn, params=p or {})
def execute(q, p=None):
    with get_engine().begin() as conn: return conn.execute(text(q), p or {})

def get_users(): return fetch_df("SELECT id,nome,usuario,email,perfil,ativo,criado_em,atualizado_em FROM users ORDER BY nome")
def count_users():
    df = fetch_df("SELECT COUNT(*) AS total FROM users"); return int(df.iloc[0]["total"]) if not df.empty else 0
def authenticate_user(usuario, senha):
    df = fetch_df("SELECT id,nome,usuario,email,perfil,ativo,senha_hash FROM users WHERE usuario=:usuario LIMIT 1", {"usuario": usuario.strip()})
    if df.empty: return None
    r = df.iloc[0]
    if int(r["ativo"]) != 1 or (r["senha_hash"] or "") != hash_password(senha): return None
    return {"id": int(r["id"]), "nome": r["nome"], "usuario": r["usuario"], "email": r["email"], "perfil": r["perfil"]}
def create_user(nome, usuario, email, perfil, senha, ativo=True):
    execute("INSERT INTO users (nome,usuario,email,perfil,senha_hash,ativo,criado_em,atualizado_em) VALUES (:nome,:usuario,:email,:perfil,:senha_hash,:ativo,:criado_em,:atualizado_em)",
            {"nome": nome.strip(),"usuario": usuario.strip(),"email": email.strip(),"perfil": perfil,"senha_hash": hash_password(senha),"ativo": 1 if ativo else 0,"criado_em": datetime.now(),"atualizado_em": datetime.now()})

def get_products(): return fetch_df("SELECT id,nome,descricao,unidade,estoque_atual,estoque_minimo,criado_em,atualizado_em FROM products ORDER BY nome")
def create_product(nome, descricao, unidade, estoque_inicial, estoque_minimo):
    execute("INSERT INTO products (codigo,nome,descricao,unidade,estoque_atual,estoque_minimo,criado_em,atualizado_em) VALUES (NULL,:nome,:descricao,:unidade,:estoque_atual,:estoque_minimo,:criado_em,:atualizado_em)",
            {"nome": nome.strip(),"descricao": descricao.strip(),"unidade": unidade,"estoque_atual": float(estoque_inicial),"estoque_minimo": float(estoque_minimo),"criado_em": datetime.now(),"atualizado_em": datetime.now()})

def update_product(product_id, nome, descricao, unidade, estoque_minimo):
    execute("UPDATE products SET nome=:nome, descricao=:descricao, unidade=:unidade, estoque_minimo=:estoque_minimo, atualizado_em=:agora WHERE id=:id",
            {"id": product_id, "nome": nome.strip(), "descricao": descricao.strip(), "unidade": unidade, "estoque_minimo": float(estoque_minimo), "agora": datetime.now()})

def delete_product(product_id):
    refs = fetch_df("SELECT COUNT(*) AS total FROM service_order_parts WHERE product_id=:id", {"id": product_id})
    if not refs.empty and int(refs.iloc[0]["total"]) > 0:
        raise ValueError("Este produto já foi usado em ordens e não pode ser excluído.")
    movs = fetch_df("SELECT COUNT(*) AS total FROM movements WHERE produto_id=:id", {"id": product_id})
    if not movs.empty and int(movs.iloc[0]["total"]) > 0:
        raise ValueError("Este produto possui movimentações e não pode ser excluído.")
    execute("DELETE FROM products WHERE id=:id", {"id": product_id})
def register_stock_movement(produto_id, tipo, quantidade, observacao, usuario_lancamento):
    quantidade = float(quantidade)
    with get_engine().begin() as conn:
        produto = conn.execute(text("SELECT id,estoque_atual FROM products WHERE id=:id FOR UPDATE"), {"id": produto_id}).mappings().first()
        atual = float(produto["estoque_atual"]); novo = atual + quantidade if tipo == "ENTRADA" else atual - quantidade
        if novo < 0: raise ValueError("Estoque insuficiente.")
        conn.execute(text("UPDATE products SET estoque_atual=:estoque, atualizado_em=:agora WHERE id=:id"), {"estoque": novo,"agora": datetime.now(),"id": produto_id})
        conn.execute(text("INSERT INTO movements (produto_id,tipo,quantidade,observacao,usuario_lancamento,criado_em) VALUES (:produto_id,:tipo,:quantidade,:observacao,:usuario_lancamento,:criado_em)"),
                     {"produto_id": produto_id,"tipo": tipo,"quantidade": quantidade,"observacao": observacao,"usuario_lancamento": usuario_lancamento,"criado_em": datetime.now()})
def get_movements(limit=200):
    return fetch_df("SELECT m.id,p.id AS produto_id,p.nome AS produto,m.tipo,m.quantidade,p.unidade,m.usuario_lancamento,m.observacao,m.criado_em FROM movements m INNER JOIN products p ON p.id=m.produto_id ORDER BY m.id DESC LIMIT :limite", {"limite": int(limit)})
def get_critical_products():
    return fetch_df("SELECT id,nome,unidade,estoque_atual,estoque_minimo,(estoque_minimo-estoque_atual) AS falta_para_minimo FROM products WHERE estoque_atual<=estoque_minimo ORDER BY falta_para_minimo DESC,nome")

def get_machines(): return fetch_df("SELECT id,nome,status,criado_em,atualizado_em FROM machines ORDER BY nome")
def create_machine(nome, status): execute("INSERT INTO machines (nome,status,criado_em,atualizado_em) VALUES (:nome,:status,:criado_em,:atualizado_em)", {"nome": nome.strip(),"status": status,"criado_em": datetime.now(),"atualizado_em": datetime.now()})
def update_machine(machine_id, nome, status): execute("UPDATE machines SET nome=:nome,status=:status,atualizado_em=:agora WHERE id=:id", {"id": machine_id,"nome": nome.strip(),"status": status,"agora": datetime.now()})

def delete_machine(machine_id):
    refs = fetch_df("SELECT COUNT(*) AS total FROM service_orders WHERE machine_id=:id", {"id": machine_id})
    if not refs.empty and int(refs.iloc[0]["total"]) > 0:
        raise ValueError("Esta máquina possui ordens vinculadas e não pode ser excluída.")
    execute("DELETE FROM machines WHERE id=:id", {"id": machine_id})

def get_employees(): return fetch_df("SELECT id,nome,setor,funcao,criado_em,atualizado_em FROM employees ORDER BY nome")
def create_employee(nome, setor, funcao): execute("INSERT INTO employees (nome,setor,funcao,criado_em,atualizado_em) VALUES (:nome,:setor,:funcao,:criado_em,:atualizado_em)", {"nome": nome.strip(),"setor": setor.strip(),"funcao": funcao.strip(),"criado_em": datetime.now(),"atualizado_em": datetime.now()})
def update_employee(emp_id, nome, setor, funcao): execute("UPDATE employees SET nome=:nome,setor=:setor,funcao=:funcao,atualizado_em=:agora WHERE id=:id", {"id": emp_id,"nome": nome.strip(),"setor": setor.strip(),"funcao": funcao.strip(),"agora": datetime.now()})

def delete_employee(emp_id):
    refs = fetch_df("SELECT COUNT(*) AS total FROM service_order_employees WHERE employee_id=:id", {"id": emp_id})
    if not refs.empty and int(refs.iloc[0]["total"]) > 0:
        raise ValueError("Este funcionário possui apontamentos em ordens e não pode ser excluído.")
    execute("DELETE FROM employees WHERE id=:id", {"id": emp_id})

def get_orders(tipo):
    return fetch_df("SELECT so.id,so.tipo,so.opened_by,m.nome AS maquina,so.machine_id,so.start_datetime,so.end_datetime,so.problem_description,so.status,so.solution_description,so.created_at,so.updated_at FROM service_orders so INNER JOIN machines m ON m.id=so.machine_id WHERE so.tipo=:tipo ORDER BY so.id DESC", {"tipo": tipo})
def get_orders_filtered(tipo, machine_id=None, status=None, date_from=None, date_to=None):
    params = {"tipo": tipo}
    sql = "SELECT so.id,so.tipo,so.opened_by,m.nome AS maquina,so.machine_id,so.start_datetime,so.end_datetime,so.problem_description,so.status,so.solution_description,so.created_at,so.updated_at FROM service_orders so INNER JOIN machines m ON m.id=so.machine_id WHERE so.tipo=:tipo"
    if machine_id is not None: sql += " AND so.machine_id=:machine_id"; params["machine_id"] = machine_id
    if status and status != "TODOS": sql += " AND so.status=:status"; params["status"] = status
    if date_from is not None: sql += " AND so.start_datetime>=:date_from"; params["date_from"] = f"{date_from} 00:00:00"
    if date_to is not None: sql += " AND so.start_datetime<=:date_to"; params["date_to"] = f"{date_to} 23:59:59"
    sql += " ORDER BY so.id DESC"
    return fetch_df(sql, params)
def create_order(tipo, opened_by, machine_id, start_dt, end_dt, problem_description, status, solution_description):
    execute("INSERT INTO service_orders (tipo,opened_by,machine_id,start_datetime,end_datetime,problem_description,status,solution_description,created_at,updated_at) VALUES (:tipo,:opened_by,:machine_id,:start_datetime,:end_datetime,:problem_description,:status,:solution_description,:created_at,:updated_at)",
            {"tipo": tipo,"opened_by": opened_by,"machine_id": machine_id,"start_datetime": start_dt,"end_datetime": end_dt,"problem_description": problem_description.strip(),"status": status,"solution_description": solution_description.strip(),"created_at": datetime.now(),"updated_at": datetime.now()})
def update_order(order_id, machine_id, start_dt, end_dt, problem_description, status, solution_description):
    execute("UPDATE service_orders SET machine_id=:machine_id,start_datetime=:start_datetime,end_datetime=:end_datetime,problem_description=:problem_description,status=:status,solution_description=:solution_description,updated_at=:updated_at WHERE id=:id",
            {"id": order_id,"machine_id": machine_id,"start_datetime": start_dt,"end_datetime": end_dt,"problem_description": problem_description.strip(),"status": status,"solution_description": solution_description.strip(),"updated_at": datetime.now()})
def close_order(order_id, solution_description, end_dt):
    execute("UPDATE service_orders SET status='Finalizada',solution_description=:solution_description,end_datetime=:end_datetime,updated_at=:updated_at WHERE id=:id",
            {"id": order_id,"solution_description": solution_description.strip(),"end_datetime": end_dt,"updated_at": datetime.now()})
def get_order_employees(order_id):
    return fetch_df("SELECT oe.id,e.id AS funcionario_id,e.nome,e.setor,e.funcao,oe.start_datetime,oe.end_datetime FROM service_order_employees oe INNER JOIN employees e ON e.id=oe.employee_id WHERE oe.order_id=:order_id ORDER BY oe.id DESC", {"order_id": order_id})
def add_employee_to_order(order_id, employee_id, start_dt, end_dt):
    execute("INSERT INTO service_order_employees (order_id,employee_id,start_datetime,end_datetime,created_at) VALUES (:order_id,:employee_id,:start_datetime,:end_datetime,:created_at)",
            {"order_id": order_id,"employee_id": employee_id,"start_datetime": start_dt,"end_datetime": end_dt,"created_at": datetime.now()})
def get_order_parts(order_id):
    return fetch_df("SELECT op.id,p.id AS peca_id,p.nome,op.quantidade,p.unidade FROM service_order_parts op INNER JOIN products p ON p.id=op.product_id WHERE op.order_id=:order_id ORDER BY op.id DESC", {"order_id": order_id})
def add_part_to_order(order_id, product_id, quantidade, usuario_lancamento):
    quantidade = float(quantidade)
    with get_engine().begin() as conn:
        produto = conn.execute(text("SELECT id,estoque_atual FROM products WHERE id=:id FOR UPDATE"), {"id": product_id}).mappings().first()
        novo = float(produto["estoque_atual"]) - quantidade
        if novo < 0: raise ValueError("Estoque insuficiente para lançar esta peça.")
        conn.execute(text("UPDATE products SET estoque_atual=:estoque, atualizado_em=:agora WHERE id=:id"), {"estoque": novo,"agora": datetime.now(),"id": product_id})
        conn.execute(text("INSERT INTO service_order_parts (order_id,product_id,quantidade,created_at) VALUES (:order_id,:product_id,:quantidade,:created_at)"), {"order_id": order_id,"product_id": product_id,"quantidade": quantidade,"created_at": datetime.now()})
        conn.execute(text("INSERT INTO movements (produto_id,tipo,quantidade,observacao,usuario_lancamento,criado_em) VALUES (:produto_id,'SAIDA',:quantidade,:observacao,:usuario_lancamento,:criado_em)"),
                     {"produto_id": product_id,"quantidade": quantidade,"observacao": f"Peça utilizada na ordem {order_id}","usuario_lancamento": usuario_lancamento,"criado_em": datetime.now()})

if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user" not in st.session_state: st.session_state.user = None
def logout(): st.session_state.logged_in = False; st.session_state.user = None; st.rerun()

init_db()
if count_users() == 0:
    app_header("Primeira configuração", "Crie o primeiro usuário administrador.")
    with st.form("form_primeiro_admin"):
        c1,c2 = st.columns(2); nome = c1.text_input("Nome"); usuario = c2.text_input("Usuário")
        c3,c4 = st.columns(2); email = c3.text_input("E-mail"); senha = c4.text_input("Senha", type="password")
        if st.form_submit_button("Criar administrador", use_container_width=True):
            create_user(nome, usuario, email, "Administrador", senha, True); st.success("Administrador criado."); st.rerun()
    st.stop()
if not st.session_state.logged_in:
    app_header("Acesso ao sistema", APP_SUBTITLE)
    c1,c2,c3 = st.columns([1,1.1,1])
    with c2:
        st.markdown('<div class="login-wrap">', unsafe_allow_html=True)
        with st.form("login"):
            usuario = st.text_input("Usuário"); senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                u = authenticate_user(usuario, senha)
                if u: st.session_state.logged_in = True; st.session_state.user = u; st.rerun()
                else: st.error("Usuário ou senha inválidos.")
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

user = st.session_state.user
products_df = get_products(); users_df = get_users(); machines_df = get_machines(); employees_df = get_employees(); criticos_df = get_critical_products(); os_df = get_orders("CORRETIVA"); pm_df = get_orders("PREVENTIVA")

with st.sidebar:
    if logo_b64: 
        st.markdown(f'<div class="sidebar-brand"><div style="text-align:center;font-weight:800;">{APP_NAME}</div><div class="small-muted" style="text-align:center;">{APP_SUBTITLE}</div></div>', unsafe_allow_html=True)
    st.markdown(f"**{user['nome']}**"); st.caption(f"Perfil: {user['perfil']} | {user['usuario']}")
    if st.button("Sair", use_container_width=True): logout()
    menu = st.radio("Menu", ["Dashboard","Produtos / Estoque","Máquinas","Funcionários","Usuários","Ordem de serviço","Ordem de preventiva","Relatórios"])

app_header("Sistema de controle de estoque e manutenção", "Estoque + máquinas + OS + preventivas + funcionários")

if menu == "Dashboard":
    c1,c2,c3,c4 = st.columns(4); c1.metric("Produtos", len(products_df)); c2.metric("Máquinas", len(machines_df)); c3.metric("Funcionários", len(employees_df)); c4.metric("OS abertas", len(os_df[os_df["status"].isin(["Aberta","Em andamento"])]))
    c5,c6,c7,c8 = st.columns(4); c5.metric("Preventivas abertas", len(pm_df[pm_df["status"].isin(["Aberta","Em andamento"])])); c6.metric("Itens críticos", len(criticos_df)); c7.metric("Usuários", len(users_df)); c8.metric("Saldo total estoque", format_number(products_df["estoque_atual"].sum() if not products_df.empty else 0))
    if not criticos_df.empty:
        st.subheader("Itens críticos"); st.dataframe(criticos_df.rename(columns={"id":"ID","nome":"Produto","unidade":"Unidade","estoque_atual":"Estoque atual","estoque_minimo":"Estoque mínimo","falta_para_minimo":"Falta para mínimo"}), use_container_width=True, hide_index=True)

elif menu == "Produtos / Estoque":
    st.subheader("Produtos / Estoque")
    t1,t2,t3,t4 = st.tabs(["Novo produto","Editar / Excluir","Entrada/Saída","Histórico"])
    with t1:
        with st.form("novo_produto", clear_on_submit=True):
            c1,c2,c3 = st.columns(3); nome = c1.text_input("Nome"); unidade = c2.selectbox("Unidade", ["UN","KG","PC","M","L"]); estoque_inicial = c3.number_input("Estoque inicial", min_value=0.0, value=0.0)
            c4,c5 = st.columns([1,2]); estoque_minimo = c4.number_input("Estoque mínimo", min_value=0.0, value=0.0); descricao = c5.text_area("Descrição")
            if st.form_submit_button("Salvar produto", use_container_width=True): create_product(nome, descricao, unidade, estoque_inicial, estoque_minimo); st.success("Produto cadastrado."); st.rerun()
    with t2:
        if products_df.empty:
            st.info("Nenhum produto cadastrado.")
        else:
            prod_map = {f"ID {int(r['id'])} - {r['nome']}": r for _,r in products_df.iterrows()}
            sel = st.selectbox("Editar produto", list(prod_map.keys()))
            row = prod_map[sel]
            with st.form("editar_produto"):
                c1,c2 = st.columns(2)
                nome = c1.text_input("Nome", value=str(row["nome"]))
                unidades = ["UN","KG","PC","M","L"]
                unidade = c2.selectbox("Unidade", unidades, index=unidades.index(row["unidade"]) if row["unidade"] in unidades else 0)
                c3,c4 = st.columns(2)
                c3.number_input("Estoque atual", value=float(row["estoque_atual"]), disabled=True)
                estoque_minimo = c4.number_input("Estoque mínimo", min_value=0.0, value=float(row["estoque_minimo"]))
                descricao = st.text_area("Descrição", value="" if pd.isna(row["descricao"]) else str(row["descricao"]))
                b1,b2 = st.columns(2)
                atualizar = b1.form_submit_button("Atualizar produto", use_container_width=True)
                excluir = b2.form_submit_button("Excluir produto", use_container_width=True)
                if atualizar:
                    update_product(int(row["id"]), nome, descricao, unidade, estoque_minimo)
                    st.success("Produto atualizado.")
                    st.rerun()
                if excluir:
                    try:
                        delete_product(int(row["id"]))
                        st.success("Produto excluído.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            st.dataframe(products_df.rename(columns={"id":"ID","nome":"Produto","descricao":"Descrição","unidade":"Unidade","estoque_atual":"Estoque atual","estoque_minimo":"Estoque mínimo"}), use_container_width=True, hide_index=True)
    with t3:
        if products_df.empty: st.info("Cadastre produtos primeiro.")
        else:
            with st.form("mov_estoque", clear_on_submit=True):
                produto_map = {f"ID {int(r['id'])} - {r['nome']} | saldo: {r['estoque_atual']} {r['unidade']}": int(r["id"]) for _,r in products_df.iterrows()}
                produto = st.selectbox("Produto", list(produto_map.keys())); tipo = st.selectbox("Tipo", ["ENTRADA","SAIDA"]); quantidade = st.number_input("Quantidade", min_value=0.01, value=1.0); observacao = st.text_input("Observação")
                if st.form_submit_button("Lançar", use_container_width=True): register_stock_movement(produto_map[produto], tipo, quantidade, observacao, user["usuario"]); st.success("Movimentação registrada."); st.rerun()
    with t4:
        mov_df = get_movements()
        if not mov_df.empty: st.dataframe(mov_df.rename(columns={"id":"ID","produto_id":"ID produto","produto":"Produto","tipo":"Tipo","quantidade":"Quantidade","unidade":"Unidade","usuario_lancamento":"Usuário","observacao":"Observação","criado_em":"Data/hora"}), use_container_width=True, hide_index=True)

elif menu == "Máquinas":
    st.subheader("Máquinas")
    t1,t2 = st.tabs(["Nova / Editar","Consulta"])
    with t1:
        with st.form("nova_maquina", clear_on_submit=True):
            c1,c2 = st.columns(2); nome = c1.text_input("Nome da máquina"); status = c2.selectbox("Status", ["Ativa","Parada","Em manutenção","Inativa"])
            if st.form_submit_button("Salvar máquina", use_container_width=True): create_machine(nome, status); st.success("Máquina cadastrada."); st.rerun()
        if not machines_df.empty:
            maq_map = {f"ID {int(r['id'])} - {r['nome']}": r for _,r in machines_df.iterrows()}
            sel = st.selectbox("Editar máquina", list(maq_map.keys())); row = maq_map[sel]
            with st.form("editar_maquina"):
                nome = st.text_input("Nome", value=str(row["nome"])); opts = ["Ativa","Parada","Em manutenção","Inativa"]; status = st.selectbox("Status", opts, index=opts.index(row["status"]) if row["status"] in opts else 0)
                b1,b2 = st.columns(2)
                atualizar = b1.form_submit_button("Atualizar máquina", use_container_width=True)
                excluir = b2.form_submit_button("Excluir máquina", use_container_width=True)
                if atualizar: update_machine(int(row["id"]), nome, status); st.success("Máquina atualizada."); st.rerun()
                if excluir:
                    try:
                        delete_machine(int(row["id"]))
                        st.success("Máquina excluída.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    with t2: st.dataframe(machines_df.rename(columns={"id":"ID","nome":"Máquina","status":"Status"}), use_container_width=True, hide_index=True)

elif menu == "Funcionários":
    st.subheader("Funcionários")
    t1,t2 = st.tabs(["Novo / Editar","Consulta"])
    with t1:
        with st.form("novo_funcionario", clear_on_submit=True):
            c1,c2,c3 = st.columns(3); nome = c1.text_input("Nome"); setor = c2.text_input("Setor"); funcao = c3.text_input("Função")
            if st.form_submit_button("Salvar funcionário", use_container_width=True): create_employee(nome, setor, funcao); st.success("Funcionário cadastrado."); st.rerun()
        if not employees_df.empty:
            emp_map = {f"ID {int(r['id'])} - {r['nome']}": r for _,r in employees_df.iterrows()}
            sel = st.selectbox("Editar funcionário", list(emp_map.keys())); row = emp_map[sel]
            with st.form("editar_funcionario"):
                c1,c2,c3 = st.columns(3); nome = c1.text_input("Nome", value=str(row["nome"])); setor = c2.text_input("Setor", value="" if pd.isna(row["setor"]) else str(row["setor"])); funcao = c3.text_input("Função", value="" if pd.isna(row["funcao"]) else str(row["funcao"]))
                b1,b2 = st.columns(2)
                atualizar = b1.form_submit_button("Atualizar funcionário", use_container_width=True)
                excluir = b2.form_submit_button("Excluir funcionário", use_container_width=True)
                if atualizar: update_employee(int(row["id"]), nome, setor, funcao); st.success("Funcionário atualizado."); st.rerun()
                if excluir:
                    try:
                        delete_employee(int(row["id"]))
                        st.success("Funcionário excluído.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
    with t2: st.dataframe(employees_df.rename(columns={"id":"ID","nome":"Nome","setor":"Setor","funcao":"Função"}), use_container_width=True, hide_index=True)

def order_page(tipo, titulo):
    st.subheader(titulo)
    t1,t2,t3,t4,t5 = st.tabs(["Nova ordem","Editar ordem","Fechamento","Equipe / Peças","Consulta"])
    with t1:
        if machines_df.empty: st.warning("Cadastre máquinas antes de abrir ordens.")
        else:
            with st.form(f"nova_ordem_{tipo}", clear_on_submit=True):
                maq_map = {f"ID {int(r['id'])} - {r['nome']}": int(r["id"]) for _,r in machines_df.iterrows()}
                maquina = st.selectbox("Máquina", list(maq_map.keys()))
                c1,c2 = st.columns(2); data_inicio = c1.date_input("Data início", value=date.today(), key=f"di_{tipo}"); hora_inicio = c2.time_input("Hora início", key=f"hi_{tipo}")
                c3,c4 = st.columns(2); data_fim = c3.date_input("Data fim", value=date.today(), key=f"df_{tipo}"); hora_fim = c4.time_input("Hora fim", key=f"hf_{tipo}")
                problema = st.text_area("Descrição do problema"); status = st.selectbox("Status", ["Aberta","Em andamento","Finalizada","Cancelada"], key=f"st_{tipo}"); solucao = st.text_area("Descrição da solução")
                if st.form_submit_button("Salvar ordem", use_container_width=True): create_order(tipo, user["usuario"], maq_map[maquina], combine_date_time(data_inicio, hora_inicio), combine_date_time(data_fim, hora_fim), problema, status, solucao); st.success("Ordem cadastrada."); st.rerun()
    with t2:
        df = get_orders(tipo)
        if not df.empty:
            ord_map = {f"Ordem {int(r['id'])} - {r['maquina']}": r for _,r in df.iterrows()}
            sel = st.selectbox("Selecione a ordem", list(ord_map.keys()), key=f"ed_{tipo}"); row = ord_map[sel]
            maq_map = {f"ID {int(r['id'])} - {r['nome']}": int(r["id"]) for _,r in machines_df.iterrows()}
            machine_label = next((k for k,v in maq_map.items() if v == int(row["machine_id"])), list(maq_map.keys())[0])
            with st.form(f"editar_ordem_{tipo}"):
                maquina = st.selectbox("Máquina", list(maq_map.keys()), index=list(maq_map.keys()).index(machine_label))
                start_dt = pd.to_datetime(row["start_datetime"]); end_dt = pd.to_datetime(row["end_datetime"]) if pd.notna(row["end_datetime"]) else pd.Timestamp.now()
                c1,c2 = st.columns(2); data_inicio = c1.date_input("Data início", value=start_dt.date(), key=f"edi_{tipo}_1"); hora_inicio = c2.time_input("Hora início", value=start_dt.time(), key=f"edi_{tipo}_2")
                c3,c4 = st.columns(2); data_fim = c3.date_input("Data fim", value=end_dt.date(), key=f"edi_{tipo}_3"); hora_fim = c4.time_input("Hora fim", value=end_dt.time(), key=f"edi_{tipo}_4")
                problema = st.text_area("Descrição do problema", value="" if pd.isna(row["problem_description"]) else str(row["problem_description"]))
                status_opts = ["Aberta","Em andamento","Finalizada","Cancelada"]; status = st.selectbox("Status", status_opts, index=status_opts.index(row["status"]) if row["status"] in status_opts else 0, key=f"edi_{tipo}_5")
                solucao = st.text_area("Descrição da solução", value="" if pd.isna(row["solution_description"]) else str(row["solution_description"]))
                if st.form_submit_button("Atualizar ordem", use_container_width=True): update_order(int(row["id"]), maq_map[maquina], combine_date_time(data_inicio, hora_inicio), combine_date_time(data_fim, hora_fim), problema, status, solucao); st.success("Ordem atualizada."); st.rerun()
    with t3:
        df_close = get_orders_filtered(tipo, status="TODOS")
        if not df_close.empty:
            df_close = df_close[df_close["status"].isin(["Aberta","Em andamento"])]
        if df_close.empty: st.info("Nenhuma ordem aberta ou em andamento para fechamento.")
        else:
            ord_map = {f"Ordem {int(r['id'])} - {r['maquina']} - {r['status']}": r for _,r in df_close.iterrows()}
            sel = st.selectbox("Selecione a ordem para fechar", list(ord_map.keys()), key=f"close_{tipo}"); row = ord_map[sel]
            with st.form(f"fechar_ordem_{tipo}"):
                c1,c2 = st.columns(2); data_fim = c1.date_input("Data final", value=date.today(), key=f"fech_df_{tipo}"); hora_fim = c2.time_input("Hora final", key=f"fech_hf_{tipo}")
                solucao = st.text_area("Descrição final da solução", value="" if pd.isna(row["solution_description"]) else str(row["solution_description"]))
                if st.form_submit_button("Fechar ordem", use_container_width=True): close_order(int(row["id"]), solucao, combine_date_time(data_fim, hora_fim)); st.success("Ordem finalizada com sucesso."); st.rerun()
    with t4:
        df = get_orders(tipo)
        if not df.empty:
            ord_map = {f"Ordem {int(r['id'])} - {r['maquina']}": int(r["id"]) for _,r in df.iterrows()}
            order_label = st.selectbox("Ordem", list(ord_map.keys()), key=f"ges_{tipo}"); order_id = ord_map[order_label]
            ca,cb = st.columns(2)
            with ca:
                st.markdown("### Funcionários")
                if not employees_df.empty:
                    with st.form(f"func_ordem_{tipo}", clear_on_submit=True):
                        emp_map = {f"ID {int(r['id'])} - {r['nome']}": int(r["id"]) for _,r in employees_df.iterrows()}
                        emp = st.selectbox("Funcionário", list(emp_map.keys()), key=f"emp_{tipo}")
                        c1,c2 = st.columns(2); di = c1.date_input("Data início", value=date.today(), key=f"empdi_{tipo}"); hi = c2.time_input("Hora início", key=f"emphi_{tipo}")
                        c3,c4 = st.columns(2); dfim = c3.date_input("Data fim", value=date.today(), key=f"empdf_{tipo}"); hfim = c4.time_input("Hora fim", key=f"emphf_{tipo}")
                        if st.form_submit_button("Adicionar funcionário", use_container_width=True): add_employee_to_order(order_id, emp_map[emp], combine_date_time(di, hi), combine_date_time(dfim, hfim)); st.success("Funcionário vinculado."); st.rerun()
                order_emp = get_order_employees(order_id)
                if not order_emp.empty:
                    order_emp["Tempo"] = order_emp.apply(lambda r: format_duration(r["start_datetime"], r["end_datetime"]), axis=1)
                    st.dataframe(order_emp.rename(columns={"id":"ID vínculo","funcionario_id":"ID funcionário","nome":"Nome","setor":"Setor","funcao":"Função","start_datetime":"Início","end_datetime":"Fim"}), use_container_width=True, hide_index=True)
            with cb:
                st.markdown("### Peças utilizadas")
                if not products_df.empty:
                    with st.form(f"peca_ordem_{tipo}", clear_on_submit=True):
                        part_map = {f"ID {int(r['id'])} - {r['nome']} | saldo: {r['estoque_atual']} {r['unidade']}": int(r["id"]) for _,r in products_df.iterrows()}
                        peca = st.selectbox("Peça", list(part_map.keys()), key=f"peca_{tipo}"); quantidade = st.number_input("Quantidade", min_value=0.01, value=1.0, key=f"qtd_{tipo}")
                        if st.form_submit_button("Adicionar peça e baixar estoque", use_container_width=True): add_part_to_order(order_id, part_map[peca], quantidade, user["usuario"]); st.success("Peça lançada na ordem."); st.rerun()
                order_parts = get_order_parts(order_id)
                if not order_parts.empty:
                    st.dataframe(order_parts.rename(columns={"id":"ID vínculo","peca_id":"ID peça","nome":"Peça","quantidade":"Quantidade","unidade":"Unidade"}), use_container_width=True, hide_index=True)
    with t5:
        st.markdown("### Filtros")
        c1,c2,c3,c4 = st.columns(4); machine_id = None
        if not machines_df.empty:
            maq_labels = ["TODAS"] + [f"ID {int(r['id'])} - {r['nome']}" for _,r in machines_df.iterrows()]
            maq_sel = c1.selectbox("Máquina", maq_labels, key=f"fmaq_{tipo}")
            if maq_sel != "TODAS": machine_id = int(maq_sel.split(" - ")[0].replace("ID ",""))
        status = c2.selectbox("Status", ["TODOS","Aberta","Em andamento","Finalizada","Cancelada"], key=f"fstatus_{tipo}")
        d_ini = c3.date_input("De", value=date.today()-timedelta(days=30), key=f"fdi_{tipo}")
        d_fim = c4.date_input("Até", value=date.today(), key=f"fdf_{tipo}")
        df = get_orders_filtered(tipo, machine_id=machine_id, status=status, date_from=d_ini, date_to=d_fim)
        if not df.empty:
            df["Tempo total"] = df.apply(lambda r: format_duration(r["start_datetime"], r["end_datetime"]), axis=1)
            st.dataframe(df.rename(columns={"id":"ID ordem","opened_by":"Aberta por","maquina":"Máquina","start_datetime":"Início","end_datetime":"Fim","problem_description":"Problema","status":"Status","solution_description":"Solução"}), use_container_width=True, hide_index=True)
        else: st.info("Nenhuma ordem encontrada com os filtros.")

if menu == "Ordem de serviço": order_page("CORRETIVA", "Ordem de serviço")
elif menu == "Ordem de preventiva": order_page("PREVENTIVA", "Ordem de preventiva")
elif menu == "Relatórios":
    st.subheader("Relatórios")
    os_report = get_orders_filtered("CORRETIVA"); pm_report = get_orders_filtered("PREVENTIVA")
    if not os_report.empty: os_report["Tempo total"] = os_report.apply(lambda r: format_duration(r["start_datetime"], r["end_datetime"]), axis=1)
    if not pm_report.empty: pm_report["Tempo total"] = pm_report.apply(lambda r: format_duration(r["start_datetime"], r["end_datetime"]), axis=1)
    excel = df_to_excel_bytes({"Produtos": products_df.rename(columns={"id":"ID","nome":"Produto"}),"Maquinas": machines_df.rename(columns={"id":"ID","nome":"Máquina"}),"Funcionarios": employees_df.rename(columns={"id":"ID","nome":"Nome"}),"OS": os_report.rename(columns={"id":"ID ordem","maquina":"Máquina"}),"Preventivas": pm_report.rename(columns={"id":"ID ordem","maquina":"Máquina"})})
    st.download_button("Baixar relatório geral.xlsx", data=excel, file_name="relatorio_geral_stockpro.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

# TRECHO PARA RESTAURAR USUÁRIOS (cole no seu app.py)

elif menu == "Usuários":
    st.subheader("Usuários")

    t1, t2 = st.tabs(["Novo usuário", "Editar / Excluir"])

    with t1:
        with st.form("novo_usuario", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome")
            usuario = c2.text_input("Usuário")

            c3, c4 = st.columns(2)
            email = c3.text_input("E-mail")
            senha = c4.text_input("Senha", type="password")

            perfil = st.selectbox("Perfil", ["Administrador", "Usuário"])

            if st.form_submit_button("Criar usuário", use_container_width=True):
                create_user(nome, usuario, email, perfil, senha, True)
                st.success("Usuário criado com sucesso")
                st.rerun()

    with t2:
        users_df = get_users()

        if users_df.empty:
            st.info("Nenhum usuário cadastrado")
        else:
            user_map = {
                f"ID {int(r['id'])} - {r['nome']} ({r['usuario']})": r
                for _, r in users_df.iterrows()
            }

            selected = st.selectbox("Selecionar usuário", list(user_map.keys()))
            row = user_map[selected]

            with st.form("editar_usuario"):
                c1, c2 = st.columns(2)
                nome = c1.text_input("Nome", value=row["nome"])
                usuario = c2.text_input("Usuário", value=row["usuario"])

                c3, c4 = st.columns(2)
                email = c3.text_input("E-mail", value=row["email"])
                senha = c4.text_input("Nova senha (opcional)", type="password")

                perfil = st.selectbox(
                    "Perfil",
                    ["Administrador", "Usuário"],
                    index=0 if row["perfil"] == "Administrador" else 1,
                )

                ativo = st.checkbox("Ativo", value=bool(row["ativo"]))

                col1, col2 = st.columns(2)

                with col1:
                    if st.form_submit_button("Atualizar usuário", use_container_width=True):
                        query = """
                        UPDATE users
                        SET nome=:nome,
                            usuario=:usuario,
                            email=:email,
                            perfil=:perfil,
                            ativo=:ativo,
                            atualizado_em=:agora
                        WHERE id=:id
                        """

                        params = {
                            "id": int(row["id"]),
                            "nome": nome,
                            "usuario": usuario,
                            "email": email,
                            "perfil": perfil,
                            "ativo": 1 if ativo else 0,
                            "agora": __import__("datetime").datetime.now(),
                        }

                        execute(query, params)

                        if senha:
                            execute(
                                "UPDATE users SET senha_hash=:senha WHERE id=:id",
                                {
                                    "id": int(row["id"]),
                                    "senha": __import__("hashlib").sha256(senha.encode()).hexdigest(),
                                },
                            )

                        st.success("Usuário atualizado")
                        st.rerun()

                with col2:
                    if st.form_submit_button("Excluir usuário", use_container_width=True):
                        if int(row["id"]) == 1:
                            st.error("Não é permitido excluir o usuário administrador principal")
                        else:
                            execute("DELETE FROM users WHERE id=:id", {"id": int(row["id"])})
                            st.success("Usuário excluído")
                            st.rerun()
