"""
GDrive Saver — Streamlit frontend.
"""

import os
import sys
import time
import threading
from dataclasses import dataclass
from typing import Optional

import streamlit as st

# ── add project root to path so sibling modules are importable ──────────────
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from utils import extract_file_id, is_folder_url, sanitize_filename
from browser_handler import BrowserHandler
from pdf_builder import PDFBuilder
import config

# ─────────────────────────────────────────────────────────────────────────────
#  Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GDrive Saver",
    page_icon=None,
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
#  Custom CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Background ── */
.stApp {
    background: #0d0f14;
}

/* ── Hide default streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding-top: 3rem;
    padding-bottom: 3rem;
    max-width: 680px;
}

/* ── Hero header ── */
.gs-hero {
    text-align: center;
    margin-bottom: 2.5rem;
}
.gs-wordmark {
    font-size: 2.25rem;
    font-weight: 700;
    letter-spacing: -0.04em;
    color: #ffffff;
    line-height: 1;
}
.gs-wordmark span {
    color: #6c8fff;
}
.gs-tagline {
    margin-top: 0.5rem;
    font-size: 0.9rem;
    font-weight: 400;
    color: #6b7280;
    letter-spacing: 0.01em;
}

/* ── Card ── */
.gs-card {
    background: #161a24;
    border: 1px solid #1f2535;
    border-radius: 16px;
    padding: 2rem;
    box-shadow: 0 4px 40px rgba(0,0,0,0.4);
}

/* ── Input label ── */
.gs-label {
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #6b7280;
    margin-bottom: 0.4rem;
}

/* ── Streamlit text_input override ── */
.stTextInput > div > div > input {
    background: #0d0f14 !important;
    border: 1px solid #1f2535 !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-size: 0.95rem !important;
    padding: 0.75rem 1rem !important;
    transition: border-color 0.2s;
}
.stTextInput > div > div > input:focus {
    border-color: #6c8fff !important;
    box-shadow: 0 0 0 3px rgba(108,143,255,0.12) !important;
    outline: none !important;
}
.stTextInput > div > div > input::placeholder {
    color: #374151 !important;
}
.stTextInput label { display: none !important; }

/* ── Primary button ── */
.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #6c8fff 0%, #4f46e5 100%) !important;
    border: none !important;
    border-radius: 10px !important;
    color: #ffffff !important;
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    padding: 0.75rem 1.5rem !important;
    transition: opacity 0.2s, transform 0.15s !important;
    width: 100% !important;
}
.stButton > button[kind="primary"]:hover {
    opacity: 0.88 !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"]:active {
    transform: translateY(0) !important;
}
.stButton > button[kind="primary"]:disabled {
    opacity: 0.35 !important;
    cursor: not-allowed !important;
    transform: none !important;
}

/* ── Secondary / reset button ── */
.stButton > button[kind="secondary"],
.stButton > button[data-testid="baseButton-secondary"] {
    background: transparent !important;
    border: 1px solid #1f2535 !important;
    border-radius: 10px !important;
    color: #9ca3af !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    width: 100% !important;
    transition: border-color 0.2s, color 0.2s !important;
}
.stButton > button[kind="secondary"]:hover {
    border-color: #374151 !important;
    color: #e2e8f0 !important;
}

/* ── Download button ── */
.stDownloadButton > button {
    background: #161a24 !important;
    border: 1px solid #6c8fff !important;
    border-radius: 10px !important;
    color: #6c8fff !important;
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    padding: 0.75rem 1.5rem !important;
    width: 100% !important;
    transition: background 0.2s, color 0.2s !important;
}
.stDownloadButton > button:hover {
    background: #6c8fff !important;
    color: #ffffff !important;
}

