# SPDX-License-Identifier: GPL-3.0-only
"""Opt-in, offline SETS page using Companion's public extension API."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
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
    # Only bundled static definitions and local images; no Cargo or download workers.
    controller.images.load_base_images()
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
    label = QLabel("SETS build preview · No live player build loaded")
    label.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(label)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(controller.window)
    layout.addWidget(scroll)
    # Retain Python controller/signal owners for the lifetime of the contributed page.
    page.sets_controller = controller
    return page


class Extension:
    def activate(self, context):
        self.context = context
        context.ui.register_page("build", "Build", self.page)

    def page(self):
        root = Path(__file__).resolve().parents[2]
        return create_view(root, self.context.storage.path.parent / "sets-preview")

    def deactivate(self):
        self.context = None


def create_extension():
    return Extension()
