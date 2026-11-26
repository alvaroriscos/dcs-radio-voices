"""Prueba de humo de la ventana: carga un guion, previsualiza, genera y hace capturas.

QT_QPA_PLATFORM=offscreen python tests/gui_smoke.py guion.txt carpeta_salida carpeta_capturas
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from dcsradio import gui  # noqa: E402


def main():
    script, out, shots = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    shots.mkdir(parents=True, exist_ok=True)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    errors = []
    QMessageBox.critical = staticmethod(lambda *a, **k: errors.append(a[2] if len(a) > 2 else a) or QMessageBox.Ok)
    gui.play_wav = lambda p: True
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(gui.STYLE)
    w = gui.MainWindow()
    w.resize(1280, 820)
    w.show()

    def wait_idle(timeout=600):
        t0 = time.time()
        while time.time() - t0 < timeout:
            app.processEvents()
            if w.thread is None:
                return True
            time.sleep(0.02)
        return False

    wait_idle()
    w.load_script(script)
    w.out_edit.setText(out)
    app.processEvents()
    for i, name in enumerate(["lineas", "voces", "efectos", "pronunciacion"]):
        w.tabs.setCurrentIndex(i)
        if i == 0:
            w.lines_tbl.selectRow(1)
        app.processEvents()
        w.grab().save(str(shots / f"{i}_{name}.png"))
    w.tabs.setCurrentIndex(0)
    w.lines_tbl.selectRow(1)
    w.preview()
    wait_idle()
    print("preview:", w.status.text())
    w.generate()
    wait_idle(3600)
    app.processEvents()
    w.grab().save(str(shots / "5_registro.png"))
    print("status:", w.status.text())
    print("log:\n" + w.log_view.toPlainText()[-1500:])
    if errors:
        print("ERRORES:", errors)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
