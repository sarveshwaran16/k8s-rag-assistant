# pyrefly: ignore [missing-import]
import streamlit as st
import requests
import time

API_URL = "http://localhost:8000"

st.set_page_config(page_title="K8s Troubleshooting Assistant", page_icon="🛠️", layout="centered")

st.title("🛠️ Kubernetes Troubleshooting Assistant")
st.caption("Local Hybrid RAG — ChromaDB + Neo4j + Ollama (phi3:mini)")

query = st.text_input("Ask a Kubernetes question:", placeholder="Why is my pod in CrashLoopBackOff?")

if st.button("Ask", type="primary") and query.strip():
    with st.spinner("Searching knowledge base and generating answer... (may take a few minutes on CPU)"):
        start = time.time()
        try:
            resp = requests.post(f"{API_URL}/query", json={"query": query}, timeout=600)
            resp.raise_for_status()
            result = resp.json()
            elapsed = round(time.time() - start, 1)

            st.markdown(f"### Answer _(response time: {elapsed}s)_")
            st.write(result["answer"])

            with st.expander(f"📚 Sources ({len(result['sources'])})"):
                for s in result["sources"]:
                    st.markdown(f"- **{s['title']}** ({s['source']}) — relevance: {s['relevance_score']}")
                    if s["source_url"]:
                        st.markdown(f"  [{s['source_url']}]({s['source_url']})")

        except Exception as e:
            st.error(f"Error: {e}")