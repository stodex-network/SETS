# SETS in STOdex

This opt-in extension wraps the existing SETS space, ground and skill layouts as a read-only Companion Build page. It receives immutable version-1 player builds through `context.builds`, populates supplied item/trait/officer slots, renders known skill ownership, and loads item/ship icons through Companion's shared HOGG resources. Version 0.5 obtains descriptive records from Companion's shared `catalog` provider and formats tooltips with the existing SETS renderer. It uses the host's QApplication and scopes its theme to the view. Live acquisition is explicit through **Read current Captain**; the page queries Companion for descriptions and never loads or writes a standalone SETS autosave.

The fork's `stodex-extension` branch retains upstream standalone metadata and startup defaults. The upstream source diff adds a keyword-only `hosted` constructor option and Python 3.11 syntax equivalents in four modules. The Companion adapter is entirely in `stodex/companion_pack`. Bundled game artwork is removed from this fork; the supported Companion view obtains it through resources. Installing the upstream wheel into Companion is unsupported: upstream declares Python 3.14 / Qt 6.11, while this embedded preview is tested on Python 3.11 / Qt 6.8.3.

From the SETS repository root on `stodex-extension`, after installing the sibling STOdex app checkout:

```powershell
../stodex-app/.venv/Scripts/python -m pip install -r stodex/requirements-companion.txt
../stodex-app/.venv/Scripts/python -m stodex_companion --mock --extension-dir stodex
../stodex-app/.venv/Scripts/python -m stodex_companion --mock --extension-dir stodex --build-file stodex/build-fixture.json
```

Select Build in Companion. All four view buttons remain usable; the unchanged wide layout is accessible through horizontal and vertical scrolling. The supplied fixture is explicitly authored demonstration data and includes a synthetic icon path for the HOGG test fixture, so its item will retain a text placeholder against an ordinary installation. To review real images, supply exact archive/member references from the installed-game resource inventory. Missing icons or missing HOGG configuration leave item names/native IDs visible with explicit errors.

For a heavily populated interactive demonstration using installed-game icons, run the showcase from this repository root:

```powershell
../stodex-app/.venv/Scripts/python stodex/showcase.py --output results/sets-showcase
```

The showcase inventories item-icon WTEX members through the shared HOGG helper, fills space/ground display slots with distinct representative resources and records the actual helper PID, decoded icon results, source fingerprints and three fresh-read SHA-256 comparisons. It saves the supplied JSON build, space/ground screenshots and a verification receipt in the output directory. `--archive-root <piggs>` overrides installed-game discovery. This is an icon/rendering demonstration: names derive from resource filenames, categories are illustrative, and it does not claim real equipped items, legal build combinations or native item-definition joins.

Run the integration check with Companion installed and the requirements above available:

```powershell
../stodex-app/.venv/Scripts/python -m pytest stodex/test_companion.py ../stodex-app/tests/test_extensions.py -q
$env:QT_SCALE_FACTOR = '1.5'
../stodex-app/.venv/Scripts/python -m pytest stodex/test_companion.py -q
Remove-Item Env:QT_SCALE_FACTOR
```

The tests use explicitly configured offline providers, exercise actual extension lifecycle and all four tabs, check host ownership and read-only controls, and read a compressed WTEX through the real C# HOGG helper into the displayed item. They also cover retained builds, native item identity, deduplicated icons, missing images, escaped metadata, replacement snapshots, late completion suppression and interchangeability of catalog providers. A parity check compares the STOwiki port's equipment categories and tooltip body against the original SETS CargoManager. Screenshots of populated space/ground views are saved in temporary test directories. These are supplied-build checks, not live inventory acceptance or comprehensive upstream editor regressions.

Publish via `context.builds.publish(snapshot)` on the GUI thread, or explicitly supply JSON through `--build-file`. See the host repository's `../stodex-app/BUILDS.md` for the envelope, slot capacities/states, skills, revision/session rules and HOGG icon response contract. The renderer projects copied identities and metadata directly into SETS widgets and retains the immutable source observation separately; no SETS catalog-name cleanup runs. STOdex app owns current-Captain acquisition and native slot/rank mapping through `context.builds.read_current()`; the shared resources provider owns icon-token resolution. Upstream `src/` is unchanged by this extension update.

## Current Captain reads

The toolbar button delegates to the app's shared `context.builds.read_current()` API. SETS no longer imports a native projection or publishes the read result itself. The app checks identity, session, scene and revision before publishing, and cancellation on extension deactivation prevents late updates. Use the matching current `stodex-app` checkout. The retained local `captain_layout.py` remains for existing fixture and compatibility consumers; production acquisition uses the unchanged selectors copied into the app.

