"""Community Cloud entry point."""
import runpy
import streamlit as st

if st.query_params.get("view") == "classic":
    runpy.run_module("classic", run_name="__main__")
else:
    runpy.run_module("suite.application", run_name="__main__")
