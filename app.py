"""
GDrive Saver — Streamlit frontend.
Tab 1: tải file View-only từ Google Drive về PDF.
Tab 2: nén file PDF.
"""

import os
import sys
import time
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
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
#  Custom CSS — Eye-Friendly Soft Zinc Theme
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    -webkit-font-smoothing: antialiased;
    color: #f4f4f5;
}

/* ── Soft Dark Background (Eye-Friendly Zinc Theme) ── */
.stApp {
    background-color: #18181b !important;
}

#MainMenu, footer, header { visibility: hidden; }
.block-container {
    padding-top: 2.5rem;
    padding-bottom: 3.5rem;
    max-width: 640px;
}

/* ── Minimal Soft Hero Header ── */
.gs-hero {
    margin-bottom: 1.6rem;
}
.gs-badge-header {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 99px;
    background: rgba(99, 102, 241, 0.1);
    border: 1px solid rgba(99, 102, 241, 0.2);
    color: #a5b4fc;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.5rem;
}
.gs-wordmark {
    font-size: 2.2rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: #f4f4f5;
    line-height: 1.2;
}
.gs-wordmark span {
    color: #818cf8;
}
.gs-tagline {
    margin-top: 0.35rem;
    font-size: 0.9rem;
    color: #a1a1aa;
    font-weight: 400;
}

/* ── Soft Tab Bar ── */
.stTabs [data-baseweb="tab-list"] {
    background: #27272a !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 4px !important;
    border: 1px solid #3f3f46 !important;
    margin-bottom: 1.5rem !important;
    display: flex !important;
    width: 100% !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.65rem 1.1rem !important;
    flex: 1 !important;
    justify-content: center !important;
    transition: all 0.2s ease !important;
    cursor: pointer !important;
}
.stTabs [data-baseweb="tab"] *,
.stTabs [data-baseweb="tab"] p,
.stTabs [data-baseweb="tab"] span,
.stTabs [data-baseweb="tab"] div {
    color: #a1a1aa !important;
    font-size: 0.9rem !important;
    font-weight: 600 !important;
}
.stTabs [data-baseweb="tab"]:hover {
    background: rgba(255, 255, 255, 0.04) !important;
}
.stTabs [data-baseweb="tab"]:hover * {
    color: #e4e4e7 !important;
}
.stTabs [aria-selected="true"] {
    background: #3f3f46 !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2) !important;
}
.stTabs [aria-selected="true"] *,
.stTabs [aria-selected="true"] p,
.stTabs [aria-selected="true"] span,
.stTabs [aria-selected="true"] div {
    color: #ffffff !important;
    font-weight: 700 !important;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none !important; }

/* ── Clean Card Container ── */
.gs-card {
    background: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 16px;
    padding: 1.8rem;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

/* ── Field Labels ── */
.gs-label {
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: #e4e4e7 !important;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.gs-label-tag {
    font-size: 0.72rem;
    color: #71717a;
    font-weight: 400;
    text-transform: none;
}

/* ── Form Inputs ── */
.stTextInput > div > div > input {
    background: #18181b !important;
    border: 1px solid #3f3f46 !important;
    border-radius: 10px !important;
    color: #f4f4f5 !important;
    font-size: 0.92rem !important;
    padding: 0.75rem 1rem !important;
}
.stTextInput > div > div > input:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15) !important;
    outline: none !important;
}
.stTextInput > div > div > input::placeholder {
    color: #71717a !important;
}
.stTextInput label { display: none !important; }

/* ── File Uploader ── */
[data-testid="stFileUploader"],
[data-testid="stFileUploaderDropzone"] {
    background: #18181b !important;
    border: 1.5px dashed #3f3f46 !important;
    border-radius: 10px !important;
    color: #f4f4f5 !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: #6366f1 !important;
    background: #202024 !important;
}
[data-testid="stFileUploader"] p,
[data-testid="stFileUploader"] span,
[data-testid="stFileUploaderDropzoneInstructions"] {
    color: #d4d4d8 !important;
    font-size: 0.88rem !important;
}
[data-testid="stFileUploader"] button {
    background: #27272a !important;
    border: 1px solid #3f3f46 !important;
    border-radius: 6px !important;
    color: #f4f4f5 !important;
}

