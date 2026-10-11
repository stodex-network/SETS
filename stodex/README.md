# SETS in STOdex Companion

This opt-in extension wraps the existing SETS space, ground and skill layouts as a read-only Companion Build page. Version 0.2 receives immutable version-1 player builds through `context.builds`, populates supplied item/trait/officer slots, renders known skill ownership, and loads supplied item/ship icons through Companion's shared HOGG resources. It uses the host's QApplication and scopes its theme to the view. It starts neither wiki catalogue downloads nor live inventory acquisition, and never loads or writes a standalone SETS autosave.

The fork's `stodex` branch retains upstream standalone metadata and startup defaults. The upstream diff adds a keyword-only `hosted` constructor option and Python 3.11 syntax equivalents in four modules. The Companion adapter is entirely in `stodex/companion_pack`. Installing the upstream wheel into Companion is unsupported: upstream declares Python 3.14 / Qt 6.11, while this embedded preview is tested on Python 3.11 / Qt 6.8.3.

From the sto-datamine repository root, after initializing the SETS submodule and installing Companion as documented in its README:

```powershell
git submodule update --init integrations/SETS
companion/.venv/Scripts/python -m pip install -r integrations/SETS/stodex/requirements-companion.txt
companion/.venv/Scripts/python -m stodex_companion --mock --extension-dir integrations/SETS/stodex
companion/.venv/Scripts/python -m stodex_companion --mock --extension-dir integrations/SETS/stodex --build-file integrations/SETS/stodex/build-fixture.json
```

Select Build in Companion. All four view buttons remain usable; the unchanged wide layout is accessible through horizontal and vertical scrolling. The supplied fixture is explicitly authored demonstration data and includes a synthetic icon path for the HOGG test fixture, so its item will retain a text placeholder against an ordinary installation. To review real images, supply exact archive/member references from the installed-game resource inventory. Missing icons or missing HOGG configuration leave item names/native IDs visible with explicit errors.

Run the integration check with Companion installed and the requirements above available:

```powershell
companion/.venv/Scripts/python -m pytest integrations/SETS/stodex/test_companion.py companion/tests/test_extensions.py -q
$env:QT_SCALE_FACTOR = '1.5'
companion/.venv/Scripts/python -m pytest integrations/SETS/stodex/test_companion.py -q
Remove-Item Env:QT_SCALE_FACTOR
```

The tests deny wiki network IO, exercise actual extension lifecycle and all four tabs, check host ownership and read-only controls, and read a compressed WTEX through the real C# HOGG helper into the displayed item. They also cover retained builds, native item identity, deduplicated icons, missing images, escaped metadata, replacement snapshots and late completion suppression. Screenshots of populated space/ground views are saved in temporary test directories. These are supplied-build checks, not live inventory acceptance or comprehensive upstream editor regressions.

Publish via `context.builds.publish(snapshot)` on the GUI thread, or explicitly supply JSON through `--build-file`. See the host repository's `companion/BUILDS.md` for the envelope, slot capacities/states, skills, revision/session rules and HOGG icon response contract. The renderer projects copied identities and metadata directly into SETS widgets and retains the immutable source observation separately; no SETS catalogue-name cleanup runs. A future live publisher owns acquisition, source freshness, native slot/rank mapping and icon-token-to-archive/member resolution. Upstream `src/` is unchanged by this extension update.
