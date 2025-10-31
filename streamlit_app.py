import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import io
import time

def safe_rerun():
    try:
        # tenta usar API oficial (se existir)
        st.experimental_rerun()
    except Exception:
        # fallback: altera query params para forçar reload no navegador
        try:
            params = st.experimental_get_query_params()
            params["_rerun"] = str(int(time.time()))
            st.experimental_set_query_params(**params)
            st.stop()
        except Exception:
            # último recurso: atualiza token na session_state e para execução
            st.session_state.setdefault("_force_rerun_token", 0)
            st.session_state["_force_rerun_token"] += 1
            st.stop()

st.set_page_config(layout="wide", page_title="Painel de Métricas - Semáforo")

# Para startar o Streamlit execute no terminal:streamlit run streamlit_app.py

PROJECT_CSV = Path(r"metrics.csv")

st.title("Painel de Métricas — Simulador de Semáforo")
st.markdown("Visualize métricas gravadas em metrics.csv (tempo simulado, filas, prioridade, etc).")

# Sidebar: escolher arquivo ou upload
st.sidebar.header("Fonte de dados")
uploaded = st.sidebar.file_uploader("Enviar CSV (opcional)", type=["csv"])
use_project_file = False
if uploaded is None:
    if PROJECT_CSV.exists():
        use_project_file = st.sidebar.checkbox(f"Usar {PROJECT_CSV.name}", value=True)
    else:
        st.sidebar.info("Arquivo metrics.csv não encontrado no diretório do projeto.")
else:
    st.sidebar.success("Arquivo carregado via upload")

# Novo: controles de atualização
st.sidebar.header("Atualização")
if st.sidebar.button("Atualizar agora"):
    st.rerun()
auto_refresh = st.sidebar.checkbox("Auto atualizar (a cada N s)", value=False)
auto_interval = st.sidebar.number_input("Intervalo auto-atualização (s)", min_value=1, value=5, step=1)

