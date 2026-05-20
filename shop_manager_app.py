from datetime import date, datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from database import *
from pdf_generator import gerar_pdf_pedido
from utils import emoji_prioridade, emoji_status, valor_moeda
import email_sender as email_mod
from email_sender import *
import telegram_sender as telegram_mod
from telegram_sender import *

# Mensagens sem link
def mensagem_pedido_criado(numero, pedido_id, usuario, fornecedor, total, prioridade):
    return f"""🛒 NOVO PEDIDO DE COMPRA

Pedido: {numero}
Fornecedor: {fornecedor}
Valor: {total}
Prioridade: {prioridade}
Criado por: {usuario}
"""


def mensagem_status_alterado(numero, pedido_id, status, usuario, prioridade):
    return f"""📦 ATUALIZAÇÃO DE PEDIDO

Pedido: {numero}
Prioridade: {prioridade}

Novo status: {status}
Alterado por: {usuario}
"""


def mensagem_pedido_editado(numero, pedido_id, usuario, prioridade):
    return f"""✏️ PEDIDO DE COMPRA EDITADO

Pedido: {numero}
Prioridade: {prioridade}
Editado por: {usuario}
"""


def mensagem_pedido_excluido(numero, pedido_id, usuario, prioridade):
    return f"""🗑️ PEDIDO DE COMPRA EXCLUÍDO

Pedido: {numero}
Prioridade: {prioridade}
Excluído por: {usuario}
"""


# Wrappers para o app.py conseguir chamar shop_manager.email_configurado()
# e shop_manager.telegram_configurado() sem depender do import *
def email_configurado():
    try:
        return email_mod.email_configurado()
    except Exception:
        return False


def telegram_configurado():
    try:
        return telegram_mod.telegram_configurado()
    except Exception:
        return False


# Mensagens do módulo Compras sem link do pedido





def seletor_centro_custo(label='Centro de custo', key=None, permitir_vazio=True):
    centros = carregar_centros_custo()
    opcoes = []
    if permitir_vazio:
        opcoes.append('Sem centro de custo')
    if not centros.empty:
        opcoes += [f"ID {int(r.id)} - {r.nome}" for r in centros.itertuples()]
    escolha = st.selectbox(label, opcoes or ['Sem centro de custo'], key=key)
    if escolha == 'Sem centro de custo':
        return None
    return int(escolha.split(' - ')[0].replace('ID ', ''))


def nome_centro_custo(cc_id):
    if not cc_id:
        return 'Sem centro de custo'
    centros = carregar_centros_custo(apenas_ativos=False)
    if centros.empty:
        return f'Centro {cc_id}'
    row = centros[centros['id'].astype(int) == int(cc_id)]
    return str(row.iloc[0]['nome']) if not row.empty else f'Centro {cc_id}'


def verificar_alerta_orcamento(ano, mes, centro_custo_id, tipo_orcamento='OPEX', numero_pedido=''):
    resumo = resumo_orcamento_mes(ano, mes, centro_custo_id, tipo_orcamento)
    if resumo['valor_orcado'] <= 0:
        return
    if resumo['percentual'] >= resumo['alerta_percentual'] or resumo['percentual'] >= 100:
        cc_nome = nome_centro_custo(centro_custo_id)
        msg = f"""⚠️ ALERTA DE ORÇAMENTO DE COMPRAS

Pedido: {numero_pedido}
Centro de custo: {cc_nome}
Tipo: {str(tipo_orcamento).upper()}
Mês: {int(mes):02d}/{int(ano)}

Orçamento: {valor_moeda(resumo['valor_orcado'])}
Consumido: {valor_moeda(resumo['consumido'])}
Saldo: {valor_moeda(resumo['saldo'])}
Uso: {resumo['percentual']:.1f}%
Limite de alerta: {resumo['alerta_percentual']:.1f}%
"""
        try:
            telegram_mod.enviar_telegram(msg)
        except Exception as e:
            print('Erro alerta orçamento Telegram:', e)
        try:
            email_mod.enviar_email_notificacao('Alerta de orçamento de compras', msg)
        except Exception as e:
            print('Erro alerta orçamento e-mail:', e)

def tem_permissao_aprovar(): return st.session_state.perfil in ['admin','aprovador']
def tem_permissao_excluir(): return st.session_state.perfil in ['admin','aprovador']

def notificar(tipo,pedido_id,numero,msg,usuario,pdf=None,legenda='',enviar_anexos_telegram=False):
    """Envia notificações.

    E-mail:
        continua podendo enviar o PDF da ordem de compra gerado pelo sistema.

    Telegram:
        sempre envia a mensagem.
        envia os anexos reais do pedido somente quando enviar_anexos_telegram=True,
        ou seja, somente na criação do pedido de compra.
    """
    assunto = f'StockPro Compras - {tipo} - {numero}'

    # E-mail mantém o comportamento anterior.
    try:
        ok_email = email_mod.enviar_email_notificacao(assunto, msg, pdf, legenda)
    except Exception as erro_email:
        print("Erro email:", erro_email)
        ok_email = False

    # Telegram envia a mensagem.
    try:
        ok_msg_telegram = telegram_mod.enviar_telegram(msg)
    except Exception as erro_telegram:
        print("Erro Telegram:", erro_telegram)
        ok_msg_telegram = False

    ok_anexos_telegram = True
    anexos = carregar_anexos_pedido(pedido_id) if enviar_anexos_telegram else None

    if enviar_anexos_telegram and anexos is not None and not anexos.empty:
        for anexo in anexos.itertuples():
            legenda_anexo = f'📎 Orçamento/anexo do pedido {numero}: {anexo.nome_arquivo}'
            try:
                ok_doc = telegram_mod.enviar_telegram_documento(anexo.caminho, legenda_anexo)
            except Exception as erro_doc:
                print("Erro Telegram documento:", erro_doc)
                ok_doc = False
            if not ok_doc:
                ok_anexos_telegram = False

    ok_telegram = ok_msg_telegram and ok_anexos_telegram

    canais = []
    canais.append('Email enviado' if ok_email else 'Email não enviado')

    if enviar_anexos_telegram:
        if anexos is None or anexos.empty:
            canais.append('Telegram enviado sem anexos do pedido' if ok_telegram else 'Telegram não enviado')
        else:
            canais.append('Telegram enviado com anexos do pedido' if ok_telegram else 'Telegram enviado com falha em algum anexo')
    else:
        canais.append('Telegram enviado somente mensagem' if ok_telegram else 'Telegram não enviado')

    registrar_notificacao(tipo,pedido_id,numero,msg,' | '.join(canais),usuario)

def tela_login():
    st.title('🔐 Login - Gerenciador de Compras'); c1,c2,c3=st.columns([1,1,1])
    with c2:
        u=st.text_input('Usuário'); s=st.text_input('Senha',type='password')
        if st.button('Entrar', use_container_width=True):
            user=login(u,s)
            if user:
                st.session_state.logado=True; st.session_state.usuario=user[0]; st.session_state.nome=user[1]; st.session_state.perfil=user[2]; st.rerun()
            else: st.error('Usuário ou senha inválidos.')
        #st.info('admin/admin123 | aprovador/ap123 | operador/op123')


