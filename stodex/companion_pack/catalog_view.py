# SPDX-License-Identifier: GPL-3.0-only
"""Map source-neutral catalog descriptions to the upstream SETS formatter."""
import html
import importlib


def description(blocks, styles):
    textedit = importlib.import_module("stodex_sets_upstream.textedit")
    parts = []
    fields = {"who": "who", "heading": "head1", "subheading": "subhead1", "text": "text1"}
    for block in blocks:
        text = block.get("text", "")
        if not isinstance(text, str) or block.get("kind") not in fields:
            raise ValueError("Unsupported catalog description block")
        format_ = block.get("format", "text")
        if format_ == "wikitext":
            # A single block uses the original formatter, preserving its wiki cleanup,
            # list/indent handling and the exact upstream tooltip styles.
            cargo = {"who": None, **{prefix + str(i): None for i in range(1, 10)
                                      for prefix in ("head", "subhead", "text")}}
            cargo[fields[block["kind"]]] = text
            parts.append(textedit.create_equipment_tooltip(cargo, styles))
        elif format_ == "text":
            style = {"who": styles.equipment_who, "heading": styles.equipment_head,
                     "subheading": styles.equipment_subhead, "text": "margin:0"}[block["kind"]]
            parts.append(f"<p style='{style}'>" + html.escape(text).replace("\n", "<br>") + "</p>")
        else:
            raise ValueError("Unsupported catalog text format: " + str(format_))
    return "".join(parts)


def catalog_tooltip(item, record, styles, provenance=None):
    textedit = importlib.import_module("stodex_sets_upstream.textedit")
    constants = importlib.import_module("stodex_sets_upstream.constants")
    body = description(record.get("description", ()), styles)
    name = html.escape(item.get("name") or item["id"])
    rarity = item.get("rarity", "")  # Catalog defaults never replace observed rarity.
    type_ = html.escape(record.get("type", ""))
    if rarity in constants.RARITY_COLORS:
        tooltip = textedit.add_equipment_tooltip_header(
            {"item": name, "mark": html.escape(item.get("mark", "")),
             "modifiers": [html.escape(mod) for mod in item.get("modifiers", ())], "rarity": rarity},
            {"type": type_, "tooltip": body}, styles)
    else:
        extras = [item.get("mark", ""), *item.get("modifiers", ())]
        name += "".join(" " + html.escape(value) for value in extras if value)
        tooltip = f"<p style='{styles.equipment_name}'>{name}</p>"
        subtitle = " ".join(filter(None, (html.escape(rarity), type_)))
        if subtitle:
            tooltip += f"<p style='{styles.equipment_type_subheader}'>{subtitle}</p>"
        tooltip += body
    tooltip += "<p>" + html.escape(item["id"]) + "</p>"
    if provenance and provenance.get("stale"):
        tooltip += "<p>Saved catalog data; refresh unavailable.</p>"
    return tooltip