/* ── Radio & Select ── */
.stRadio label,
.stRadio [data-testid="stMarkdownContainer"] p {
    font-size: 0.88rem !important;
    color: #e4e4e7 !important;
}
.stSelectbox [data-baseweb="select"] > div {
    background: #18181b !important;
    border-color: #3f3f46 !important;
    border-radius: 10px !important;
    color: #f4f4f5 !important;
}

/* ── Soft Primary Button ── */
.stButton > button[kind="primary"] {
    background: #4f46e5 !important;
    border: none !important;
    border-radius: 10px !important;
    color: #ffffff !important;
    font-size: 0.92rem !important;
    font-weight: 600 !important;
    padding: 0.75rem 1.4rem !important;
    width: 100% !important;
    transition: all 0.2s ease !important;
}
.stButton > button[kind="primary"]:hover {
    background: #4338ca !important;
}
.stButton > button[kind="primary"]:disabled {
    background: #27272a !important;
    color: #71717a !important;
    border: 1px solid #3f3f46 !important;
    opacity: 0.6 !important;
    cursor: not-allowed !important;
}

/* ── Download Button ── */
.stDownloadButton > button {
    background: #4f46e5 !important;
    border: none !important;
    border-radius: 10px !important;
    color: #ffffff !important;
    font-size: 0.92rem !important;
    font-weight: 600 !important;
    padding: 0.75rem 1.4rem !important;
    width: 100% !important;
}
.stDownloadButton > button:hover {
    background: #4338ca !important;
}

/* ── Progress Bar ── */
.stProgress > div > div {
    background: #18181b !important;
    border-radius: 99px !important;
    height: 6px !important;
}
.stProgress > div > div > div {
    background: #6366f1 !important;
    border-radius: 99px !important;
}

/* ── Soft Custom Boxes ── */
.gs-status-box {
    background: #18181b;
    border: 1px solid #3f3f46;
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin: 0.8rem 0;
}
.gs-status-badge {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    background: rgba(99, 102, 241, 0.15);
    color: #a5b4fc;
}
.gs-status-text {
    font-size: 0.9rem;
    color: #f4f4f5;
    font-weight: 500;
}
.gs-status-hint {
    font-size: 0.8rem;
    color: #a1a1aa;
    margin-top: 0.2rem;
}

.gs-result {
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.25);
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin: 0.8rem 0;
}
.gs-result-badge {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    background: rgba(16, 185, 129, 0.15);
    color: #34d399;
    margin-bottom: 0.3rem;
}
.gs-result-name {
    font-size: 0.92rem;
    color: #f4f4f5;
    font-weight: 600;
    word-break: break-all;
}
.gs-result-meta {
    font-size: 0.8rem;
    color: #a1a1aa;
    margin-top: 0.2rem;
}

.gs-error {
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.25);
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin: 0.8rem 0;
}
.gs-error-badge {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    margin-bottom: 0.3rem;
}
.gs-error-msg {
    font-size: 0.88rem;
    color: #f4f4f5;
}

.gs-compress-prompt {
    background: #18181b;
    border: 1px solid #3f3f46;
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin: 0.8rem 0;
}
.gs-compress-badge {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    background: rgba(99, 102, 241, 0.15);
    color: #a5b4fc;
    margin-bottom: 0.3rem;
}
.gs-compress-title {
    font-size: 0.9rem;
    font-weight: 600;
    color: #f4f4f5;
}
.gs-compress-desc {
    font-size: 0.82rem;
    color: #a1a1aa;
    margin-top: 0.15rem;
}

.gs-divider {
    height: 1px;
    background: #3f3f46;
    margin: 1.2rem 0;
}
.gs-spacer { height: 0.75rem; }
.gs-spacer-sm { height: 0.4rem; }

/* ── Stats Pill Grid ── */
.gs-stats {
    display: flex;
    gap: 0.6rem;
    margin: 0.7rem 0 1rem 0;
}
.gs-stat {
    background: #18181b;
    border: 1px solid #3f3f46;
    border-radius: 8px;
    padding: 0.55rem 0.75rem;
    font-size: 0.78rem;
    color: #a1a1aa;
    flex: 1;
    text-align: center;
}
.gs-stat strong {
    display: block;
    font-size: 0.95rem;
    color: #f4f4f5;
    font-weight: 700;
}
.gs-stat-highlight strong {
    color: #34d399;
}