def tela_dashboard():
    st.subheader('📊 Dashboard de Compras')
    st.caption('Indicadores filtrados automaticamente pelo mês vigente.')

    hoje = datetime.now()
    inicio_mes = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    fim_mes = hoje.replace(hour=23, minute=59, second=59, microsecond=999999)

    pedidos = carregar_pedidos()
    if pedidos.empty:
        st.info('Nenhum pedido cadastrado.')
        return

    df = pedidos.copy()
    coluna_data = None
    for col in ['data', 'data_pedido', 'criado_em', 'data_criacao']:
        if col in df.columns:
            coluna_data = col
            break

    if coluna_data:
        df[coluna_data] = pd.to_datetime(df[coluna_data], errors='coerce')
        pedidos_mes = df[(df[coluna_data] >= inicio_mes) & (df[coluna_data] <= fim_mes)].copy()
    else:
        pedidos_mes = df.copy()

    st.markdown(f"### Mês vigente: {hoje.strftime('%m/%Y')}")

    total_valor = 0.0
    for col_valor in ['valor_total', 'total']:
        if col_valor in pedidos_mes.columns:
            total_valor = pd.to_numeric(pedidos_mes[col_valor], errors='coerce').fillna(0).sum()
            break

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Pedidos no mês', len(pedidos_mes))
    c2.metric('Valor no mês', valor_moeda(total_valor))
    c3.metric('Abertos', len(pedidos_mes[pedidos_mes['status'].isin(['Aberto', 'Pendente', 'Solicitado'])]) if 'status' in pedidos_mes.columns else 0)
    c4.metric('Recebidos', len(pedidos_mes[pedidos_mes['status'].isin(['Recebido', 'Finalizado'])]) if 'status' in pedidos_mes.columns else 0)

    st.divider()
    c5, c6 = st.columns(2)
    with c5:
        st.markdown('### Status no mês')
        if 'status' in pedidos_mes.columns and not pedidos_mes.empty:
            status_df = pedidos_mes.groupby('status').size().reset_index(name='total').sort_values('total', ascending=False)
            st.dataframe(status_df, use_container_width=True, hide_index=True)
        else:
            st.info('Sem status no mês.')

    with c6:
        st.markdown('### Prioridades no mês')
        if 'prioridade' in pedidos_mes.columns and not pedidos_mes.empty:
            pr_df = pedidos_mes.groupby('prioridade').size().reset_index(name='total').sort_values('total', ascending=False)
            st.dataframe(pr_df, use_container_width=True, hide_index=True)
        else:
            st.info('Sem prioridades no mês.')

    st.markdown('### Resumo por tipo de orçamento')
    if 'tipo_orcamento' in pedidos_mes.columns and not pedidos_mes.empty:
        tipo_df = pedidos_mes.groupby('tipo_orcamento').size().reset_index(name='total_pedidos')
        st.dataframe(tipo_df, use_container_width=True, hide_index=True)
    else:
        st.info('Sem tipo de orçamento nos pedidos do mês.')

    st.markdown('### Últimos pedidos do mês')
    if pedidos_mes.empty:
        st.info('Nenhum pedido no mês vigente.')
    else:
        cols_pref = ['id', 'numero', 'data', 'data_pedido', 'fornecedor', 'fornecedor_nome', 'prioridade', 'status', 'valor_total', 'total', 'solicitante', 'usuario']
        cols = [c for c in cols_pref if c in pedidos_mes.columns]
        st.dataframe(pedidos_mes[cols or pedidos_mes.columns.tolist()].tail(20), use_container_width=True, hide_index=True)

def tela_novo_pedido():
    st.subheader('📝 Novo Pedido de Compra')
    if st.session_state.perfil not in ['admin', 'almoxarifado', 'aprovador']:
        st.warning('Somente Administrador, Almoxarifado e Aprovador podem criar pedido de compra.')
        return
    produtos=carregar_produtos(); fornecedores=carregar_fornecedores()
    if produtos.empty: st.warning('Cadastre produtos no módulo Produtos / Estoque antes de fazer pedidos.'); return
    if fornecedores.empty: st.warning('Cadastre pelo menos um fornecedor.'); return
    with st.form('add_item'):
        st.markdown('### Adicionar produto ao pedido'); c1,c2,c3=st.columns([3,1,1])
        opts=[f'{r.codigo} - {r.nome} ({r.unidade or "UN"})' for r in produtos.itertuples()]
        with c1: escolhido=st.selectbox('Produto',opts)
        with c2: qtd=st.number_input('Quantidade',min_value=0.0,step=1.0)
        with c3: val=st.number_input('Valor unitário',min_value=0.0,step=1.0)
        obs_item=st.text_input('Observação do item')
        if st.form_submit_button('Adicionar Produto ao Pedido'):
            if qtd<=0: st.error('Quantidade precisa ser maior que zero.')
            else:
                r=produtos.iloc[opts.index(escolhido)]
                st.session_state.itens_novo_pedido.append({'produto_id':int(r.id),'codigo':r.codigo,'produto':r.nome,'unidade':r.unidade,'quantidade':float(qtd),'valor_unitario':float(val),'valor_total':float(qtd)*float(val),'observacao_item':obs_item})
                st.success('Produto adicionado.'); st.rerun()
    st.divider(); st.markdown('### Itens adicionados')
    if st.session_state.itens_novo_pedido:
        df=pd.DataFrame(st.session_state.itens_novo_pedido); ex=df.copy(); ex['valor_unitario']=ex.valor_unitario.apply(valor_moeda); ex['valor_total']=ex.valor_total.apply(valor_moeda); st.dataframe(ex[['codigo','produto','unidade','quantidade','valor_unitario','valor_total','observacao_item']], use_container_width=True)
        total=sum(i['valor_total'] for i in st.session_state.itens_novo_pedido); st.metric('Total do Pedido',valor_moeda(total))
        c1,c2=st.columns(2)
        with c1:
            if st.button('Limpar todos os itens'): st.session_state.itens_novo_pedido=[]; st.rerun()
        with c2:
            idx=st.number_input('Remover item nº',min_value=1,max_value=len(st.session_state.itens_novo_pedido),step=1)
            if st.button('Remover item selecionado'): st.session_state.itens_novo_pedido.pop(idx-1); st.rerun()
    else: st.info('Nenhum produto adicionado ainda.')
    st.divider()
    with st.form('finalizar'):
        st.markdown('### Dados do pedido'); data=st.date_input('Data do pedido',value=date.today()); fornecedor_nome=st.selectbox('Fornecedor',fornecedores.nome.tolist()); prioridade=st.selectbox('Prioridade',['Baixa','Normal','Alta','Urgente'],index=1); centro_custo_id=seletor_centro_custo('Centro de custo do pedido', key='cc_novo_pedido'); st.caption('O tipo OPEX/CAPEX será puxado automaticamente do orçamento mensal do centro de custo.'); obs=st.text_area('Observação geral do pedido'); anexos=st.file_uploader('Anexos da compra',accept_multiple_files=True)
        if st.form_submit_button('Salvar Pedido de Compra'):
            if not st.session_state.itens_novo_pedido: st.error('Adicione pelo menos um produto ao pedido.')
            else:
                fornecedor_id=int(fornecedores[fornecedores.nome==fornecedor_nome].id.iloc[0]); pedido_id,numero=criar_pedido(data,fornecedor_id,prioridade,st.session_state.itens_novo_pedido,obs,st.session_state.usuario,centro_custo_id)
                adir=Path('shop_data')/'anexos'/numero; adir.mkdir(parents=True,exist_ok=True)
                for arq in anexos:
                    dest=adir/arq.name; dest.write_bytes(arq.getbuffer()); inserir_anexo(pedido_id,arq.name,str(dest),st.session_state.usuario)
                total=sum(i['valor_total'] for i in st.session_state.itens_novo_pedido); pdf=gerar_pdf_pedido(pedido_id); msg=mensagem_pedido_criado(numero,pedido_id,st.session_state.usuario,fornecedor_nome,valor_moeda(total),prioridade); notificar('Pedido criado',pedido_id,numero,msg,st.session_state.usuario,pdf,f'📄 Ordem de Compra {numero}',enviar_anexos_telegram=True); tipo_orcamento=obter_tipo_orcamento_para_pedido(data.year,data.month,centro_custo_id); verificar_alerta_orcamento(data.year,data.month,centro_custo_id,tipo_orcamento,numero)
                st.session_state.itens_novo_pedido=[]; st.success(f'Pedido {numero} criado.'); st.rerun()