# Carregar DataFrame
@st.cache_data
def load_df(uploaded_file, use_project, project_mtime):
    """
    project_mtime é apenas para invalidar o cache automaticamente quando o arquivo local mudar.
    """
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
    elif use_project:
        df = pd.read_csv(PROJECT_CSV)
    else:
        return None
    # parse types
    if "timestamp" in df.columns:
        try:
            df["timestamp_dt"] = pd.to_datetime(df["timestamp"], unit="s")
        except Exception:
            df["timestamp_dt"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if "sim_time_s" in df.columns:
        df["sim_time_s"] = pd.to_numeric(df["sim_time_s"], errors="coerce")
    # numeric conversions
    for col in ["cars_alive","total_spawned","cars_exited","waiting_v","waiting_h"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "priority" in df.columns:
        df["priority"] = pd.to_numeric(df["priority"], errors="coerce")
    return df

# passa mtime para invalidar cache quando o arquivo mudar
project_mtime = None
if use_project_file and PROJECT_CSV.exists():
    try:
        project_mtime = PROJECT_CSV.stat().st_mtime
    except Exception:
        project_mtime = None

# Auto-refresh simples: dispara um rerun quando o tempo desde o último run excede o intervalo
if auto_refresh:
    if 'last_auto_refresh' not in st.session_state:
        st.session_state['last_auto_refresh'] = 0.0
    if time.time() - st.session_state['last_auto_refresh'] > float(auto_interval):
        st.session_state['last_auto_refresh'] = time.time()
        st.rerun()

df = load_df(uploaded, use_project_file, project_mtime)
if df is None or df.empty:
    st.warning("Nenhum dado disponível. Carregue um CSV ou habilite o metrics.csv do projeto na sidebar.")
    st.stop()

# Filtros de tempo
st.sidebar.header("Filtros")
if "timestamp" in df.columns and df["timestamp"].notna().any():
    tmin = df["timestamp"].min()
    tmax = df["timestamp"].max()
    timerange = st.sidebar.slider("Intervalo de tempo (timestamp)", value=(tmin, tmax), min_value=tmin, max_value=tmax)
    df = df[(df["timestamp"] >= timerange[0]) & (df["timestamp"] <= timerange[1])]
else:
    smin = float(df["sim_time_s"].min())
    smax = float(df["sim_time_s"].max())
    sim_range = st.sidebar.slider("Intervalo de tempo (sim_time_s)", value=(smin, smax), min_value=smin, max_value=smax)
    df = df[(df["sim_time_s"] >= sim_range[0]) & (df["sim_time_s"] <= sim_range[1])]

# Rolling window
st.sidebar.header("Visualização")
roll = st.sidebar.slider("Janela média móvel (s)", min_value=0, max_value=30, value=5, step=1)

# KPIs
col1, col2, col3, col4 = st.columns(4)
last = df.iloc[-1]
col1.metric("Cars vivos", int(last.get("cars_alive", 0)))
col2.metric("Total gerados", int(last.get("total_spawned", 0)))
col3.metric("Cars saídos", int(last.get("cars_exited", 0)))
col4.metric("Prioridade (últ.)", f"{last.get('priority', 0):.2f}")

# Gráficos
st.markdown("### Séries temporais")
time_col = "timestamp_dt" if "timestamp_dt" in df.columns and df["timestamp_dt"].notna().any() else "sim_time_s"

# prepare series with rolling
plot_df = df.copy()
if roll > 0:
    # compute rolling based on index spacing; assume rows ~1s, so use rolling on window=roll
    plot_df["waiting_v_roll"] = plot_df["waiting_v"].rolling(window=max(1, int(roll))).mean()
    plot_df["waiting_h_roll"] = plot_df["waiting_h"].rolling(window=max(1, int(roll))).mean()
    plot_df["priority_roll"] = plot_df["priority"].rolling(window=max(1, int(roll))).mean()
else:
    plot_df["waiting_v_roll"] = plot_df["waiting_v"]
    plot_df["waiting_h_roll"] = plot_df["waiting_h"]
    plot_df["priority_roll"] = plot_df["priority"]

# Waiting V/H
fig1 = px.line(plot_df, x=time_col, y=["waiting_v_roll","waiting_h_roll"],
               labels={time_col:"Tempo", "value":"Carros na fila", "variable":"Via"},
               title="Tamanho da fila (média móvel)")
st.plotly_chart(fig1, use_container_width=True)

# Priority
fig2 = px.line(plot_df, x=time_col, y="priority_roll", labels={time_col:"Tempo", "priority_roll":"Prioridade"}, title="Prioridade Fuzzy (média móvel)")
st.plotly_chart(fig2, use_container_width=True)

# Cars alive and throughput
fig3 = px.line(plot_df, x=time_col, y=["cars_alive","cars_exited"], labels={time_col:"Tempo", "value":"Contagem", "variable":"Métrica"}, title="Crescimento: vivos e saídos")
st.plotly_chart(fig3, use_container_width=True)

# Estatísticas resumidas
st.markdown("### Estatísticas resumidas")
st.dataframe(pd.DataFrame({
    "Métrica":["waiting_v_mean","waiting_h_mean","priority_mean","throughput_total"],
    "Valor":[
        plot_df["waiting_v"].mean(),
        plot_df["waiting_h"].mean(),
        plot_df["priority"].mean(),
        int(plot_df["cars_exited"].max() if "cars_exited" in plot_df.columns else 0)
    ]
}).set_index("Métrica"))

# Download dos dados filtrados
st.markdown("### Exportar dados")
buffer = io.StringIO()
plot_df.to_csv(buffer, index=False)
st.download_button("Baixar CSV filtrado", buffer.getvalue(), file_name="metrics_filtered.csv", mime="text/csv")

st.markdown("Feito com Streamlit — ative/mande o CSV correto se quiser ajustes nos gráficos.")