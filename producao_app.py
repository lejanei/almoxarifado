from datetime import date, datetime
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

DEFAULT_DB_URL = "mysql+pymysql://ljsyst02_adm:vinimalu121924@ljsystem.com.br/ljsyst02_almoxarifado?charset=utf8mb4"
DB_URL = DEFAULT_DB_URL
engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=280, future=True)
APP_TIMEZONE = ZoneInfo("America/Sao_Paulo")

STATUS_OPCOES = ["PROGRAMADO", "PRODUZIDO", "REJEITADO"]
TURNOS_PADRAO = ["1º Turno", "2º Turno", "3º Turno", "Turno A", "Turno B", "Turno C"]


def set_database_url(db_url: str):
    """Atualiza a conexão do módulo Produção conforme a planta escolhida."""
    global DB_URL, engine
    if db_url and str(db_url) != str(DB_URL):
        DB_URL = str(db_url)
        try:
            engine.dispose()
        except Exception:
            pass
        engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=280, future=True)


def agora_br():
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


def executar(sql, params=None):
    with engine.begin() as conn:
        return conn.execute(text(sql), params or {})


def carregar_df(sql, params=None):
    with engine.begin() as conn:
        return pd.read_sql_query(text(sql), conn, params=params or {})


def buscar_um(sql, params=None):
    with engine.begin() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
        return dict(row) if row else None


