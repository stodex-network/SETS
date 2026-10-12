# SPDX-License-Identifier: GPL-3.0-only
"""Read-only SETS page using Companion builds and HOGG resources."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from .build_view import BuildRenderer
from .captain_layout import skill_layout

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QSlider, QVBoxLayout, QHBoxLayout, QWidget,
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
    # Observed builds are read-only; widget callbacks must never persist a projection.
    controller.build.autosave = lambda: None
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
    label.setWordWrap(True)
    header = QHBoxLayout()
    header.addWidget(label, 1)
    refresh = QPushButton("Read current Captain")
    refresh.setObjectName("sets-read-current-captain")
    header.addWidget(refresh)
    layout.addLayout(header)
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
        context.data.subscribe("catalogue", lambda _: self.changed(context.builds.get()))

    def changed(self, snapshot):
        if self.view is not None:
            self.view.build_renderer.update(snapshot)

    def page(self):
        root = Path(__file__).resolve().parents[2]
        self.view = create_view(root, self.context.storage.path.parent / "sets-preview")
        self.view.build_renderer = BuildRenderer(self.view, self.context)
        self.view.build_renderer.update(self.context.builds.get())
        self.context.ui.connect(self.view.read_current_captain.clicked, self.read_current)
        return self.view

    def read_current(self):
        if self.pending_read is not None:
            return
        from stodex_companion.build_projection import from_bridge
        context, page = self.context, self.view
        if not context.game.capability("captain.build.get").get("available"):
            page.build_status.setText("Current Captain read unavailable: connect to Bridge 0.2.5 or later")
            return
        layout = skill_layout()
        page.read_current_captain.setEnabled(False)
        page.build_status.setText("Reading current Captain…")
        captain_before = context.state.get("captain")
        actor_before = captain_before.data.get("captain_id") if captain_before else None
        self.pending_read = context.game.captain_build_get()
        def completed(result):
            self.pending_read = None
            page.read_current_captain.setEnabled(True)
            if result.status != "succeeded":
                page.build_status.setText("Captain read failed: " + str((result.error or {}).get("code", result.status)))
                return
            try:
                current = context.state.get("captain")
                actor_now = current.data.get("captain_id") if current else None
                if actor_before != actor_now or (actor_now is not None and result.data["data"].get("active_entity_id") != actor_now):
                    page.build_status.setText("Captain read discarded: active Captain changed")
                    return
                snapshot = from_bridge(result.data, layout)
                if not context.builds.publish(snapshot):
                    page.build_status.setText("Captain read discarded: session/scene changed or an older copy arrived")
            except (ValueError, TypeError, KeyError) as error:
                page.build_status.setText("Captain read unavailable: " + str(error))
        self.pending_read.then(completed)

    def deactivate(self):
        if self.view is not None:
            self.view.build_renderer.close()
        self.view = None
        self.pending_read = None
        self.context = None


def create_extension():
    return Extension()