def tela_pedidos():
    st.subheader('📋 Pedidos'); pedidos=carregar_pedidos()
    if pedidos.empty: st.info('Nenhum pedido cadastrado.'); return
    sf=st.selectbox('Filtrar por status',['Todos','Aberto','Aprovado','Comprado','Recebido','Cancelado']); pf=st.selectbox('Filtrar por prioridade',['Todas','Baixa','Normal','Alta','Urgente']); cc_filtro=st.selectbox('Filtrar por centro de custo',['Todos'] + sorted([str(x) for x in pedidos['centro_custo'].dropna().unique()]) if 'centro_custo' in pedidos.columns else ['Todos'])
    df=pedidos.copy();
    if sf!='Todos': df=df[df.status==sf]
    if pf!='Todas': df=df[df.prioridade==pf]
    if 'centro_custo' in df.columns and cc_filtro!='Todos': df=df[df.centro_custo==cc_filtro]
    ex=df.copy(); ex['status']=ex.status.apply(lambda x:f'{emoji_status(x)} {x}'); ex['prioridade']=ex.prioridade.apply(lambda x:f'{emoji_prioridade(x)} {x}'); ex['valor_total']=ex.valor_total.apply(valor_moeda); st.dataframe(ex, use_container_width=True)
    st.divider(); opts=[f'{r.numero} | {r.data} | {r.fornecedor or "Sem fornecedor"} | {r.status} | {emoji_prioridade(r.prioridade)} {r.prioridade}' for r in pedidos.itertuples()]; esc=st.selectbox('Pedido',opts); pedido_id=int(pedidos.iloc[opts.index(esc)].id); pedido=buscar_pedido(pedido_id)
    st.markdown(f"### Pedido {pedido['numero']} - {emoji_status(pedido['status'])} {pedido['status']} - {emoji_prioridade(pedido['prioridade'])} {pedido['prioridade']}")
    st.caption(f"Centro de custo: {nome_centro_custo(pedido.get('centro_custo_id'))}")
    pdf=gerar_pdf_pedido(pedido_id)
    if pdf and Path(pdf).exists():
        with open(pdf,'rb') as f: st.download_button('📄 Baixar Ordem de Compra PDF',f,file_name=Path(pdf).name,mime='application/pdf')
    itens=carregar_itens_pedido(pedido_id)
    if not itens.empty:
        it=itens.copy(); it['valor_unitario']=it.valor_unitario.apply(valor_moeda); it['valor_total']=it.valor_total.apply(valor_moeda); st.dataframe(it[['codigo','produto','unidade','quantidade','valor_unitario','valor_total','observacao_item']], use_container_width=True)
    st.markdown('### 📎 Anexos'); anexos=carregar_anexos_pedido(pedido_id)
    if anexos.empty: st.info('Nenhum anexo.')
    else:
        for a in anexos.itertuples():
            p=Path(a.caminho)
            if p.exists():
                with open(p,'rb') as f: st.download_button(f'Baixar {a.nome_arquivo}',f,file_name=a.nome_arquivo,key=f'anexo_{a.id}')
    novos=st.file_uploader('Adicionar anexo ao pedido',accept_multiple_files=True,key=f'up_{pedido_id}')
    if novos and st.button('Salvar anexos'):
        adir=Path('shop_data')/'anexos'/pedido['numero']; adir.mkdir(parents=True,exist_ok=True)
        for arq in novos:
            dest=adir/arq.name; dest.write_bytes(arq.getbuffer()); inserir_anexo(pedido_id,arq.name,str(dest),st.session_state.usuario)
        st.success('Anexos salvos.'); st.rerun()
    st.divider(); st.subheader('✅ Aprovação / Status'); c1,c2,c3,c4=st.columns(4)
    def mudar(ns,leg):
        alterar_status(pedido_id,ns,st.session_state.usuario); pdf2=gerar_pdf_pedido(pedido_id); msg=mensagem_status_alterado(pedido['numero'],pedido_id,ns,st.session_state.usuario,pedido['prioridade']); notificar(f'Status {ns}',pedido_id,pedido['numero'],msg,st.session_state.usuario,pdf2,leg); st.success(f'Pedido marcado como {ns}.'); st.rerun()
    with c1:
        if tem_permissao_aprovar():
            if st.button('✅ Aprovar'): mudar('Aprovado',f"✅ Pedido {pedido['numero']} aprovado")
        else: st.info('Sem permissão para aprovar.')
    with c2:
        if st.button('🛒 Comprado'): mudar('Comprado',f"🛒 Pedido {pedido['numero']} comprado")
    with c3:
        if st.button('📦 Recebido'): mudar('Recebido',f"📦 Pedido {pedido['numero']} recebido")
    with c4:
        if st.button('🚫 Cancelado'): mudar('Cancelado',f"🚫 Pedido {pedido['numero']} cancelado")
    st.divider(); st.subheader('✏️ Editar Pedido'); produtos=carregar_produtos(); fornecedores=carregar_fornecedores()
    with st.form('editar'):
        try: data_atual=datetime.strptime(str(pedido['data']),'%Y-%m-%d').date()
        except Exception: data_atual=date.today()
        data=st.date_input('Data',value=data_atual); lista=fornecedores.nome.tolist(); fn=''
        if pedido['fornecedor_id']:
            m=fornecedores[fornecedores.id==pedido['fornecedor_id']]
            if not m.empty: fn=m.nome.iloc[0]
        fornecedor_nome=st.selectbox('Fornecedor',lista,index=lista.index(fn) if fn in lista else 0); prioridade=st.selectbox('Prioridade',['Baixa','Normal','Alta','Urgente'],index=['Baixa','Normal','Alta','Urgente'].index(pedido['prioridade'] or 'Normal')); obs=st.text_area('Observação / Log',value=pedido['observacao'] or '',height=220)
        edit=[]; pops=[f'{r.codigo} - {r.nome} ({r.unidade or "UN"})' for r in produtos.itertuples()]
        for idx,item in itens.iterrows():
            st.markdown(f'**Item {idx+1}**'); a,b,c=st.columns([3,1,1]); atual=f"{item['codigo']} - {item['produto']} ({item['unidade'] or 'UN'})"; pi=pops.index(atual) if atual in pops else 0
            with a: pl=st.selectbox(f'Produto item {idx+1}',pops,index=pi,key=f'p_{item.id}')
            with b: qtd=st.number_input(f'Quantidade item {idx+1}',min_value=0.0,step=1.0,value=float(item.quantidade),key=f'q_{item.id}')
            with c: val=st.number_input(f'Valor unitário item {idx+1}',min_value=0.0,step=1.0,value=float(item.valor_unitario),key=f'v_{item.id}')
            obsi=st.text_input(f'Observação item {idx+1}',value=item.observacao_item or '',key=f'o_{item.id}'); pr=produtos.iloc[pops.index(pl)]; edit.append({'produto_id':int(pr.id),'quantidade':float(qtd),'valor_unitario':float(val),'observacao_item':obsi})
        if st.checkbox('Adicionar mais um item neste pedido'):
            pl=st.selectbox('Novo produto',pops); qtd=st.number_input('Quantidade novo item',min_value=0.0,step=1.0); val=st.number_input('Valor unitário novo item',min_value=0.0,step=1.0); obsi=st.text_input('Observação novo item')
            if qtd>0: pr=produtos.iloc[pops.index(pl)]; edit.append({'produto_id':int(pr.id),'quantidade':float(qtd),'valor_unitario':float(val),'observacao_item':obsi})
        if st.form_submit_button('Salvar Alterações do Pedido'):
            fid=int(fornecedores[fornecedores.nome==fornecedor_nome].id.iloc[0]); valid=[i for i in edit if i['quantidade']>0]
            if not valid: st.error('O pedido precisa ter pelo menos um item.')
            else:
                atualizar_pedido(pedido_id,data,fid,prioridade,valid,obs,st.session_state.usuario); pdf2=gerar_pdf_pedido(pedido_id); msg=mensagem_pedido_editado(pedido['numero'],pedido_id,st.session_state.usuario,prioridade); notificar('Pedido editado',pedido_id,pedido['numero'],msg,st.session_state.usuario,pdf2,f"✏️ Pedido {pedido['numero']} editado"); st.success('Pedido atualizado.'); st.rerun()
    if tem_permissao_excluir():
        if st.checkbox('Confirmo que desejo excluir este pedido permanentemente.') and st.button('Excluir Pedido'):
            num=pedido['numero']; excluir_pedido(pedido_id); msg=mensagem_pedido_excluido(num,st.session_state.usuario); notificar('Pedido excluído',pedido_id,num,msg,st.session_state.usuario); st.success('Pedido excluído.'); st.rerun()

