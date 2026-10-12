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
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QThread
from PySide6.QtGui import QCursor, QEnterEvent, QHelpEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QToolTip
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
            assert page.read_current_captain.isVisible()
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
                "SPACE", "GROUND", "SPACE SKILLS", "GROUND SKILLS", "Read current Captain"})
            assert page.build_status.isHidden() and shell.status.isHidden()
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
    root = Path(__file__).resolve().parents[3]
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
        pending[1].finish("rejected", error={"code": "fixture_read_failure"})
        assert page.read_current_captain.isEnabled()
        assert page.read_current_captain.text() == "Retry Captain read"
        assert "fixture_read_failure" in page.read_current_captain.toolTip()
        assert page.build_status.isHidden() and manager.builds.get() is retained
        page.read_current_captain.click()
        assert len(pending) == 3
        manager.deactivate(key[0])
        value["revision"] = 2
        pending[2].finish("succeeded", value)
        QTest.qWait(50)
        assert manager.builds.get() is retained
    finally:
        manager.close()
        adapter.close()
        shell.close()


def fixture_build():
    return json.loads((Path(__file__).parent / "build-fixture.json").read_text(encoding="utf-8"))


def make_host(tmp_path, resources=None, build=None, catalogue=None):
    # Explicit offline catalogue fixture; deactivate the shipped network fallback for these tests.
    providers = {"catalogue": catalogue or SimpleNamespace(query=lambda _: {"availability": "unavailable", "reason": "Offline fixture"})}
    if resources:
        providers["resources"] = resources
    result = create_host(SimpleNamespace(
        mock=True, pid=None, fixture="typical", storage_dir=tmp_path,
        extension_dir=[Path(__file__).parent],
        data=Data(providers),
        build_snapshot=build,
    ))
    result[1].deactivate("network.stodex.stowiki-data")
    return result


@pytest.mark.parametrize("target", ["equipment", "unknown-slot", "skill", "skill-unlock"])
def test_hover_shows_only_sets_tooltip(app, tmp_path, target):
    shell, manager, adapter = make_host(tmp_path, build=fixture_build())
    try:
        shell.select_page(("network.stodex.sets", "build"))
        page = shell.pages[("network.stodex.sets", "build")]["widget"]
        controller = page.sets_controller
        targets = {"equipment": (0, controller.build.space.fore_weapons[0]),
                   "unknown-slot": (0, controller.build.space.fore_weapons[2]),
                   "skill": (2, controller.build.skills.space["eng"][0]),
                   "skill-unlock": (2, controller.build.skills.unlocks["eng"][0])}
        tab, button = targets[target]
        controller.tabbers.switch(tab)
        shell.resize(2200, 1100)
        shell.show()
        app.processEvents()
        assert button.tooltip
        pointer = button.mapToGlobal(button.rect().center())
        QCursor.setPos(pointer)
        button.enterEvent(QEnterEvent(QPointF(button.rect().center()), QPointF(button.rect().center()), QPointF(pointer)))
        assert button._tooltip_frame.isVisible()
        QToolTip.hideText()
        app.sendEvent(button, QHelpEvent(QEvent.Type.ToolTip, button.rect().center(), pointer))
        assert not QToolTip.isVisible(), "Qt displayed a second tooltip beside the SETS tooltip"
        assert button._tooltip_frame.isVisible()
    finally:
        QToolTip.hideText()
        manager.close(); adapter.close(); shell.close()