/* ── Popover Top Right Help Button ── */
div[data-testid="stPopover"] {
    display: flex;
    justify-content: flex-end;
}
div[data-testid="stPopover"] > button,
button[data-testid="stBaseButton-popover"] {
    background: #27272a !important;
    border: 1px solid #3f3f46 !important;
    border-radius: 50% !important;
    width: 38px !important;
    height: 38px !important;
    min-width: 38px !important;
    max-width: 38px !important;
    padding: 0 !important;
    color: #a1a1aa !important;
    font-size: 1rem !important;
    font-weight: 700 !important;
    transition: all 0.2s ease !important;
}
div[data-testid="stPopover"] > button:hover,
button[data-testid="stBaseButton-popover"]:hover {
    background: #3f3f46 !important;
    color: #ffffff !important;
    border-color: #52525b !important;
}

/* Modal Body Overlay ── Soft Dark Card */
[data-baseweb="popover"],
[data-baseweb="popover"] > div,
div[data-testid="stPopoverBody"],
div[data-testid="stPopoverBody"] > div,
div[data-testid="stPopoverContent"] {
    background-color: #27272a !important;
    background: #27272a !important;
    border: 1px solid #3f3f46 !important;
    border-radius: 14px !important;
    color: #f4f4f5 !important;
}
div[data-testid="stPopoverBody"] {
    padding: 1.3rem !important;
    max-width: 440px !important;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4) !important;
}
div[data-testid="stPopoverBody"] * {
    background-color: transparent !important;
}
div[data-testid="stPopoverBody"] h3 {
    color: #f4f4f5 !important;
    font-size: 1rem !important;
    font-weight: 700 !important;
    margin-bottom: 0.6rem !important;
    border-bottom: 1px solid #3f3f46 !important;
    padding-bottom: 0.4rem !important;
}
div[data-testid="stPopoverBody"] h4 {
    font-weight: 700 !important;
    margin-top: 1rem !important;
    margin-bottom: 0.35rem !important;
}
div[data-testid="stPopoverBody"] p,
div[data-testid="stPopoverBody"] li,
div[data-testid="stPopoverBody"] span,
div[data-testid="stPopoverBody"] strong {
    color: #f1f5f9 !important;
    font-size: 0.85rem !important;
    line-height: 1.65 !important;
}
div[data-testid="stPopoverBody"] code {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #38bdf8 !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
}


.stAlert { display: none !important; }
</style>


""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  Session state
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class AppState:
    running: bool = False
    phase: str = "idle"       # idle | running | done | error
    progress: float = 0.0
    status_msg: str = ""
    error: Optional[str] = None
    pdf_bytes: Optional[bytes] = None
    pdf_filename: str = "document.pdf"
    # inline compression (after download done)
    compress_running: bool = False
    compress_done: bool = False
    compress_bytes: Optional[bytes] = None
    compress_filename: str = "compressed.pdf"
    compress_original_size: int = 0
    compress_size: int = 0
    compress_error: Optional[str] = None


def _init_state():
    if "app" not in st.session_state:
        st.session_state.app = AppState()
    elif not hasattr(st.session_state.app, "compress_done"):
        # Old AppState from a previous deploy — recreate with new fields
        st.session_state.app = AppState()


_init_state()
state: AppState = st.session_state.app

# ─────────────────────────────────────────────────────────────────────────────
#  Compression utility
# ─────────────────────────────────────────────────────────────────────────────
_QUALITY_MAP = {
    "Nhỏ nhất (72 dpi)":       "screen",
    "Cân bằng (150 dpi)":      "ebook",
    "Chất lượng cao (300 dpi)": "printer",
    "Tối đa (300+ dpi)":       "prepress",
}


def _compress_pdf(data: bytes, quality: str = "ebook") -> bytes:
    """Compress PDF using Ghostscript. quality: screen|ebook|printer|prepress"""
    gs_bin = shutil.which("gs") or shutil.which("ghostscript") or "gs"

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fin:
        fin.write(data)
        in_path = fin.name

    out_path = in_path + "_out.pdf"
    try:
        result = subprocess.run(
            [
                gs_bin,
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                f"-dPDFSETTINGS=/{quality}",
                "-dNOPAUSE",
                "-dQUIET",
                "-dBATCH",
                f"-sOutputFile={out_path}",
                in_path,
            ],
            capture_output=True,
            timeout=180,
        )
        if result.returncode != 0:
            msg = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(msg or f"Ghostscript trả về lỗi (code {result.returncode})")
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        for p in (in_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def _fmt_size(n: int) -> str:
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f} MB"
    return f"{n / 1024:.0f} KB"


