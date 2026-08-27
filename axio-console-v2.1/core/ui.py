"""
AXIO Core — Terminal UI Helpers
Shared colors, banners, status lines, and spinner used across all modes.
"""

import sys
import threading
import time

# ─────────────────────────────────────────────────────────
#  ANSI COLOR SHORTCUTS
# ─────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[90m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
PURPLE = "\033[35m"
WHITE  = "\033[97m"

def c(text, color): return f"{color}{text}{RESET}"
def bold(text):     return f"{BOLD}{text}{RESET}"
def dim(text):      return f"{DIM}{text}{RESET}"
def ok(text):       return f"{GREEN}{text}{RESET}"
def warn(text):     return f"{YELLOW}{text}{RESET}"
def err(text):      return f"{RED}{text}{RESET}"
def hi(text):       return f"{CYAN}{text}{RESET}"
def lo(text):       return f"{DIM}{text}{RESET}"

# ─────────────────────────────────────────────────────────
#  MODE COLORS
# ─────────────────────────────────────────────────────────
MODE_COLOR = {
    "chat":    "\033[36m",   # cyan
    "cowork":  "\033[32m",   # green
    "code":    "\033[33m",   # yellow
    "revrec":  "\033[35m",   # purple
}

def mode_tag(mode: str) -> str:
    color = MODE_COLOR.get(mode, CYAN)
    return f"{color}[{mode.upper()}]{RESET}"

# ─────────────────────────────────────────────────────────
#  MAIN PLATFORM BANNER
# ─────────────────────────────────────────────────────────
AXIO_BANNER = f"""
{CYAN}{BOLD}
 █████╗ ██╗  ██╗██╗ ██████╗     ██████╗ ██╗      █████╗ ████████╗███████╗ ██████╗ ██████╗ ███╗   ███╗
██╔══██╗╚██╗██╔╝██║██╔═══██╗    ██╔══██╗██║     ██╔══██╗╚══██╔══╝██╔════╝██╔═══██╗██╔══██╗████╗ ████║
███████║ ╚███╔╝ ██║██║   ██║    ██████╔╝██║     ███████║   ██║   █████╗  ██║   ██║██████╔╝██╔████╔██║
██╔══██║ ██╔██╗ ██║██║   ██║    ██╔═══╝ ██║     ██╔══██║   ██║   ██╔══╝  ██║   ██║██╔══██╗██║╚██╔╝██║
██║  ██║██╔╝ ██╗██║╚██████╔╝    ██║     ███████╗██║  ██║   ██║   ██║     ╚██████╔╝██║  ██║██║ ╚═╝ ██║
╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝    ╚═╝     ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝
{RESET}"""

# ─────────────────────────────────────────────────────────
#  MODE-SPECIFIC BANNERS
# ─────────────────────────────────────────────────────────
def mode_banner(mode: str, subtitle: str = ""):
    color = MODE_COLOR.get(mode, CYAN)
    label = mode.upper()
    line  = "─" * 68
    print(f"\n{color}{BOLD}  ┌{line}┐")
    print(f"  │  AXIO {label:<61}│")
    if subtitle:
        print(f"  │  {subtitle:<63}│")
    print(f"  └{line}┘{RESET}\n")

# ─────────────────────────────────────────────────────────
#  STATUS LINE (shown before each prompt)
# ─────────────────────────────────────────────────────────
def status_line(mode: str, session_name: str, model: str, n_msgs: int, backend: str = "ollama"):
    color  = MODE_COLOR.get(mode, CYAN)
    b_tag  = ok("ollama") if backend == "ollama" else c("claude", PURPLE)
    print(
        f"{DIM}  session:{RESET} {color}{session_name}{RESET}  "
        f"{DIM}model:{RESET} {YELLOW}{model}{RESET}  "
        f"{DIM}msgs:{RESET} {WHITE}{n_msgs}{RESET}  "
        f"{DIM}backend:{RESET} {b_tag}"
    )

# ─────────────────────────────────────────────────────────
#  DIVIDER
# ─────────────────────────────────────────────────────────
def divider(color_code: str = DIM):
    print(f"{color_code}  {'─' * 60}{RESET}")

# ─────────────────────────────────────────────────────────
#  SPINNER — shows while the model thinks
# ─────────────────────────────────────────────────────────
class Spinner:
    FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    ASCII_FRAMES = ["|", "/", "-", "\\"]

    def __init__(self, label: str = "Thinking"):
        self.label   = label
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        i = 0
        frames = self.FRAMES
        encoding = sys.stdout.encoding or "utf-8"
        try:
            "".join(frames).encode(encoding)
        except (LookupError, UnicodeEncodeError):
            frames = self.ASCII_FRAMES
        while not self._stop.is_set():
            frame = frames[i % len(frames)]
            print(f"\r  {CYAN}{frame}{RESET}  {self.label} ...", end="", flush=True)
            time.sleep(0.1)
            i += 1

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join()
        print("\r" + " " * 60 + "\r", end="", flush=True)