Version 0.7 loads all 110 Skills button images from copied native node definitions through Companion's shared resources provider. Ownership remains a separate observation. Missing and ambiguous icon identities leave the image unavailable; replacement observations clear old images. Rarity borders and profession images also use verified HOGG resources. The hosted image manager never reads a game-image download cache. Bundled game artwork is deleted; SETS branding, fonts and generic application controls remain local. This fork's standalone entry point is not validated after that asset removal.

The Build page places **Read current Captain** in the existing SETS toolbar and omits the capture-status rows. Read diagnostics go to Companion's log. Extension actions, including STOwiki refresh, are accessible under **Extensions / settings → Extension actions**, alongside connection details.

Version 0.6 adds typed Ground Captain career/origin/species and Elite Captain status, assigned primary/secondary specializations, selected trait categories, and native Skills/Skill Unlock ownership from Bridge 0.2.7. Skills use exact Player_Skills node identities in `companion_pack/captain_layout.py`, covering all 110 buttons independently of SETS icon names. Skill Unlock arrows and ultimate enhancements display observed ownership; missing and conflicting choices remain explicit. Unknown Elite status is indeterminate. Current alignment remains separate from the Faction selector's origin/species meaning. Native trait assignments preserve native slot indices, and descriptions/icons use the existing independent datasource contracts. Ground representation and loaded definition Messages are required for Captain species; a Space ship skeleton never supplies it. Officer training/seating and build application remain deferred.

Version 0.3 adds **Read current Captain** to the embedded Build page. Connect Companion to an admitted Bridge 0.2.5 session and click the button to request one copied build. Ground/Space equipment and uniquely mapped Skills populate the existing read-only view; native trait slots and specialization IDs remain available in the retained observation, with their unvalidated display mappings explicit. The page does not poll or query public Info. Older/disconnected Bridges report the unavailable capability. [The Bridge API contract](../../stodex-bridge-reshade/experiments/sto-reshade-bridge/protocol/captain-build.md) lists acquisition and display limits.

## Catalog descriptions

Version 0.5 uses `context.data.query("catalog", {"op": "lookup", "kind": ..., "items": [...]})` through managed Tasks, independent of HOGG icon loading. Native definition IDs, display names and slot categories are supplied as lookup hints. Companion tries registered catalogs in descending priority order, passing unresolved items to each subsequent provider and retaining each match's provenance. Each provider chooses how to match them; SETS has no wiki downloader, fallback URL or dependency on a particular datasource extension. Companion's default STOwiki Data extension uses SETS' original acquisition backend and resolves normalized display names. A future STOdex provider can resolve native keys using the same [catalog contract](../../stodex-app/CATALOG.md).

Matched description blocks use upstream SETS tooltip formatting with the observed item's name, rarity, Mark and modifiers. Source definition rarity never changes an item's overlay. Missing, ambiguous or unsupported descriptions keep the item and its basic tooltip visible. Provider changes and explicit data refreshes rerun enrichment; replaced builds and deactivated views suppress late delivery. Wiki descriptions do not establish current-Captain computed statistics. Bundled Skills layouts and native ownership mappings remain unchanged.

Version 0.6.1 uses the existing SETS hover window as the sole tooltip for items, Traits, Skills and Skill Unlocks. It avoids registering that content with Qt's delayed tooltip, which otherwise displays a second copy. Ordinary controls without a SETS hover window retain their Qt tooltips.

Version 0.4 displays copied equipment's native `icon_token` through installed-game resources. The shared provider inventories UI icon WTEX members in `texture*.hogg`, matches exact basenames case-insensitively and prefers Item_Icons over other UI icon members. Equally preferred duplicates remain ambiguous; missing, unsupported or changed resources leave text placeholders and explicit icon errors. Exact supplied archive/member references continue to take precedence. Resolution, decode and rendering use managed workers and retain source/hash evidence; no addon replacement or game restart is needed.

Version 0.4.1 supplies equipment rarity from the copied ItemQuality values, using AlgoItemProps when observed and ItemDef only when the algorithm is observed absent. Common, Uncommon, Rare, Very Rare, Ultra Rare and Epic use the existing upstream rarity overlays and appear in tooltips. Unavailable or unsupported quality remains unavailable, with raw values retained. This is a correction to the live publisher's item metadata; upstream rendering code and rarity assets are unchanged. Mark and modifier presentation remain unfinished.

Matched catalog definitions can supply an explicit static image identity when the observed item has no native icon reference or token. The renderer resolves that identity through the app's `resources.images` catalog on a worker, validates the PNG fingerprint and applies it only to the current build generation. SETS-Data owns downloading and caching. The observed item identity and immutable build snapshot remain intact.