# ─────────────────────────────────────────────────────────────────────────────
#  Background workers
# ─────────────────────────────────────────────────────────────────────────────
def _make_progress_cb(base: float, span: float):
    def _cb(current: int, total: int, msg: str):
        state.status_msg = msg
        state.progress = base + span * (current / max(total, 1))
    return _cb


def _run_download(url: str):
    """Full GDrive download pipeline — background thread."""
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
            state.error = "Không thể truy cập tài liệu. File có thể yêu cầu đăng nhập Google."
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


def _run_inline_compress(pdf_bytes: bytes, filename: str, quality: str):
    """Compress the just-downloaded PDF — background thread."""
    try:
        compressed = _compress_pdf(pdf_bytes, quality)
        state.compress_bytes = compressed
        base = filename.rsplit(".", 1)[0]
        state.compress_filename = f"{base}_compressed.pdf"
        state.compress_size = len(compressed)
        state.compress_done = True
    except Exception as exc:
        state.compress_error = str(exc)
    finally:
        state.compress_running = False


# ─────────────────────────────────────────────────────────────────────────────
#  UI — Hero & Top Right Help Button
# ─────────────────────────────────────────────────────────────────────────────
col_hero, col_help = st.columns([6, 1])

with col_hero:
    st.markdown("""
<div class="gs-hero" style="text-align: left; margin-bottom: 1.5rem;">
    <div class="gs-badge-header">STUDIO UTILITY</div>
    <div class="gs-wordmark">GDrive<span>Saver</span></div>
    <div class="gs-tagline">Công cụ tải và tối ưu tài liệu Google Drive chuyên nghiệp</div>
</div>
""", unsafe_allow_html=True)

with col_help:
    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
    with st.popover("?", use_container_width=True):
        st.markdown("""
### Hướng dẫn & Lưu ý sử dụng

#### 1. Tải xuống file Google Drive
- **Link hỗ trợ**: Dán đường dẫn dạng `/file/d/...` hoặc link thư mục `/drive/folders/...` (hệ thống sẽ tải file đầu tiên).
- **Loại tài liệu**: Phù hợp cho file dạng **View-only** (Chỉ xem, bị khóa nút Download).
- **Thời gian xử lý**: Trình duyệt ảo sẽ tự động mở và cuộn qua toàn bộ trang (từ 1 đến 3 phút tùy độ dài file).

#### 2. Nén dung lượng file PDF
- **Tự động**: Sau khi tải xong file từ GDrive, bạn có thể nhấn **Nén file này** ngay tại chỗ.
- **Tải lên thủ công**: Chuyển sang tab **Nén file PDF** để nén bất kỳ file PDF nào có sẵn.
- **Mức chất lượng nén**:
  - *Nhỏ nhất (72 dpi)*: Giảm tối đa dung lượng file.
  - *Cân bằng (150 dpi)*: Khuyên dùng cho đọc và lưu trữ thông thường.
  - *Chất lượng cao (300 dpi)*: Thích hợp in ấn tài liệu.
  - *Tối đa (300+ dpi)*: Giữ nguyên độ nét cao nhất.

#### 3. Lưu ý quan trọng
- **Quyền truy cập**: File yêu cầu đăng nhập tài khoản Google cá nhân sẽ không tải được (cần quyền xem công khai / có link).
- **Giữ nguyên màn hình**: Không tắt hoặc làm mới (Refresh) trang web khi hệ thống đang xử lý.
""")

# ─────────────────────────────────────────────────────────────────────────────
#  Tabs
# ─────────────────────────────────────────────────────────────────────────────
tab_dl, tab_compress = st.tabs(["Tải xuống GDrive", "Nén file PDF"])

