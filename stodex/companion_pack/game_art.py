from stodex.sdk.assets import reference as catalog_reference, image as catalog_image
# SPDX-License-Identifier: GPL-3.0-only
"""Load copied game artwork exclusively through the Companion resources API."""
import base64
import hashlib
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

RARITY_COLORS = {"common": "White", "uncommon": "Green", "rare": "Blue",
                 "veryrare": "Purple", "ultrarare": "Ultraviolet", "epic": "Gold"}
GAME_ART = {name: {"archive": "texture.hogg", "member":
    f"Texture_Library/Ui/Icons/Rarity_Borders/Item_Rarity_Border_{color}.Wtex"}
    for name, color in RARITY_COLORS.items()}
for name, profession in {"eng": "Engineering", "sci": "Science", "tac": "Tactical",
                         "sci-small": "Science", "tac-small": "Tactical"}.items():
    size = "Small" if name.endswith("-small") else "Large"
    GAME_ART[name] = {"archive": "texture.hogg", "member":
        f"Texture_Library/Ui/Icons/Class_Icons/Class_Icons_Boff_Federation/Class_Icon_Boff_{profession}_{size}.Wtex"}
GAME_ART["ground"] = {"archive": "texture.hogg", "member":
    "Texture_Library/Ui/Icons/Hud_Icons/Hud_Skill_Ground.Wtex"}


GAME_ART = {name: catalog_reference(["images", "hogg", value["archive"], value["member"]]) for name, value in GAME_ART.items()}

def prepare_images(images, root):
    # Only application controls come from SETS. No disk cache of game images.
    images._images = {"arrow-up": QImage(root / "local/arrow-up.png"),
                      "arrow-down": QImage(root / "local/arrow-down.png")}
    images.get = lambda name: images._images.get(name, QImage())
    images.overlays.check = QImage(root / "local/check_overlay.png")
    for rarity in RARITY_COLORS:
        setattr(images.overlays, rarity, QImage())


class GameArt:
    def __init__(self, page, context):
        self.page, self.context = page, context
        self.results, self.ready, self.work = {}, False, None

    def load(self):
        if not self.context.data.has_provider("resources"):
            self.ready = True
            return
        def load():
            return {name: catalog_image(self.context.data, reference)
                    for name, reference in GAME_ART.items()}
        def delivered(results):
            self.results = results
            controller = self.page.sets_controller
            for name, result in results.items():
                image = QImage()
                if result.get("availability") == "available":
                    try:
                        png = base64.b64decode(result["data"], validate=True)
                        if len(png) > 4 * 1024 * 1024 or len(png) != result["bytes"] or hashlib.sha256(png).hexdigest() != result["sha256"]:
                            raise ValueError("Game artwork fingerprint mismatch")
                        image.loadFromData(png, "PNG")
                    except (ValueError, KeyError, TypeError):
                        pass
                if name in RARITY_COLORS:
                    setattr(controller.images.overlays, name, image)
                else:
                    size = 25 if name.endswith("-small") else round(controller.theme.opt.box_width * 1.2)
                    pixmap = QPixmap.fromImage(image).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                                          Qt.TransformationMode.SmoothTransformation) if not image.isNull() else QPixmap()
                    if name.endswith("-small"):
                        controller.images.icons[name] = pixmap
                    else:
                        controller.theme.icons[name] = pixmap
                        count = controller.build.skills.count_labels[name]
                        layout = count.parentWidget().layout()
                        row, col, _, _ = layout.getItemPosition(layout.indexOf(count))
                        label = layout.itemAtPosition(row - 1, col).widget()
                        label.setPixmap(pixmap)
                        if pixmap.isNull():
                            label.setText({"eng": "Engineering", "sci": "Science", "tac": "Tactical", "ground": "Ground"}[name])
                if image.isNull() and result.get("availability") == "available":
                    self.results[name] = {**result, "availability": "unavailable", "reason": "Invalid decoded game artwork"}
            self.ready = True
            self.page.build_renderer.refresh_rarity()
            unavailable = sum(r.get("availability") != "available" for r in self.results.values())
            self.context.log.info(f"SETS game artwork: {len(results) - unavailable} loaded through resources; {unavailable} unavailable")
        self.work = self.context.tasks.submit(load, delivered)

    def close(self):
        if self.work:
            self.work.close()
            self.work = None
