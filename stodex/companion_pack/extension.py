# SPDX-License-Identifier: GPL-3.0-only
"""Read-only SETS page using Companion builds and HOGG resources."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from .build_view import BuildRenderer
from .game_art import GameArt, prepare_images

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget,
)


def load_sets(root):
    # Upstream's generic `src` package must not shadow other extension packages.
    name = "stodex_sets_upstream"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, root / "src" / "__init__.py",
            submodule_search_locations=[str(root / "src")],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    del sys.modules[key]
            raise
    return sys.modules[name].SETS


def create_view(root, storage):
    sets_class = load_sets(root)

    class HostedSETS(sets_class):
        def cache_icons(self):
            load_icon = sys.modules["stodex_sets_upstream.iofunc"].load_icon
            for name, filename in {"copy": "copy.png", "paste": "paste.png", "clear": "clear.png",
                                   "edit": "edit.png", "link": "external_link.png", "info": "info.svg"}.items():
                self.theme.icons[name] = load_icon(filename, root)
            self.theme.icons["STOCD"] = load_icon("stocd.png", root,
                (self.theme.opt.box_height, self.theme.opt.box_width * 182 / 106))
            for name in ("ground", "eng", "sci", "tac", "dual_cannons"):
                self.theme.icons[name] = QPixmap()
            for name in ("sci-small", "tac-small"):
                self.images.icons[name] = QPixmap()

        def create_main_window(self, argv=None):
            app = QApplication.instance()
            if app is None:
                raise RuntimeError("Companion must create QApplication first")
            for filename in ("Overpass-VariableFont_wght.ttf", "RobotoMono-Regular.ttf"):
                QFontDatabase.addApplicationFont(str(root / "local" / filename))
            window = QWidget()
            window.setStyleSheet(self.theme.create_style_sheet(self.theme['app']['style']))
            return app, window

    storage.mkdir(parents=True, exist_ok=True)
    controller = HostedSETS(SimpleNamespace(config_dir=str(storage)), str(root),
                            "3.1.2 / STOdex preview", hosted=True)
    # Observed builds are read-only; widget callbacks must never persist a projection.
    controller.build.autosave = lambda: None
    # Only bundled static definitions and local images; no Cargo or download workers.
    prepare_images(controller.images, root)
    controller.init_ui()
    controller.build.load_build()
    controller.splash.show_splash(False)
    navigation = {"SPACE", "GROUND", "SPACE SKILLS", "GROUND SKILLS"}
    for button in controller.window.findChildren(QPushButton):
        button.setEnabled(button.text() in navigation)
    widgets = sys.modules["stodex_sets_upstream.widgets"]
    for kind in (widgets.ItemButton, widgets.ShipImage, widgets.ShipButton):
        for control in controller.window.findChildren(kind):
            control.setEnabled(False)
    for kind in (QComboBox, QCheckBox, QSlider):
        for control in controller.window.findChildren(kind):
            control.setEnabled(False)
    for kind in (QLineEdit, QPlainTextEdit):
        for control in controller.window.findChildren(kind):
            control.setReadOnly(True)
    page = QWidget()
    page.setObjectName("sets-build-viewer")
    layout = QVBoxLayout(page)
    label = QLabel("SETS build preview · No live player build loaded", page)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.hide()
    refresh = sys.modules["stodex_sets_upstream.widgetbuilder"].create_button2(controller.theme, "Read current Captain")
    refresh.setObjectName("sets-read-current-captain")
    refresh.setToolTip("Read your Captain from the connected STO session")
    # Reuse the upstream toolbar's occupied slot instead of adding a header row.
    save = next(button for button in controller.window.findChildren(QPushButton) if button.text() == "Clear Current Tab")
    toolbar = save.parentWidget().layout()
    def replace_button(layout):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget() is save:
                layout.insertWidget(i, refresh)
                for j in range(layout.count()):
                    button = layout.itemAt(j).widget()
                    if button and button is not refresh:
                        button.hide()
                return True
            if item.layout() and replace_button(item.layout()):
                return True
        return False
    if not replace_button(toolbar):
        raise RuntimeError("SETS build toolbar was not found")
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(controller.window)
    layout.addWidget(scroll)
    # Retain Python controller/signal owners for the lifetime of the contributed page.
    page.sets_controller = controller
    page.build_status = label
    page.sets_scroll = scroll
    page.read_current_captain = refresh
    return page


class Extension:
    def activate(self, context):
        self.context = context
        self.view = None
        self.pending_read = None
        context.ui.register_page("build", "Build", self.page)
        context.builds.subscribe(self.changed)
        context.data.subscribe("catalog", lambda _: self.changed(context.builds.get()))

    def changed(self, snapshot):
        if self.view is not None:
            self.view.build_renderer.update(snapshot)

    def page(self):
        root = Path(__file__).resolve().parents[2]
        self.view = create_view(root, self.context.storage.path.parent / "sets-preview")
        self.view.build_renderer = BuildRenderer(self.view, self.context)
        self.view.build_renderer.update(self.context.builds.get())
        self.view.game_art = GameArt(self.view, self.context)
        self.view.game_art.load()
        self.context.ui.connect(self.view.read_current_captain.clicked, self.read_current)
        return self.view

    def read_current(self):
        if self.pending_read is not None:
            return
        context, page = self.context, self.view
        page.read_current_captain.setEnabled(False)
        page.read_current_captain.setText("Reading Captain…")
        page.build_status.setText("Reading current Captain…")
        self.pending_read = context.builds.read_current()
        def completed(result):
            self.pending_read = None
            page.read_current_captain.setEnabled(True)
            page.read_current_captain.setText("Read current Captain")
            page.read_current_captain.setToolTip("Read your Captain from the connected STO session")
            if result.status != "succeeded":
                self.read_failed("Captain read failed: " + str((result.error or {}).get("code", result.status)))
        self.pending_read.then(completed)

    def read_failed(self, message):
        self.view.build_status.setText(message)
        self.view.read_current_captain.setText("Retry Captain read")
        self.view.read_current_captain.setToolTip(message)
        self.context.log.info(message)

    def deactivate(self):
        if self.view is not None:
            self.view.build_renderer.close()
            self.view.game_art.close()
        self.view = None
        self.pending_read = None
        self.context = None


def create_extension():
    return Extension()