# ═════════════════════════════════════════════════════════════════════════════
#  TAB 1 — Download
# ═════════════════════════════════════════════════════════════════════════════
with tab_dl:
    st.markdown('<div class="gs-card">', unsafe_allow_html=True)

    st.markdown("""
    <div class="gs-label">
        <span>LINK GOOGLE DRIVE & GOOGLE SLIDES</span>
        <span class="gs-label-tag">PDF, Slides, Docs, Thư mục</span>
    </div>
    """, unsafe_allow_html=True)
    
    url_input = st.text_input(
        label="url",
        placeholder="Dán đường dẫn Google Drive / Presentation tại đây...",
        disabled=state.running,
        label_visibility="collapsed",
        key="url_input",
    )

    st.markdown('<div class="gs-spacer"></div>', unsafe_allow_html=True)

    start_btn = st.button(
        "Bắt đầu tải xuống",
        type="primary",
        disabled=state.running or not url_input.strip(),
        use_container_width=True,
        key="start_btn",
    )

    # ── Running ──
    if state.phase == "running":
        st.markdown('<div class="gs-divider"></div>', unsafe_allow_html=True)
        st.progress(state.progress)
        st.markdown(f"""
<div class="gs-status-box">
    <div class="gs-status-header">
        <span class="gs-status-badge">ĐANG XỬ LÝ</span>
    </div>
    <div class="gs-status-text">{state.status_msg or "Đang tiến hành..."}</div>
    <div class="gs-status-hint">Trình duyệt ảo đang làm việc — vui lòng giữ nguyên trang web</div>
</div>
""", unsafe_allow_html=True)

    # ── Error ──
    if state.phase == "error" and state.error:
        st.markdown('<div class="gs-divider"></div>', unsafe_allow_html=True)
        st.markdown(f"""
<div class="gs-error">
    <span class="gs-error-badge">LỖI XỬ LÝ</span>
    <div class="gs-error-msg">{state.error}</div>
</div>
""", unsafe_allow_html=True)
        if st.button("Thử lại", key="retry_btn"):
            st.session_state.app = AppState()
            st.rerun()

    # ── Done ──
    if state.phase == "done" and state.pdf_bytes:
        st.markdown('<div class="gs-divider"></div>', unsafe_allow_html=True)
        st.progress(1.0)
        file_size = _fmt_size(len(state.pdf_bytes))
        st.markdown(f"""
<div class="gs-result">
    <span class="gs-result-badge">TẢI THÀNH CÔNG</span>
    <div class="gs-result-name">{state.pdf_filename}</div>
    <div class="gs-result-meta">Kích thước file: {file_size}</div>
</div>
""", unsafe_allow_html=True)
        st.download_button(
            label="Tải file PDF về máy",
            data=state.pdf_bytes,
            file_name=state.pdf_filename,
            mime="application/pdf",
            use_container_width=True,
            key="download_btn",
        )

        # ── Inline compress prompt ──────────────────────────────────────────
        st.markdown('<div class="gs-spacer-sm"></div>', unsafe_allow_html=True)

        if not state.compress_done and not state.compress_running:
            st.markdown("""
<div class="gs-compress-prompt">
    <span class="gs-compress-badge">TỐI ƯU DUNG LƯỢNG</span>
    <div class="gs-compress-title">Tối ưu nén file PDF vừa tải</div>
    <div class="gs-compress-desc">Giảm dung lượng file giúp lưu trữ và chia sẻ nhanh chóng hơn.</div>
</div>
""", unsafe_allow_html=True)
            col_q, col_b = st.columns([2, 1])
            with col_q:
                inline_quality = st.selectbox(
                    "Chất lượng nén",
                    options=list(_QUALITY_MAP.keys()),
                    index=1,
                    key="inline_quality",
                    label_visibility="collapsed",
                )
            with col_b:
                if st.button("Nén file này", key="inline_compress_btn", use_container_width=True):
                    state.compress_running = True
                    state.compress_original_size = len(state.pdf_bytes)
                    state.compress_error = None
                    q = _QUALITY_MAP[inline_quality]
                    threading.Thread(
                        target=_run_inline_compress,
                        args=(state.pdf_bytes, state.pdf_filename, q),
                        daemon=True,
                    ).start()
                    st.rerun()

        if state.compress_running:
            st.markdown("""
<div class="gs-status-box">
    <div class="gs-status-header">
        <span class="gs-status-badge">ĐANG NÉN FILE</span>
    </div>
    <div class="gs-status-text">Đang tối ưu dung lượng...</div>
    <div class="gs-status-hint">Ghostscript đang xử lý file PDF — vui lòng chờ giây lát</div>
</div>
""", unsafe_allow_html=True)

        if state.compress_error:
            st.markdown(f"""
<div class="gs-error">
    <span class="gs-error-badge">LỖI NÉN FILE</span>
    <div class="gs-error-msg">{state.compress_error}</div>
</div>
""", unsafe_allow_html=True)

        if state.compress_done and state.compress_bytes:
            orig = _fmt_size(state.compress_original_size)
            comp = _fmt_size(state.compress_size)
            ratio = round((1 - state.compress_size / max(state.compress_original_size, 1)) * 100)
            st.markdown(f"""
<div class="gs-result">
    <span class="gs-result-badge">NÉN THÀNH CÔNG</span>
    <div class="gs-result-name">{state.compress_filename}</div>
</div>
<div class="gs-stats">
    <div class="gs-stat"><strong>{orig}</strong>Dung lượng gốc</div>
    <div class="gs-stat gs-stat-highlight"><strong>{comp}</strong>Sau khi nén</div>
    <div class="gs-stat gs-stat-highlight"><strong>-{ratio}%</strong>Tiết kiệm</div>
</div>
""", unsafe_allow_html=True)
            st.download_button(
                label="Tải file PDF đã nén",
                data=state.compress_bytes,
                file_name=state.compress_filename,
                mime="application/pdf",
                use_container_width=True,
                key="dl_compressed_inline",
            )

        st.markdown('<div class="gs-spacer-sm"></div>', unsafe_allow_html=True)
        if st.button("Tải file mới", key="reset_btn"):
            st.session_state.app = AppState()
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)  # end .gs-card


