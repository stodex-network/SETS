# SPDX-License-Identifier: GPL-3.0-only
"""Canonical observations populate upstream widgets without catalogue-name joins."""
import base64
import hashlib
import html
import threading

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from stodex_companion.sdk.builds import BUILD_SLOTS


def placeholder(text):
    image = QImage(98, 128, QImage.Format.Format_ARGB32)
    image.fill(QColor("#303030"))
    painter = QPainter(image)
    painter.setPen(QColor("#eeeeee"))
    painter.setFont(QFont("Sans Serif", 12))
    painter.drawText(image.rect().adjusted(3, 3, -3, -3),
                     Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text[:64])
    painter.end()
    return image


def tooltip(slot):
    if slot["state"] != "occupied":
        return html.escape(slot.get("reason", slot["state"].capitalize()))
    item = slot["item"]
    details = [item.get("name") or item["id"], item["id"],
               " ".join(filter(None, [item.get("rarity"), item.get("mark"),
                                      " ".join(item.get("modifiers", ()))])),
               item.get("description", "")]
    return "<br>".join(html.escape(text) for text in details if text)


class BuildRenderer:
    def __init__(self, page, context):
        self.page, self.context = page, context
        self.generation = 0
        self.work = None
        self.cancelled = None
        self.snapshot = None

    def close(self):
        self.generation += 1
        if self.cancelled:
            self.cancelled.set()
        if self.work:
            self.work.close()
        self.work = None

    def update(self, snapshot):
        self.close()
        self.snapshot = snapshot
        page, controller = self.page, self.page.sets_controller
        scroll = (page.sets_scroll.horizontalScrollBar().value(),
                  page.sets_scroll.verticalScrollBar().value())
        if snapshot is None:
            data = {}
        else:
            data = snapshot.observation.data
        captain, ship = data.get("captain", {}), data.get("ship", {})
        controller.build.character.name.setText(captain.get("name", ""))
        controller.build.character.elite.setChecked(captain.get("elite", False))
        for field, widget in (("career", "career"), ("faction", "faction"), ("species", "species"),
                              ("primary_spec", "primary"), ("secondary_spec", "secondary")):
            combo = getattr(controller.build.character, widget)
            combo.blockSignals(True)
            value = captain.get(field, "")
            if combo.findText(value) < 0:
                combo.addItem(value)
            combo.setCurrentText(value)
            combo.blockSignals(False)
        controller.build.ship.button.setText(ship.get("name", "No ship observed"))
        controller.build.ship.name.setText(ship.get("instance_name", ""))
        controller.build.ship.desc.setPlainText(ship.get("description", ""))
        controller.build.ship.tier.blockSignals(True)
        controller.build.ship.tier.clear()
        controller.build.ship.tier.addItem(ship.get("tier", ""))
        controller.build.ship.tier.blockSignals(False)
        controller.build.ship.image.set_image(controller.images.empty)
        # Standalone template professions must not masquerade as observed officer seats.
        for index, combo in enumerate(controller.build.space.boff_labels):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(f"Station {index + 1}")
            combo.blockSignals(False)
            controller.build.space.boff_label_icons[index].hide()
        for combos in (controller.build.ground.boff_profs, controller.build.ground.boff_specs):
            for index, combo in enumerate(combos):
                combo.blockSignals(True)
                combo.clear()
                combo.addItem(f"Officer {index + 1}" if combos is controller.build.ground.boff_profs else "Not observed")
                combo.blockSignals(False)
        targets = {}
        if "icon" in ship:
            reference = ship["icon"]
            targets[(reference["archive"], reference["member"])] = [controller.build.ship.image]
        self.icon_results = {}
        occupied = unknown = 0
        for environment, categories in BUILD_SLOTS.items():
            build_widgets = getattr(controller.build, environment)
            supplied = data.get("slots", {}).get(environment, {})
            for category in categories:
                if category == "doffs":
                    slots = supplied.get(category, ())
                    for index, (spec, variant) in enumerate(zip(build_widgets.doffs_spec, build_widgets.doffs_variant)):
                        slot = slots[index] if index < len(slots) else {"state": "unknown"}
                        item = slot.get("item", {})
                        for combo, value in ((spec, item.get("name") or item.get("id") or slot["state"]),
                                             (variant, item.get("description", ""))):
                            combo.blockSignals(True)
                            combo.clear()
                            combo.addItem(value)
                            combo.setToolTip(tooltip(slot))
                            combo.blockSignals(False)
                        occupied += slot["state"] == "occupied"
                        unknown += slot["state"] == "unknown"
                    continue
                buttons = getattr(build_widgets, category)
                if category == "boffs":
                    buttons = [button for station in buttons for button in station]
                slots = supplied.get(category, ())
                for index, button in enumerate(buttons):
                    slot = slots[index] if index < len(slots) else {"state": "unknown", "reason": "Slot was not supplied"}
                    state = slot["state"]
                    button.clear()
                    button.setVisible(state != "unavailable")
                    text = tooltip(slot)
                    button.tooltip = text
                    button.setToolTip(text)
                    button.setProperty("buildSlotState", state)
                    button.setProperty("buildItemId", "")
                    if state == "occupied":
                        occupied += 1
                        item = slot["item"]
                        button.setProperty("buildItemId", item["id"])
                        button.set_item(placeholder(item.get("name") or item["id"]))
                        rarity = item.get("rarity", "").lower().replace(" ", "")
                        overlay = getattr(controller.images.overlays, rarity, None)
                        if overlay is not None:
                            button.set_overlay(overlay)
                        if "icon" in item:
                            reference = item["icon"]
                            key = (reference["archive"], reference["member"])
                            targets.setdefault(key, []).append(button)
                    elif state == "unknown":
                        unknown += 1
                        button.set_item(placeholder("?"))
        skills = data.get("skills", {})
        for career, buttons in controller.build.skills.space.items():
            nodes = skills.get("space", {}).get(career, [None] * len(buttons))
            controller.build.skills.count_labels[career].setText(
                f"{sum(node is True for node in nodes)} owned · {sum(node is None for node in nodes)} unknown")
            for button, state in zip(buttons, nodes):
                button.set_overlay(controller.images.overlays.check if state is True else QImage())
                button.setProperty("buildSkillState", "unknown" if state is None else "owned" if state else "unowned")
                button.setToolTip(button.tooltip + "<br>" + ("Not observed" if state is None else "Owned" if state else "Not owned"))
        for buttons, nodes in zip(controller.build.skills.ground, skills.get("ground", [[None] * 6, [None] * 6, [None] * 4, [None] * 4])):
            for button, state in zip(buttons, nodes):
                button.set_overlay(controller.images.overlays.check if state is True else QImage())
                button.setProperty("buildSkillState", "unknown" if state is None else "owned" if state else "unowned")
        ground_nodes = [node for group in skills.get("ground", [[None] * 20]) for node in group]
        controller.build.skills.count_labels["ground"].setText(
            f"{sum(node is True for node in ground_nodes)} owned · {sum(node is None for node in ground_nodes)} unknown")
        if snapshot is None:
            page.build_status.setText("SETS build viewer · No player build loaded")
            self.summary = page.build_status.text()
            return
        observation = snapshot.observation
        self.summary = (f"{captain.get('name') or data['captain_id']} · {snapshot.kind} · "
                        f"{observation.availability} · {occupied} items · {unknown} unknown slots · "
                        f"{observation.source} · {observation.observed_at_utc}")
        page.build_status.setText(self.summary)
        page.sets_scroll.horizontalScrollBar().setValue(scroll[0])
        page.sets_scroll.verticalScrollBar().setValue(scroll[1])
        if not targets:
            return
        if not self.context.data.has_provider("resources"):
            page.build_status.setText(self.summary + " · Icons unavailable: HOGG resources not configured")
            return
        generation = self.generation
        cancelled = self.cancelled = threading.Event()
        context = self.context

        def load():
            results = []
            for archive, member in targets:
                if cancelled.is_set():
                    break
                result = context.data.query("resources", {"op": "icon", "archive": archive, "member": member})
                results.append(((archive, member), result))
            return results

        def delivered(results):
            if generation != self.generation:
                return
            missing = 0
            for key, result in results:
                self.icon_results[key] = result
                image = QImage()
                reason = result.get("reason", "Invalid decoded icon")
                if result.get("availability") == "available":
                    try:
                        png = base64.b64decode(result["data"], validate=True)
                        if len(png) > 4 * 1024 * 1024 or len(png) != result["bytes"] or hashlib.sha256(png).hexdigest() != result["sha256"]:
                            raise ValueError("Icon fingerprint mismatch")
                        image.loadFromData(png, "PNG")
                    except (ValueError, KeyError, TypeError) as error:
                        reason = str(error)
                if image.isNull():
                    missing += 1
                    for button in targets[key]:
                        text = "<br>Icon unavailable: " + html.escape(reason)
                        if hasattr(button, "tooltip"):
                            button.tooltip += text
                        button.setToolTip(button.toolTip() + text)
                else:
                    for button in targets[key]:
                        if hasattr(button, "set_item"):
                            button.set_item(image)
                        else:
                            button.set_image(image)
            self.page.build_status.setText(self.summary + f" · {len(results) - missing} icons loaded · {missing} unavailable")

        page.build_status.setText(self.summary + " · Loading HOGG icons…")
        self.work = context.tasks.submit(load, delivered)