def tela_notificacoes():
    st.subheader('🔔 Painel de Notificações'); df=carregar_notificacoes()
    if df.empty: st.info('Nenhuma notificação registrada.'); return
    c1,c2=st.columns(2); c1.metric('Total',len(df)); c2.metric('Não lidas',len(df[df.lida==0]))
    if st.button('Marcar todas como lidas'): marcar_notificacoes_lidas(); st.rerun()
    st.dataframe(df, use_container_width=True)

def tela_produtos():
    st.subheader('📦 Produtos do Estoque')
    st.info('Os pedidos de compra usam diretamente os produtos cadastrados em Produtos / Estoque. Não existe mais cadastro separado de produtos em Compras.')
    produtos = carregar_produtos()
    if produtos.empty:
        st.warning('Nenhum produto cadastrado no estoque.')
        return
    cols = [c for c in ['codigo', 'nome', 'unidade', 'estoque_atual', 'estoque_minimo', 'descricao'] if c in produtos.columns]
    st.dataframe(produtos[cols], use_container_width=True, hide_index=True)


def tela_fornecedores():
    st.subheader('🏢 Fornecedores')
    with st.form('forn'):
        nome=st.text_input('Nome'); contato=st.text_input('Contato'); telefone=st.text_input('Telefone')
        if st.form_submit_button('Salvar Fornecedor'):
            if nome.strip(): inserir_fornecedor(nome,contato,telefone); st.success('Fornecedor cadastrado.'); st.rerun()
            else: st.error('Informe o nome do fornecedor.')
    fornecedores=carregar_fornecedores(); st.dataframe(fornecedores, use_container_width=True)
    if not fornecedores.empty:
        st.subheader('✏️ Editar / Excluir Fornecedor'); opts=[f'{r.id} - {r.nome}' for r in fornecedores.itertuples()]; esc=st.selectbox('Selecione o fornecedor',opts); f=fornecedores.iloc[opts.index(esc)]
        with st.form('edit_forn'):
            n=st.text_input('Nome',value=f.nome); c=st.text_input('Contato',value=f.contato or ''); t=st.text_input('Telefone',value=f.telefone or '')
            if st.form_submit_button('Salvar Alterações'): atualizar_fornecedor(int(f.id),n,c,t); st.success('Fornecedor atualizado.'); st.rerun()
        if tem_permissao_excluir() and st.checkbox('Confirmo que desejo excluir este fornecedor.'):
            if st.button('Excluir Fornecedor'): excluir_fornecedor(int(f.id)); st.success('Fornecedor excluído.'); st.rerun()

def tela_configuracoes():
    st.subheader('⚙️ Configurações'); st.markdown('### Logo do PDF'); logo=st.file_uploader('Enviar logo PNG',type=['png'])
    if logo and st.button('Salvar logo'):
        Path('assets').mkdir(exist_ok=True); (Path('assets')/'logo.png').write_bytes(logo.getbuffer()); st.success('Logo salva.')
    st.markdown('### E-mail SMTP')
    st.write('Status:', '✅ Configurado' if email_configurado() else '⚠️ Não configurado')
    st.caption('Configure via Secrets ou .env: EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_SMTP_USER, EMAIL_SMTP_PASSWORD, EMAIL_REMETENTE e EMAIL_DESTINATARIOS.')
    if st.button('Enviar e-mail de teste'):
        ok = enviar_email_notificacao('Teste StockPro Compras', 'E-mail de teste enviado pelo StockPro Compras.')
        st.success('E-mail de teste enviado.') if ok else st.error('Falha no envio. Verifique Secrets, .env e SMTP.')

    st.markdown('### Telegram')
    st.write('Status:', '✅ Configurado' if telegram_configurado() else '⚠️ Não configurado')
    st.caption('Configure via Secrets ou .env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID e TELEGRAM_ATIVO.')
    if st.button('Enviar Telegram de teste'):
        ok = enviar_telegram('🔔 Teste do StockPro Compras\n\nTelegram configurado com sucesso.')
        st.success('Telegram de teste enviado.') if ok else st.error('Falha no envio. Verifique token, chat_id e se o bot está no grupo.')


