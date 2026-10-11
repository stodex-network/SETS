# SETS in STOdex Companion

This opt-in extension wraps the existing SETS space, ground and skill layouts as a read-only Companion Build page. It receives immutable version-1 player builds through `context.builds`, populates supplied item/trait/officer slots, renders known skill ownership, and loads item/ship icons through Companion's shared HOGG resources. Version 0.4 resolves copied equipment icon tokens against the installed texture archives. It uses the host's QApplication and scopes its theme to the view. Live acquisition is explicit through **Read current Captain**; it starts no wiki catalogue downloads and never loads or writes a standalone SETS autosave.

The fork's `stodex-extension` branch retains upstream standalone metadata and startup defaults. The upstream diff adds a keyword-only `hosted` constructor option and Python 3.11 syntax equivalents in four modules. The Companion adapter is entirely in `stodex/companion_pack`. Installing the upstream wheel into Companion is unsupported: upstream declares Python 3.14 / Qt 6.11, while this embedded preview is tested on Python 3.11 / Qt 6.8.3.

From the SETS repository root on `stodex-extension`, after installing the sibling Companion checkout:

```powershell
../stodex-companion/.venv/Scripts/python -m pip install -r stodex/requirements-companion.txt
../stodex-companion/.venv/Scripts/python -m stodex_companion --mock --extension-dir stodex
../stodex-companion/.venv/Scripts/python -m stodex_companion --mock --extension-dir stodex --build-file stodex/build-fixture.json
```

Select Build in Companion. All four view buttons remain usable; the unchanged wide layout is accessible through horizontal and vertical scrolling. The supplied fixture is explicitly authored demonstration data and includes a synthetic icon path for the HOGG test fixture, so its item will retain a text placeholder against an ordinary installation. To review real images, supply exact archive/member references from the installed-game resource inventory. Missing icons or missing HOGG configuration leave item names/native IDs visible with explicit errors.

For a heavily populated interactive demonstration using installed-game icons, run the showcase from this repository root:

```powershell
../stodex-companion/.venv/Scripts/python stodex/showcase.py --output results/sets-showcase
```

The showcase inventories item-icon WTEX members through the shared HOGG helper, fills space/ground display slots with distinct representative resources and records the actual helper PID, decoded icon results, source fingerprints and three fresh-read SHA-256 comparisons. It saves the supplied JSON build, space/ground screenshots and a verification receipt in the output directory. `--archive-root <piggs>` overrides installed-game discovery. This is an icon/rendering demonstration: names derive from resource filenames, categories are illustrative, and it does not claim real equipped items, legal build combinations or native item-definition joins.

Run the integration check with Companion installed and the requirements above available:

```powershell
../stodex-companion/.venv/Scripts/python -m pytest stodex/test_companion.py ../stodex-companion/tests/test_extensions.py -q
$env:QT_SCALE_FACTOR = '1.5'
../stodex-companion/.venv/Scripts/python -m pytest stodex/test_companion.py -q
Remove-Item Env:QT_SCALE_FACTOR
```

The tests deny wiki network IO, exercise actual extension lifecycle and all four tabs, check host ownership and read-only controls, and read a compressed WTEX through the real C# HOGG helper into the displayed item. They also cover retained builds, native item identity, deduplicated icons, missing images, escaped metadata, replacement snapshots and late completion suppression. Screenshots of populated space/ground views are saved in temporary test directories. These are supplied-build checks, not live inventory acceptance or comprehensive upstream editor regressions.

Publish via `context.builds.publish(snapshot)` on the GUI thread, or explicitly supply JSON through `--build-file`. See the host repository's `../stodex-companion/BUILDS.md` for the envelope, slot capacities/states, skills, revision/session rules and HOGG icon response contract. The renderer projects copied identities and metadata directly into SETS widgets and retains the immutable source observation separately; no SETS catalogue-name cleanup runs. The current-Captain publisher owns acquisition and native slot/rank mapping; the shared resources provider owns icon-token resolution. Upstream `src/` is unchanged by this extension update.

## Current Captain reads

Version 0.3 adds **Read current Captain** to the embedded Build page. Connect Companion to an admitted Bridge 0.2.5 session and click the button to request one copied build. Ground/Space equipment and uniquely mapped Skills populate the existing read-only view; native trait slots and specialization IDs remain available in the retained observation, with their unvalidated display mappings explicit. The page does not poll, query public Info or contact the wiki. Older/disconnected Bridges report the unavailable capability. [The Bridge API contract](../../stodex-bridge-reshade/experiments/sto-reshade-bridge/protocol/captain-build.md) lists acquisition and display limits.

Version 0.4 displays copied equipment's native `icon_token` through installed-game resources. The shared provider inventories UI icon WTEX members in `texture*.hogg`, matches exact basenames case-insensitively and prefers Item_Icons over other UI icon members. Equally preferred duplicates remain ambiguous; missing, unsupported or changed resources leave text placeholders and explicit icon errors. Exact supplied archive/member references continue to take precedence. Resolution, decode and rendering use managed workers and retain source/hash evidence; no addon replacement or game restart is needed.

Version 0.4.1 supplies equipment rarity from the copied ItemQuality values, using AlgoItemProps when observed and ItemDef only when the algorithm is observed absent. Common, Uncommon, Rare, Very Rare, Ultra Rare and Epic use the existing upstream rarity overlays and appear in tooltips. Unavailable or unsupported quality remains unavailable, with raw values retained. This is a correction to the live publisher's item metadata; upstream rendering code and rarity assets are unchanged. Mark and modifier presentation remain unfinished.
