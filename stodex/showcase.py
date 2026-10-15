# SPDX-License-Identifier: GPL-3.0-only
"""Interactive supplied-build showcase using icons read from installed HOGGs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel
from stodex.__main__ import create_application, create_host
from stodex.sdk import plain
from stodex.sdk.builds import BUILD_SLOTS
from stodex.installation import discover_archive_root
from types import SimpleNamespace


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = create_application()
    root = Path(__file__).resolve().parent
    archives = args.archive_root or discover_archive_root()
    if archives is None:
        raise RuntimeError("Configure an installed piggs directory with --archive-root")
    shell, manager, adapter = create_host(SimpleNamespace(
        mock=True, pid=None, fixture="typical", storage_dir=args.output / "storage",
        extension_dir=[root], archive_root=archives))
    key = ("network.stodex.sets", "build")
    shell.select_page(key)
    package = manager.packages[key[0]]
    if package.error:
        raise RuntimeError(package.error)
    page = shell.pages[key]["widget"]
    context = package.context[1]
    evidence = QLabel("HOGG: reading installed icon inventory…")
    evidence.setWordWrap(True)
    page.layout().insertWidget(0, evidence)
    shell.setWindowTitle("STOdex — HOGG Icon Showcase")
    shell.showMaximized()
    shell.raise_()
    shell.activateWindow()
    app.aboutToQuit.connect(manager.close)
    app.aboutToQuit.connect(adapter.close)
    app.aboutToQuit.connect(shell.resources.close)
    state = {"inventory": None, "receipt": None}

    def inventory():
        health = shell.resources.request("health")
        members, offset = [], 0
        while True:
            result = shell.resources.list_members("texture.hogg",
                prefix="Texture_Library/Ui/Icons/Item_Icons/", offset=offset, limit=1000)
            members.extend(member["name"] for member in result["members"]
                           if member["name"].lower().endswith(".wtex"))
            offset += len(result["members"])
            if offset >= result["total"]:
                return health, members
            if not result["members"]:
                raise RuntimeError("Icon inventory made no progress")

    def populate(result):
        health, members = result
        state["inventory"] = {"health": health, "icons_in_archive": len(members)}
        evidence.setText(f"HOGG server online · PID {health['pid']} · {len(members):,} icon members found · Loading showcase")
        if not members:
            raise RuntimeError("No native item icons found")
        preferences = {
            "fore_weapons": ["space_weapon"], "aft_weapons": ["space_weapon"],
            "experimental": ["experimental"], "hangars": ["hangar"],
            "deflector": ["deflector"], "sec_def": ["deflector"], "engines": ["impulse"],
            "core": ["warp"], "shield": ["shield"], "devices": ["device"],
            "uni_consoles": ["console"], "eng_consoles": ["console"],
            "sci_consoles": ["console"], "tac_consoles": ["console"],
            "weapons": ["ground_weapon"], "armor": ["armor"], "ev_suit": ["ev_suit"],
            "personal_shield": ["personal_shield"], "kit": ["kit"], "kit_modules": ["kit_module"],
            "ground_devices": ["ground_device"], "traits": ["trait"],
            "starship_traits": ["trait"], "rep_traits": ["trait"], "active_rep_traits": ["trait"],
            "boffs": ["power", "kit_module"], "doffs": ["dutyofficer"],
        }
        used, slots = set(), {}
        for environment, categories in BUILD_SLOTS.items():
            slots[environment] = {}
            for category, capacity in categories.items():
                candidates = [name for name in members if any(token in name.lower()
                              for token in preferences.get(category, []))]
                candidates = candidates or members
                entries = []
                for index in range(capacity):
                    stride = max(1, len(candidates) // (capacity + 1))
                    start = ((index + 1) * stride) % len(candidates)
                    member = next((candidates[(start + n) % len(candidates)]
                                   for n in range(len(candidates))
                                   if candidates[(start + n) % len(candidates)] not in used), candidates[start])
                    used.add(member)
                    entries.append({"state": "occupied", "item": {
                        "id": "fixture:" + member, "name": Path(member).stem.replace("_", " "),
                        "rarity": ["Very Rare", "Ultra Rare", "Epic"][index % 3], "mark": "Mk XV",
                        "description": "Icon showcase only; not observed equipped inventory or a catalog join",
                        "icon": {"archive": "texture.hogg", "member": member},
                    }})
                slots[environment][category] = entries
        snapshot = {"schema_version": 1, "kind": "fixture", "session_id": "hogg-showcase",
            "scene_epoch": None, "revision": 1, "observed_at_utc": "2026-10-11T18:00:00Z",
            "source": "authored icon showcase; installed HOGG images", "consistency": "snapshot",
            "availability": "partial", "missing_fields": {"skills": "Not acquired", "ownership": "Demonstration only"},
            "data": {"captain_id": "showcase-captain", "captain": {"name": "Icon Showcase", "elite": True,
                "career": "Tactical", "species": "Alien", "faction": "Federation"},
                "ship": {"name": "Demonstration Ship", "instance_name": "HOGG Icon Showcase", "tier": "T6-X2"},
                "slots": slots}}
        (args.output / "build.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        context.builds.publish(snapshot)
        page.sets_controller.tabbers.switch(0)

    def verify():
        icons = page.build_renderer.icon_results
        samples = []
        for (archive, member), result in list(icons.items())[:3]:
            payload, source = shell.resources.read_member(archive, member)
            digest = hashlib.sha256(payload).hexdigest()
            if digest != result.get("member_sha256"):
                raise RuntimeError("Displayed icon differs from fresh HOGG read")
            samples.append({"member": member, "sha256": digest, "source": source})
        return {"health": shell.resources.request("health"), "fresh_read_checks": samples}

    def verified(result):
        icons = page.build_renderer.icon_results
        loaded = sum(icon.get("availability") == "available" for icon in icons.values())
        failed = len(icons) - loaded
        evidence.setText(f"HOGG server online · PID {result['health']['pid']} · {loaded} distinct native icons loaded · "
                         f"{failed} unavailable · 3 fresh-read hashes verified")
        receipt = {"pid": os.getpid(), "status": "passed", "visible": shell.isVisible(),
            "title": shell.windowTitle(), "icons_loaded": loaded, "icons_unavailable": failed,
            "scope": "authored showcase; no live equipped-build acquisition",
            "inventory": state["inventory"], **result,
            "icons": [{"archive": key[0], "member": key[1],
                       **plain({k: v for k, v in value.items() if k != 'data'})}
                      for key, value in icons.items()]}
        (args.output / "window.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        app.processEvents()
        shell.grab().save(str(args.output / "space.png"))
        page.sets_controller.tabbers.switch(1)
        app.processEvents()
        shell.grab().save(str(args.output / "ground.png"))
        page.sets_controller.tabbers.switch(0)

    def check():
        if package.error:
            evidence.setText("HOGG showcase failed: " + package.error)
            (args.output / "error.txt").write_text(package.error)
            timer.stop()
        elif state["inventory"] and page.build_renderer.icon_results and "Loading" not in page.build_status.text():
            timer.stop()
            context.tasks.submit(verify, verified)

    timer = QTimer()
    timer.setInterval(500)
    timer.timeout.connect(check)
    timer.start()
    context.tasks.submit(inventory, populate)
    app.exec()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        Path("results/sets-validation/showcase-error.txt").write_text(traceback.format_exc())
        raise