def test_catalogue_provider_is_interchangeable_and_uses_upstream_tooltip(app, tmp_path):
    class Catalogue:
        def __init__(self):
            self.threads, self.queries = [], []

        def query(self, query):
            self.threads.append(QThread.currentThread())
            self.queries.append(query)
            return {"schema_version": 1, "availability": "available", "source": "stodex-fixture",
                    "data": {"results": [{"availability": "available", "record": {
                        "id": "definition:" + item["id"], "kind": query["kind"], "name": "Catalogue name",
                        "type": "Ship Weapon", "rarity": "Common", "description": [
                            {"kind": "heading", "format": "text", "text": "Weapon effects"},
                            {"kind": "text", "format": "text", "text": "Catalogue <damage> & description"}]}}
                        for item in query["items"]]}}
    catalogue = Catalogue()
    build = fixture_build()
    shell, manager, adapter = make_host(tmp_path, build=build, catalogue=catalogue)
    try:
        shell.select_page(("network.stodex.sets", "build"))
        page = shell.pages[("network.stodex.sets", "build")]["widget"]
        wait_for(lambda: "descriptions loaded" in page.build_status.text())
        button = page.sets_controller.build.space.fore_weapons[0]
        assert "Catalogue &lt;damage&gt; &amp; description" in button.tooltip
        assert "Phaser Beam Array" in button.tooltip and "Catalogue name" not in button.tooltip
        assert "Common Ship Weapon" not in button.tooltip
        assert "color:" in button.tooltip and "Mk XV" in button.tooltip
        assert button.toolTip() == ""
        assert button.property("buildItemId") == "fixture-phaser"
        assert all(thread is not app.thread() for thread in catalogue.threads)
        assert catalogue.queries[0]["items"][0]["id"] == "fixture-phaser"
        assert manager.builds.get().to_dict() == build
        assert "stodex-fixture" in page.build_status.text()
    finally:
        manager.close(); adapter.close(); shell.close()


def test_native_skill_icons_use_resources_without_wiki_downloads(app, tmp_path, monkeypatch):
    from PIL import Image
    import requests
    monkeypatch.setattr(requests.sessions.Session, "request", lambda *a, **k: pytest.fail("Skills icon requested from wiki"))
    images = {}
    for token, color in [("Space_Hull_Heal", "red"), ("Ground_Damage", "blue")]:
        buffer = io.BytesIO()
        Image.new("RGBA", (8, 8), color).save(buffer, format="PNG")
        png = buffer.getvalue()
        images[token] = {"availability": "available", "bytes": len(png), "sha256": hashlib.sha256(png).hexdigest(),
                         "data": base64.b64encode(png).decode()}
    queries = []
    def query(arguments):
        queries.append(arguments)
        if "token" not in arguments:
            return {"availability": "unavailable", "reason": "No UI artwork in fixture"}
        return images[arguments["token"]]
    build = fixture_build()
    del build["data"]["slots"]["space"]["fore_weapons"][0]["item"]["icon"]
    build["data"]["skills"] = {"space": {"eng": [True] + [None] * 29},
                               "ground": [[False] + [None] * 5, [None] * 6, [None] * 4, [None] * 4]}
    build["data"]["native"] = {"skills": {"trees": [
        {"definition_key": "Player_Skills_Space", "definitions": [
            {"definition_key": "Player_Skills_Space.Engineering_T1.Hull_Healing_1", "icon_token": "Space_Hull_Heal"}]},
        {"definition_key": "Player_Skills_Ground", "definitions": [
            {"definition_key": "Player_Skills_Ground.Ground_Skills_C1.Wpn_Dmg_1", "icon_token": "Ground_Damage"}]}]}}
    shell, manager, adapter = make_host(tmp_path, resources=SimpleNamespace(query=query), build=build)
    try:
        shell.select_page(("network.stodex.sets", "build"))
        page = shell.pages[("network.stodex.sets", "build")]["widget"]
        wait_for(lambda: "2 icons loaded" in page.build_status.text())
        space = page.sets_controller.build.skills.space["eng"][0]
        ground = page.sets_controller.build.skills.ground[0][0]
        assert space._base.pixelColor(0, 0).getRgb() == (255, 0, 0, 255)
        assert ground._base.pixelColor(0, 0).getRgb() == (0, 0, 255, 255)
        assert space._overlay == page.sets_controller.images.overlays.check
        assert ground._overlay.isNull()
        assert space.property("buildSkillState") == "owned" and ground.property("buildSkillState") == "unowned"
        assert {q["token"] for q in queries if "token" in q} == set(images)
        assert manager.builds.get().to_dict() == build
        # A replacement without icon evidence must not keep the previous images.
        replacement = deepcopy(build)
        replacement["revision"] += 1
        del replacement["data"]["native"]
        assert manager.builds.publish(replacement)
        assert space._base.isNull() and ground._base.isNull()
    finally:
        manager.close(); adapter.close(); shell.close()


