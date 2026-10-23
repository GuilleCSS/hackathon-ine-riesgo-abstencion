import streamlit as st

st.set_page_config(page_title="Riesgo territorial de abstención", page_icon="🗺️", layout="wide")

st.navigation([
    st.Page("mapa.py", title="Mapa de riesgo 2027", icon="🗺️", default=True),
    st.Page("datos_anuales.py", title="Datos por año", icon="📊"),
    st.Page("clustering/grupos.py", title="Grupos de secciones", icon="🧩"),
    st.Page("random_forest.py", title="Random Forest M17", icon="🌳"),
    st.Page("semaforo_oscar/comparacion.py", title="Semáforo alternativo (Oscar)", icon="🚦"),
]).run()
