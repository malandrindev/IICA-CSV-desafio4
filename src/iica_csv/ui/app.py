"""Ponto de entrada inicial da interface Streamlit."""

import streamlit as st


st.set_page_config(page_title="IICA-CSV", page_icon="📊", layout="wide")
st.title("IICA-CSV — Consulta inteligente de arquivos CSV")
st.caption("Estrutura inicial do Desafio 4 — MVP em desenvolvimento")

uploaded_file = st.file_uploader(
    "Envie um ZIP com um ou mais CSVs e o respectivo dicionário de dados",
    type=["zip"],
)

if uploaded_file is None:
    st.info("Envie um arquivo ZIP para iniciar. Nenhum dado de exemplo acompanha o projeto.")
else:
    st.success(f"Arquivo recebido: {uploaded_file.name}")
    st.warning("O processamento e a consulta serão implementados nas próximas tarefas do MVP.")
