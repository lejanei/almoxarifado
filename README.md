# StockPro Almoxarifado - versão v5

## O que foi lapidado
- identidade visual nova
- logo em SVG incluso na pasta `assets`
- cabeçalho com branding
- tela de login mais refinada
- sidebar personalizada
- visual geral mais profissional

## Como rodar
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud
Adicione em Secrets:
```toml
ALMOXARIFADO_URL = "mysql+pymysql://USUARIO:SENHA@HOST/BANCO?charset=utf8mb4"
```
