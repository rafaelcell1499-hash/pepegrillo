"""ReelForge - punto de entrada."""
import os
import sys

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _fix_streams():
    """La consola de Windows usa cp1252: forzamos UTF-8 y evitamos fallos sin consola (--noconsole)."""
    for name in ("stdout", "stderr"):
        s = getattr(sys, name, None)
        if s is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
        else:
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _crash_log(text):
    try:
        from reelforge.ffutil import app_dir
        p = app_dir() / "reelforge_error.log"
        p.write_text(text, encoding="utf-8")
        return str(p)
    except Exception:
        return ""


def main():
    _fix_streams()
    if "--selftest" in sys.argv:
        from reelforge.selftest import main as selftest
        return selftest()
    try:
        from reelforge.gui import run
        run()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        path = _crash_log(tb)
        try:
            import tkinter
            from tkinter import messagebox
            r = tkinter.Tk()
            r.withdraw()
            messagebox.showerror("ReelForge", "Error al iniciar:\n\n%s\n\n%s" % (tb[-900:], path))
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
