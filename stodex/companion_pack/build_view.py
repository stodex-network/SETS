# SPDX-License-Identifier: GPL-3.0-only
"""Render observations directly; enrich descriptions through Companion catalogs."""
import base64
import hashlib
import html
import threading

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from stodex.sdk.builds import BUILD_SLOTS
from .catalog_view import catalog_tooltip
from .captain_layout import skill_layout


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
        self.catalog_work = None

    def close(self):
        self.generation += 1
        if self.cancelled:
            self.cancelled.set()
        if self.work:
            self.work.close()
        if self.catalog_work:
            self.catalog_work.close()
        self.work = None
        self.catalog_work = None

    def update(self, snapshot):
        self.close()
        self.snapshot = snapshot
        self.cancelled = threading.Event()
        self.icon_status = self.catalog_status = ""
        self.icon_errors = {}
        self.catalog_results = {}
        self.catalog_image_results = {}
        page, controller = self.page, self.page.sets_controller
        scroll = (page.sets_scroll.horizontalScrollBar().value(),
                  page.sets_scroll.verticalScrollBar().value())
        if snapshot is None:
            data = {}
        else:
            data = snapshot.observation.data
        captain, ship = data.get("captain", {}), data.get("ship", {})
        controller.build.character.name.setText(captain.get("name", ""))
        elite = controller.build.character.elite
        elite.blockSignals(True)
        elite.setTristate(True)
        state = captain.get("elite")
        elite.setCheckState(Qt.CheckState.Checked if state is True else Qt.CheckState.Unchecked if state is False else Qt.CheckState.PartiallyChecked)
        elite.setToolTip("Elite Captain" if state is not None else "Elite Captain status not observed")
        elite.blockSignals(False)
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
        targets, catalog_targets = {}, {}
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
                    # ItemButton owns the SETS hover window; Qt's delayed tooltip
                    # would display the same content a second time.
                    button.setToolTip("")
                    button.setProperty("buildSlotState", state)
                    button.setProperty("buildItemId", "")
                    if state == "occupied":
                        occupied += 1
                        item = slot["item"]
                        kind = {"traits": "traits", "rep_traits": "traits", "active_rep_traits": "traits",
                                "starship_traits": "starship_traits", "boffs": "boff_abilities"}.get(category, "equipment")
                        lookup = (kind, environment, category, item["id"], item.get("name", ""))
                        catalog_targets.setdefault(lookup, []).append((button, item))
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
                        elif item.get("icon_token"):
                            targets.setdefault(("token", item["icon_token"]), []).append(button)
                    elif state == "unknown":
                        unknown += 1
                        button.set_item(placeholder("?"))
        skills = data.get("skills", {})
        layout = skill_layout()
        definitions = {}
        for tree in data.get("native", {}).get("skills", {}).get("trees", ()):
            for definition in tree.get("definitions", ()):
                key = definition.get("definition_key")
                if key:
                    # Repeated identities are ambiguous even if their images agree.
                    definitions[key] = None if key in definitions else definition
        def skill_icon(button, selector):
            # Reset the previous observation's image before asynchronous delivery.
            button.set_item(QImage())
            definition = definitions.get(selector["id"])
            if definition and definition.get("icon_token"):
                targets.setdefault(("token", definition["icon_token"]), []).append(button)
        for career, buttons in controller.build.skills.space.items():
            nodes = skills.get("space", {}).get(career, [None] * len(buttons))
            controller.build.skills.count_labels[career].setText(
                f"{sum(node is True for node in nodes)} owned · {sum(node is None for node in nodes)} unknown")
            for button, state, selector in zip(buttons, nodes, layout["space"][career]):
                skill_icon(button, selector)
                button.set_overlay(controller.images.overlays.check if state is True else QImage())
                button.setProperty("buildSkillState", "unknown" if state is None else "owned" if state else "unowned")
                self.skill_tooltip(button, state)
        for buttons, nodes, selectors in zip(controller.build.skills.ground, skills.get("ground", [[None] * 6, [None] * 6, [None] * 4, [None] * 4]), layout["ground"]):
            for button, state, selector in zip(buttons, nodes, selectors):
                skill_icon(button, selector)
                button.set_overlay(controller.images.overlays.check if state is True else QImage())
                button.setProperty("buildSkillState", "unknown" if state is None else "owned" if state else "unowned")
                self.skill_tooltip(button, state)
        ground_nodes = [node for group in skills.get("ground", [[None] * 20]) for node in group]
        controller.build.skills.count_labels["ground"].setText(
            f"{sum(node is True for node in ground_nodes)} owned · {sum(node is None for node in ground_nodes)} unknown")
        self.show_skill_unlocks(data)
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
        self.load_catalog(catalog_targets)
        if not targets:
            return
        if not self.context.data.has_provider("resources"):
            self.icon_status = "Icons unavailable: HOGG resources not configured"
            self.show_status()
            return
        generation = self.generation
        cancelled = self.cancelled
        context = self.context

        def load():
            results = []
            for archive, member in targets:
                if cancelled.is_set():
                    break
                arguments = {"token": member} if archive == "token" else {"archive": archive, "member": member}
                result = context.data.query("resources", {"op": "icon", **arguments})
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
                        self.icon_errors[id(button)] = reason
                        text = "<br>Icon unavailable: " + html.escape(reason)
                        if hasattr(button, "tooltip"):
                            button.tooltip += text
                        else:
                            button.setToolTip(button.toolTip() + text)
                else:
                    for button in targets[key]:
                        if hasattr(button, "set_item"):
                            button.set_item(image)
                        else:
                            button.set_image(image)
            self.icon_status = f"{len(results) - missing} icons loaded · {missing} unavailable"
            self.show_status()

        self.icon_status = "Loading HOGG icons…"
        self.show_status()
        self.work = context.tasks.submit(load, delivered)

    def show_status(self):
        self.page.build_status.setText(" · ".join(filter(None, (self.summary, self.icon_status, self.catalog_status))))
        self.context.log.info(self.page.build_status.text())

    def refresh_rarity(self):
        if self.snapshot is None:
            return
        controller = self.page.sets_controller
        for environment, categories in self.snapshot.observation.data.get("slots", {}).items():
            for category, slots in categories.items():
                if category in {"doffs", "boffs"}:
                    continue
                buttons = getattr(getattr(controller.build, environment), category)
                for button, slot in zip(buttons, slots):
                    if slot["state"] == "occupied":
                        rarity = slot["item"].get("rarity", "").lower().replace(" ", "")
                        overlay = getattr(controller.images.overlays, rarity, None)
                        if overlay is not None:
                            button.set_overlay(overlay)

    @staticmethod
    def skill_tooltip(button, state):
        original = button.property("buildSkillBaseTooltip")
        if original is None:
            original = button.tooltip
            button.setProperty("buildSkillBaseTooltip", original)
        button.tooltip = original + "<br>" + ("Not observed" if state is None else "Owned" if state else "Not owned")
        button.setToolTip("")

    def show_skill_unlocks(self, data):
        controller = self.page.sets_controller
        skills, unlocks = data.get("skills", {}), data.get("skill_unlocks", {})
        for career, buttons in controller.build.skills.unlocks.items():
            environment = "ground" if career == "ground" else "space"
            observed = unlocks.get("ground", ()) if environment == "ground" else unlocks.get("space", {}).get(career, ())
            definitions = controller.build._cache.skills.get(environment + "_unlocks", {})
            if environment == "space":
                definitions = definitions.get(career, ())
            for i, button in enumerate(buttons):
                button.clear()
                choices = observed[i] if i < len(observed) else ()
                known = bool(choices) and all(c is not None for c in choices)
                selected = [j for j, c in enumerate(choices) if c is True]
                state = "unknown" if not known else "owned" if selected else "unowned"
                if known and len(choices) == 2 and len(selected) > 1:
                    state = "ambiguous"
                button.setProperty("buildSkillUnlockState", state)
                button.tooltip = {"unknown": "Skill Unlock not observed", "unowned": "Skill Unlock not owned",
                                  "ambiguous": "Both Skill Unlock choices are owned"}.get(state, "")
                if state == "owned" and i < len(definitions):
                    definition = definitions[i]
                    if len(choices) == 2:
                        detail = definition["nodes"][selected[0]]
                        button.set_item(controller.images.get("arrow-up" if selected[0] == 0 else "arrow-down"))
                        button.tooltip = f"<p>{html.escape(detail['name'])}</p><p>{detail['desc']}</p>"
                    else:
                        button.set_item(controller.images.get(definition["name"]))
                        names = [definition["name"] if j == 0 else definition["options"][j - 1]["name"] for j in selected]
                        button.tooltip = "<br>".join(html.escape(name) for name in names)
                button.setToolTip("")
            nodes = skills.get("ground", ()) if environment == "ground" else (skills.get("space", {}).get(career, ()),)
            nodes = [node for group in nodes for node in group]
            total = sum(node is True for node in nodes)
            complete = bool(nodes) and all(node is not None for node in nodes)
            for index, segment in enumerate(controller.build.skills.bonus_bars[career]):
                segment.blockSignals(True)
                segment.setChecked(index < total)
                segment.setProperty("buildSkillState", "owned" if index < total else "unowned" if complete else "unknown")
                segment.setToolTip("Owned Skill points" if index < total else "Not owned" if complete else "Skill points not fully observed")
                segment.blockSignals(False)

    def load_catalog(self, targets):
        if not targets:
            return
        context = self.context
        if not context.data.has_provider("catalog"):
            self.catalog_status = "Descriptions unavailable: no catalog datasource"
            self.show_status()
            return
        generation, cancelled = self.generation, self.cancelled
        def load():
            groups = {}
            for key in targets:
                groups.setdefault(key[0], []).append(key)
            results = []
            for kind, keys in groups.items():
                if cancelled.is_set():
                    break
                query = {"op": "lookup", "kind": kind, "items": [
                    {"id": key[3], "name": key[4], "environment": key[1], "category": key[2]} for key in keys]}
                response = context.data.query("catalog", query)
                values = response.get("data", {}).get("results", ())
                images, downloaded = {}, {}
                for key, result in zip(keys, values):
                    if cancelled.is_set():
                        break
                    # Explicit native icon evidence keeps ownership of its artwork.
                    if any("icon" in item or item.get("icon_token") for _, item in targets[key]):
                        continue
                    identity = result.get("record", {}).get("image", {}).get("id") if result.get("availability") == "available" else None
                    if isinstance(identity, str):
                        if identity not in downloaded:
                            downloaded[identity] = context.data.query("resources", {"op": "get", "path": ["images", identity]})
                        images[key] = downloaded[identity]
                results.append((keys, response, images))
            return results
        def delivered(groups):
            if generation != self.generation:
                return
            loaded = 0
            source = "catalog"
            for keys, response, images in groups:
                source = response.get("source", source)
                values = response.get("data", {}).get("results", ()) if response.get("schema_version") == 1 else ()
                for index, key in enumerate(keys):
                    result = values[index] if index < len(values) else {"availability": "unavailable", "reason": response.get("reason", "Invalid catalog response")}
                    self.catalog_results[key] = result
                    if result.get("availability") != "available":
                        continue
                    try:
                        rendered = [(button, catalog_tooltip(item, result["record"], self.page.sets_controller.theme.tooltips,
                                                              result.get("provenance", response.get("provenance")))) for button, item in targets[key]]
                    except (ValueError, TypeError, KeyError):
                        continue
                    loaded += 1
                    image_result = images.get(key)
                    image = QImage()
                    if image_result is not None:
                        self.catalog_image_results[key] = image_result
                        if image_result.get("availability") in {"available", "partial"}:
                            try:
                                value = image_result["data"]["value"]
                                png = base64.b64decode(value["data"], validate=True)
                                if value["format"] != "png" or len(png) > 4 * 1024 * 1024 or len(png) != value["bytes"] or hashlib.sha256(png).hexdigest() != value["sha256"]:
                                    raise ValueError("Catalog image fingerprint mismatch")
                                image.loadFromData(png, "PNG")
                            except (ValueError, KeyError, TypeError):
                                pass
                    for button, text in rendered:
                        if not image.isNull():
                            button.set_item(image)
                        if id(button) in self.icon_errors:
                            text += "<br>Icon unavailable: " + html.escape(self.icon_errors[id(button)])
                        button.tooltip = text
            self.catalog_status = f"{loaded} descriptions loaded · {len(targets) - loaded} unmatched · {source}"
            self.show_status()
        self.catalog_status = "Loading catalog descriptions…"
        self.show_status()
        self.catalog_work = context.tasks.submit(load, delivered)