def criar_tabelas_producao():
    executar(
        """
        CREATE TABLE IF NOT EXISTS producao_produtos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            codigo VARCHAR(50),
            nome VARCHAR(150) NOT NULL,
            unidade VARCHAR(20) DEFAULT 'KG',
            peso_padrao DECIMAL(12,3) DEFAULT 0,
            ativo TINYINT(1) DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_prod_produtos_nome (nome),
            INDEX idx_prod_produtos_codigo (codigo)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    executar(
        """
        CREATE TABLE IF NOT EXISTS producao_pallets (
            id INT AUTO_INCREMENT PRIMARY KEY,
            maquina_id INT NULL,
            produto_producao_id INT NULL,
            turno VARCHAR(50),
            lote VARCHAR(100),
            data_producao DATE,
            kg DECIMAL(12,3) NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'PROGRAMADO',
            codigo_barras VARCHAR(100) NOT NULL UNIQUE,
            data_leitura DATETIME NULL,
            observacao TEXT NULL,
            criado_por VARCHAR(150),
            produzido_por VARCHAR(150),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NULL,
            INDEX idx_prod_data (data_producao),
            INDEX idx_prod_status (status),
            INDEX idx_prod_maquina (maquina_id),
            INDEX idx_prod_produto_producao (produto_producao_id),
            INDEX idx_prod_codigo (codigo_barras)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    
    )
    try:
        executar("ALTER TABLE producao_pallets ADD COLUMN produto_producao_id INT NULL")
    except Exception:
        pass

    try:
        executar("UPDATE producao_pallets SET produto_producao_id = produto_id WHERE produto_producao_id IS NULL")
    except Exception:
        pass
    
    executar(
        """
        CREATE TABLE IF NOT EXISTS producao_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            pallet_id INT NOT NULL,
            codigo_barras VARCHAR(100) NOT NULL,
            evento VARCHAR(80) NOT NULL,
            status_anterior VARCHAR(30) NULL,
            status_novo VARCHAR(30) NULL,
            usuario VARCHAR(150),
            observacao TEXT NULL,
            created_at DATETIME NOT NULL,
            INDEX idx_prod_logs_pallet (pallet_id),
            INDEX idx_prod_logs_codigo (codigo_barras),
            CONSTRAINT fk_prod_logs_pallet FOREIGN KEY (pallet_id) REFERENCES producao_pallets(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def registrar_log(pallet_id, codigo_barras, evento, status_anterior, status_novo, usuario, observacao=""):
    try:
        executar(
            """
            INSERT INTO producao_logs
                (pallet_id, codigo_barras, evento, status_anterior, status_novo, usuario, observacao, created_at)
            VALUES
                (:pallet_id, :codigo_barras, :evento, :status_anterior, :status_novo, :usuario, :observacao, :created_at)
            """,
            {
                "pallet_id": pallet_id,
                "codigo_barras": codigo_barras,
                "evento": evento,
                "status_anterior": status_anterior,
                "status_novo": status_novo,
                "usuario": usuario,
                "observacao": observacao,
                "created_at": agora_br(),
            },
        )
    except Exception:
        pass


def format_number(v):
    try:
        return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0,00"


def format_date_br(v):
    if v is None or pd.isna(v):
        return ""
    try:
        return pd.to_datetime(v).strftime("%d/%m/%Y")
    except Exception:
        return str(v)


def format_datetime_br(v):
    if v is None or pd.isna(v):
        return ""
    try:
        return pd.to_datetime(v).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(v)


def carregar_maquinas():
    try:
        return carregar_df("SELECT id, nome FROM machines ORDER BY nome")
    except Exception:
        return pd.DataFrame(columns=["id", "nome"])


def carregar_produtos_producao():
    try:
        return carregar_df("""
        SELECT
        id,
        codigo,
        nome,
        unidade,
        peso_padrao
        FROM producao_produtos
        WHERE ativo=1
        ORDER BY nome
        """)
    except:
        return pd.DataFrame(
            columns=[
                "id",
                "codigo",
                "nome",
                "unidade",
                "peso_padrao"
            ]
        )

def carregar_pallets(filtros=None):

    filtros = filtros or {}

    where=[]

    params={}

    if filtros.get("data_ini"):
        where.append("p.data_producao>=:data_ini")
        params["data_ini"]=filtros["data_ini"]

    if filtros.get("data_fim"):
        where.append("p.data_producao<=:data_fim")
        params["data_fim"]=filtros["data_fim"]

    if filtros.get("maquina_id"):
        where.append("p.maquina_id=:maquina_id")
        params["maquina_id"]=filtros["maquina_id"]

    if filtros.get("produto_id"):
        where.append("p.produto_producao_id=:produto_id")
        params["produto_id"]=filtros["produto_id"]

    if filtros.get("status") and filtros["status"]!="TODOS":
        where.append("p.status=:status")
        params["status"]=filtros["status"]

    if filtros.get("lote"):
        where.append("p.lote LIKE :lote")
        params["lote"]="%"+filtros["lote"]+"%"

    where_sql=""

    if where:
        where_sql="WHERE "+" AND ".join(where)

    return carregar_df(f"""
    SELECT
    p.id,
    p.codigo_barras,
    p.data_producao,
    m.nome maquina,
    pr.nome produto,
    pr.codigo codigo_produto,
    p.turno,
    p.lote,
    p.kg,
    p.status,
    p.data_leitura,
    p.criado_por,
    p.produzido_por,
    p.observacao,
    p.created_at,
    p.updated_at
    FROM producao_pallets p
    LEFT JOIN machines m
    ON m.id=p.maquina_id
    LEFT JOIN producao_produtos pr
    ON pr.id=p.produto_producao_id
    """+where_sql+"""
    ORDER BY
    p.data_producao DESC,
    p.id DESC
    LIMIT 1000
    """,params)

def normalizar_codigo_pallet(codigo):
    return str(codigo or "").strip().upper()

def gerar_codigo_pallet():
    row = buscar_um("""
        SELECT MAX(id) AS ultimo_id
        FROM producao_pallets
    """)
    ultimo = int(row["ultimo_id"] or 0) if row else 0
    proximo = ultimo + 1
    return f"PAL-{proximo:06d}"

def criar_programacao(maquina_id, produto_producao_id, turno, lote, data_producao, kg, codigo_barras, usuario, observacao=""):
    agora = agora_br()
    codigo = normalizar_codigo_pallet(codigo_barras)
    result = executar(
        """
        INSERT INTO producao_pallets
            (maquina_id, produto_producao_id, turno, lote, data_producao, kg, status, codigo_barras, observacao, criado_por, created_at)
        VALUES
            (:maquina_id, :produto_producao_id, :turno, :lote, :data_producao, :kg, 'PROGRAMADO', :codigo_barras, :observacao, :criado_por, :created_at)
        """,
        {
            "maquina_id": maquina_id,
            "produto_producao_id": produto_producao_id,
            "turno": turno,
            "lote": lote,
            "data_producao": data_producao,
            "kg": kg,
            "codigo_barras": codigo,
            "observacao": observacao,
            "criado_por": usuario,
            "created_at": agora,
        },
    )
    producao_id = result.lastrowid
    registrar_log(producao_id, codigo, "PROGRAMACAO_CRIADA", None, "PROGRAMADO", usuario, observacao)
    return producao_id, codigo


def marcar_produzido(codigo_barras, usuario):
    codigo = normalizar_codigo_pallet(codigo_barras)
    if not codigo:
        return False, "Informe ou leia o código da etiqueta."

    pallet = buscar_um("SELECT * FROM producao_pallets WHERE UPPER(codigo_barras)=:codigo LIMIT 1", {"codigo": codigo})
    if not pallet:
        return False, f"Etiqueta {codigo} não encontrada."

    if str(pallet.get("status", "")).upper() == "PRODUZIDO":
        return False, f"Etiqueta {codigo} já estava marcada como PRODUZIDA em {format_datetime_br(pallet.get('data_leitura'))}."

    agora = agora_br()
    status_anterior = str(pallet.get("status") or "")
    executar(
        """
        UPDATE producao_pallets
        SET status='PRODUZIDO', data_leitura=:data_leitura, produzido_por=:produzido_por, updated_at=:updated_at
        WHERE id=:id
        """,
        {"data_leitura": agora, "produzido_por": usuario, "updated_at": agora, "id": pallet["id"]},
    )
    registrar_log(pallet["id"], codigo, "PALLET_PRODUZIDO", status_anterior, "PRODUZIDO", usuario, "Leitura de etiqueta")
    return True, f"Pallet {codigo} marcado como PRODUZIDO."


def atualizar_status_manual(producao_id, status, observacao, usuario):
    pallet = buscar_um("SELECT id, codigo_barras, status FROM producao_pallets WHERE id=:id", {"id": producao_id})
    status_anterior = str(pallet.get("status") or "") if pallet else None
    codigo = str(pallet.get("codigo_barras") or "") if pallet else ""
    campos = {
        "status": status,
        "observacao": observacao,
        "updated_at": agora_br(),
        "id": producao_id,
    }
    extra = ""
    if status == "PRODUZIDO":
        extra = ", data_leitura=COALESCE(data_leitura, :data_leitura), produzido_por=COALESCE(produzido_por, :produzido_por)"
        campos["data_leitura"] = agora_br()
        campos["produzido_por"] = usuario

    executar(
        f"UPDATE producao_pallets SET status=:status, observacao=:observacao, updated_at=:updated_at {extra} WHERE id=:id",
        campos,
    )
    registrar_log(producao_id, codigo, "STATUS_ALTERADO", status_anterior, status, usuario, observacao)


def etiqueta_html(row, planta_label=""):
    codigo = str(row.get("codigo_barras") or "")
    produto = str(row.get("produto") or "")
    maquina = str(row.get("maquina") or "")
    lote = str(row.get("lote") or "")
    turno = str(row.get("turno") or "")
    kg = format_number(row.get("kg", 0))
    data_txt = format_date_br(row.get("data_producao"))

    barcode_url = f"https://barcode.tec-it.com/barcode.ashx?data={codigo}&code=Code128&translate-esc=true"

    return f"""
<div style="background:white;color:#111;border:2px solid #111;border-radius:12px;padding:18px;width:560px;font-family:Arial,sans-serif;">
    <div style="font-size:12px;font-weight:bold;text-transform:uppercase;letter-spacing:1px;">{planta_label}</div>
    <div style="font-size:26px;font-weight:900;margin:4px 0 10px 0;">ETIQUETA DE PRODUÇÃO</div>

    <table style="width:100%;font-size:16px;border-collapse:collapse;">
        <tr><td style="font-weight:bold;width:120px;">Código:</td><td>{codigo}</td></tr>
        <tr><td style="font-weight:bold;">Produto:</td><td>{produto}</td></tr>
        <tr><td style="font-weight:bold;">Máquina:</td><td>{maquina}</td></tr>
        <tr><td style="font-weight:bold;">Lote:</td><td>{lote}</td></tr>
        <tr><td style="font-weight:bold;">Turno:</td><td>{turno}</td></tr>
        <tr><td style="font-weight:bold;">Data:</td><td>{data_txt}</td></tr>
        <tr><td style="font-weight:bold;">Kg:</td><td>{kg}</td></tr>
    </table>

    <div style="margin-top:16px;text-align:center;border:1px dashed #111;padding:10px;">
        <img src="{barcode_url}" style="height:75px;max-width:100%;" />
        <div style="font-family:Courier New,monospace;font-size:24px;font-weight:900;letter-spacing:2px;margin-top:6px;">{codigo}</div>
        
    </div>
</div>
"""
def tela_produtos():
    st.subheader("Produtos Produzidos")
    with st.form("cad_produto"):
        c1,c2=st.columns(2)
        codigo=c1.text_input("Código")
        nome=c2.text_input("Produto")
        c3,c4=st.columns(2)
        unidade=c3.text_input("Unidade","KG")
        peso=c4.number_input(
            "Peso padrão pallet",
            min_value=0.0,
            step=1.0
        )

        salvar=st.form_submit_button(
            "Salvar",
            use_container_width=True
        )

    if salvar:
        if nome.strip()=="":
            st.error("Informe o produto.")
        else:
            executar("""
            INSERT INTO producao_produtos
            (
            codigo,
            nome,
            unidade,
            peso_padrao,
            ativo
            )
            VALUES
            (
            :codigo,
            :nome,
            :unidade,
            :peso,
            1
            )
            """,{
            "codigo":codigo,
            "nome":nome,
            "unidade":unidade,
            "peso":peso
            })
            st.success("Produto cadastrado.")
            st.rerun()
    st.markdown("### Produtos cadastrados")

    try:
        df=carregar_produtos_producao()
        st.dataframe( 
            df,
            use_container_width=True,
            hide_index=True
        )
    except:
        st.info("Nenhum produto cadastrado.")

def tela_programar(usuario, planta_label):
    st.subheader("Programar produção")
    maquinas = carregar_maquinas()
    produtos = carregar_produtos_producao()

    if maquinas.empty:
        st.warning("Cadastre pelo menos uma máquina antes de programar a produção.")
        return
    if produtos.empty:
        st.warning("Cadastre pelo menos um produto antes de programar a produção.")
        return

    maq_labels = {f"{r['nome']} (ID {int(r['id'])})": int(r["id"]) for _, r in maquinas.iterrows()}
    prod_labels = {f"{r['nome']} (ID {int(r['id'])})": int(r["id"]) for _, r in produtos.iterrows()}

    with st.form("form_producao_programar"):
        c1, c2 = st.columns(2)
        maquina_label = c1.selectbox("Máquina", list(maq_labels.keys()))
        produto_label = c2.selectbox("Produto", list(prod_labels.keys()))
        c3, c4, c5 = st.columns(3)
        turno = c3.selectbox("Turno", TURNOS_PADRAO)
        lote = c4.text_input("Lote")
        data_producao = c5.date_input("Data", value=date.today(), format="DD/MM/YYYY")
        c6, c7 = st.columns([1, 2])
        kg = c6.number_input("Kg", min_value=0.0, step=1.0, format="%.3f")
        codigo_sugerido = gerar_codigo_pallet()
        codigo_barras = c7.text_input("Código do pallet / etiqueta", value=codigo_sugerido)
        observacao = st.text_input("Observação")
        salvar = st.form_submit_button("Programar produção", use_container_width=True)

    if salvar:
        if not lote.strip():
            st.error("Informe o lote.")
            return
        if kg <= 0:
            st.error("Informe o peso em kg.")
            return
        codigo_informado = normalizar_codigo_pallet(codigo_barras)
        if not codigo_informado:
            st.error("Informe o código do pallet que estará na etiqueta.")
            return
        if buscar_um("SELECT id FROM producao_pallets WHERE UPPER(codigo_barras)=:codigo LIMIT 1", {"codigo": codigo_informado}):
            st.error(f"O código {codigo_informado} já existe. Cada pallet precisa ter um código único.")
            return
        producao_id, codigo = criar_programacao(
            maq_labels[maquina_label],
            prod_labels[produto_label],
            turno,
            lote.strip(),
            data_producao,
            kg,
            codigo_informado,
            usuario,
            observacao,
        )
        st.success(f"Produção programada com sucesso. Código do pallet: {codigo}")
        st.session_state["ultima_etiqueta_producao_id"] = producao_id

    ultima_id = st.session_state.get("ultima_etiqueta_producao_id")
    if ultima_id:
        row = buscar_um(
            """
            SELECT
            p.*,
            m.nome AS maquina,
            pr.nome AS produto
            FROM producao_pallets p
            LEFT JOIN machines m
            ON m.id=p.maquina_id
            LEFT JOIN producao_produtos pr
            ON pr.id=p.produto_producao_id
            WHERE p.id=:id
            """,
            {"id": ultima_id},
        )
        if row:
            #st.markdown("#### Prévia da etiqueta")
            # BOTÕES PARA IMPRESSÃO DA ETIQUETA
            botao_imprimir_etiqueta(row, planta_label)

            zpl = gerar_zpl_etiqueta(row, planta_label)

            st.download_button(
                "Baixar ZPL Zebra",
                data=zpl,
                file_name=f"etiqueta_{row.get('codigo_barras', 'pallet')}.zpl",
                mime="text/plain",
                use_container_width=True,
            )
            st.info("Nesta primeira versão o sistema apenas registra o código que já estará na etiqueta impressa por vocês. Não há impressão automática de etiqueta.")


def tela_leitura(usuario):
    st.subheader("Leitura de etiqueta")
    st.info("Clique no campo abaixo e faça a leitura da etiqueta. O leitor normalmente digita o código e pressiona Enter automaticamente.")

    with st.form("form_leitura_etiqueta", clear_on_submit=True):
        codigo = st.text_input("Código da etiqueta", placeholder="Ex: PAL-000001")
        confirmar = st.form_submit_button("Marcar como produzido", use_container_width=True)

    if confirmar:
        ok, msg = marcar_produzido(codigo, usuario)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    st.markdown("#### Últimos pallets produzidos")
    df = carregar_pallets({"status": "PRODUZIDO"})
    if df.empty:
        st.info("Nenhum pallet produzido ainda.")
    else:
        exibir = df[["codigo_barras", "data_producao", "maquina", "produto", "lote", "kg", "data_leitura", "produzido_por"]].head(20).copy()
        exibir["data_producao"] = exibir["data_producao"].apply(format_date_br)
        exibir["data_leitura"] = exibir["data_leitura"].apply(format_datetime_br)
        st.dataframe(exibir, use_container_width=True, hide_index=True)


def tela_consulta(usuario, planta_label):
    st.subheader("Consulta de produção")
    maquinas = carregar_maquinas()
    produtos = carregar_produtos_producao()

    c1, c2, c3, c4 = st.columns(4)
    data_ini = c1.date_input("Data inicial", value=date.today().replace(day=1), format="DD/MM/YYYY")
    data_fim = c2.date_input("Data final", value=date.today(), format="DD/MM/YYYY")
    status = c3.selectbox("Status", ["TODOS"] + STATUS_OPCOES)
    lote = c4.text_input("Lote contém")

    c5, c6 = st.columns(2)
    maq_map = {"Todas": None}
    for _, r in maquinas.iterrows():
        maq_map[f"{r['nome']} (ID {int(r['id'])})"] = int(r["id"])
    prod_map = {"Todos": None}
    for _, r in produtos.iterrows():
        prod_map[f"{r['nome']} (ID {int(r['id'])})"] = int(r["id"])

    maquina_label = c5.selectbox("Máquina", list(maq_map.keys()))
    produto_label = c6.selectbox("Produto", list(prod_map.keys()))

    df = carregar_pallets(
        {
            "data_ini": data_ini,
            "data_fim": data_fim,
            "status": status,
            "lote": lote.strip(),
            "maquina_id": maq_map[maquina_label],
            "produto_id": prod_map[produto_label],
        }
    )

    if df.empty:
        st.info("Nenhum registro encontrado para os filtros selecionados.")
        return

    resumo = df.groupby("status", dropna=False).agg(pallets=("id", "count"), kg=("kg", "sum")).reset_index()
    st.markdown("#### Resumo")
    st.dataframe(resumo, use_container_width=True, hide_index=True)

    exibir = df[["id", "codigo_barras", "data_producao", "maquina", "produto", "turno", "lote", "kg", "status", "data_leitura", "criado_por", "produzido_por", "observacao"]].copy()
    exibir["data_producao"] = exibir["data_producao"].apply(format_date_br)
    exibir["data_leitura"] = exibir["data_leitura"].apply(format_datetime_br)
    st.dataframe(exibir, use_container_width=True, hide_index=True)

    st.markdown("#### Atualizar status / reimprimir etiqueta")
    labels = {f"{r['codigo_barras']} | {r['produto']} | Lote {r['lote']} | {r['status']}": int(r["id"]) for _, r in df.iterrows()}
    selecionado = st.selectbox("Selecione o pallet", list(labels.keys()))
    row = buscar_um(
        """
        SELECT
        p.*,
        m.nome AS maquina,
        pr.nome AS produto
        FROM producao_pallets p
        LEFT JOIN machines m
        ON m.id=p.maquina_id
        LEFT JOIN producao_produtos pr
        ON pr.id=p.produto_producao_id
        WHERE p.id=:id
        """,
        {"id": labels[selecionado]},
    )
    if row:
        c1, c2 = st.columns([1, 2])
        novo_status = c1.selectbox("Novo status", STATUS_OPCOES, index=STATUS_OPCOES.index(row.get("status", "PROGRAMADO")) if row.get("status") in STATUS_OPCOES else 0)
        nova_obs = c2.text_input("Observação", value=str(row.get("observacao") or ""))
        if st.button("Salvar alteração de status", use_container_width=True):
            atualizar_status_manual(row["id"], novo_status, nova_obs, usuario)
            st.success("Status atualizado.")
            st.rerun()
        st.markdown("##### Registro do pallet")
        # BOTÕES PARA IMPRESSÃO DA ETIQUETA
        botao_imprimir_etiqueta(row, planta_label)

        zpl = gerar_zpl_etiqueta(row, planta_label)

        st.download_button(
            "Baixar ZPL Zebra",
            data=zpl,
            file_name=f"etiqueta_{row.get('codigo_barras', 'pallet')}.zpl",
            mime="text/plain",
            use_container_width=True,
        )
        logs = carregar_df(
            "SELECT evento, status_anterior, status_novo, usuario, observacao, created_at FROM producao_logs WHERE pallet_id=:id ORDER BY id DESC",
            {"id": row["id"]},
        )
        if not logs.empty:
            logs["created_at"] = logs["created_at"].apply(format_datetime_br)
            st.markdown("##### Histórico")
            st.dataframe(logs, use_container_width=True, hide_index=True)


def tela_dashboard():
    st.subheader("Dashboard de produção")
    maquinas = carregar_maquinas()
    c1, c2, c3 = st.columns(3)
    data_ini = c1.date_input("Data inicial dashboard", value=date.today().replace(day=1), format="DD/MM/YYYY")
    data_fim = c2.date_input("Data final dashboard", value=date.today(), format="DD/MM/YYYY")
    maq_map = {"Todas": None}
    for _, r in maquinas.iterrows():
        maq_map[f"{r['nome']} (ID {int(r['id'])})"] = int(r["id"])
    maq_label = c3.selectbox("Máquina dashboard", list(maq_map.keys()))

    df = carregar_pallets({"data_ini": data_ini, "data_fim": data_fim, "maquina_id": maq_map[maq_label]})
    if df.empty:
        st.info("Sem dados de produção no período.")
        return

    total_programado = len(df[df["status"] == "PROGRAMADO"])
    total_produzido = len(df[df["status"] == "PRODUZIDO"])
    total_rejeitado = len(df[df["status"] == "REJEITADO"])
    kg_produzido = float(df.loc[df["status"] == "PRODUZIDO", "kg"].sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Programados", int(total_programado))
    m2.metric("Produzidos", int(total_produzido))
    m3.metric("Rejeitados", int(total_rejeitado))
    m4.metric("Kg produzidos", format_number(kg_produzido))

    por_maquina = df.groupby(["maquina", "status"], dropna=False).agg(pallets=("id", "count"), kg=("kg", "sum")).reset_index()
    por_turno = df.groupby(["turno", "status"], dropna=False).agg(pallets=("id", "count"), kg=("kg", "sum")).reset_index()
    por_produto = df.groupby(["produto", "status"], dropna=False).agg(pallets=("id", "count"), kg=("kg", "sum")).reset_index()

    st.markdown("#### Produção por máquina")
    st.dataframe(por_maquina, use_container_width=True, hide_index=True)
    st.markdown("#### Produção por turno")
    st.dataframe(por_turno, use_container_width=True, hide_index=True)
    st.markdown("#### Produção por produto")
    st.dataframe(por_produto, use_container_width=True, hide_index=True)


def tela_producao(usuario="Sistema", planta_label=""):
    criar_tabelas_producao()
    st.markdown("## Produção / Palletização")
    st.caption("Módulo independente para programação, leitura de etiquetas e dashboard de produção por pallet.")

    aba = st.radio(
        "Menu Produção",
        ["Produtos", "Programar produção", "Leitura de etiqueta", "Consulta", "Dashboard"],
        horizontal=True,
    )
    if aba=="Produtos":
        tela_produtos()
    elif aba == "Programar produção":
        tela_programar(usuario, planta_label)
    elif aba == "Leitura de etiqueta":
        tela_leitura(usuario)
    elif aba == "Consulta":
        tela_consulta(usuario, planta_label)
    else:
        tela_dashboard()
        

def botao_imprimir_etiqueta(row, planta_label=""):
    html_etiqueta = etiqueta_html(row, planta_label)

    html_print = f"""
    <html>
    <head>
        <title>Etiqueta {row.get("codigo_barras", "")}</title>
        <style>
            body {{
                margin: 0;
                padding: 10px;
                background: white;
            }}

            @media print {{
                body {{
                    margin: 0;
                    padding: 0;
                }}

                button {{
                    display: none;
                }}
            }}
        </style>
    </head>
    <body>
        {html_etiqueta}

        <br>

        <button onclick="window.print()" style="
            font-size:18px;
            padding:12px 22px;
            border-radius:8px;
            cursor:pointer;
        ">
            Imprimir etiqueta
        </button>
    </body>
    </html>
    """

    components.html(
        html_print,
        height=620,
        scrolling=True,
    )
    
def gerar_zpl_etiqueta(row, planta_label=""):
    codigo = str(row.get("codigo_barras") or "")
    produto = str(row.get("produto") or "")[:35]
    maquina = str(row.get("maquina") or "")[:30]
    lote = str(row.get("lote") or "")[:30]
    turno = str(row.get("turno") or "")[:20]
    kg = format_number(row.get("kg", 0))
    data_txt = format_date_br(row.get("data_producao"))

    return f"""
^XA
^CI28
^PW800
^LL560
^FO30,25^A0N,28,28^FD{planta_label}^FS
^FO30,60^A0N,38,38^FDETIQUETA DE PRODUCAO^FS

^FO30,120^A0N,28,28^FDCodigo:^FS
^FO170,120^A0N,28,28^FD{codigo}^FS

^FO30,160^A0N,28,28^FDProduto:^FS
^FO170,160^A0N,28,28^FD{produto}^FS

^FO30,200^A0N,28,28^FDMaquina:^FS
^FO170,200^A0N,28,28^FD{maquina}^FS

^FO30,240^A0N,28,28^FDLote:^FS
^FO170,240^A0N,28,28^FD{lote}^FS

^FO30,280^A0N,28,28^FDTurno:^FS
^FO170,280^A0N,28,28^FD{turno}^FS

^FO30,320^A0N,28,28^FDData:^FS
^FO170,320^A0N,28,28^FD{data_txt}^FS

^FO30,360^A0N,28,28^FDKg:^FS
^FO170,360^A0N,28,28^FD{kg}^FS

^FO90,415^BY3
^BCN,90,Y,N,N
^FD{codigo}^FS

^XZ
""".strip()
