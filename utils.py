"""
Utility functions for GDrive ViewOnly Saver.
"""

import os
import re
import sys
import shutil
from colorama import Fore, Style, init

# Initialize colorama for Windows support
init(autoreset=True)


def extract_file_id(url: str) -> str:
    """
    Extract the Google Drive file ID from various URL formats.
    
    Supported formats:
    - https://drive.google.com/file/d/FILE_ID/view
    - https://drive.google.com/file/d/FILE_ID/view?usp=sharing
    - https://drive.google.com/open?id=FILE_ID
    - https://docs.google.com/document/d/FILE_ID/edit
    - https://docs.google.com/spreadsheets/d/FILE_ID/edit
    - https://docs.google.com/presentation/d/FILE_ID/edit
    - Just the FILE_ID itself
    """
    if not url:
        raise ValueError("URL cannot be empty")
    
    # Pattern 1: /d/FILE_ID/
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    # Pattern 2: ?id=FILE_ID
    match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    # Pattern 3: Assume raw file ID (no slashes, no dots)
    if re.match(r'^[a-zA-Z0-9_-]+$', url) and len(url) > 10:
        return url
    
    if is_folder_url(url):
        raise ValueError(
            f"URL is a folder, not a file: {url}\n"
            f"Please use folder download logic or provide a file URL."
        )
        
    raise ValueError(
        f"Could not extract file ID from URL: {url}\n"
        f"Please provide a valid Google Drive URL or file ID."
    )

def is_folder_url(url: str) -> bool:
    """Check if the URL is a Google Drive folder."""
    if not url:
        return False
    return "/folders/" in url or "folderview" in url or "drive/u/0/folders" in url

def extract_folder_id(url: str) -> str:
    """Extract folder ID from URL."""
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    if re.match(r'^[a-zA-Z0-9_-]+$', url) and len(url) > 10:
        return url
    return ""


def build_view_url(file_id: str) -> str:
    """Build the Google Drive viewer URL from a file ID."""
    return f"https://drive.google.com/file/d/{file_id}/view"


def is_presentation_url(url: str) -> bool:
    """Return True if the URL points to a Google Slides presentation."""
    return "docs.google.com/presentation" in url


def is_docs_url(url: str) -> bool:
    """Return True if the URL points to a Google Docs document."""
    return "docs.google.com/document" in url


def is_sheets_url(url: str) -> bool:
    """Return True if the URL points to a Google Sheets spreadsheet."""
    return "docs.google.com/spreadsheets" in url


def build_export_url(file_id: str, doc_type: str = "presentation", fmt: str = "pdf") -> str:
    """Build a direct export URL for Google Docs editors.
    
    doc_type: presentation | document | spreadsheets
    fmt: pdf | pptx | docx | xlsx | ...
    """
    return f"https://docs.google.com/{doc_type}/d/{file_id}/export/{fmt}"


def sanitize_filename(name: str) -> str:
    """Remove invalid characters from a filename."""
    # Remove characters that are invalid in Windows filenames
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(' .')
    # Limit length
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized or "untitled"


def ensure_dir(path: str) -> str:
    """Create directory if it doesn't exist. Returns the path."""
    os.makedirs(path, exist_ok=True)
    return path


def cleanup_dir(path: str):
    """Remove a directory and all its contents."""
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes == 0:
        return "0 B"
    units = ['B', 'KB', 'MB', 'GB']
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.1f} {units[i]}"


# ═══════════════════════════════════════════════════════════════
#  LOGGING / DISPLAY HELPERS
# ═══════════════════════════════════════════════════════════════

def print_banner():
    """Print the application banner."""
    banner = f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   {Fore.WHITE}██████╗ ██████╗ ██████╗ ██╗██╗   ██╗███████╗{Fore.CYAN}              ║
║   {Fore.WHITE}██╔════╝ ██╔══██╗██╔══██╗██║██║   ██║██╔════╝{Fore.CYAN}              ║
║   {Fore.WHITE}██║  ███╗██║  ██║██████╔╝██║██║   ██║█████╗  {Fore.CYAN}              ║
║   {Fore.WHITE}██║   ██║██║  ██║██╔══██╗██║╚██╗ ██╔╝██╔══╝  {Fore.CYAN}              ║
║   {Fore.WHITE}╚██████╔╝██████╔╝██║  ██║██║ ╚████╔╝ ███████╗{Fore.CYAN}              ║
║   {Fore.WHITE} ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝  ╚══════╝{Fore.CYAN}              ║
║                                                              ║
║   {Fore.YELLOW}ViewOnly Saver{Fore.CYAN} — Download View-Only Google Drive Files    ║
║   {Fore.WHITE}High-Quality • Lossless • Fast{Fore.CYAN}                            ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""
    print(banner)


def log_info(msg: str):
    """Print an info message."""
    print(f"  {Fore.CYAN}[INFO]{Style.RESET_ALL}  {msg}")


def log_success(msg: str):
    """Print a success message."""
    print(f"  {Fore.GREEN}[  OK ]{Style.RESET_ALL}  {msg}")


def log_warning(msg: str):
    """Print a warning message."""
    print(f"  {Fore.YELLOW}[WARN]{Style.RESET_ALL}  {msg}")


def log_error(msg: str):
    """Print an error message."""
    print(f"  {Fore.RED}[ERROR]{Style.RESET_ALL} {msg}")


def log_step(step: int, total: int, msg: str):
    """Print a step progress message."""
    print(f"  {Fore.MAGENTA}[{step}/{total}]{Style.RESET_ALL}   {msg}")


def log_progress(current: int, total: int, prefix: str = ""):
    """Print a simple progress indicator on the same line."""
    pct = (current / total * 100) if total > 0 else 0
    bar_len = 30
    filled = int(bar_len * current / total) if total > 0 else 0
    bar = f"{Fore.GREEN}{'█' * filled}{Fore.WHITE}{'░' * (bar_len - filled)}{Style.RESET_ALL}"
    sys.stdout.write(f"\r  {prefix} {bar} {pct:5.1f}% ({current}/{total})")
    if current >= total:
        sys.stdout.write("\n")
    sys.stdout.flush()
