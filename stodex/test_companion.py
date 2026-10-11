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


def test_explicit_current_captain_read_and_late_completion(app, tmp_path, monkeypatch):
    from stodex_companion.operations import Operation
    root = Path(__file__).resolve().parents[1].parent / "stodex-bridge-reshade"
    fixture = root / "results/sto-companion-mvp/bin/captain-build-fixture.json"
    if not fixture.exists():
        pytest.skip("Build the native Captain fixture first")
    shell, manager, adapter = make_host(tmp_path)
    key = ("network.stodex.sets", "build")
    pending = []
    original = adapter.request
    def request(name, arguments, origin="host"):
        if name != "captain.build.get":
            return original(name, arguments, origin)
        assert arguments == {}
        operation = Operation(name, origin, lambda _: None)
        pending.append(operation)
        return operation
    monkeypatch.setattr(adapter, "request", request)
    adapter.capabilities["captain.build.get"] = {"available": True, "status": "available"}
    try:
        shell.select_page(key)
        page = shell.pages[key]["widget"]
        assert pending == []
        page.read_current_captain.click()
        assert len(pending) == 1 and not page.read_current_captain.isEnabled()
        value = json.loads(fixture.read_text())["native"]
        # The native bounds fixture deliberately puts three positions in Body.
        # Supply one armor position for this separate display/lifecycle test.
        value["data"]["equipment"]["captain"][0]["slots"] = value["data"]["equipment"]["captain"][0]["slots"][:1]
        value.update(session_id=manager.state.session_id, scene_epoch=manager.state.scene_epoch,
                     revision=1, observed_at_utc="2026-10-11T20:00:00Z", source="captain_self_read", consistency="identity_checked")
        captain = manager.state.get("captain")
        value["data"]["active_entity_id"] = captain.data.get("captain_id") or value["data"]["active_entity_id"]
        pending[0].finish("succeeded", value)
        wait_for(lambda: manager.builds.get() is not None)
        assert page.read_current_captain.isEnabled()
        assert page.sets_controller.build.ground.armor[0].property("buildItemId") == "Native_Armor"
        retained = manager.builds.get()
        assert retained.observation.data["native"]["traits"]["primary"]["slots"][0]["power_id"] == 7
        page.read_current_captain.click()
        assert len(pending) == 2
        manager.deactivate(key[0])
        value["revision"] = 2
        pending[1].finish("succeeded", value)
        QTest.qWait(50)
        assert manager.builds.get() is retained
    finally:
        manager.close()
        adapter.close()
        shell.close()


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
def test_native_item_tokens_load_actual_icons_and_keep_missing_placeholders(app, tmp_path):
    from PIL import Image
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('sets_token_hogg_fixtures',
        root.parent / 'stodex-companion/tests/test_resources.py')
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    image = Image.new('RGBA', (32, 32), (180, 80, 25, 255))
    buffer = io.BytesIO()
    image.save(buffer, format='DDS')
    dds = buffer.getvalue()
    payload = struct.pack('<II', 40, 40 + len(dds)) + b'\0' * 32 + dds
    archives = tmp_path / 'piggs'
    archives.mkdir()
    member = 'Texture_Library/UI/Icons/Item_Icons/Weapons/Phaser.Wtex'
    fixtures.write_hogg(archives / 'texture.hogg', [(member, payload, True)])
    value = fixture_build()
    item = value['data']['slots']['space']['fore_weapons'][0]['item']
    item.pop('icon')
    item['icon_token'] = 'phaser'
    item['rarity'] = 'Epic'
    value['data']['slots']['space']['fore_weapons'][1] = {
        'state': 'occupied', 'item': {'id': 'missing', 'name': 'Missing icon', 'icon_token': 'missing'}}
    with ResourcesProvider(archives) as resources:
        shell, manager, adapter = make_host(tmp_path / 'storage', resources, value)
        try:
            shell.select_page(('network.stodex.sets', 'build'))
            page = shell.pages[('network.stodex.sets', 'build')]['widget']
            wait_for(lambda: '1 icons loaded' in page.build_status.text())
            button, missing = page.sets_controller.build.space.fore_weapons[:2]
            assert button._base.pixelColor(0, 0).getRgb() == (180, 80, 25, 255)
            assert button._overlay == page.sets_controller.images.overlays.epic
            assert 'Epic' in button.toolTip()
            assert button.property('buildItemId') == item['id']
            assert page.build_renderer.icon_results[('token', 'phaser')]['resolution']['member'] == member
            assert missing.property('buildItemId') == 'missing'
            assert 'Icon unavailable' in missing.toolTip()
            assert '1 unavailable' in page.build_status.text()
            replacement = deepcopy(value)
            replacement['revision'] += 1
            replacement['data']['slots']['space']['fore_weapons'][0]['item']['rarity'] = 'Rare'
            assert manager.builds.publish(replacement)
            wait_for(lambda: '1 icons loaded' in page.build_status.text())
            assert button._overlay == page.sets_controller.images.overlays.rare
            assert 'Rare' in button.toolTip() and 'Epic' not in button.toolTip()
            replacement['revision'] += 1
            del replacement['data']['slots']['space']['fore_weapons'][0]['item']['rarity']
            assert manager.builds.publish(replacement)
            wait_for(lambda: '1 icons loaded' in page.build_status.text())
            assert button._overlay is None
        finally:
            manager.close()
            adapter.close()
            shell.close()


@pytest.mark.skipif(not DEFAULT_HELPER.is_file(), reason="Build HOGG helper first")
def test_published_build_populates_items_from_hogg_and_survives_reactivation(app, tmp_path, monkeypatch):
    from PIL import Image
    import requests

    monkeypatch.setattr(requests.sessions.Session, "request", lambda *a, **k: pytest.fail("Wiki request"))
    root = Path(__file__).resolve().parents[1]
    test_path = root.parent / "stodex-companion/tests/test_resources.py"
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