# ═════════════════════════════════════════════════════════════════════════════
#  TAB 2 — Standalone compression
# ═════════════════════════════════════════════════════════════════════════════
with tab_compress:
    st.markdown('<div class="gs-card">', unsafe_allow_html=True)

    st.markdown("""
    <div class="gs-label">
        <span>TẬP TIN CẦN NÉN</span>
        <span class="gs-label-tag">Định dạng .pdf</span>
    </div>
    """, unsafe_allow_html=True)

    uploaded = st.file_uploader(
        label="pdf_upload",
        type=["pdf"],
        label_visibility="collapsed",
        key="pdf_upload",
    )

    if uploaded:
        st.markdown('<div class="gs-spacer-sm"></div>', unsafe_allow_html=True)
        st.markdown(f"""
<div class="gs-status-box">
    <div class="gs-status-header">
        <span class="gs-status-badge">TẬP TIN ĐÃ CHỌN</span>
    </div>
    <div class="gs-status-text">{uploaded.name}</div>
    <div class="gs-status-hint">Dung lượng ban đầu: {_fmt_size(uploaded.size)}</div>
</div>
""", unsafe_allow_html=True)

    st.markdown('<div class="gs-spacer"></div>', unsafe_allow_html=True)
    st.markdown('<div class="gs-label"><span>MỨC ĐỘ NÉN DUNG LƯỢNG</span></div>', unsafe_allow_html=True)
    quality_choice = st.radio(
        label="quality",
        options=list(_QUALITY_MAP.keys()),
        index=1,
        horizontal=True,
        label_visibility="collapsed",
        key="quality_radio",
    )

    st.markdown('<div class="gs-spacer"></div>', unsafe_allow_html=True)

    if "sc" not in st.session_state:
        st.session_state.sc = {
            "running": False, "done": False,
            "result": None, "filename": "",
            "orig_size": 0, "result_size": 0, "error": None,
        }
    sc = st.session_state.sc

    def _run_standalone_compress(data: bytes, filename: str, quality: str):
        try:
            result = _compress_pdf(data, quality)
            base = filename.rsplit(".", 1)[0]
            sc["result"] = result
            sc["filename"] = f"{base}_compressed.pdf"
            sc["result_size"] = len(result)
            sc["done"] = True
        except Exception as exc:
            sc["error"] = str(exc)
        finally:
            sc["running"] = False

    compress_btn = st.button(
        "Nén tập tin",
        type="primary",
        disabled=uploaded is None or sc["running"],
        use_container_width=True,
        key="compress_btn",
    )

    if compress_btn and uploaded:
        data = uploaded.read()
        sc.update({
            "running": True, "done": False,
            "result": None, "error": None,
            "orig_size": len(data),
        })
        threading.Thread(
            target=_run_standalone_compress,
            args=(data, uploaded.name, _QUALITY_MAP[quality_choice]),
            daemon=True,
        ).start()
        st.rerun()

    if sc["running"]:
        st.markdown('<div class="gs-divider"></div>', unsafe_allow_html=True)
        st.markdown("""
<div class="gs-status-box">
    <div class="gs-status-header">
        <span class="gs-status-badge">ĐANG XỬ LÝ</span>
    </div>
    <div class="gs-status-text">Thuật toán Ghostscript đang tối ưu dung lượng...</div>
    <div class="gs-status-hint">Vui lòng chờ trong giây lát</div>
</div>
""", unsafe_allow_html=True)

    if sc.get("error"):
        st.markdown('<div class="gs-divider"></div>', unsafe_allow_html=True)
        st.markdown(f"""
<div class="gs-error">
    <span class="gs-error-badge">LỖI THỰC THI</span>
    <div class="gs-error-msg">{sc["error"]}</div>
</div>
""", unsafe_allow_html=True)
        if st.button("Thử lại", key="sc_retry"):
            sc.update({"running": False, "done": False, "result": None, "error": None})
            st.rerun()

    if sc["done"] and sc["result"]:
        orig = _fmt_size(sc["orig_size"])
        comp = _fmt_size(sc["result_size"])
        ratio = round((1 - sc["result_size"] / max(sc["orig_size"], 1)) * 100)
        st.markdown('<div class="gs-divider"></div>', unsafe_allow_html=True)
        st.markdown(f"""
<div class="gs-result">
    <span class="gs-result-badge">NÉN HOÀN TẤT</span>
    <div class="gs-result-name">{sc["filename"]}</div>
</div>
<div class="gs-stats">
    <div class="gs-stat"><strong>{orig}</strong>Dung lượng gốc</div>
    <div class="gs-stat gs-stat-highlight"><strong>{comp}</strong>Sau khi nén</div>
    <div class="gs-stat gs-stat-highlight"><strong>-{ratio}%</strong>Tiết kiệm</div>
</div>
""", unsafe_allow_html=True)
        st.download_button(
            label="Tải file PDF đã nén",
            data=sc["result"],
            file_name=sc["filename"],
            mime="application/pdf",
            use_container_width=True,
            key="dl_compressed_standalone",
        )
        st.markdown('<div class="gs-spacer-sm"></div>', unsafe_allow_html=True)
        if st.button("Nén file khác", key="sc_reset"):
            sc.update({"running": False, "done": False, "result": None, "error": None})
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)  # end .gs-card