/* ── Progress bar ── */
.stProgress > div > div {
    background: #1f2535 !important;
    border-radius: 99px !important;
    height: 6px !important;
}
.stProgress > div > div > div {
    background: linear-gradient(90deg, #6c8fff, #4f46e5) !important;
    border-radius: 99px !important;
}

/* ── Status area ── */
.gs-status-box {
    background: #0d0f14;
    border: 1px solid #1f2535;
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin: 0.75rem 0;
}
.gs-status-text {
    font-size: 0.85rem;
    color: #9ca3af;
    font-weight: 400;
}
.gs-status-hint {
    font-size: 0.78rem;
    color: #374151;
    margin-top: 0.3rem;
}

/* ── Success state ── */
.gs-result {
    background: #0d1a12;
    border: 1px solid #166534;
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin: 0.75rem 0;
}
.gs-result-title {
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #22c55e;
    margin-bottom: 0.2rem;
}
.gs-result-filename {
    font-size: 0.9rem;
    color: #e2e8f0;
    font-weight: 500;
    word-break: break-all;
}

/* ── Error state ── */
.gs-error {
    background: #1a0d0d;
    border: 1px solid #7f1d1d;
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin: 0.75rem 0;
}
.gs-error-label {
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #ef4444;
    margin-bottom: 0.2rem;
}
.gs-error-msg {
    font-size: 0.88rem;
    color: #fca5a5;
    font-weight: 400;
}

/* ── Divider ── */
.gs-divider {
    height: 1px;
    background: #1f2535;
    margin: 1.5rem 0;
}

/* ── Guide in sidebar ── */
section[data-testid="stSidebar"] {
    background: #0d0f14 !important;
    border-right: 1px solid #1f2535 !important;
}
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #e2e8f0;
    font-size: 0.9rem;
    font-weight: 600;
}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] li {
    color: #6b7280;
    font-size: 0.83rem;
    line-height: 1.7;
}
section[data-testid="stSidebar"] strong {
    color: #9ca3af;
}
section[data-testid="stSidebar"] code {
    background: #161a24;
    border: 1px solid #1f2535;
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 0.8rem;
    color: #6c8fff;
}

