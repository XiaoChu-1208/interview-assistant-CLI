"""ANSI theme + cross-platform color enabling."""
import os
import platform
import shutil


if platform.system() == "Windows":
    try:
        import colorama
        colorama.just_fix_windows_console()
    except ImportError:
        pass


RST  = "\033[0m"
B    = "\033[1m"
DIM  = "\033[2m"
IT   = "\033[3m"
UL   = "\033[4m"
RED  = "\033[31m"
GRN  = "\033[32m"
YEL  = "\033[33m"
BLU  = "\033[34m"
MAG  = "\033[35m"
CYN  = "\033[36m"
WHT  = "\033[37m"
BRED = "\033[91m"
BGRN = "\033[92m"
BYEL = "\033[93m"
BBLU = "\033[94m"
BCYN = "\033[96m"
BWHT = "\033[97m"
BG_MAG = "\033[45m"
WARM   = "\033[38;5;173m"
SAND   = "\033[38;5;180m"
BG_WARM = "\033[48;5;173m"
BG_SAND = "\033[48;5;180m"
BG_236  = "\033[48;5;236m"


def detect_theme():
    """Detect terminal theme: 'dark', 'light', or 'none'."""
    manual = os.environ.get("INTERVIEW_THEME", "").lower()
    if manual in ("light", "dark", "none"):
        return manual
    if os.environ.get("NO_COLOR"):
        return "none"
    colorfgbg = os.environ.get("COLORFGBG", "")
    if colorfgbg:
        try:
            bg = int(colorfgbg.split(";")[-1])
            return "light" if bg > 8 else "dark"
        except (ValueError, IndexError):
            pass
    return "dark"


def tree_colors():
    """Color palette for rendered Unicode tree blocks."""
    if detect_theme() == "light":
        return {"root": GRN + B, "branch": B, "step": CYN + B, "leaf": DIM, "line": DIM}
    return {"root": BGRN + B, "branch": B, "step": BCYN, "leaf": DIM, "line": DIM}


def term_width(default=80):
    return shutil.get_terminal_size((default, 20)).columns
