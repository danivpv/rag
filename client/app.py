import os
import requests
import streamlit as st
from dotenv import load_dotenv

# Load environment variables (from .env file)
load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "").strip().rstrip("/")
API_TOKEN = os.getenv("API_TOKEN", "").strip()

# --- Page Config ---
st.set_page_config(
    page_title="Knowledge Base AI Agent",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for aesthetics
st.markdown("""
<style>
    .stTextArea textarea {
        font-size: 16px !important;
        border-radius: 8px !important;
    }
    div[data-testid="stForm"] {
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 20px;
        background-color: #f9f9f9;
    }
    div[data-testid="stExpander"] {
        border-radius: 8px;
    }
    /* Dark mode support */
    @media (prefers-color-scheme: dark) {
        div[data-testid="stForm"] {
            background-color: #1e1e1e;
            border-color: #333;
        }
    }
</style>
""", unsafe_allow_html=True)

st.title("📚 Knowledge Base Agent")
st.markdown("Ask questions against your deployed AWS RAG API. The architecture leverages AWS CDK, API Gateway, and Docker Lambda for production-ready serverless search.")

# --- Config Check ---
if not API_BASE_URL or not API_TOKEN:
    st.error("⚠️ Missing configuration: `API_BASE_URL` or `API_TOKEN` not found in `.env`.")
    st.stop()

# --- API Health Check ---
if "api_health" not in st.session_state:
    try:
        res = requests.get(f"{API_BASE_URL}/health", timeout=5)
        st.session_state.api_health = (res.status_code == 200)
    except Exception:
        st.session_state.api_health = False

if not st.session_state.api_health:
    st.warning("⚠️ The API is currently unreachable. Queries may fail or time out. Please ensure your AWS API is deployed and running.")

# --- Layout ---
left_col, right_col = st.columns([1, 1.2], gap="large")

with left_col:
    st.subheader("💬 Ask the Agent")
    with st.form(key="query_form"):
        question = st.text_area(
            "Enter your question:", 
            placeholder="What is retrieval-augmented generation and why is it useful?", 
            label_visibility="collapsed",
            height=130
        )
        submit_button = st.form_submit_button(label="🔍 Ask Agent", use_container_width=True)
    
    # Placeholder for sources
    sources_container = st.container()

with right_col:
    st.subheader("🤖 Answer")
    answer_container = st.container()
    
    if not submit_button:
        answer_container.info("👋 Welcome! Ask a question on the left to get started. The answer will appear here.")

# --- Logic ---
if submit_button and question:
    with answer_container:
        with st.spinner("Searching knowledge base & generating answer..."):
            try:
                response = requests.post(
                    f"{API_BASE_URL}/query",
                    json={"question": question, "top_k": 5},
                    headers={"x-api-key": API_TOKEN},
                    timeout=35  # Account for Lambda cold starts
                )
                
                if response.status_code == 403:
                    st.error("🚫 403 Forbidden: Invalid API Token. Please check your `.env`.")
                elif response.status_code == 500:
                    st.error("🔥 500 Internal Server Error: The AWS API encountered a problem.")
                elif response.status_code == 200:
                    data = response.json()
                    
                    # Answer
                    st.success("✅ **Done!**")
                    st.markdown(f"#### {data.get('answer', 'No answer generated.')}")
                    
                    st.divider()
                    
                    # Confidence & Metadata in the right column
                    confidence = float(data.get("confidence", 0.0))
                    st.markdown(f"**Confidence Score:** {confidence:.2f}")
                    st.progress(min(max(confidence, 0.0), 1.0))
                    
                    metadata = data.get("metadata", {})
                    if metadata:
                        st.caption(f"**Metadata:** Model: `{metadata.get('model', 'N/A')}` | "
                                   f"Strategy: `{metadata.get('retrieval_strategy', 'N/A')}` | "
                                   f"Latency: `{metadata.get('latency_ms', 'N/A')}ms` | "
                                   f"ReqID: `{metadata.get('request_id', 'N/A')}`")
                                   
                    # Sources in the left column
                    with sources_container:
                        sources = data.get("sources", [])
                        if sources:
                            st.subheader("📚 Recovered Context")
                            for i, src in enumerate(sources, 1):
                                doc_id = src.get("document_id", "Unknown Document")
                                score = src.get("score", 0.0)
                                excerpt = src.get("excerpt", "").strip()
                                with st.expander(f"Source {i}: {doc_id} (Score: {score:.2f})", expanded=(i==1)):
                                    st.markdown(f"> {excerpt}")
                        else:
                            st.info("No sources retrieved for this query.")
                else:
                    st.error(f"⚠️ Unexpected status code: {response.status_code}")
                    st.text(response.text)
                    
            except requests.exceptions.Timeout:
                st.error("⏳ Request timed out. The AWS Lambda might be cold-starting or taking too long.")
            except requests.exceptions.ConnectionError:
                st.error("🔌 Connection error. Could not connect to the API Gateway.")
            except Exception as e:
                st.error(f"❌ An unexpected error occurred: {str(e)}")
elif submit_button and not question:
    answer_container.warning("⚠️ Please enter a question before asking.")