def tela_centros_custo_orcamento():
    st.subheader('🏷️ Centros de custo e orçamento mensal')
    t1, t2, t3, t4 = st.tabs(['Centros de custo', 'Orçamento geral mensal', 'Orçamento por centro', 'Consumo do mês'])

    with t1:
        st.markdown('### Novo centro de custo')
        with st.form('novo_centro_custo', clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            nome = c1.text_input('Nome do centro de custo')
            ativo = c2.checkbox('Ativo', value=True)
            descricao = st.text_area('Descrição')

            if st.form_submit_button('Salvar centro de custo', use_container_width=True):
                if not nome.strip():
                    st.error('Informe o nome do centro de custo.')
                else:
                    try:
                        criar_centro_custo(nome, descricao, ativo)
                        st.success('Centro de custo cadastrado.')
                        st.rerun()
                    except Exception as e:
                        st.error(f'Erro ao cadastrar centro de custo: {e}')

        st.divider()
        st.markdown('### Editar / Excluir centro de custo')
        centros = carregar_centros_custo(apenas_ativos=False)

        if centros.empty:
            st.info('Nenhum centro de custo cadastrado.')
        else:
            centro_map = {f"ID {int(r.id)} - {r.nome}": r for r in centros.itertuples()}
            selecionado = st.selectbox('Selecionar centro de custo', list(centro_map.keys()))
            row = centro_map[selecionado]

            with st.form('editar_centro_custo'):
                c1, c2 = st.columns([2, 1])
                nome_edit = c1.text_input('Nome', value=str(row.nome))
                ativo_edit = c2.checkbox('Ativo', value=bool(row.ativo))
                desc_atual = '' if pd.isna(row.descricao) else str(row.descricao)
                descricao_edit = st.text_area('Descrição', value=desc_atual)

                b1, b2, b3 = st.columns(3)
                with b1:
                    salvar = st.form_submit_button('Atualizar', use_container_width=True)
                with b2:
                    inativar = st.form_submit_button('Inativar', use_container_width=True)
                with b3:
                    excluir = st.form_submit_button('Excluir', use_container_width=True)

                if salvar:
                    if not nome_edit.strip():
                        st.error('Informe o nome do centro de custo.')
                    else:
                        try:
                            atualizar_centro_custo(int(row.id), nome_edit, descricao_edit, ativo_edit)
                            st.success('Centro de custo atualizado.')
                            st.rerun()
                        except Exception as e:
                            st.error(f'Erro ao atualizar centro de custo: {e}')

                if inativar:
                    try:
                        inativar_centro_custo(int(row.id))
                        st.success('Centro de custo inativado.')
                        st.rerun()
                    except Exception as e:
                        st.error(f'Erro ao inativar centro de custo: {e}')

                if excluir:
                    try:
                        excluir_centro_custo(int(row.id))
                        st.success('Centro de custo excluído.')
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            st.markdown('### Centros cadastrados')
            visual = centros.copy()
            visual['ativo'] = visual['ativo'].apply(lambda x: 'Sim' if int(x) == 1 else 'Não')
            st.dataframe(
                visual.rename(columns={'id': 'ID', 'nome': 'Nome', 'descricao': 'Descrição', 'ativo': 'Ativo'}),
                use_container_width=True,
                hide_index=True,
            )

    with t2:
        st.markdown('### Definir valor mensal geral por tipo')
        st.info('Cadastre primeiro o valor total mensal de OPEX e/ou CAPEX. Depois distribua esse valor entre os centros de custo.')

        hoje = datetime.now()

        with st.form('orcamento_geral_mensal'):
            c1, c2, c3, c4 = st.columns(4)
            ano = c1.number_input('Ano', min_value=2024, max_value=2100, value=hoje.year, step=1, key='og_ano')
            mes = c2.number_input('Mês', min_value=1, max_value=12, value=hoje.month, step=1, key='og_mes')
            tipo_orcamento = c3.selectbox('Tipo de orçamento', ['OPEX', 'CAPEX'], key='og_tipo')
            valor_total = c4.number_input('Valor total mensal', min_value=0.0, value=0.0, step=100.0, key='og_valor')

            alerta = st.slider('Avisar quando consumir (%)', min_value=10, max_value=100, value=80, key='og_alerta')
            observacao = st.text_area('Observação', key='og_obs')

            if st.form_submit_button('Salvar orçamento geral', use_container_width=True):
                try:
                    salvar_orcamento_geral(ano, mes, tipo_orcamento, valor_total, alerta, observacao)
                    st.success('Orçamento geral salvo.')
                    st.rerun()
                except Exception as e:
                    st.error(f'Erro ao salvar orçamento geral: {e}')

        st.markdown('### Orçamentos gerais cadastrados')
        consulta_ano = st.number_input('Filtrar ano', min_value=2024, max_value=2100, value=hoje.year, step=1, key='og_f_ano')
        consulta_mes = st.number_input('Filtrar mês', min_value=1, max_value=12, value=hoje.month, step=1, key='og_f_mes')

        orcs = carregar_orcamentos_gerais(consulta_ano, consulta_mes)
        if orcs.empty:
            st.info('Nenhum orçamento geral cadastrado para o período.')
        else:
            orcs_view = orcs.copy()
            st.dataframe(
                orcs_view.rename(columns={
                    'id': 'ID',
                    'ano': 'Ano',
                    'mes': 'Mês',
                    'tipo_orcamento': 'Tipo',
                    'valor_total': 'Valor total',
                    'alerta_percentual': 'Alerta %',
                    'observacao': 'Observação',
                }),
                use_container_width=True,
                hide_index=True,
            )

            mapa = {
                f"ID {int(r.id)} - {r.tipo_orcamento} {int(r.mes):02d}/{int(r.ano)} - {valor_moeda(float(r.valor_total))}": r
                for r in orcs.itertuples()
            }
            escolha_orc = st.selectbox('Editar / excluir orçamento geral', list(mapa.keys()), key='og_edit_sel')
            row = mapa[escolha_orc]

            with st.form('editar_orcamento_geral'):
                c1, c2, c3, c4 = st.columns(4)
                ano_e = c1.number_input('Ano', min_value=2024, max_value=2100, value=int(row.ano), step=1, key='og_e_ano')
                mes_e = c2.number_input('Mês', min_value=1, max_value=12, value=int(row.mes), step=1, key='og_e_mes')
                tipo_e = c3.selectbox('Tipo', ['OPEX', 'CAPEX'], index=0 if row.tipo_orcamento == 'OPEX' else 1, key='og_e_tipo')
                valor_e = c4.number_input('Valor total mensal', min_value=0.0, value=float(row.valor_total), step=100.0, key='og_e_valor')
                alerta_e = st.slider('Alerta (%)', min_value=10, max_value=100, value=int(float(row.alerta_percentual)), key='og_e_alerta')
                obs_e = st.text_area('Observação', value='' if pd.isna(row.observacao) else str(row.observacao), key='og_e_obs')

                b1, b2 = st.columns(2)
                with b1:
                    salvar = st.form_submit_button('Atualizar orçamento geral', use_container_width=True)
                with b2:
                    excluir = st.form_submit_button('Excluir orçamento geral', use_container_width=True)

                if salvar:
                    salvar_orcamento_geral(ano_e, mes_e, tipo_e, valor_e, alerta_e, obs_e)
                    st.success('Orçamento geral atualizado.')
                    st.rerun()

                if excluir:
                    try:
                        excluir_orcamento_geral(int(row.id))
                        st.success('Orçamento geral excluído.')
                        st.rerun()
                    except Exception as e:
                        st.error(f'Erro ao excluir orçamento geral: {e}')

        st.markdown('### Resumo geral do mês')
        c1, c2 = st.columns(2)
        for tipo in ['OPEX', 'CAPEX']:
            with c1 if tipo == 'OPEX' else c2:
                resumo = resumo_orcamento_geral_mes(hoje.year, hoje.month, tipo)
                st.markdown(f'#### {tipo}')
                st.metric('Valor mensal', valor_moeda(resumo['valor_total']))
                st.metric('Distribuído aos centros', valor_moeda(resumo['distribuido']))
                st.metric('Consumido em compras', valor_moeda(resumo['consumido']))
                st.metric('Saldo para distribuir', valor_moeda(resumo['saldo_distribuir']))
                st.metric('Saldo real', valor_moeda(resumo['saldo_real']))


    with t3:
        st.markdown('### Definir orçamento mensal por centro de custo')
        st.info('Defina aqui se o orçamento é OPEX ou CAPEX. O pedido herdará automaticamente esse tipo pelo centro de custo e mês.')
        hoje = datetime.now()
        centros = carregar_centros_custo()
        with st.form('orcamento_mensal'):
            c1, c2, c3, c4 = st.columns(4)
            ano = c1.number_input('Ano', min_value=2024, max_value=2100, value=hoje.year, step=1)
            mes = c2.number_input('Mês', min_value=1, max_value=12, value=hoje.month, step=1)
            tipo_orcamento = st.selectbox('Tipo de orçamento', ['OPEX', 'CAPEX'], key='tipo_orcamento_orcamento_mensal')
            resumo_geral = resumo_orcamento_geral_mes(ano, mes, tipo_orcamento)
            st.caption(f"Orçamento geral {tipo_orcamento}: {valor_moeda(resumo_geral['valor_total'])} | Distribuído: {valor_moeda(resumo_geral['distribuido'])} | Saldo a distribuir: {valor_moeda(resumo_geral['saldo_distribuir'])}")
            opcoes = ['Orçamento geral'] + [f"ID {int(r.id)} - {r.nome}" for r in centros.itertuples()]
            escolha = c3.selectbox('Centro de custo', opcoes)
            cc_id = None if escolha == 'Orçamento geral' else int(escolha.split(' - ')[0].replace('ID ', ''))
            valor = c4.number_input('Valor orçado', min_value=0.0, value=0.0, step=100.0)
            alerta = st.slider('Avisar quando atingir (%)', min_value=10, max_value=100, value=80)

            if st.form_submit_button('Salvar orçamento', use_container_width=True):
                try:
                    resumo_geral = resumo_orcamento_geral_mes(ano, mes, tipo_orcamento)
                    if resumo_geral['valor_total'] > 0 and valor > resumo_geral['saldo_distribuir'] + 0.01:
                        st.warning('O valor informado é maior que o saldo disponível para distribuir neste tipo de orçamento.')
                    salvar_orcamento_mensal(ano, mes, valor, alerta, cc_id, tipo_orcamento)
                    st.success('Orçamento salvo.')
                    st.rerun()
                except Exception as e:
                    st.error(f'Erro ao salvar orçamento: {e}')

    with t4:
        st.markdown('### Consumo do orçamento no mês')
        hoje = datetime.now()
        centros = carregar_centros_custo()
        opcoes = ['Orçamento geral'] + [f"ID {int(r.id)} - {r.nome}" for r in centros.itertuples()]
        tipo_orcamento_consulta = st.selectbox('Tipo de orçamento para consulta', ['OPEX', 'CAPEX'], key='tipo_orc_consulta')
        escolha = st.selectbox('Centro de custo para consulta', opcoes)
        cc_id = None if escolha == 'Orçamento geral' else int(escolha.split(' - ')[0].replace('ID ', ''))
        resumo = resumo_orcamento_mes(hoje.year, hoje.month, cc_id, tipo_orcamento_consulta)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric('Orçamento mensal', valor_moeda(resumo['valor_orcado']))
        c2.metric('Consumido no mês', valor_moeda(resumo['consumido']))
        c3.metric('Saldo disponível', valor_moeda(resumo['saldo']))
        c4.metric('Uso do orçamento', f"{resumo['percentual']:.1f}%")

        if resumo['valor_orcado'] <= 0:
            st.info('Nenhum orçamento definido para este mês.')
        elif resumo['percentual'] >= resumo['alerta_percentual']:
            st.warning('Atenção: orçamento atingiu ou ultrapassou o limite de alerta.')
        else:
            st.success('Orçamento dentro do limite.')



# ===== Páginas de Serviços de Terceiros =====

def mensagem_servico_criado(numero, usuario, fornecedor, valor, prioridade, centro_custo, tipo_orcamento):
    return f"""🧰 NOVO SERVIÇO DE TERCEIRO

Serviço: {numero}
Fornecedor: {fornecedor}
Centro de custo: {centro_custo}
Tipo: {tipo_orcamento}
Valor: {valor}
Prioridade: {prioridade}
Criado por: {usuario}
"""


def mensagem_status_servico(numero, status, usuario, prioridade):
    return f"""🧰 ATUALIZAÇÃO DE SERVIÇO

Serviço: {numero}
Prioridade: {prioridade}

Novo status: {status}
Alterado por: {usuario}
"""


def notificar_servico(tipo, servico_id, numero, msg, usuario, anexo=None, legenda='', enviar_anexos_telegram=False):
    assunto = f"StockPro Serviços - {tipo} - {numero}"

    try:
        ok_email = enviar_email_notificacao(assunto, msg, anexo, legenda)
    except Exception as erro_email:
        print("Erro email serviço:", erro_email)
        ok_email = False

    try:
        ok_msg_telegram = enviar_telegram(msg)
    except Exception as erro_telegram:
        print("Erro Telegram serviço:", erro_telegram)
        ok_msg_telegram = False

    ok_anexos = True
    if enviar_anexos_telegram:
        anexos = carregar_anexos_servico(servico_id)
        if not anexos.empty:
            for anexo in anexos.itertuples():
                try:
                    ok_doc = enviar_telegram_documento(anexo.caminho, f"📎 Anexo do serviço {numero}: {anexo.nome_arquivo}")
                    if not ok_doc:
                        ok_anexos = False
                except Exception as erro_doc:
                    print("Erro anexo Telegram serviço:", erro_doc)
                    ok_anexos = False

    status_envio = []
    status_envio.append("Email enviado" if ok_email else "Email não enviado")
    status_envio.append("Telegram enviado" if ok_msg_telegram and ok_anexos else "Telegram não enviado ou anexo com falha")
    registrar_notificacao(tipo, servico_id, numero, msg, " | ".join(status_envio), usuario)




def verificar_alerta_orcamento_servico(servico_id, numero_servico=''):
    serv = buscar_servico(servico_id)
    if not serv:
        return

    data_ref = pd.to_datetime(serv.get('data'), errors='coerce')
    if pd.isna(data_ref):
        data_ref = datetime.now()

    centro_custo_id = serv.get('centro_custo_id')
    tipo_orcamento = serv.get('tipo_orcamento') or 'OPEX'
    resumo = resumo_orcamento_mes(data_ref.year, data_ref.month, centro_custo_id, tipo_orcamento)

    if resumo["valor_orcado"] <= 0:
        msg = f"""⚠️ SERVIÇO APROVADO SEM ORÇAMENTO DEFINIDO

Serviço: {numero_servico}
Centro de custo: {serv.get('centro_custo') or 'Sem centro de custo'}
Tipo: {tipo_orcamento}
Mês: {data_ref.month:02d}/{data_ref.year}

Valor do serviço: {valor_moeda(float(serv.get('valor_total') or 0))}
Nenhum orçamento mensal foi definido para este centro de custo/tipo.
"""
        try:
            enviar_telegram(msg)
        except Exception as e:
            print("Erro alerta orçamento serviço Telegram:", e)
        try:
            enviar_email_notificacao("Serviço aprovado sem orçamento definido", msg)
        except Exception as e:
            print("Erro alerta orçamento serviço e-mail:", e)
        return

    if resumo["percentual"] >= resumo["alerta_percentual"]:
        msg = f"""⚠️ ALERTA DE ORÇAMENTO - SERVIÇOS

Serviço aprovado: {numero_servico}
Centro de custo: {serv.get('centro_custo') or 'Sem centro de custo'}
Tipo: {tipo_orcamento}
Mês: {data_ref.month:02d}/{data_ref.year}

Orçamento: {valor_moeda(resumo['valor_orcado'])}
Compras: {valor_moeda(resumo.get('compras', 0))}
Serviços: {valor_moeda(resumo.get('servicos', 0))}
Consumido total: {valor_moeda(resumo['consumido'])}
Saldo: {valor_moeda(resumo['saldo'])}
Uso: {resumo['percentual']:.1f}%

Limite de alerta: {resumo['alerta_percentual']:.1f}%
"""
        try:
            enviar_telegram(msg)
        except Exception as e:
            print("Erro alerta orçamento serviço Telegram:", e)
        try:
            enviar_email_notificacao("Alerta de orçamento - Serviços", msg)
        except Exception as e:
            print("Erro alerta orçamento serviço e-mail:", e)


def tela_servicos_dashboard():
    st.subheader("📊 Dashboard de Serviços")
    hoje = datetime.now()
    servicos = carregar_servicos()

    if servicos.empty:
        st.info("Nenhum serviço cadastrado.")
        return

    df = servicos.copy()
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    mes_df = df[(df["data"].dt.year == hoje.year) & (df["data"].dt.month == hoje.month)].copy()

    st.caption(f"Indicadores do mês vigente: {hoje.strftime('%m/%Y')}")

    total_mes = pd.to_numeric(mes_df["valor_total"], errors="coerce").fillna(0).sum() if not mes_df.empty else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Serviços no mês", len(mes_df))
    c2.metric("Valor no mês", valor_moeda(total_mes))
    c3.metric("Abertos", len(mes_df[mes_df["status"].isin(["Aberto", "Aprovado", "Executado"])]) if not mes_df.empty else 0)
    c4.metric("Finalizados", len(mes_df[mes_df["status"].isin(["Finalizado"])]) if not mes_df.empty else 0)

    c5, c6 = st.columns(2)
    with c5:
        st.markdown("### Por status")
        if not mes_df.empty:
            st.dataframe(mes_df.groupby("status").size().reset_index(name="total"), use_container_width=True, hide_index=True)
        else:
            st.info("Sem serviços no mês.")

    with c6:
        st.markdown("### Por tipo de orçamento")
        if not mes_df.empty and "tipo_orcamento" in mes_df.columns:
            tipo_df = mes_df.groupby("tipo_orcamento")["valor_total"].sum().reset_index()
            tipo_df["valor_total"] = tipo_df["valor_total"].apply(valor_moeda)
            st.dataframe(tipo_df, use_container_width=True, hide_index=True)
        else:
            st.info("Sem serviços no mês.")

    st.markdown("### Últimos serviços do mês")
    if not mes_df.empty:
        st.dataframe(
            mes_df[["numero", "data", "fornecedor", "centro_custo", "tipo_orcamento", "status", "prioridade", "valor_total"]].head(30),
            use_container_width=True,
            hide_index=True,
        )


def tela_novo_servico():
    st.subheader("🧰 Novo Serviço de Terceiro")
    if st.session_state.perfil not in ["admin", "almoxarifado", "aprovador"]:
        st.warning("Seu perfil possui acesso somente para consulta.")
        return

    fornecedores = carregar_fornecedores()
    if fornecedores.empty:
        st.warning("Cadastre pelo menos um fornecedor antes de criar serviços.")
        return

    with st.form("novo_servico", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        data_servico = c1.date_input("Data do serviço", value=date.today())
        fornecedor_nome = c2.selectbox("Fornecedor", fornecedores.nome.tolist())
        prioridade = c3.selectbox("Prioridade", ["Baixa", "Normal", "Alta", "Urgente"], index=1)

        centro_custo_id = seletor_centro_custo("Centro de custo", key="cc_novo_servico")
        st.caption("O tipo OPEX/CAPEX será puxado automaticamente do orçamento mensal do centro de custo.")

        descricao = st.text_area("Descrição do serviço")
        valor_total = st.number_input("Valor do serviço", min_value=0.0, value=0.0, step=100.0)
        observacao = st.text_area("Observação")
        anexos = st.file_uploader("Anexos do serviço/orçamento", accept_multiple_files=True)

        if st.form_submit_button("Salvar serviço", use_container_width=True):
            if not descricao.strip():
                st.error("Informe a descrição do serviço.")
            elif valor_total <= 0:
                st.error("Informe o valor do serviço.")
            else:
                fornecedor_id = int(fornecedores[fornecedores.nome == fornecedor_nome].id.iloc[0])
                servico_id, numero, tipo_orcamento = criar_servico(
                    data_servico,
                    fornecedor_id,
                    centro_custo_id,
                    descricao,
                    valor_total,
                    prioridade,
                    observacao,
                    st.session_state.usuario,
                )

                adir = Path("shop_data") / "servicos_anexos" / numero
                adir.mkdir(parents=True, exist_ok=True)

                for arq in anexos:
                    dest = adir / arq.name
                    dest.write_bytes(arq.getbuffer())
                    inserir_anexo_servico(servico_id, arq.name, str(dest), st.session_state.usuario)

                msg = mensagem_servico_criado(
                    numero,
                    st.session_state.usuario,
                    fornecedor_nome,
                    valor_moeda(valor_total),
                    prioridade,
                    nome_centro_custo(centro_custo_id),
                    tipo_orcamento,
                )
                notificar_servico("Serviço criado", servico_id, numero, msg, st.session_state.usuario, None, "", True)
                st.success(f"Serviço {numero} cadastrado.")
                st.rerun()


def tela_servicos():
    st.subheader("🧰 Serviços")
    servicos = carregar_servicos()
    if servicos.empty:
        st.info("Nenhum serviço cadastrado.")
        return

    servicos_view = servicos.copy()
    filtros = st.columns(4)
    status_f = filtros[0].selectbox("Status", ["Todos"] + sorted(servicos_view["status"].dropna().unique().tolist()))
    tipo_f = filtros[1].selectbox("Tipo", ["Todos"] + sorted(servicos_view["tipo_orcamento"].dropna().unique().tolist()))
    cc_f = filtros[2].selectbox("Centro de custo", ["Todos"] + sorted(servicos_view["centro_custo"].dropna().unique().tolist()))
    mes_atual = datetime.now().month
    mes_f = filtros[3].selectbox("Mês", ["Todos"] + list(range(1, 13)), index=mes_atual)

    df = servicos_view.copy()
    df["data"] = pd.to_datetime(df["data"], errors="coerce")

    if status_f != "Todos":
        df = df[df["status"] == status_f]
    if tipo_f != "Todos":
        df = df[df["tipo_orcamento"] == tipo_f]
    if cc_f != "Todos":
        df = df[df["centro_custo"] == cc_f]
    if mes_f != "Todos":
        df = df[df["data"].dt.month == int(mes_f)]

    st.dataframe(
        df[["id", "numero", "data", "fornecedor", "centro_custo", "tipo_orcamento", "descricao", "valor_total", "status", "prioridade", "criado_por"]],
        use_container_width=True,
        hide_index=True,
    )

    mapa = {f"ID {int(r.id)} - {r.numero} - {r.fornecedor} - {valor_moeda(float(r.valor_total))}": int(r.id) for r in df.itertuples()}
    if not mapa:
        return

    servico_id = st.selectbox("Selecionar serviço", list(mapa.keys()))
    sid = mapa[servico_id]
    serv = buscar_servico(sid)

    st.markdown("### Detalhes")
    st.write(f"**Número:** {serv['numero']}")
    st.write(f"**Fornecedor:** {serv.get('fornecedor')}")
    st.write(f"**Centro de custo:** {serv.get('centro_custo') or 'Sem centro de custo'}")
    st.write(f"**Tipo:** {serv.get('tipo_orcamento')}")
    st.write(f"**Status:** {serv.get('status')}")
    st.write(f"**Valor:** {valor_moeda(float(serv.get('valor_total') or 0))}")
    st.write(f"**Descrição:** {serv.get('descricao')}")

    anexos = carregar_anexos_servico(sid)
    st.markdown("### Anexos")
    if anexos.empty:
        st.info("Nenhum anexo.")
    else:
        for a in anexos.itertuples():
            p = Path(a.caminho)
            if p.exists():
                with open(p, "rb") as f:
                    st.download_button(f"Baixar {a.nome_arquivo}", f, file_name=a.nome_arquivo, key=f"serv_anexo_{a.id}")

    st.divider()
    st.markdown("### Status")
    c1, c2, c3, c4 = st.columns(4)

    def mudar(ns, legenda):
        alterar_status_servico(sid, ns, st.session_state.usuario)
        msg = mensagem_status_servico(serv["numero"], ns, st.session_state.usuario, serv["prioridade"])
        notificar_servico(f"Status {ns}", sid, serv["numero"], msg, st.session_state.usuario, None, legenda, False)
        if ns == "Aprovado":
            verificar_alerta_orcamento_servico(sid, serv["numero"])
        st.success(f"Serviço marcado como {ns}.")
        st.rerun()

    with c1:
        if st.button("✅ Aprovado", use_container_width=True):
            mudar("Aprovado", f"✅ Serviço {serv['numero']} aprovado")
    with c2:
        if st.button("🧰 Executado", use_container_width=True):
            mudar("Executado", f"🧰 Serviço {serv['numero']} executado")
    with c3:
        if st.button("🏁 Finalizado", use_container_width=True):
            mudar("Finalizado", f"🏁 Serviço {serv['numero']} finalizado")
    with c4:
        if st.button("❌ Cancelado", use_container_width=True):
            mudar("Cancelado", f"❌ Serviço {serv['numero']} cancelado")

    if st.session_state.perfil in ["admin", "aprovador"]:
        if st.button("🗑️ Excluir serviço", use_container_width=True):
            excluir_servico(sid)
            msg = f"🗑️ SERVIÇO EXCLUÍDO\n\nServiço: {serv['numero']}\nExcluído por: {st.session_state.usuario}"
            notificar_servico("Serviço excluído", sid, serv["numero"], msg, st.session_state.usuario)
            st.success("Serviço excluído.")
            st.rerun()


def tela_servicos_integrada():
    criar_tabelas()
    st.subheader("🧰 Serviços de terceiros")
    st.caption("Controle de serviços usando fornecedores, centro de custo, orçamento e notificações do sistema.")

    menu_servicos = st.radio(
        "Menu de serviços",
        ["Dashboard", "Novo Serviço", "Serviços"],
        horizontal=True,
    )

    paginas = {
        "Dashboard": tela_servicos_dashboard,
        "Novo Serviço": tela_novo_servico,
        "Serviços": tela_servicos,
    }

    paginas[menu_servicos]()

def main():
    criar_tabelas(); st.set_page_config(page_title='Gerenciador de Compras',layout='wide')
    if 'logado' not in st.session_state: st.session_state.logado=False
    if 'itens_novo_pedido' not in st.session_state: st.session_state.itens_novo_pedido=[]
    if not st.session_state.logado: tela_login(); st.stop()
    st.sidebar.success(f"Usuário: {st.session_state.nome}")
    st.sidebar.info(f"Perfil: {st.session_state.perfil}")

    if email_configurado():
        st.sidebar.success("E-mail configurado")
    else:
        st.sidebar.warning("E-mail não configurado")

    if telegram_configurado():
        st.sidebar.success("Telegram configurado")
    else:
        st.sidebar.warning("Telegram não configurado")
    if st.sidebar.button('Sair'): st.session_state.clear(); st.rerun()
    st.title('🛒 Gerenciador de Compras')
    menu=st.sidebar.radio('Menu',['Dashboard','Novo Pedido','Pedidos','Notificações','Produtos','Fornecedores','Centro de custo / Orçamento','Configurações'])
    {'Dashboard':tela_dashboard,'Novo Pedido':tela_novo_pedido,'Pedidos':tela_pedidos,'Notificações':tela_notificacoes,'Produtos':tela_produtos,'Fornecedores':tela_fornecedores,'Centro de custo / Orçamento':tela_centros_custo_orcamento,'Configurações':tela_configuracoes}[menu]()
if __name__=='__main__': main()
