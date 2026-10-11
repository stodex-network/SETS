# SPDX-License-Identifier: GPL-3.0-only
"""Integration checks against the installed Companion and its actual Qt runtime."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThread
from PySide6.QtWidgets import QApplication, QPushButton
from stodex_companion.__main__ import create_host


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def test_host_lifecycle_and_offline_view(app, tmp_path, monkeypatch):
    import requests

    def forbid_network(*args, **kwargs):
        pytest.fail("Offline build viewer attempted network IO")

    monkeypatch.setattr(requests.sessions.Session, "request", forbid_network)
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("sets_test_pack", root / "stodex/companion_pack/extension.py")
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    priority = QThread.currentThread().priority()
    shell, manager, adapter = create_host(SimpleNamespace(
        mock=True, pid=None, fixture="typical", storage_dir=tmp_path,
        extension_dir=[root / "stodex"],
    ))
    key = ("network.stodex.sets", "build")
    theme = app.styleSheet()
    try:
        for _ in range(2):
            manager.activate(key[0])
            shell.select_page(key)
            package = manager.packages[key[0]]
            assert not package.error, package.error
            page = shell.pages[key]["widget"]
            controller = page.sets_controller
            shell.resize(1280, 800)
            shell.show()
            app.processEvents()
            if _ == 0:
                shell.grab().save(str(tmp_path / "sets-companion-preview.png"))
            assert QApplication.instance() is app
            assert QThread.currentThread().priority() == priority
            assert not hasattr(controller, "_backend_thread")
            assert controller.build.data["captain"]["name"] == ""
            assert not controller.build.ship.button.isEnabled()
            assert all(not slot.isEnabled() for slot in controller.build.space.fore_weapons)
            buttons = controller.window.findChildren(QPushButton)
            for title, index in [("SPACE", 0), ("GROUND", 1), ("SPACE SKILLS", 2), ("GROUND SKILLS", 3)]:
                button = next(b for b in buttons if b.text() == title)
                button.click()
                assert controller.tabbers.build_tabber.currentIndex() == index
            assert all(not b.isEnabled() for b in buttons if b.text() not in {
                "SPACE", "GROUND", "SPACE SKILLS", "GROUND SKILLS"})
            manager.deactivate(key[0])
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert key not in shell.pages
        shell_theme = app.styleSheet()
        assert shell_theme == theme
    finally:
        manager.close()
        adapter.close()
        shell.close()