def test_catalogue_priority_changes_reenrich_existing_build(app, tmp_path):
    def catalogue(source):
        def query(key):
            return {"schema_version": 1, "availability": "available", "source": source, "data": {"results": [
                {"availability": "available", "record": {"id": source + ":" + item["id"], "type": "Ship Weapon",
                    "description": [{"kind": "text", "format": "text", "text": source + " description"}]}}
                for item in key["items"]]}}
        return SimpleNamespace(query=query)
    build = fixture_build()
    shell, manager, adapter = make_host(tmp_path, build=build, catalogue=catalogue("backup"))
    try:
        key = ("network.stodex.sets", "build")
        shell.select_page(key)
        page = shell.pages[key]["widget"]
        button = page.sets_controller.build.space.fore_weapons[0]
        wait_for(lambda: "backup description" in button.tooltip)
        token = manager.data.register("catalogue", catalogue("primary"), priority=200, source="primary-extension")
        wait_for(lambda: "primary description" in button.tooltip)
        assert "backup description" not in button.tooltip
        assert button.property("buildItemId") == "fixture-phaser"
        token.close()
        wait_for(lambda: "backup description" in button.tooltip)
        assert "primary description" not in button.tooltip
        assert manager.builds.get().to_dict() == build
        assert not manager.packages[key[0]].error
    finally:
        manager.close(); adapter.close(); shell.close()


def test_captain_unknown_elite_and_owned_skill_unlocks_render_read_only(app, tmp_path):
    from PySide6.QtCore import Qt
    build = fixture_build()
    build["data"]["captain"].update(career="Science", faction="Federation", species="Joined Trill", primary_spec="Miracle Worker", secondary_spec="Strategist")
    build["data"]["skill_unlocks"] = {"space": {"eng": [[True, False], [False, True], [None, None], [False, False], [True, False, True, False]]},
                                       "ground": [[False, True], [False, False], [None, None], [False, False], [True, False]]}
    shell, manager, adapter = make_host(tmp_path, build=build)
    try:
        shell.select_page(("network.stodex.sets", "build"))
        page = shell.pages[("network.stodex.sets", "build")]["widget"]
        controller = page.sets_controller
        assert controller.build.character.elite.checkState() == Qt.CheckState.PartiallyChecked
        assert controller.build.character.species.currentText() == "Joined Trill"
        assert controller.build.character.primary.currentText() == "Miracle Worker"
        eng = controller.build.skills.unlocks["eng"]
        assert "Hangar Health" in eng[0].tooltip and "Subsystem Repair" in eng[1].tooltip
        assert eng[2].property("buildSkillUnlockState") == "unknown"
        assert eng[3].property("buildSkillUnlockState") == "unowned"
        assert "Ablative Corruption" in eng[4].tooltip
        assert "Device Expertise" in controller.build.skills.unlocks["ground"][0].tooltip
        assert manager.builds.get().to_dict() == build
        assert not manager.packages["network.stodex.sets"].error
    finally:
        manager.close(); adapter.close(); shell.close()