# ─────────────────────────────────────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Hướng dẫn — Tải xuống")
    st.markdown("""
1. Dán link Google Drive dạng **View-only** vào ô nhập.
2. Nhấn **Bắt đầu tải xuống**.
3. Đợi trình duyệt ảo cuộn qua toàn bộ tài liệu *(1 – 3 phút)*.
4. Nhấn **Tải file PDF** khi hoàn tất.

---

### Hướng dẫn — Nén PDF

1. Chuyển sang tab **Nén file PDF**.
2. Tải lên file PDF cần nén.
3. Chọn mức chất lượng phù hợp.
4. Nhấn **Nén file** và tải kết quả về.

---

**Mức chất lượng nén:**
- **Nhỏ nhất** — 72 dpi, dung lượng tối thiểu
- **Cân bằng** — 150 dpi, khuyến nghị
- **Cao** — 300 dpi, in ấn
- **Tối đa** — 300+ dpi, xuất bản

---

**Lưu ý:**
- File yêu cầu đăng nhập Google sẽ không tải được.
- Hỗ trợ link file đơn (`/file/d/`) và thư mục (`/drive/folders/`).
""")

# ─────────────────────────────────────────────────────────────────────────────
#  Trigger download + polling
# ─────────────────────────────────────────────────────────────────────────────
if start_btn and url_input.strip():
    state.running = True
    state.phase = "running"
    state.progress = 0.0
    state.status_msg = "Đang khởi động..."
    state.error = None
    state.pdf_bytes = None
    state.pdf_filename = "document.pdf"
    state.compress_done = False
    state.compress_bytes = None
    state.compress_error = None

    threading.Thread(target=_run_download, args=(url_input.strip(),), daemon=True).start()
    st.rerun()

# Polling — keep UI live while any background thread is running
if state.phase == "running" or state.compress_running or sc.get("running"):
    time.sleep(2)
    st.rerun()
