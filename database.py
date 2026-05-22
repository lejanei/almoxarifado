import pandas as pd
from sqlalchemy import create_engine, text
from utils import agora, formatar_pedido_id, formatar_produto_id, get_config

DEFAULT_DB_URL = "mysql+pymysql://ljsyst02_adm:vinimalu121924@ljsystem.com.br/ljsyst02_almoxarifado?charset=utf8mb4"
DB_URL = str(get_config("DB_URL", "")) or str(get_config("ALMOXARIFADO_URL", "")) or DEFAULT_DB_URL

engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=280, future=True)


def set_database_url(db_url):
    """Atualiza a conexão do módulo Compras/Serviços conforme a planta escolhida."""
    global DB_URL, engine
    if db_url and str(db_url) != str(DB_URL):
        DB_URL = str(db_url)
        engine.dispose()
        engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=280, future=True)


def garantir_coluna(tabela, coluna, definicao):
    try:
        executar(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")
    except Exception:
        pass


def executar(sql, params=None):
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})


def buscar_um(sql, params=None):
    with engine.begin() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
        return dict(row) if row else None


def carregar_df(sql, params=None):
    with engine.begin() as conn:
        return pd.read_sql_query(text(sql), conn, params=params or {})


def criar_tabelas():
    executar("""CREATE TABLE IF NOT EXISTS servicos_terceiros (
        id INT AUTO_INCREMENT PRIMARY KEY,
        numero VARCHAR(50),
        data DATE NOT NULL,
        fornecedor_id INT NOT NULL,
        centro_custo_id INT NULL,
        tipo_orcamento VARCHAR(20) NOT NULL DEFAULT 'OPEX',
        descricao TEXT NOT NULL,
        valor_total DECIMAL(15,2) NOT NULL DEFAULT 0,
        status VARCHAR(50) NOT NULL DEFAULT 'Aberto',
        prioridade VARCHAR(50) NOT NULL DEFAULT 'Normal',
        observacao LONGTEXT,
        criado_por VARCHAR(100),
        aprovado_por VARCHAR(100),
        data_aprovacao VARCHAR(50),
        executado_por VARCHAR(100),
        data_execucao VARCHAR(50),
        finalizado_por VARCHAR(100),
        data_finalizacao VARCHAR(50),
        cancelado_por VARCHAR(100),
        data_cancelamento VARCHAR(50),
        criado_em VARCHAR(50),
        atualizado_em VARCHAR(50),
        INDEX idx_serv_data (data),
        INDEX idx_serv_status (status),
        INDEX idx_serv_fornecedor (fornecedor_id),
        INDEX idx_serv_cc (centro_custo_id)      
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS servico_anexos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        servico_id INT NOT NULL,
        nome_arquivo VARCHAR(255) NOT NULL,
        caminho VARCHAR(500) NOT NULL,
        enviado_por VARCHAR(100),
        data_envio VARCHAR(50),
        INDEX idx_serv_anexos (servico_id),
        CONSTRAINT fk_serv_anexos FOREIGN KEY (servico_id) REFERENCES servicos_terceiros(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")


    executar("""CREATE TABLE IF NOT EXISTS orcamentos_gerais_mensais (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ano INT NOT NULL,
        mes INT NOT NULL,
        tipo_orcamento VARCHAR(20) NOT NULL DEFAULT 'OPEX',
        valor_total DECIMAL(15,2) NOT NULL DEFAULT 0,
        alerta_percentual DECIMAL(5,2) NOT NULL DEFAULT 80,
        observacao TEXT,
        criado_em VARCHAR(50),
        atualizado_em VARCHAR(50),
        UNIQUE KEY uq_orc_geral_mes_tipo (ano, mes, tipo_orcamento)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")


    executar("""CREATE TABLE IF NOT EXISTS centros_custo (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nome VARCHAR(150) NOT NULL UNIQUE,
        descricao TEXT,
        ativo TINYINT(1) NOT NULL DEFAULT 1,
        criado_em VARCHAR(50)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS orcamentos_mensais (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ano INT NOT NULL,
        mes INT NOT NULL,
        centro_custo_id INT NULL,
        tipo_orcamento VARCHAR(20) NOT NULL DEFAULT 'OPEX',
        valor_orcado DECIMAL(15,2) NOT NULL DEFAULT 0,
        alerta_percentual DECIMAL(5,2) NOT NULL DEFAULT 80,
        criado_em VARCHAR(50),
        atualizado_em VARCHAR(50),
        UNIQUE KEY uq_orc_mes_cc_tipo (ano, mes, centro_custo_id, tipo_orcamento),
        INDEX idx_orc_cc (centro_custo_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS usuarios (
        id INT AUTO_INCREMENT PRIMARY KEY,
        usuario VARCHAR(100) UNIQUE NOT NULL,
        senha VARCHAR(255) NOT NULL,
        nome VARCHAR(150) NOT NULL,
        perfil VARCHAR(50) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS fornecedores (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nome VARCHAR(255) NOT NULL,
        contato VARCHAR(255),
        telefone VARCHAR(100)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    # Tabela oficial do estoque StockPro. O módulo Compras passa a usar esta tabela.
    executar("""CREATE TABLE IF NOT EXISTS products (
        id INT AUTO_INCREMENT PRIMARY KEY,
        codigo VARCHAR(80) NULL UNIQUE,
        nome VARCHAR(150) NOT NULL,
        descricao TEXT,
        unidade VARCHAR(20) NOT NULL DEFAULT 'UN',
        estoque_atual DECIMAL(18,3) NOT NULL DEFAULT 0,
        estoque_minimo DECIMAL(18,3) NOT NULL DEFAULT 0,
        valor_unitario DECIMAL(18,4) NOT NULL DEFAULT 0,
        criado_em DATETIME NOT NULL,
        atualizado_em DATETIME NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    # Mantida apenas por compatibilidade com pedidos antigos do Shop Manager.
    executar("""CREATE TABLE IF NOT EXISTS produtos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        codigo VARCHAR(50),
        nome VARCHAR(255) NOT NULL,
        unidade VARCHAR(50)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS pedidos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        numero VARCHAR(50),
        data DATE NOT NULL,
        fornecedor_id INT NULL,
        status VARCHAR(50),
        prioridade VARCHAR(50) DEFAULT 'Normal',
        observacao LONGTEXT,
        criado_por VARCHAR(100),
        aprovado_por VARCHAR(100),
        data_aprovacao VARCHAR(50),
        comprado_por VARCHAR(100),
        data_compra VARCHAR(50),
        recebido_por VARCHAR(100),
        data_recebimento VARCHAR(50),
        cancelado_por VARCHAR(100),
        data_cancelamento VARCHAR(50),
        INDEX idx_pedidos_fornecedor (fornecedor_id),
        CONSTRAINT fk_pedidos_fornecedor FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS pedido_itens (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pedido_id INT NOT NULL,
        produto_id INT NOT NULL,
        quantidade DECIMAL(15,3) NOT NULL,
        valor_unitario DECIMAL(15,2) NOT NULL,
        observacao_item TEXT,
        INDEX idx_itens_pedido (pedido_id),
        INDEX idx_itens_produto (produto_id),
        CONSTRAINT fk_itens_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
        CONSTRAINT fk_itens_produto FOREIGN KEY (produto_id) REFERENCES products(id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS pedido_anexos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pedido_id INT NOT NULL,
        nome_arquivo VARCHAR(255) NOT NULL,
        caminho VARCHAR(500) NOT NULL,
        enviado_por VARCHAR(100),
        data_envio VARCHAR(50),
        INDEX idx_anexos_pedido (pedido_id),
        CONSTRAINT fk_anexos_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS notificacoes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        data VARCHAR(50) NOT NULL,
        tipo VARCHAR(100) NOT NULL,
        pedido_id INT,
        numero_pedido VARCHAR(50),
        mensagem LONGTEXT NOT NULL,
        destino TEXT,
        status_envio VARCHAR(100),
        usuario VARCHAR(100),
        lida TINYINT DEFAULT 0,
        INDEX idx_notificacao_pedido (pedido_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    inserir_usuarios_padrao()
    migrar_banco()


def coluna_existe(tabela, coluna):
    df = carregar_df("""SELECT COUNT(*) AS total FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = :tabela AND column_name = :coluna""", {"tabela": tabela, "coluna": coluna})
    return int(df["total"].iloc[0]) > 0


def adicionar_coluna_se_nao_existir(tabela, coluna, tipo):
    if not coluna_existe(tabela, coluna):
        executar(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


def migrar_banco():
    for coluna, tipo in [("numero","VARCHAR(50)"),("fornecedor_id","INT NULL"),("status","VARCHAR(50)"),("prioridade","VARCHAR(50) DEFAULT 'Normal'"),("observacao","LONGTEXT"),("criado_por","VARCHAR(100)"),("aprovado_por","VARCHAR(100)"),("data_aprovacao","VARCHAR(50)"),("comprado_por","VARCHAR(100)"),("data_compra","VARCHAR(50)"),("recebido_por","VARCHAR(100)"),("data_recebimento","VARCHAR(50)"),("cancelado_por","VARCHAR(100)"),("data_cancelamento","VARCHAR(50)")]:
        adicionar_coluna_se_nao_existir("pedidos", coluna, tipo)

    # Compatibilidade com tabela antiga de produtos de compras.
    adicionar_coluna_se_nao_existir("produtos", "codigo", "VARCHAR(50)")
    adicionar_coluna_se_nao_existir("produtos", "unidade", "VARCHAR(50)")

    for _, row in carregar_df("SELECT id FROM produtos WHERE codigo IS NULL OR codigo = ''").iterrows():
        executar("UPDATE produtos SET codigo=:codigo WHERE id=:id", {"codigo": formatar_produto_id(row["id"]), "id": int(row["id"])})
    for _, row in carregar_df("SELECT id FROM pedidos WHERE numero IS NULL OR numero = ''").iterrows():
        executar("UPDATE pedidos SET numero=:numero WHERE id=:id", {"numero": formatar_pedido_id(row["id"]), "id": int(row["id"])})
    executar("UPDATE pedidos SET prioridade='Normal' WHERE prioridade IS NULL OR prioridade=''")

    # Migração para que pedido_itens.produto_id aponte para products.id do estoque.
    # Se houver pedidos antigos incompatíveis, o sistema remove a FK antiga e continua funcionando.
    try:
        executar("ALTER TABLE pedido_itens DROP FOREIGN KEY fk_itens_produto")
    except Exception:
        pass
    try:
        executar("ALTER TABLE pedido_itens ADD CONSTRAINT fk_itens_produto FOREIGN KEY (produto_id) REFERENCES products(id) ON DELETE RESTRICT")
    except Exception:
        pass


def inserir_usuarios_padrao():
    executar("""INSERT IGNORE INTO usuarios (usuario, senha, nome, perfil) VALUES
        ('admin','admin123','Administrador','admin'),
        ('aprovador','ap123','Aprovador','aprovador'),
        ('operador','op123','Operador','operador')""")


def login(usuario, senha):
    row = buscar_um("SELECT usuario,nome,perfil FROM usuarios WHERE usuario=:u AND senha=:s", {"u": usuario, "s": senha})
    return (row["usuario"], row["nome"], row["perfil"]) if row else None


    garantir_coluna("products", "centro_custo_id", "INT NULL")
    garantir_coluna("products", "valor_unitario", "DECIMAL(18,4) NOT NULL DEFAULT 0")
    garantir_coluna("pedidos", "centro_custo_id", "INT NULL")
    garantir_coluna("pedidos", "tipo_orcamento", "VARCHAR(20) NOT NULL DEFAULT 'OPEX'")
    garantir_coluna("orcamentos_mensais", "tipo_orcamento", "VARCHAR(20) NOT NULL DEFAULT 'OPEX'")
    garantir_coluna("service_orders", "centro_custo_id", "INT NULL")


def carregar_produtos():
    df = carregar_df("""SELECT
            p.id,
            COALESCE(NULLIF(p.codigo, ''), CONCAT('P', LPAD(p.id, 5, '0'))) AS codigo,
            p.nome,
            COALESCE(p.unidade, 'UN') AS unidade,
            p.descricao,
            p.estoque_atual,
            p.estoque_minimo,
            p.centro_custo_id,
            cc.nome AS centro_custo
        FROM products p
        LEFT JOIN centros_custo cc ON cc.id=p.centro_custo_id
        ORDER BY p.nome""")
    return df


def inserir_produto(nome, unidade):
    # Compras não cadastra produtos separados. Cadastre produtos em Produtos / Estoque.
    executar("""INSERT INTO products (nome, unidade, estoque_atual, estoque_minimo, criado_em, atualizado_em)
               VALUES (:nome, :unidade, 0, 0, NOW(), NOW())""", {"nome": nome, "unidade": unidade or "UN"})

def atualizar_produto(id_produto, nome, unidade):
    executar("UPDATE products SET nome=:nome, unidade=:unidade, atualizado_em=NOW() WHERE id=:id", {"nome": nome, "unidade": unidade or "UN", "id": id_produto})

def excluir_produto(id_produto):
    executar("DELETE FROM products WHERE id=:id", {"id": id_produto})

def carregar_fornecedores():
    return carregar_df("SELECT * FROM fornecedores ORDER BY nome")


def inserir_fornecedor(nome, contato, telefone):
    executar("INSERT INTO fornecedores (nome,contato,telefone) VALUES (:nome,:contato,:telefone)", {"nome": nome, "contato": contato, "telefone": telefone})


def atualizar_fornecedor(id_fornecedor, nome, contato, telefone):
    executar("UPDATE fornecedores SET nome=:nome, contato=:contato, telefone=:telefone WHERE id=:id", {"nome": nome, "contato": contato, "telefone": telefone, "id": id_fornecedor})


def excluir_fornecedor(id_fornecedor):
    executar("DELETE FROM fornecedores WHERE id=:id", {"id": id_fornecedor})


def carregar_pedidos():
    df = carregar_df("""SELECT p.id,p.numero,p.data,f.nome AS fornecedor,p.status,p.prioridade,
        p.centro_custo_id, cc.nome AS centro_custo,
        COALESCE(SUM(i.quantidade*i.valor_unitario),0) AS valor_total,
        COUNT(i.id) AS quantidade_itens,p.observacao,p.criado_por,p.aprovado_por,p.data_aprovacao,
        p.comprado_por,p.data_compra,p.recebido_por,p.data_recebimento,p.cancelado_por,p.data_cancelamento
        FROM pedidos p
        LEFT JOIN fornecedores f ON f.id=p.fornecedor_id
        LEFT JOIN centros_custo cc ON cc.id=p.centro_custo_id
        LEFT JOIN pedido_itens i ON i.pedido_id=p.id
        GROUP BY p.id,p.numero,p.data,f.nome,p.status,p.prioridade,p.centro_custo_id,cc.nome,p.observacao,p.criado_por,p.aprovado_por,p.data_aprovacao,p.comprado_por,p.data_compra,p.recebido_por,p.data_recebimento,p.cancelado_por,p.data_cancelamento
        ORDER BY p.id DESC""")
    if not df.empty:
        df["numero"] = df.apply(lambda r: r["numero"] if r["numero"] else formatar_pedido_id(r["id"]), axis=1)
        df["prioridade"] = df["prioridade"].fillna("Normal")
    return df


def carregar_itens_pedido(id_pedido):
    return carregar_df("""SELECT i.id,i.pedido_id,i.produto_id,
        COALESCE(NULLIF(pr.codigo, ''), CONCAT('P', LPAD(pr.id, 5, '0'))) AS codigo,
        pr.nome AS produto, COALESCE(pr.unidade, 'UN') AS unidade,
        i.quantidade,i.valor_unitario,i.quantidade*i.valor_unitario AS valor_total,i.observacao_item
        FROM pedido_itens i LEFT JOIN products pr ON pr.id=i.produto_id
        WHERE i.pedido_id=:id ORDER BY i.id""", {"id": id_pedido})


def buscar_pedido(id_pedido):
    return buscar_um("SELECT * FROM pedidos WHERE id=:id", {"id": id_pedido})


def criar_pedido(data_pedido, fornecedor_id, prioridade, itens, observacao, usuario, centro_custo_id=None):
    log = f"[{agora()}] Pedido criado por {usuario}."
    obs_final = f"{observacao}\n\n{log}" if observacao else log
    with engine.begin() as conn:
        res = conn.execute(text("""INSERT INTO pedidos (data,fornecedor_id,centro_custo_id,status,prioridade,observacao,criado_por)
            VALUES (:data,:fornecedor_id,:centro_custo_id,'Aberto',:prioridade,:observacao,:usuario)"""), {"data": str(data_pedido), "fornecedor_id": fornecedor_id, "centro_custo_id": centro_custo_id, "prioridade": prioridade, "observacao": obs_final, "usuario": usuario})
        pedido_id = res.lastrowid
        numero = formatar_pedido_id(pedido_id)
        conn.execute(text("UPDATE pedidos SET numero=:numero WHERE id=:id"), {"numero": numero, "id": pedido_id})
        for item in itens:
            conn.execute(text("""INSERT INTO pedido_itens (pedido_id,produto_id,quantidade,valor_unitario,observacao_item)
                VALUES (:pedido_id,:produto_id,:quantidade,:valor_unitario,:obs)"""), {"pedido_id": pedido_id, "produto_id": item["produto_id"], "quantidade": item["quantidade"], "valor_unitario": item["valor_unitario"], "obs": item.get("observacao_item", "")})
    return pedido_id, numero


def atualizar_pedido(id_pedido, data_pedido, fornecedor_id, prioridade, itens, observacao, usuario):
    log = f"[{agora()}] Pedido editado por {usuario}."
    obs_final = f"{observacao}\n\n{log}"
    with engine.begin() as conn:
        conn.execute(text("""UPDATE pedidos SET data=:data, fornecedor_id=:fornecedor_id, prioridade=:prioridade, observacao=:observacao WHERE id=:id"""), {"data": str(data_pedido), "fornecedor_id": fornecedor_id, "prioridade": prioridade, "observacao": obs_final, "id": id_pedido})
        conn.execute(text("DELETE FROM pedido_itens WHERE pedido_id=:id"), {"id": id_pedido})
        for item in itens:
            conn.execute(text("""INSERT INTO pedido_itens (pedido_id,produto_id,quantidade,valor_unitario,observacao_item)
                VALUES (:pedido_id,:produto_id,:quantidade,:valor_unitario,:obs)"""), {"pedido_id": id_pedido, "produto_id": item["produto_id"], "quantidade": item["quantidade"], "valor_unitario": item["valor_unitario"], "obs": item.get("observacao_item", "")})


def alterar_status(id_pedido, novo_status, usuario):
    pedido = buscar_pedido(id_pedido)
    if not pedido:
        return
    obs = (pedido.get("observacao") or "") + f"\n\n[{agora()}] Status alterado de {pedido.get('status')} para {novo_status} por {usuario}."
    campos = {"Aprovado": ("aprovado_por", "data_aprovacao"), "Comprado": ("comprado_por", "data_compra"), "Recebido": ("recebido_por", "data_recebimento"), "Cancelado": ("cancelado_por", "data_cancelamento")}
    if novo_status in campos:
        usuario_col, data_col = campos[novo_status]
        executar(f"UPDATE pedidos SET status=:status, observacao=:obs, {usuario_col}=:usuario, {data_col}=:data WHERE id=:id", {"status": novo_status, "obs": obs, "usuario": usuario, "data": agora(), "id": id_pedido})
    else:
        executar("UPDATE pedidos SET status=:status, observacao=:obs WHERE id=:id", {"status": novo_status, "obs": obs, "id": id_pedido})


def excluir_pedido(id_pedido):
    executar("DELETE FROM pedidos WHERE id=:id", {"id": id_pedido})


def inserir_anexo(pedido_id, nome_arquivo, caminho, usuario):
    executar("INSERT INTO pedido_anexos (pedido_id,nome_arquivo,caminho,enviado_por,data_envio) VALUES (:pedido_id,:nome,:caminho,:usuario,:data)", {"pedido_id": pedido_id, "nome": nome_arquivo, "caminho": caminho, "usuario": usuario, "data": agora()})


def carregar_anexos_pedido(pedido_id):
    return carregar_df("SELECT * FROM pedido_anexos WHERE pedido_id=:id ORDER BY id DESC", {"id": pedido_id})


def registrar_notificacao(tipo, pedido_id, numero_pedido, mensagem, status_envio, usuario):
    executar("""INSERT INTO notificacoes (data,tipo,pedido_id,numero_pedido,mensagem,destino,status_envio,usuario,lida)
        VALUES (:data,:tipo,:pedido_id,:numero,:mensagem,'Email',:status,:usuario,0)""", {"data": agora(), "tipo": tipo, "pedido_id": pedido_id, "numero": numero_pedido, "mensagem": mensagem, "status": status_envio, "usuario": usuario})


def carregar_notificacoes():
    return carregar_df("SELECT * FROM notificacoes ORDER BY id DESC")


def marcar_notificacoes_lidas():
    executar("UPDATE notificacoes SET lida=1")


def carregar_centros_custo(apenas_ativos=True):
    sql = "SELECT id, nome, descricao, ativo FROM centros_custo"
    if apenas_ativos:
        sql += " WHERE ativo=1"
    sql += " ORDER BY nome"
    return carregar_df(sql)


def criar_centro_custo(nome, descricao="", ativo=True):
    executar(
        "INSERT INTO centros_custo (nome, descricao, ativo, criado_em) VALUES (:nome, :descricao, :ativo, :criado)",
        {"nome": nome.strip(), "descricao": descricao.strip(), "ativo": 1 if ativo else 0, "criado": agora()},
    )


def atualizar_centro_custo(cc_id, nome, descricao="", ativo=True):
    executar(
        "UPDATE centros_custo SET nome=:nome, descricao=:descricao, ativo=:ativo WHERE id=:id",
        {"id": int(cc_id), "nome": nome.strip(), "descricao": descricao.strip(), "ativo": 1 if ativo else 0},
    )




def centro_custo_possui_vinculos(cc_id):
    cc_id = int(cc_id)
    consultas = {
        "produtos": "SELECT COUNT(*) AS total FROM products WHERE centro_custo_id=:id",
        "pedidos de compra": "SELECT COUNT(*) AS total FROM pedidos WHERE centro_custo_id=:id",
        "ordens de serviço/preventivas": "SELECT COUNT(*) AS total FROM service_orders WHERE centro_custo_id=:id",
        "orçamentos mensais": "SELECT COUNT(*) AS total FROM orcamentos_mensais WHERE centro_custo_id=:id",
    }
    vinculos = {}
    for nome, sql in consultas.items():
        try:
            row = buscar_um(sql, {"id": cc_id})
            total = int(row["total"] or 0) if row else 0
        except Exception:
            total = 0
        if total > 0:
            vinculos[nome] = total
    return vinculos


def excluir_centro_custo(cc_id):
    vinculos = centro_custo_possui_vinculos(cc_id)
    if vinculos:
        detalhes = ", ".join([f"{k}: {v}" for k, v in vinculos.items()])
        raise ValueError(f"Este centro de custo possui vínculos e não pode ser excluído. Vínculos: {detalhes}. Use Inativo para bloquear novos lançamentos.")
    executar("DELETE FROM centros_custo WHERE id=:id", {"id": int(cc_id)})


def inativar_centro_custo(cc_id):
    executar("UPDATE centros_custo SET ativo=0 WHERE id=:id", {"id": int(cc_id)})


def carregar_orcamento_mensal(ano, mes, centro_custo_id=None):
    if centro_custo_id:
        return buscar_um("SELECT * FROM orcamentos_mensais WHERE ano=:ano AND mes=:mes AND centro_custo_id=:cc LIMIT 1", {"ano": int(ano), "mes": int(mes), "cc": int(centro_custo_id)})
    return buscar_um("SELECT * FROM orcamentos_mensais WHERE ano=:ano AND mes=:mes AND centro_custo_id IS NULL LIMIT 1", {"ano": int(ano), "mes": int(mes)})


def salvar_orcamento_mensal(ano, mes, valor_orcado, alerta_percentual=80, centro_custo_id=None):
    existente = carregar_orcamento_mensal(ano, mes, centro_custo_id)
    params = {"ano": int(ano), "mes": int(mes), "valor": float(valor_orcado), "alerta": float(alerta_percentual), "cc": int(centro_custo_id) if centro_custo_id else None, "agora": agora()}
    if existente:
        executar("UPDATE orcamentos_mensais SET valor_orcado=:valor, alerta_percentual=:alerta, atualizado_em=:agora WHERE id=:id", {**params, "id": int(existente["id"])})
    else:
        executar("INSERT INTO orcamentos_mensais (ano, mes, centro_custo_id, valor_orcado, alerta_percentual, criado_em, atualizado_em) VALUES (:ano, :mes, :cc, :valor, :alerta, :agora, :agora)", params)


def total_compras_mes(ano, mes, centro_custo_id=None):
    inicio = f"{int(ano):04d}-{int(mes):02d}-01"
    fim = f"{int(ano)+1:04d}-01-01" if int(mes)==12 else f"{int(ano):04d}-{int(mes)+1:02d}-01"
    sql = """
        SELECT COALESCE(SUM(pi.quantidade * pi.valor_unitario), 0) AS total
        FROM pedidos p
        INNER JOIN pedido_itens pi ON pi.pedido_id = p.id
        WHERE p.data >= :inicio AND p.data < :fim
          AND p.status NOT IN ('Cancelado')
    """
    params = {"inicio": inicio, "fim": fim}
    if centro_custo_id:
        sql += " AND p.centro_custo_id = :cc"
        params["cc"] = int(centro_custo_id)
    row = buscar_um(sql, params)
    return float(row["total"] or 0) if row else 0.0


def resumo_orcamento_mes(ano, mes, centro_custo_id=None):
    orc = carregar_orcamento_mensal(ano, mes, centro_custo_id)
    valor_orcado = float(orc["valor_orcado"]) if orc else 0.0
    alerta_percentual = float(orc["alerta_percentual"]) if orc else 80.0
    consumido = total_compras_mes(ano, mes, centro_custo_id)
    saldo = valor_orcado - consumido
    percentual = (consumido / valor_orcado * 100) if valor_orcado > 0 else 0
    return {"valor_orcado": valor_orcado, "consumido": consumido, "saldo": saldo, "percentual": percentual, "alerta_percentual": alerta_percentual}


# ===== Overrides CAPEX/OPEX =====

def carregar_orcamento_mensal(ano, mes, centro_custo_id=None, tipo_orcamento='OPEX'):
    tipo = str(tipo_orcamento or 'OPEX').upper()
    if centro_custo_id:
        return buscar_um(
            "SELECT * FROM orcamentos_mensais WHERE ano=:ano AND mes=:mes AND centro_custo_id=:cc AND tipo_orcamento=:tipo LIMIT 1",
            {"ano": int(ano), "mes": int(mes), "cc": int(centro_custo_id), "tipo": tipo},
        )
    return buscar_um(
        "SELECT * FROM orcamentos_mensais WHERE ano=:ano AND mes=:mes AND centro_custo_id IS NULL AND tipo_orcamento=:tipo LIMIT 1",
        {"ano": int(ano), "mes": int(mes), "tipo": tipo},
    )


def salvar_orcamento_mensal(ano, mes, valor_orcado, alerta_percentual=80, centro_custo_id=None, tipo_orcamento='OPEX'):
    tipo = str(tipo_orcamento or 'OPEX').upper()
    existente = carregar_orcamento_mensal(ano, mes, centro_custo_id, tipo)
    params = {
        "ano": int(ano),
        "mes": int(mes),
        "valor": float(valor_orcado),
        "alerta": float(alerta_percentual),
        "cc": int(centro_custo_id) if centro_custo_id else None,
        "tipo": tipo,
        "agora": agora(),
    }
    if existente:
        executar(
            "UPDATE orcamentos_mensais SET valor_orcado=:valor, alerta_percentual=:alerta, atualizado_em=:agora WHERE id=:id",
            {**params, "id": int(existente["id"])},
        )
    else:
        executar(
            "INSERT INTO orcamentos_mensais (ano, mes, centro_custo_id, tipo_orcamento, valor_orcado, alerta_percentual, criado_em, atualizado_em) VALUES (:ano, :mes, :cc, :tipo, :valor, :alerta, :agora, :agora)",
            params,
        )


def total_compras_mes(ano, mes, centro_custo_id=None, tipo_orcamento='OPEX'):
    inicio = f"{int(ano):04d}-{int(mes):02d}-01"
    fim = f"{int(ano)+1:04d}-01-01" if int(mes) == 12 else f"{int(ano):04d}-{int(mes)+1:02d}-01"
    sql = """
        SELECT COALESCE(SUM(pi.quantidade * pi.valor_unitario), 0) AS total
        FROM pedidos p
        INNER JOIN pedido_itens pi ON pi.pedido_id = p.id
        WHERE p.data >= :inicio AND p.data < :fim
          AND p.status NOT IN ('Cancelado')
          AND COALESCE(p.tipo_orcamento, 'OPEX') = :tipo
    """
    params = {"inicio": inicio, "fim": fim, "tipo": str(tipo_orcamento or 'OPEX').upper()}
    if centro_custo_id:
        sql += " AND p.centro_custo_id = :cc"
        params["cc"] = int(centro_custo_id)
    row = buscar_um(sql, params)
    return float(row["total"] or 0) if row else 0.0


def resumo_orcamento_mes(ano, mes, centro_custo_id=None, tipo_orcamento='OPEX'):
    orc = carregar_orcamento_mensal(ano, mes, centro_custo_id, tipo_orcamento)
    valor_orcado = float(orc["valor_orcado"]) if orc else 0.0
    alerta_percentual = float(orc["alerta_percentual"]) if orc else 80.0
    consumido = total_compras_mes(ano, mes, centro_custo_id, tipo_orcamento)
    saldo = valor_orcado - consumido
    percentual = (consumido / valor_orcado * 100) if valor_orcado > 0 else 0
    return {
        "valor_orcado": valor_orcado,
        "consumido": consumido,
        "saldo": saldo,
        "percentual": percentual,
        "alerta_percentual": alerta_percentual,
        "tipo_orcamento": str(tipo_orcamento or 'OPEX').upper(),
    }


def obter_tipo_orcamento_para_pedido(ano, mes, centro_custo_id=None):
    """Busca o tipo OPEX/CAPEX pelo orçamento mensal do centro de custo."""
    if centro_custo_id:
        row = buscar_um(
            "SELECT tipo_orcamento FROM orcamentos_mensais WHERE ano=:ano AND mes=:mes AND centro_custo_id=:cc ORDER BY id DESC LIMIT 1",
            {"ano": int(ano), "mes": int(mes), "cc": int(centro_custo_id)},
        )
        if row and row.get("tipo_orcamento"):
            return str(row["tipo_orcamento"]).upper()

    row = buscar_um(
        "SELECT tipo_orcamento FROM orcamentos_mensais WHERE ano=:ano AND mes=:mes AND centro_custo_id IS NULL ORDER BY id DESC LIMIT 1",
        {"ano": int(ano), "mes": int(mes)},
    )
    if row and row.get("tipo_orcamento"):
        return str(row["tipo_orcamento"]).upper()

    return "OPEX"


# ===== Orçamento mensal geral OPEX/CAPEX =====

def carregar_orcamentos_gerais(ano=None, mes=None, tipo_orcamento=None):
    sql = "SELECT * FROM orcamentos_gerais_mensais WHERE 1=1"
    params = {}
    if ano:
        sql += " AND ano=:ano"
        params["ano"] = int(ano)
    if mes:
        sql += " AND mes=:mes"
        params["mes"] = int(mes)
    if tipo_orcamento:
        sql += " AND tipo_orcamento=:tipo"
        params["tipo"] = str(tipo_orcamento).upper()
    sql += " ORDER BY ano DESC, mes DESC, tipo_orcamento"
    return carregar_df(sql, params)


def carregar_orcamento_geral(ano, mes, tipo_orcamento='OPEX'):
    return buscar_um(
        "SELECT * FROM orcamentos_gerais_mensais WHERE ano=:ano AND mes=:mes AND tipo_orcamento=:tipo LIMIT 1",
        {"ano": int(ano), "mes": int(mes), "tipo": str(tipo_orcamento or 'OPEX').upper()},
    )


def salvar_orcamento_geral(ano, mes, tipo_orcamento, valor_total, alerta_percentual=80, observacao=""):
    tipo = str(tipo_orcamento or "OPEX").upper()
    existente = carregar_orcamento_geral(ano, mes, tipo)
    params = {
        "ano": int(ano),
        "mes": int(mes),
        "tipo": tipo,
        "valor": float(valor_total),
        "alerta": float(alerta_percentual),
        "obs": observacao,
        "agora": agora(),
    }
    if existente:
        executar(
            """UPDATE orcamentos_gerais_mensais
               SET valor_total=:valor,
                   alerta_percentual=:alerta,
                   observacao=:obs,
                   atualizado_em=:agora
             WHERE id=:id""",
            {**params, "id": int(existente["id"])},
        )
    else:
        executar(
            """INSERT INTO orcamentos_gerais_mensais
               (ano, mes, tipo_orcamento, valor_total, alerta_percentual, observacao, criado_em, atualizado_em)
               VALUES (:ano, :mes, :tipo, :valor, :alerta, :obs, :agora, :agora)""",
            params,
        )


def excluir_orcamento_geral(orcamento_id):
    executar("DELETE FROM orcamentos_gerais_mensais WHERE id=:id", {"id": int(orcamento_id)})


def total_distribuido_orcamento(ano, mes, tipo_orcamento='OPEX'):
    row = buscar_um(
        """SELECT COALESCE(SUM(valor_orcado), 0) AS total
             FROM orcamentos_mensais
            WHERE ano=:ano
              AND mes=:mes
              AND tipo_orcamento=:tipo""",
        {"ano": int(ano), "mes": int(mes), "tipo": str(tipo_orcamento or 'OPEX').upper()},
    )
    return float(row["total"] or 0) if row else 0.0


def resumo_orcamento_geral_mes(ano, mes, tipo_orcamento='OPEX'):
    tipo = str(tipo_orcamento or 'OPEX').upper()
    orc = carregar_orcamento_geral(ano, mes, tipo)
    valor_total = float(orc["valor_total"]) if orc else 0.0
    alerta_percentual = float(orc["alerta_percentual"]) if orc else 80.0
    distribuido = total_distribuido_orcamento(ano, mes, tipo)
    consumido = total_compras_mes(ano, mes, None, tipo)
    saldo_distribuir = valor_total - distribuido
    saldo_real = valor_total - consumido
    percentual_consumido = (consumido / valor_total * 100) if valor_total > 0 else 0
    percentual_distribuido = (distribuido / valor_total * 100) if valor_total > 0 else 0
    return {
        "tipo_orcamento": tipo,
        "valor_total": valor_total,
        "distribuido": distribuido,
        "consumido": consumido,
        "saldo_distribuir": saldo_distribuir,
        "saldo_real": saldo_real,
        "percentual_consumido": percentual_consumido,
        "percentual_distribuido": percentual_distribuido,
        "alerta_percentual": alerta_percentual,
    }


# ===== Serviços de terceiros =====

def formatar_servico_id(servico_id):
    return f"SERV-{int(servico_id):05d}"


def criar_servico(data_servico, fornecedor_id, centro_custo_id, descricao, valor_total, prioridade, observacao, usuario):
    tipo_orcamento = obter_tipo_orcamento_para_pedido(
        data_servico.year if hasattr(data_servico, "year") else int(str(data_servico)[:4]),
        data_servico.month if hasattr(data_servico, "month") else int(str(data_servico)[5:7]),
        centro_custo_id,
    )
    log = f"[{agora()}] Serviço criado por {usuario}."
    obs_final = f"{observacao}\n\n{log}" if observacao else log

    with engine.begin() as conn:
        res = conn.execute(
            text("""INSERT INTO servicos_terceiros
                (data, fornecedor_id, centro_custo_id, tipo_orcamento, descricao, valor_total, status, prioridade, observacao, criado_por, criado_em, atualizado_em)
                VALUES (:data, :fornecedor_id, :centro_custo_id, :tipo_orcamento, :descricao, :valor_total, 'Aberto', :prioridade, :observacao, :usuario, :criado, :atualizado)"""),
            {
                "data": str(data_servico),
                "fornecedor_id": int(fornecedor_id),
                "centro_custo_id": int(centro_custo_id) if centro_custo_id else None,
                "tipo_orcamento": tipo_orcamento,
                "descricao": descricao,
                "valor_total": float(valor_total),
                "prioridade": prioridade,
                "observacao": obs_final,
                "usuario": usuario,
                "criado": agora(),
                "atualizado": agora(),
            },
        )
        servico_id = res.lastrowid
        numero = formatar_servico_id(servico_id)
        conn.execute(text("UPDATE servicos_terceiros SET numero=:numero WHERE id=:id"), {"numero": numero, "id": servico_id})

    return servico_id, numero, tipo_orcamento


def carregar_servicos():
    return carregar_df("""SELECT s.id, s.numero, s.data, f.nome AS fornecedor,
        s.fornecedor_id, s.centro_custo_id, cc.nome AS centro_custo,
        s.tipo_orcamento, s.descricao, s.valor_total, s.status, s.prioridade,
        s.observacao, s.criado_por, s.aprovado_por, s.data_aprovacao,
        s.executado_por, s.data_execucao, s.finalizado_por, s.data_finalizacao,
        s.cancelado_por, s.data_cancelamento, s.criado_em, s.atualizado_em
        FROM servicos_terceiros s
        LEFT JOIN fornecedores f ON f.id=s.fornecedor_id
        LEFT JOIN centros_custo cc ON cc.id=s.centro_custo_id
        ORDER BY s.id DESC""")


def buscar_servico(servico_id):
    return buscar_um("""SELECT s.*, f.nome AS fornecedor, cc.nome AS centro_custo
        FROM servicos_terceiros s
        LEFT JOIN fornecedores f ON f.id=s.fornecedor_id
        LEFT JOIN centros_custo cc ON cc.id=s.centro_custo_id
        WHERE s.id=:id""", {"id": int(servico_id)})


def alterar_status_servico(servico_id, novo_status, usuario):
    serv = buscar_servico(servico_id)
    if not serv:
        return
    obs = (serv.get("observacao") or "") + f"\n\n[{agora()}] Status alterado de {serv.get('status')} para {novo_status} por {usuario}."
    campos = {
        "Aprovado": ("aprovado_por", "data_aprovacao"),
        "Executado": ("executado_por", "data_execucao"),
        "Finalizado": ("finalizado_por", "data_finalizacao"),
        "Cancelado": ("cancelado_por", "data_cancelamento"),
    }
    if novo_status in campos:
        usuario_col, data_col = campos[novo_status]
        executar(
            f"UPDATE servicos_terceiros SET status=:status, observacao=:obs, {usuario_col}=:usuario, {data_col}=:data, atualizado_em=:data WHERE id=:id",
            {"status": novo_status, "obs": obs, "usuario": usuario, "data": agora(), "id": int(servico_id)},
        )
    else:
        executar(
            "UPDATE servicos_terceiros SET status=:status, observacao=:obs, atualizado_em=:data WHERE id=:id",
            {"status": novo_status, "obs": obs, "data": agora(), "id": int(servico_id)},
        )


def excluir_servico(servico_id):
    executar("DELETE FROM servicos_terceiros WHERE id=:id", {"id": int(servico_id)})


def inserir_anexo_servico(servico_id, nome_arquivo, caminho, usuario):
    executar(
        "INSERT INTO servico_anexos (servico_id,nome_arquivo,caminho,enviado_por,data_envio) VALUES (:servico_id,:nome,:caminho,:usuario,:data)",
        {"servico_id": int(servico_id), "nome": nome_arquivo, "caminho": caminho, "usuario": usuario, "data": agora()},
    )


def carregar_anexos_servico(servico_id):
    return carregar_df("SELECT * FROM servico_anexos WHERE servico_id=:id ORDER BY id DESC", {"id": int(servico_id)})


def total_servicos_mes(ano, mes, centro_custo_id=None, tipo_orcamento=None):
    inicio = f"{int(ano):04d}-{int(mes):02d}-01"
    fim = f"{int(ano)+1:04d}-01-01" if int(mes) == 12 else f"{int(ano):04d}-{int(mes)+1:02d}-01"
    sql = """
        SELECT COALESCE(SUM(valor_total), 0) AS total
        FROM servicos_terceiros
        WHERE data >= :inicio AND data < :fim
          AND status NOT IN ('Cancelado')
    """
    params = {"inicio": inicio, "fim": fim}
    if centro_custo_id:
        sql += " AND centro_custo_id=:cc"
        params["cc"] = int(centro_custo_id)
    if tipo_orcamento:
        sql += " AND tipo_orcamento=:tipo"
        params["tipo"] = str(tipo_orcamento).upper()
    row = buscar_um(sql, params)
    return float(row["total"] or 0) if row else 0.0


# ===== Overrides Serviços x Orçamento =====

def total_servicos_mes(ano, mes, centro_custo_id=None, tipo_orcamento=None):
    """Total de serviços que devem consumir orçamento.

    Regra:
    - Serviço só consome orçamento após aprovação.
    - Status considerados no consumo: Aprovado, Executado, Finalizado.
    - Cancelado e Aberto não consomem.
    """
    inicio = f"{int(ano):04d}-{int(mes):02d}-01"
    fim = f"{int(ano)+1:04d}-01-01" if int(mes) == 12 else f"{int(ano):04d}-{int(mes)+1:02d}-01"
    sql = """
        SELECT COALESCE(SUM(valor_total), 0) AS total
        FROM servicos_terceiros
        WHERE data >= :inicio AND data < :fim
          AND status IN ('Aprovado', 'Executado', 'Finalizado')
    """
    params = {"inicio": inicio, "fim": fim}
    if centro_custo_id:
        sql += " AND centro_custo_id=:cc"
        params["cc"] = int(centro_custo_id)
    if tipo_orcamento:
        sql += " AND tipo_orcamento=:tipo"
        params["tipo"] = str(tipo_orcamento).upper()
    row = buscar_um(sql, params)
    return float(row["total"] or 0) if row else 0.0


def resumo_orcamento_mes(ano, mes, centro_custo_id=None, tipo_orcamento='OPEX'):
    """Resumo do orçamento mensal por centro de custo.

    Inclui:
    - compras de materiais
    - serviços de terceiros aprovados/executados/finalizados
    """
    orc = carregar_orcamento_mensal(ano, mes, centro_custo_id, tipo_orcamento)
    valor_orcado = float(orc["valor_orcado"]) if orc else 0.0
    alerta_percentual = float(orc["alerta_percentual"]) if orc else 80.0

    compras = total_compras_mes(ano, mes, centro_custo_id, tipo_orcamento)
    servicos = total_servicos_mes(ano, mes, centro_custo_id, tipo_orcamento)
    consumido = compras + servicos

    saldo = valor_orcado - consumido
    percentual = (consumido / valor_orcado * 100) if valor_orcado > 0 else 0
    return {
        "valor_orcado": valor_orcado,
        "compras": compras,
        "servicos": servicos,
        "consumido": consumido,
        "saldo": saldo,
        "percentual": percentual,
        "alerta_percentual": alerta_percentual,
        "tipo_orcamento": str(tipo_orcamento or 'OPEX').upper(),
    }


def resumo_orcamento_geral_mes(ano, mes, tipo_orcamento='OPEX'):
    """Resumo geral mensal OPEX/CAPEX.

    Inclui compras e serviços aprovados.
    """
    tipo = str(tipo_orcamento or 'OPEX').upper()
    orc = carregar_orcamento_geral(ano, mes, tipo)
    valor_total = float(orc["valor_total"]) if orc else 0.0
    alerta_percentual = float(orc["alerta_percentual"]) if orc else 80.0
    distribuido = total_distribuido_orcamento(ano, mes, tipo)

    compras = total_compras_mes(ano, mes, None, tipo)
    servicos = total_servicos_mes(ano, mes, None, tipo)
    consumido = compras + servicos

    saldo_distribuir = valor_total - distribuido
    saldo_real = valor_total - consumido
    percentual_consumido = (consumido / valor_total * 100) if valor_total > 0 else 0
    percentual_distribuido = (distribuido / valor_total * 100) if valor_total > 0 else 0
    return {
        "tipo_orcamento": tipo,
        "valor_total": valor_total,
        "distribuido": distribuido,
        "compras": compras,
        "servicos": servicos,
        "consumido": consumido,
        "saldo_distribuir": saldo_distribuir,
        "saldo_real": saldo_real,
        "percentual_consumido": percentual_consumido,
        "percentual_distribuido": percentual_distribuido,
        "alerta_percentual": alerta_percentual,
    }
