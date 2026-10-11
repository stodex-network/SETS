# SPDX-License-Identifier: GPL-3.0-only
"""Integration checks against the installed Companion and its actual Qt runtime."""
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import base64
import hashlib
import importlib.util
import io
import json
import struct
import threading

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from stodex_companion.__main__ import create_host
from stodex_companion.providers.resources import DEFAULT_HELPER, ResourcesProvider
from stodex_companion.storage import Data


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def test_host_lifecycle_and_offline_view(app, tmp_path, monkeypatch):
    import requests

    def forbid_network(*args, **kwargs):
        pytest.fail("Offline build viewer attempted network IO")

    monkeypatch.setattr(requests.sessions.Session, "request", forbid_network)
    root = Path(__file__).resolve().parents[1]
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


def wait_for(predicate, timeout=5000):
    for _ in range(timeout // 20):
        if predicate():
            return
        QTest.qWait(20)
    assert predicate(), "Build/icon delivery did not complete"


def fixture_build():
    return json.loads((Path(__file__).parent / "build-fixture.json").read_text(encoding="utf-8"))


def make_host(tmp_path, resources=None, build=None):
    return create_host(SimpleNamespace(
        mock=True, pid=None, fixture="typical", storage_dir=tmp_path,
        extension_dir=[Path(__file__).parent],
        data=Data({"resources": resources}) if resources else Data(),
        build_snapshot=build,
    ))


@pytest.mark.skipif(not DEFAULT_HELPER.is_file(), reason="Build HOGG helper first")
def test_published_build_populates_items_from_hogg_and_survives_reactivation(app, tmp_path, monkeypatch):
    from PIL import Image
    import requests

    monkeypatch.setattr(requests.sessions.Session, "request", lambda *a, **k: pytest.fail("Wiki request"))
    root = Path(__file__).resolve().parents[1]
    test_path = root.parents[1] / "companion/tests/test_resources.py"
    spec = importlib.util.spec_from_file_location("sets_hogg_fixtures", test_path)
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    image = Image.new("RGBA", (32, 32), (12, 120, 220, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="DDS")
    dds = buffer.getvalue()
    payload = struct.pack("<II", 40, 40 + len(dds)) + b"\0" * 32 + dds
    archives = tmp_path / "piggs"
    archives.mkdir()
    fixtures.write_hogg(archives / "texture.hogg", [
        ("Texture_Library/UI/Icons/phaser.wtex", payload, True)])
    with ResourcesProvider(archives) as resources:
        value = fixture_build()
        reference = value["data"]["slots"]["space"]["fore_weapons"][0]["item"]["icon"]
        value["data"]["slots"]["ground"]["weapons"][0]["item"]["icon"] = reference
        value["data"]["skills"] = {"space": {"tac": [True] + [None] * 29}}
        shell, manager, adapter = make_host(tmp_path / "storage", resources, value)
        key = ("network.stodex.sets", "build")
        try:
            # Published before lazy page creation; subscriber reads the retained observation.
            shell.select_page(key)
            assert not manager.packages[key[0]].error
            page = shell.pages[key]["widget"]
            renderer = page.build_renderer
            wait_for(lambda: "1 icons loaded" in page.build_status.text())
            button = page.sets_controller.build.space.fore_weapons[0]
            ground = page.sets_controller.build.ground.weapons[0]
            assert button.property("buildItemId") == "fixture-phaser"
            assert "Phaser Beam Array" in button.tooltip and "Mk XV" in button.tooltip
            assert button._base.pixelColor(0, 0).getRgb() == (12, 120, 220, 255)
            assert ground._base.pixelColor(0, 0).getRgb() == (12, 120, 220, 255)
            assert renderer.snapshot.observation.data["slots"]["space"]["fore_weapons"][0]["item"]["id"] == "fixture-phaser"
            assert len(renderer.icon_results) == 1  # shared icon requested once
            assert page.sets_controller.build.skills.space["tac"][0].property("buildSkillState") == "owned"
            assert page.sets_controller.build.space.fore_weapons[1].property("buildSlotState") == "empty"
            assert page.sets_controller.build.space.fore_weapons[2].property("buildSlotState") == "unknown"
            assert page.sets_controller.build.space.fore_weapons[3].isHidden()
            page.sets_controller.tabbers.switch(1)
            shell.resize(1280, 800)
            shell.show()
            app.processEvents()
            shell.grab().save(str(tmp_path / "populated-sets-ground.png"))
            page.sets_controller.tabbers.switch(0)
            app.processEvents()
            shell.grab().save(str(tmp_path / "populated-sets-space.png"))
            context = manager.packages[key[0]].context[1]
            assert not context.builds.publish(value)  # duplicate revision
            updated = deepcopy(value)
            updated["revision"] = 2
            updated["data"]["captain"]["name"] = "<Captain & Updated>"
            updated["data"]["slots"]["space"]["fore_weapons"][0]["item"]["id"] = "unresolved.native.item"
            updated["data"]["slots"]["space"]["fore_weapons"][0]["item"]["name"] = "<Unknown & Item>"
            updated["data"]["slots"]["space"]["fore_weapons"][0]["item"]["icon"]["member"] = "missing.wtex"
            assert context.builds.publish(updated)
            wait_for(lambda: "unavailable" in page.build_status.text() and "Loading" not in page.build_status.text())
            assert page.sets_controller.tabbers.build_tabber.currentIndex() == 0
            assert button.property("buildItemId") == "unresolved.native.item"
            assert "&lt;Unknown &amp; Item&gt;" in button.tooltip
            assert "Icon unavailable" in button.toolTip()
            assert not manager.packages[key[0]].error
            manager.deactivate(key[0])
            with pytest.raises(RuntimeError, match="activation ended"):
                context.builds.publish(updated)
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            manager.activate(key[0])
            shell.select_page(key)
            page = shell.pages[key]["widget"]
            assert page.sets_controller.build.character.name.text() == "<Captain & Updated>"
            wait_for(lambda: "Loading" not in page.build_status.text())
            assert not manager.packages[key[0]].error
        finally:
            manager.close()
            adapter.close()
            shell.close()


def test_late_icon_delivery_cannot_overwrite_new_build(app, tmp_path):
    from PIL import Image

    started, release = threading.Event(), threading.Event()
    buffer = io.BytesIO()
    Image.new("RGBA", (8, 8), "red").save(buffer, format="PNG")
    png = buffer.getvalue()

    class DelayedResources:
        def query(self, arguments):
            started.set()
            assert release.wait(5)
            return {"availability": "available", "bytes": len(png),
                    "sha256": hashlib.sha256(png).hexdigest(), "data": base64.b64encode(png).decode()}

    shell, manager, adapter = make_host(tmp_path, DelayedResources(), fixture_build())
    key = ("network.stodex.sets", "build")
    try:
        shell.select_page(key)
        page = shell.pages[key]["widget"]
        wait_for(started.is_set)
        updated = fixture_build()
        updated["revision"] = 2
        updated["data"]["slots"]["space"]["fore_weapons"] = [{"state": "empty"}]
        assert manager.builds.publish(updated)
        release.set()
        QTest.qWait(150)
        button = page.sets_controller.build.space.fore_weapons[0]
        assert button.property("buildSlotState") == "empty"
        assert button._base is None
        manager.builds.clear()
        assert page.build_status.text() == "SETS build viewer · No player build loaded"
        assert not manager.packages[key[0]].error
    finally:
        release.set()
        manager.close()
        adapter.close()
        shell.close()