/* ── Streamlit info/warning/success/error overrides ── */
.stAlert { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  Session state schema
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class AppState:
    running: bool = False
    phase: str = "idle"       # "idle" | "running" | "done" | "error"
    progress: float = 0.0
    status_msg: str = ""
    error: Optional[str] = None
    pdf_bytes: Optional[bytes] = None
    pdf_filename: str = "document.pdf"


def _init_state():
    if "app" not in st.session_state:
        st.session_state.app = AppState()


_init_state()
state: AppState = st.session_state.app

# ─────────────────────────────────────────────────────────────────────────────
#  Background worker
# ─────────────────────────────────────────────────────────────────────────────
def _make_progress_cb(base: float, span: float):
    def _cb(current: int, total: int, msg: str):
        state.status_msg = msg
        fraction = current / max(total, 1)
        state.progress = base + span * fraction
    return _cb


def _run_download(url: str):
    """Full download pipeline — executes in a background thread."""
    browser = BrowserHandler()
    builder = PDFBuilder()

    tmp_dir = os.path.join(ROOT_DIR, ".tmp_dl")
    config.TEMP_DIR = os.path.join(ROOT_DIR, ".tmp_cache")
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(config.TEMP_DIR, exist_ok=True)

    try:
        state.status_msg = "Đang phân tích link..."
        state.progress = 0.05

        is_folder = is_folder_url(url)
        browser.start()

        if is_folder:
            state.status_msg = "Đang quét thư mục..."
            state.progress = 0.10
            files_data = browser.get_folder_file_ids(url)
            if not files_data:
                browser.close()
                state.error = "Không tìm thấy file trong thư mục hoặc thư mục bị khoá."
                state.phase = "error"
                return
            fid, title = files_data[0]
            view_url = f"https://drive.google.com/file/d/{fid}/view"
        else:
            state.status_msg = "Đang lấy ID tài liệu..."
            state.progress = 0.10
            file_id = extract_file_id(url)
            view_url = f"https://drive.google.com/file/d/{file_id}/view"
            title = None

        state.status_msg = "Đang mở tài liệu trong trình duyệt..."
        state.progress = 0.20
        if not browser.open_file(view_url):
            browser.close()
            state.error = (
                "Không thể truy cập tài liệu. "
                "File có thể yêu cầu đăng nhập Google."
            )
            state.phase = "error"
            return

        if not title:
            title = browser.get_file_title()

        state.status_msg = "Đang tải toàn bộ trang..."
        state.progress = 0.30
        total_pages = browser.get_total_pages()
        browser.scroll_through_all_pages(
            total_pages,
            progress_callback=_make_progress_cb(base=0.30, span=0.35),
        )

        state.status_msg = "Đang trích xuất hình ảnh chất lượng cao..."
        state.progress = 0.65
        images = browser.capture_page_images(
            total_pages,
            progress_callback=_make_progress_cb(base=0.65, span=0.25),
        )
        browser.close()

        if not images:
            state.error = "Không thể lấy được hình ảnh nào từ tài liệu."
            state.phase = "error"
            return

        state.status_msg = "Đang đóng gói PDF..."
        state.progress = 0.90
        safe_title = sanitize_filename(title)
        pdf_path = os.path.join(tmp_dir, f"{safe_title}.pdf")

        if builder.build_pdf(images, pdf_path):
            with open(pdf_path, "rb") as f:
                state.pdf_bytes = f.read()
            state.pdf_filename = f"{safe_title}.pdf"
            try:
                os.remove(pdf_path)
            except OSError:
                pass
            state.progress = 1.0
            state.status_msg = "Hoàn tất!"
            state.phase = "done"
        else:
            state.error = "Lỗi trong quá trình tạo file PDF."
            state.phase = "error"

    except Exception as exc:
        state.error = str(exc)
        state.phase = "error"
        try:
            browser.close()
        except Exception:
            pass
    finally:
        state.running = False


# ─────────────────────────────────────────────────────────────────────────────
#  UI
# ─────────────────────────────────────────────────────────────────────────────

# Hero
st.markdown("""
<div class="gs-hero">
    <div class="gs-wordmark">GDrive<span>Saver</span></div>
    <div class="gs-tagline">Chuyển tài liệu View-only thành PDF chất lượng cao</div>
</div>
""", unsafe_allow_html=True)

# Card
st.markdown('<div class="gs-card">', unsafe_allow_html=True)

st.markdown('<div class="gs-label">Link Google Drive</div>', unsafe_allow_html=True)
url_input = st.text_input(
    label="url",
    placeholder="https://drive.google.com/file/d/...  hoặc  /drive/folders/...",
    disabled=state.running,
    label_visibility="collapsed",
)

st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

start_btn = st.button(
    "Bắt đầu tải xuống",
    type="primary",
    disabled=state.running or not url_input.strip(),
    use_container_width=True,
    key="start_btn",
)

# ── Progress ──────────────────────────────────────────────────────────────────
if state.phase == "running":
    st.markdown('<div class="gs-divider"></div>', unsafe_allow_html=True)
    st.progress(state.progress)
    st.markdown(f"""
<div class="gs-status-box">
    <div class="gs-status-text">{state.status_msg or "Đang xử lý..."}</div>
    <div class="gs-status-hint">Trình duyệt đang chạy ngầm — vui lòng không đóng trang</div>
</div>
""", unsafe_allow_html=True)

# ── Error ──────────────────────────────────────────────────────────────────────
if state.phase == "error" and state.error:
    st.markdown('<div class="gs-divider"></div>', unsafe_allow_html=True)
    st.markdown(f"""
<div class="gs-error">
    <div class="gs-error-label">Đã xảy ra lỗi</div>
    <div class="gs-error-msg">{state.error}</div>
</div>
""", unsafe_allow_html=True)
    if st.button("Thử lại", key="retry_btn"):
        st.session_state.app = AppState()
        st.rerun()

# ── Done ───────────────────────────────────────────────────────────────────────
if state.phase == "done" and state.pdf_bytes:
    st.markdown('<div class="gs-divider"></div>', unsafe_allow_html=True)
    st.progress(1.0)
    st.markdown(f"""
<div class="gs-result">
    <div class="gs-result-title">Sẵn sàng tải xuống</div>
    <div class="gs-result-filename">{state.pdf_filename}</div>
</div>
""", unsafe_allow_html=True)
    st.download_button(
        label="Tải file PDF",
        data=state.pdf_bytes,
        file_name=state.pdf_filename,
        mime="application/pdf",
        use_container_width=True,
        key="download_btn",
    )
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    if st.button("Tải file mới", key="reset_btn"):
        st.session_state.app = AppState()
        st.rerun()

st.markdown('</div>', unsafe_allow_html=True)  # end .gs-card

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Hướng dẫn sử dụng")
    st.markdown("""
1. Dán link Google Drive dạng **View-only** vào ô nhập.
2. Nhấn **Bắt đầu tải xuống**.
3. Đợi trình duyệt ảo cuộn qua toàn bộ tài liệu *(khoảng 1 – 3 phút tuỳ độ dài file)*.
4. Nhấn **Tải file PDF** khi hoàn tất.

---

**Hỗ trợ:**
- Link file đơn lẻ (`/file/d/...`)
- Link thư mục (`/drive/folders/...`) — lấy file đầu tiên

**Giới hạn:**
- File yêu cầu đăng nhập Google sẽ không tải được.
""")

# ── Start download ─────────────────────────────────────────────────────────────
if start_btn and url_input.strip():
    state.running = True
    state.phase = "running"
    state.progress = 0.0
    state.status_msg = "Đang khởi động..."
    state.error = None
    state.pdf_bytes = None
    state.pdf_filename = "document.pdf"

    thread = threading.Thread(target=_run_download, args=(url_input.strip(),), daemon=True)
    thread.start()
    st.rerun()

# ── Polling loop — keep UI live while worker thread runs ───────────────────────
if state.phase == "running":
    time.sleep(2)
    st.rerun()
