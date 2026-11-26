"""Punto de entrada: ventana (sin argumentos) o modo consola (--cli ...)."""
import sys
import multiprocessing
from pathlib import Path


def run():
    multiprocessing.freeze_support()
    args = sys.argv[1:]
    exe = Path(sys.executable).stem.lower() if getattr(sys, "frozen", False) else ""
    if exe.endswith("cli") or (args and args[0] == "--cli"):
        from dcsradio.cli import main
        return main(args[1:] if args and args[0] == "--cli" else args)
    if args and args[0] == "--selftest":
        from dcsradio.gui import selftest
        return selftest(args[1] if len(args) > 1 else "selftest")
    from dcsradio.gui import main
    return main()


if __name__ == "__main__":
    sys.exit(run())
