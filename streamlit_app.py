import streamlit as st

sel_options = st.multiselect("Hello", options=["Apple", "Orange"])

st.write(sel_options)