def test_native_skill_layout_covers_every_sets_node_without_icon_identity():
    spec = importlib.util.spec_from_file_location("_test_captain_layout", Path(__file__).parent / "companion_pack/captain_layout.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    layout = module.skill_layout()
    keys = [item["id"] for nodes in layout["space"].values() for item in nodes] + [item["id"] for nodes in layout["ground"] for item in nodes]
    assert len(keys) == len(set(keys)) == 110
    assert layout["space"]["eng"][0]["id"] == "Player_Skills_Space.Engineering_T1.Hull_Healing_1"
    assert layout["ground"][1][2]["id"] == "Player_Skills_Ground.Ground_Skills_C2.Armor_1"


def test_late_catalogue_response_cannot_replace_new_build_or_disabled_view(app, tmp_path):
    started, release = threading.Event(), threading.Event()
    class DelayedCatalogue:
        def query(self, query):
            started.set()
            assert release.wait(5)
            return {"schema_version": 1, "availability": "available", "source": "delayed", "data": {"results": [
                {"availability": "available", "record": {"type": "Ship Weapon", "description": [
                    {"kind": "text", "format": "text", "text": "OLD CATALOGUE RESPONSE"}]}} for _ in query["items"]]}}
    shell, manager, adapter = make_host(tmp_path, build=fixture_build(), catalogue=DelayedCatalogue())
    try:
        key = ("network.stodex.sets", "build")
        shell.select_page(key)
        page = shell.pages[key]["widget"]
        wait_for(started.is_set)
        replacement = fixture_build()
        replacement["revision"] += 1
        replacement["data"]["slots"] = {"space": {"fore_weapons": [{"state": "empty"}]}}
        assert manager.builds.publish(replacement)
        release.set()
        QTest.qWait(100)
        button = page.sets_controller.build.space.fore_weapons[0]
        assert button.property("buildSlotState") == "empty"
        assert "OLD CATALOGUE RESPONSE" not in button.tooltip
        manager.deactivate(key[0])
        QTest.qWait(50)
        assert key not in shell.pages and not manager.packages[key[0]].error
    finally:
        release.set(); manager.close(); adapter.close(); shell.close()


def test_stowiki_port_matches_upstream_equipment_categories_and_tooltip(app, tmp_path, monkeypatch):
    import importlib
    # Load the source extension independently, exactly as the real host does.
    module_name = "_sets_test_wiki_source"
    source_root = Path(__file__).resolve().parents[3] / "companion/src/stodex_companion/extensions/stowiki_data"
    spec = importlib.util.spec_from_file_location(module_name, source_root / "extension.py", submodule_search_locations=[str(source_root)])
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    records = importlib.import_module(module_name + ".records")
    raw = []
    for name, type_ in [("Phaser Beam Array Mk XV [Dmg]", "Ship Weapon"), ("Example Console", "Universal Console"),
                        ("Science Console", "Ship Science Console"), ("Example Armor", "Body Armor"),
                        ("Hangar - Elite Excluded", "Hangar Bay")]:
        row = {"Page": name, "name": name, "type": type_, "rarity": "Common", "who": "Starship",
               **{prefix + str(i): None for i in range(1, 10) for prefix in ("head", "subhead", "text")}}
        row.update(head1="[[Phaser]]", subhead1="Energy", text1="* 100 '''Damage'''\n:Indented")
        raw.append(row)
    normalized = records.normalize("equipment", raw)
    shell, manager, adapter = make_host(tmp_path)
    try:
        shell.select_page(("network.stodex.sets", "build"))
        page = shell.pages[("network.stodex.sets", "build")]["widget"]
        cargo = page.sets_controller.cargo
        monkeypatch.setattr(cargo, "get_cargo_data", lambda *_: raw)
        cargo.cache_equipment_data()
        for category, entries in cargo.equipment.items():
            assert set(entries) == {record["name"] for record in normalized if category in record["categories"]}
        renderer = importlib.import_module("_stodex_ext_network_stodex_sets.catalogue_view")
        phaser = next(record for record in normalized if record["name"] == "Phaser Beam Array")
        assert renderer.description(phaser["description"], page.sets_controller.theme.tooltips) == cargo.equipment["fore_weapons"]["Phaser Beam Array"]["tooltip"]
    finally:
        manager.close(); adapter.close(); shell.close()


@pytest.mark.skipif(not DEFAULT_HELPER.is_file(), reason="Build HOGG helper first")
def test_native_item_tokens_load_actual_icons_and_keep_missing_placeholders(app, tmp_path):
    from PIL import Image
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('sets_token_hogg_fixtures',
        root.parents[1] / 'companion/tests/test_resources.py')
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
            assert 'Epic' in button.tooltip
            assert button.toolTip() == ''
            assert button.property('buildItemId') == item['id']
            assert page.build_renderer.icon_results[('token', 'phaser')]['resolution']['member'] == member
            assert missing.property('buildItemId') == 'missing'
            assert 'Icon unavailable' in missing.tooltip
            assert missing.toolTip() == ''
            assert '1 unavailable' in page.build_status.text()
            replacement = deepcopy(value)
            replacement['revision'] += 1
            replacement['data']['slots']['space']['fore_weapons'][0]['item']['rarity'] = 'Rare'
            assert manager.builds.publish(replacement)
            wait_for(lambda: '1 icons loaded' in page.build_status.text())
            assert button._overlay == page.sets_controller.images.overlays.rare
            assert 'Rare' in button.tooltip and 'Epic' not in button.tooltip
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
            assert "Icon unavailable" in button.tooltip
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
