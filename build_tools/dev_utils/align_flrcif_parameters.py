#!/usr/bin/env python

"""Align parameter_registry.json with the flrCIF dictionary standard.

This script:
1. Reads parameter_registry.json and extracts parameter names + descriptions.
2. Checks each parameter against the bundled flrCIF dictionaries.
3. For parameters missing from the dictionaries, generates standard-compliant
   .dic entries and appends them to mmfdb_flr_ext.dic.
4. Adds a ``flrcif_item_id`` field to each parameter entry in the JSON,
   linking internal short names to canonical dictionary item identifiers.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from mmfdb.schema.pdbx_metadata import MmcifDictionary


CATEGORY = "flr_chisurf_parameter"
CATEGORY_ID = CATEGORY
SAVE_CATEGORY = f"save_{CATEGORY}"
SAVE_ITEM_PREFIX = f"save__{CATEGORY}."
ITEM_PREFIX = f"_{CATEGORY}."

#: Local extension namespace for schema bindings. PRD-44 replaced the
#: application-branded ``_chisurf_schema.*`` tags with this store-keyed,
#: vendor-neutral one; every entry in the shipped dictionary uses it.
SCHEMA_TAG_PREFIX = "_mmfdb_schema"

#: The extension dictionary this script appends to, resolved from the
#: dictionary package rather than a hard-coded tree location.
DEFAULT_DIC_PATH = MmcifDictionary.DATA_DIR / "mmfdb_flr_ext.dic"


def sanitize_cif_attribute(name: str) -> str:
    """Sanitize a parameter name for use as a CIF dictionary attribute.

    Dots, parentheses, commas, hyphens and other special characters are
    replaced with underscores so the result is a valid CIF identifier.
    Leading/trailing underscores and multiple consecutive underscores are
    collapsed.
    """
    s = name.replace(".", "_")
    s = s.replace("(", "_")
    s = s.replace(")", "_")
    s = s.replace(",", "_")
    s = s.replace("-", "_")
    s = re.sub(r"_+", "_", s)
    s = s.strip("_")
    if not s:
        s = "param"
    return s


def parameter_to_item_id(name: str) -> str:
    """Return the flrCIF item identifier for a parameter name."""
    attr = sanitize_cif_attribute(name)
    return f"{ITEM_PREFIX}{attr}"


def parameter_to_column_name(name: str) -> str:
    """Return the SQL column name for a parameter name."""
    col = name.replace(".", "_")
    col = col.replace("(", "_")
    col = col.replace(")", "_")
    col = col.replace(",", "_")
    col = col.replace("-", "_")
    col = re.sub(r"_+", "_", col)
    col = col.strip("_").lower()
    if not col:
        col = "param"
    return col


def load_parameter_registry(path: Path) -> Dict[str, Any]:
    """Load the parameter registry JSON."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "parameters" in data:
        return data
    return {"version": 1, "parameters": data if isinstance(data, dict) else {}}


