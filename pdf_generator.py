from pathlib import Path
import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from database import buscar_pedido, carregar_anexos_pedido, carregar_itens_pedido
from utils import emoji_prioridade, emoji_status, link_pedido, valor_moeda

def gerar_pdf_pedido(id_pedido):
    pedido=buscar_pedido(id_pedido)
    if pedido is None: return None
    itens=carregar_itens_pedido(id_pedido); anexos=carregar_anexos_pedido(id_pedido)
    pdf_dir=Path('shop_data')/'pdfs'; qr_dir=Path('shop_data')/'qrcodes'; assets=Path('assets')
    pdf_dir.mkdir(exist_ok=True); qr_dir.mkdir(exist_ok=True); assets.mkdir(exist_ok=True)
    numero=pedido['numero']; pdf_path=pdf_dir/f'pedido_{numero}.pdf'
    doc=SimpleDocTemplate(str(pdf_path),pagesize=A4,rightMargin=16*mm,leftMargin=16*mm,topMargin=14*mm,bottomMargin=14*mm)
    styles=getSampleStyleSheet(); styles.add(ParagraphStyle(name='Small', parent=styles['BodyText'], fontSize=8, leading=10))
    el=[]; logo=assets/'logo.png'
    title=Paragraph(f"<b>ORDEM DE COMPRA</b><br/><font size='12'>{numero}</font>", styles['Title'])
    if logo.exists(): header=Table([[Image(str(logo), width=36*mm, height=22*mm), title]], colWidths=[45*mm,125*mm])
    else: header=Table([['', title]], colWidths=[45*mm,125*mm])
    header.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(1,0),(1,0),'CENTER'),('BOTTOMPADDING',(0,0),(-1,-1),10)])); el.append(header)
    status=pedido['status'] or 'Aberto'; prioridade=pedido['prioridade'] or 'Normal'
    dados=[['Data',pedido['data'],'Status',f'{emoji_status(status)} {status}'],['Prioridade',f'{emoji_prioridade(prioridade)} {prioridade}','Solicitante',pedido['criado_por'] or ''],['Aprovado por',pedido['aprovado_por'] or '-','Data aprovação',pedido['data_aprovacao'] or '-'],['Comprado por',pedido['comprado_por'] or '-','Data compra',pedido['data_compra'] or '-'],['Recebido por',pedido['recebido_por'] or '-','Data recebimento',pedido['data_recebimento'] or '-']]
    tab=Table(dados,colWidths=[30*mm,55*mm,32*mm,58*mm]); tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.whitesmoke),('GRID',(0,0),(-1,-1),0.3,colors.lightgrey),('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),('FONTNAME',(2,0),(2,-1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8)])); el += [tab, Spacer(1,12)]
    dados=[['Código','Produto','Un.','Qtd','Valor Unit.','Valor Total']]; total=0
    for _,i in itens.iterrows():
        t=float(i['quantidade'])*float(i['valor_unitario']); total+=t
        dados.append([i['codigo'] or '',i['produto'] or '',i['unidade'] or '',str(i['quantidade']),valor_moeda(i['valor_unitario']),valor_moeda(t)])
    tab=Table(dados,colWidths=[28*mm,60*mm,16*mm,18*mm,29*mm,29*mm]); tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1F4E78')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('GRID',(0,0),(-1,-1),0.5,colors.black),('BACKGROUND',(0,1),(-1,-1),colors.whitesmoke),('FONTSIZE',(0,0),(-1,-1),8)])); el += [tab, Spacer(1,12), Paragraph(f"<b>VALOR TOTAL DO PEDIDO: {valor_moeda(total)}</b>", styles['Heading2']), Spacer(1,10)]
    if not anexos.empty:
        el.append(Paragraph('<b>Anexos da compra:</b>', styles['Heading3']))
        el.append(Paragraph('<br/>'.join([f'• {r.nome_arquivo} - {r.enviado_por} em {r.data_envio}' for r in anexos.itertuples()]), styles['Small'])); el.append(Spacer(1,10))
    el.append(Paragraph('<b>Observações / Histórico:</b>', styles['Heading3'])); el.append(Paragraph((pedido['observacao'] or '').replace('\n','<br/>'), styles['Small'])); el.append(Spacer(1,12))
    qr=qrcode.make(link_pedido(pedido['id'])); qr_path=qr_dir/f'qr_{numero}.png'; qr.save(qr_path)
    footer=Table([[Image(str(qr_path), width=28*mm, height=28*mm), Paragraph(f"<b>Link do pedido:</b><br/>{link_pedido(pedido['id'])}", styles['Small'])],['__________________________','__________________________'],['Solicitante','Aprovador']], colWidths=[60*mm,105*mm])
    footer.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(0,1),(-1,2),'CENTER'),('TOPPADDING',(0,1),(-1,1),18)])); el.append(footer)
    doc.build(el); return pdf_path
