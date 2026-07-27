"""
GDrive Saver — Streamlit frontend.
Replaces the old FastAPI + static HTML setup.
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
    page_icon="📥",
    layout="centered",
)

# ─────────────────────────────────────────────────────────────────────────────
#  Session state schema
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class AppState:
    running: bool = False
    # "idle" | "running" | "done" | "error"
    # Used to avoid blank-screen flash between running→done transition.
    phase: str = "idle"
    progress: float = 0.0          # 0.0 – 1.0
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
    """
    Returns a callback that maps [0, total] → [base, base+span]
    so each phase occupies its own slice of the full 0–1 bar.
    """
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
        # ── 1. Resolve URL ────────────────────────────────────────────────
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
            # ponytail: chỉ xử lý file đầu tiên trong thư mục cho demo web.
            fid, title = files_data[0]
            view_url = f"https://drive.google.com/file/d/{fid}/view"
        else:
            state.status_msg = "Đang lấy ID tài liệu..."
            state.progress = 0.10
            file_id = extract_file_id(url)
            view_url = f"https://drive.google.com/file/d/{file_id}/view"
            title = None

        # ── 2. Open file ──────────────────────────────────────────────────
        state.status_msg = "Đang mở tài liệu trong Chrome..."
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

        # ── 3. Scroll all pages (30% → 65%) ──────────────────────────────
        state.status_msg = "Đang tải toàn bộ trang..."
        state.progress = 0.30
        total_pages = browser.get_total_pages()
        browser.scroll_through_all_pages(
            total_pages,
            progress_callback=_make_progress_cb(base=0.30, span=0.35),
        )

        # ── 4. Capture images (65% → 90%) ─────────────────────────────────
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

        # ── 5. Build PDF (90% → 100%) ─────────────────────────────────────
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
st.title("GDrive Saver")
st.caption("Tải file Google Drive dạng View-only về dạng PDF chất lượng cao.")

st.divider()

url_input = st.text_input(
    "Link Google Drive",
    placeholder="https://drive.google.com/file/d/...",
    disabled=state.running,
)

start_btn = st.button(
    "Tải xuống",
    type="primary",
    disabled=state.running or not url_input.strip(),
    use_container_width=True,
)

if start_btn and url_input.strip():
    # Reset state for a fresh run
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

# ── Progress display ──────────────────────────────────────────────────────────
if state.phase == "running":
    st.progress(state.progress, text=state.status_msg)
    st.info("Chrome đang chạy ngầm. Vui lòng không đóng trang này.")
    # Poll every 2 s — avoids busy-loop CPU spike while keeping UI responsive
    time.sleep(2)
    st.rerun()

# ── Result ────────────────────────────────────────────────────────────────────
if state.phase == "error" and state.error:
    st.error(f"Lỗi: {state.error}")
    if st.button("Thử lại"):
        st.session_state.app = AppState()
        st.rerun()

if state.phase == "done" and state.pdf_bytes:
    st.progress(1.0, text="Hoàn tất!")
    st.success(f"File: **{state.pdf_filename}**")
    st.download_button(
        label="Tải file PDF",
        data=state.pdf_bytes,
        file_name=state.pdf_filename,
        mime="application/pdf",
        use_container_width=True,
    )
    if st.button("Tải file mới"):
        st.session_state.app = AppState()
        st.rerun()

# ── Sidebar info ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Hướng dẫn")
    st.markdown("""
1. Dán link Google Drive dạng **View-only** vào ô trên.
2. Bấm **Tải xuống**.
3. Đợi Chrome ảo cuộn qua toàn bộ tài liệu (có thể mất 1–3 phút tuỳ độ dài file).
4. Bấm **Tải file PDF** khi hoàn tất.

---

**Lưu ý:**
- Hỗ trợ link file đơn lẻ và link thư mục (sẽ lấy file đầu tiên).
- File yêu cầu đăng nhập Google sẽ không tải được (cần cấu hình `CHROME_USER_DATA_DIR` trong `config.py`).
""")
    st.divider()
    st.caption("Chạy bằng: `streamlit run app.py`")