def save_parameter_registry(path: Path, data: Dict[str, Any]) -> None:
    """Save the parameter registry JSON."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(path)


def get_all_dic_items() -> Set[str]:
    """Return the set of all item names across bundled flrCIF dictionaries.

    Raises
    ------
    Exception
        Whatever the dictionary loader raises. The failure is deliberately not
        swallowed: an empty set here reads as "nothing is defined yet", which
        would make :func:`process` re-append a definition for every parameter
        and duplicate the whole category in the shipped dictionary.
    """
    d = MmcifDictionary.load_bundled()
    existing: Set[str] = set()
    for cat_name in d.categories():
        cat = d.get_category(cat_name)
        if cat is None:
            continue
        for item in cat.items.values():
            existing.add(item.name)
    return existing


def generate_category_def() -> List[str]:
    """Generate the category definition for flr_chisurf_parameter."""
    return [
        "",
        f"save_{CATEGORY_ID}",
        f"   _category.id              {CATEGORY_ID}",
        "   _category.description",
        ";     ChiSurf-internal parameters mapped to flrCIF.",
        "      This category holds model/fit parameters that are used internally",
        "      by ChiSurf and exported to MMFDB using standard flrCIF identifiers.",
        "      Each item corresponds to one entry in the ChiSurf parameter registry.",
        ";",
        "   _category.mandatory_code  no",
        f"   _category_key.name        \"{ITEM_PREFIX}id\"",
        "",
    ]


def generate_item_def(
    name: str,
    description: str,
) -> str:
    """Generate the .dic item definition for a single parameter."""
    attr = sanitize_cif_attribute(name)
    item_id = f"{ITEM_PREFIX}{attr}"
    col_name = parameter_to_column_name(name)
    lines = [
        f"save__{CATEGORY_ID}.{attr}",
        f"   _item.name                \"{item_id}\"",
        f"   _item.category_id         {CATEGORY_ID}",
        "   _item_type.code           float",
        f"   {SCHEMA_TAG_PREFIX}.table_name  {CATEGORY_ID}",
        f"   {SCHEMA_TAG_PREFIX}.column_name {col_name}",
        "   _item_description.description",
    ]
    if description:
        lines.append(f";     {description}")
        lines.append(";")
    else:
        lines.append(f";     ChiSurf parameter {name}.")
        lines.append(";")
    return "\n".join(lines) + "\n"


def _replace_saveframe_description(
    content: str,
    attr: str,
    new_description: str,
) -> str:
    """Replace the ``_item_description.description`` block in one saveframe.

    Returns the updated file content. If the saveframe or its description
    block is not found, the content is returned unchanged.
    """
    save_header = f"save__{CATEGORY_ID}.{attr}"
    start = content.find(save_header)
    if start == -1:
        return content

    end = content.find("\nsave_", start + 1)
    frame_end = len(content) if end == -1 else end
    frame = content[start:frame_end]

    desc_re = re.compile(
        r"(_item_description\.description\s*\n);.*\n;",
        re.DOTALL,
    )
    if not desc_re.search(frame):
        return content

    if new_description:
        replacement = f";     {new_description}\n;"
    else:
        replacement = f";     ChiSurf parameter.\n;"

    new_frame = desc_re.sub(
        lambda m: m.group(1) + replacement,
        frame,
        count=1,
    )
    return content[:start] + new_frame + content[frame_end:]


def update_dic_descriptions(
    dic_path: Path,
    updates: Dict[str, str],
) -> int:
    """Rewrite ``_item_description.description`` blocks in the extension .dic.

    *updates* maps the sanitized attribute name (e.g. ``"ics_alpha"``) to
    the new description text. Returns the number of blocks actually
    rewritten.
    """
    if not updates:
        return 0
    content = dic_path.read_text(encoding="utf-8")
    changed = 0
    for attr, description in sorted(updates.items()):
        new_content = _replace_saveframe_description(content, attr, description)
        if new_content != content:
            content = new_content
            changed += 1
    if changed:
        dic_path.write_text(content, encoding="utf-8")
    return changed


def append_dic_entries(
    dic_path: Path,
    entries: str,
) -> None:
    """Append generated .dic entries to the extension dictionary file.

    If the file does not yet have a category definition for
    ``flr_chisurf_parameter``, it is inserted before the first item entry.
    """
    if not dic_path.exists():
        with open(dic_path, "w", encoding="utf-8") as fh:
            fh.write("")
    with open(dic_path, "r", encoding="utf-8") as fh:
        content = fh.read()
    if CATEGORY_ID not in content:
        cat_def = "\n".join(generate_category_def())
        entries = cat_def + "\n" + entries
    if content and not content.endswith("\n"):
        content += "\n"
    content += entries
    with open(dic_path, "w", encoding="utf-8") as fh:
        fh.write(content)


def process(
    registry_path: Path,
    dic_path: Path,
    dry_run: bool = False,
) -> int:
    """Run the alignment.

    Returns the number of new .dic entries added.
    """
    registry = load_parameter_registry(registry_path)
    params = registry.get("parameters", {})
    if not isinstance(params, dict):
        params = {}

    existing_dic_items = get_all_dic_items()
    d = MmcifDictionary.load_bundled()
    cat = d.get_category(CATEGORY)
    dic_descriptions: Dict[str, str] = {}
    if cat is not None:
        for attr, item in cat.items.items():
            dic_descriptions[attr] = (item.description or "").strip()

    new_entry_strings: List[str] = []
    desc_updates: Dict[str, str] = {}
    mapped_count = 0

    for key, entry in sorted(params.items()):
        if not isinstance(entry, dict):
            continue
        item_id = parameter_to_item_id(key)
        entry["flrcif_item_id"] = item_id
        mapped_count += 1
        attr = sanitize_cif_attribute(key)
        description = entry.get("description", "")
        if not isinstance(description, str):
            description = ""
        reg_desc = description.strip()
        if item_id in existing_dic_items:
            dic_desc = dic_descriptions.get(attr, None)
            if dic_desc is not None and reg_desc and dic_desc != reg_desc:
                desc_updates[attr] = reg_desc
            continue
        new_entry_strings.append(generate_item_def(key, description))

    if not dry_run:
        save_parameter_registry(registry_path, registry)
        if new_entry_strings:
            all_entries = "".join(new_entry_strings)
            append_dic_entries(dic_path, all_entries)
        if desc_updates:
            update_dic_descriptions(dic_path, desc_updates)

    return len(new_entry_strings)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Align ChiSurf's parameter registry with the flrCIF dictionary. "
            "Adds flrcif_item_id mappings to parameter_registry.json and "
            "generates missing .dic entries in mmfdb_flr_ext.dic."
        )
    )
    parser.add_argument(
        "--registry",
        type=str,
        default=None,
        help=(
            "Path to parameter_registry.json "
            "(defaults to chisurf/core/settings/constants/parameter_registry.json)."
        ),
    )
    parser.add_argument(
        "--dic",
        type=str,
        default=None,
        help=(
            "Path to mmfdb_flr_ext.dic "
            f"(defaults to the bundled {DEFAULT_DIC_PATH.name} in the "
            "dictionary package)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print changes without modifying files.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    here = Path(__file__).resolve()
    default_root = here.parent.parent.parent

    if args.registry is not None:
        registry_path = Path(args.registry).resolve()
    else:
        registry_path = default_root / "chisurf" / "core" / "settings" / "constants" / "parameter_registry.json"

    if args.dic is not None:
        dic_path = Path(args.dic).resolve()
    else:
        dic_path = DEFAULT_DIC_PATH

    added = process(registry_path, dic_path, dry_run=args.dry_run)
    if args.dry_run:
        print(f"[dry-run] Would add {added} new .dic entries to {dic_path}")
        print(f"[dry-run] Would update flrcif_item_id mappings in {registry_path}")
    else:
        print(f"Added {added} new .dic entries to {dic_path}")
        print(f"Updated flrcif_item_id mappings in {registry_path}")


if __name__ == "__main__":
    main()
