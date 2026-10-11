# SETS in STOdex Companion

This opt-in extension wraps the existing SETS space, ground and skill layouts as a Companion Build page. It uses Companion's QApplication and scopes the SETS theme to its widget. The first version is an empty, read-only offline preview: it loads bundled skill definitions and local assets, disables editor controls, and starts neither catalogue downloads nor live-data reads. It does not load a standalone SETS autosave. Configuration lives under the extension's Companion storage directory.

The fork's `stodex` branch retains upstream standalone metadata and startup defaults. The upstream diff adds a keyword-only `hosted` constructor option and Python 3.11 syntax equivalents in four modules. The Companion adapter is entirely in `stodex/companion_pack`. Installing the upstream wheel into Companion is unsupported: upstream declares Python 3.14 / Qt 6.11, while this embedded preview is tested on Python 3.11 / Qt 6.8.3.

From the sto-datamine repository root, after initializing the SETS submodule and installing Companion as documented in its README:

```powershell
git submodule update --init integrations/SETS
companion/.venv/Scripts/python -m pip install -r integrations/SETS/stodex/requirements-companion.txt
companion/.venv/Scripts/python -m stodex_companion --mock --extension-dir integrations/SETS/stodex
```

Select Build in Companion. All four view buttons remain usable; the unchanged wide SETS layout is accessible through horizontal and vertical scrolling. Images for equipped items and ships remain absent until a catalogue adapter exists. Full fidelity for tooltips and populated builds is future work.

Run the integration check with Companion installed and the requirements above available:

```powershell
companion/.venv/Scripts/python -m pytest integrations/SETS/stodex/test_companion.py companion/tests/test_extensions.py -q
$env:QT_SCALE_FACTOR = '1.5'
companion/.venv/Scripts/python -m pytest integrations/SETS/stodex/test_companion.py -q
Remove-Item Env:QT_SCALE_FACTOR
```

The test denies requests network IO, exercises real extension discovery/page creation/deactivation/reactivation and all four tabs, checks application/style/thread ownership and disabled custom equipment/ship widgets, and saves a screenshot in its temporary directory. These are offline checks, not live build acceptance or comprehensive upstream editor regression tests.

Future input should enter through a wrapper-owned canonical build observation and catalogue projection, then assign `controller.build.data` and call `controller.build.load_build()` on the GUI thread. The observation must preserve captain/session identity, time, revision, source, availability and native IDs outside the SETS dictionary. Catalogue resolution must supply ship/item/trait/officer definitions and local images before rendering populated builds. Do not pass live snapshots through the file loader's invalid-item cleanup, which can discard unresolved items. See the host repository's `notes/plans/sets-companion-integration.md` for source evidence and the staged live-data design.
