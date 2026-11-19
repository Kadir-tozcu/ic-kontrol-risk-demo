from pathlib import Path
from tempfile import TemporaryDirectory
import streamlit as st


def directory():
    if "_demo_directory" not in st.session_state:
        st.session_state["_demo_directory"] = TemporaryDirectory(prefix="risk-demo-")
    return Path(st.session_state["_demo_directory"].name)


def tenant():
    return st.session_state.get("_demo_tenant", "default")


def set_tenant(value):
    st.session_state["_demo_tenant"] = str(value or "default")
