"""Parse public armory pages without executing scripts or fetching linked assets.

Required containers and row shapes are checked deliberately: markup drift must
produce a parse error rather than a plausible but empty result.
"""
import re
from urllib.parse import parse_qs, urljoin

from bs4 import BeautifulSoup


def required(root, selector):
    node = root.select_one(selector)
    if node is None:
        raise ValueError(f"Missing {selector}")
    return node


def text(node):
    return node.get_text(" ", strip=True)


def direct_text(node):
    return " ".join(str(s).strip() for s in node.find_all(string=True, recursive=False) if str(s).strip())


def number(value):
    value = value.replace(",", "").strip()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def pair(value):
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", value)
    if not match:
        raise ValueError("Expected current / maximum")
    return [int(x) for x in match.groups()]


def linked_id(node, kind):
    match = re.search(rf"(?:[?&/]|^){kind}=(\d+)(?:\D|$)", node.get("href", ""))
    if not match:
        raise ValueError(f"Missing {kind} ID")
    return int(match[1])


def safe_url(value):
    if not value:
        return None
    result = urljoin("https://armory.warmane.com/", value)
    return result if result.startswith(("http://", "https://")) else None


# Slot names describe the WotLK profile layout, not item inventory-type IDs.
SLOTS = {"item-left": ["head", "neck", "shoulders", "back", "chest", "shirt", "tabard", "wrists"],
         "item-right": ["hands", "waist", "legs", "feet", "finger_1", "finger_2", "trinket_1", "trinket_2"],
         "item-bottom": ["main_hand", "off_hand", "ranged_or_relic"]}


def profile(soup):
    root = required(soup, "#character-profile")
    stats = {}
    for column in required(root, ".character-stats").select(".text"):
        # Each column has section labels followed by spans containing values.
        label = None
        for child in column.children:
            if isinstance(child, str) and child.strip():
                label = child.strip()
            elif getattr(child, "name", None) == "span" and "value" in child.get("class", []):
                if not label:
                    raise ValueError("Stats without a label")
                values = {}
                for line in child.stripped_strings:
                    key, sep, value = line.partition(":")
                    if sep:
                        values[key.strip()] = number(value)
                if not values:
                    raise ValueError("Empty stats section")
                stats[label] = values
    if not stats:
        raise ValueError("Missing stat groups")
    skills = {"primary": [], "secondary": []}
    for group in root.select(".profskills"):
        heading = group.find_previous("h3")
        label = text(heading) if heading else ""
        if label not in {"Professions", "Secondary Skills"}:
            raise ValueError("Unknown profession heading")
        for entry in group.select(".text"):
            current, maximum = pair(text(required(entry, ".value")))
            skills["secondary" if label == "Secondary Skills" else "primary"].append(
                {"name": direct_text(entry), "skill": current, "maximum": maximum})
    equipment = []
    for group, slots in SLOTS.items():
        cells = required(root, "." + group).select(".item-slot")
        if len(cells) != len(slots):
            raise ValueError("Equipment layout changed")
        for slot, cell in zip(slots, cells):
            link = cell.select_one("a[rel]")
            item = {"slot": slot, "item_id": None, "enchant_code": None, "gem_codes": [],
                    "quality": None, "icon_url": None}
            if link:
                rel = link.get("rel", [])
                params = parse_qs(" ".join(rel) if isinstance(rel, list) else rel)
                item["item_id"] = int(params["item"][0])
                item["enchant_code"] = int(params["ench"][0]) if "ench" in params else None
                item["gem_codes"] = [int(v) for v in params["gems"][0].split(":")] if "gems" in params else []
                quality = re.search(r"\bicon-quality(\d+)\b", " ".join(required(cell, ".icon-quality").get("class", [])))
                item["quality"] = int(quality[1]) if quality else None
                icon = link.select_one("img")
                item["icon_url"] = safe_url(icon.get("src")) if icon else None
            elif not cell.select_one(".tooltip[data-tooltip]"):
                raise ValueError("Unrecognized equipment slot")
            equipment.append(item)
    activity = []
    for entry in required(root, ".recent-activity").select(".stub"):
        link = required(entry, '.name a[href*="achievement="]')
        activity.append({"achievement_id": linked_id(link, "achievement"), "name": text(link),
                         "relative_time": text(required(entry, ".time"))})
    pvp = {direct_text(entry): number(text(required(entry, ".value")))
           for entry in required(root, ".pvpbasic").select(".text")}
    return {"stats": stats, "secondary-professions": skills["secondary"], "profession-details": skills["primary"],
            "equipment-details": equipment, "recent-activity": activity, "pvp-summary": pvp}


def talents(soup):
    glyph_root = required(soup, ".character-glyphs")
    containers = soup.select(".talents-container[id^=spec-]")
    if not containers:
        raise ValueError("No talent containers")
    selected = soup.select_one(".talent-spec-switch td.selected[data-spec]")
    active = int(selected["data-spec"]) if selected else None
    specs = []
    for container in containers:
        spec_id = int(container["id"].split("-")[1])
        trees = []
        for frame in container.select(".talent-frame"):
            info = required(frame, ".talent-tree-info")
            spans = info.select("span")
            if len(spans) != 2:
                raise ValueError("Unknown talent tree heading")
            nodes = []
            for tier, row in enumerate(required(frame, ".talent-tree").select(".tier")):
                for link in row.select("a.talent"):
                    current, maximum = pair(text(required(link, ".talent-points")))
                    column = next((int(c[3:]) for c in link.get("class", []) if re.fullmatch(r"col\d+", c)), None)
                    nodes.append({"spell_id": linked_id(link, "spell"), "points": current, "max_points": maximum,
                                  "tier": tier, "column": column})
            points = int(text(spans[1]))
            if not nodes or sum(n["points"] for n in nodes) != points:
                raise ValueError("Talent nodes do not match displayed total")
            trees.append({"name": text(spans[0]), "points": points, "talents": nodes})
        if len(trees) != 3:
            raise ValueError("Expected three talent trees")
        glyphs = []
        group = required(glyph_root, f'[data-glyphs="{spec_id}"]')
        for glyph in group.select(".glyph"):
            link = required(glyph, "a")
            kind = next((c for c in glyph.get("class", []) if c in {"major", "minor"}), None)
            if kind is None:
                raise ValueError("Unknown glyph kind")
            glyphs.append({"kind": kind, "name": text(link), "spell_id": linked_id(link, "spell")})
        specs.append({"spec_index": spec_id, "active": spec_id == active if active is not None else None,
                      "trees": trees, "glyphs": glyphs})
    return specs


def collections(soup):
    result = {}
    for name, selector in [("mounts", "#mount-tab"), ("companions", "#companion-tab")]:
        container = required(soup, selector)
        entries = []
        for box in container.select(".journal-box"):
            link = required(box, ".basic a")
            entries.append({"name": text(link), "item_id": linked_id(link, "item"), "url": safe_url(link["href"])})
        result[name] = entries
    return result


def reputation(soup):
    rows = soup.select("div.reputation")
    if not rows:
        raise ValueError("No reputation rows; empty layout not verified")
    result = []
    for row in rows:
        current, maximum = pair(text(required(row, ".contentbody")))
        standing = text(required(row, ".standing"))
        result.append({"faction": text(required(row, ".name")), "standing": standing,
                       "progress": current, "maximum": maximum,
                       "is_exalted_placeholder": standing == "Exalted" and (current, maximum) == (999, 999)})
    return result


def categories(soup):
    container = required(soup, ".categories")
    result = []
    for link in container.select("a[data-category], a[data-subcategory]"):
        parent = link.find_parent(attrs={"data-submenu": True})
        result.append({"id": link.get("data-category", link.get("data-subcategory")), "name": text(link),
                       "parent_id": parent["data-submenu"] if parent else None})
    if not result:
        raise ValueError("Missing categories")
    return result


def achievements(soup, category):
    if category == "summary":
        root = required(soup, ".achievement-summary")
        total_text = text(required(root, ".progress-text"))
        current, maximum = pair(total_text.partition(":")[2])
        groups = []
        for group in root.select(".summary-progress"):
            value = text(required(group, ".progress-text"))
            values = pair(value) if "/" in value else (int(value), None)
            groups.append({"name": direct_text(group), "completed": values[0], "total": values[1]})
        if not groups:
            raise ValueError("Missing achievement categories")
        return {"completed": current, "total": maximum, "categories": groups}
    root = required(soup, ".achievement-list")
    items = []
    for row in root.select(".achievement"):
        identifier = row.get("id", "")
        if not re.fullmatch(r"ach\d+", identifier):
            raise ValueError("Missing achievement ID")
        date = row.select_one(".date")
        points = row.select_one(".points")
        reward = row.select_one(".reward")
        items.append({"achievement_id": int(identifier[3:]), "name": text(required(row, ".title")),
                      "description": text(required(row, ".description")),
                      "points": int(text(points)) if points else None,
                      "earned": date is not None and text(date).startswith("Earned "),
                      "date_text": text(date) if date else None,
                      "reward": text(reward) if reward else None,
                      "criteria_text": [text(n) for n in row.select(".criteria, .criteria-list, .progress-text")] or None})
    return {"category": category, "achievements": items}


def statistics(soup, category):
    table = required(soup, "#data-table")
    if [text(n) for n in table.select("thead th")] != ["Description", "Value"]:
        raise ValueError("Statistics columns changed")
    values = []
    for row in required(table, "tbody").select("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) != 2:
            raise ValueError("Statistics row changed")
        raw = text(cells[1])
        values.append({"description": text(cells[0]), "value": None if raw == "- -" else number(raw), "display_value": raw})
    return {"category": category, "statistics": values}


def match_history(soup):
    table = required(soup, "#data-table-history")
    if [text(n) for n in table.select("thead th")] != ["Match ID", "Team", "Outcome", "Personal Rating", "Start Time", "Duration", "Map", "Details"]:
        raise ValueError("Match history columns changed")
    matches = []
    for row in required(table, "tbody").select("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) != 8:
            raise ValueError("Match history row changed")
        identifier = required(row, "[data-gameid]")["data-gameid"]
        if not identifier and not text(cells[0]) and not text(cells[1]) and not text(cells[2]):
            continue  # Warmane renders a blank placeholder for a character with no matches.
        if not identifier.isdigit():
            raise ValueError("Missing match ID")
        matches.append({"match_id": int(identifier), "team": text(cells[1]), "outcome": text(cells[2]),
                        "personal_rating": text(cells[3]), "start_time": text(cells[4]),
                        "start_timestamp": number(cells[4].get("data-order", "")),
                        "duration": text(cells[5]), "map": text(cells[6])})
    return matches


def match_details(data, name, realm):
    if not isinstance(data, list) or not data:
        raise ValueError("No match participants")
    result = []
    for row in data:
        if not isinstance(row, dict) or not {"charname", "realm", "damageDone", "healingDone", "deaths", "killingBlows"}.issubset(row):
            raise ValueError("Match details changed")
        result.append({"name": row["charname"], "realm": row["realm"],
                       "class_id": int(row["class"]), "race_id": int(row["race"]), "gender_id": int(row["gender"]),
                       "team": text(BeautifulSoup(row.get("teamnamerich", row.get("teamname", "")), "html.parser")),
                       "damage_done": int(row["damageDone"]), "healing_done": int(row["healingDone"]),
                       "deaths": int(row["deaths"]), "killing_blows": int(row["killingBlows"]),
                       "matchmaking_rating": text(BeautifulSoup(row.get("matchmaking_change", ""), "html.parser")),
                       "personal_rating": text(BeautifulSoup(row.get("personal_change", ""), "html.parser"))})
    if not any(r["name"].casefold() == name.casefold() and r["realm"].casefold() == realm.casefold() for r in result):
        raise ValueError("Requested character is not in this match")
    return result


def parse_page(section, markup, name, realm, category=None):
    soup = BeautifulSoup(markup, "html.parser")
    if category is not None:
        if section == "achievements":
            return achievements(soup, category)
        if section == "statistics":
            return statistics(soup, category)
        raise ValueError("Unknown category page")
    sheet = required(soup, "#character-sheet")
    title = required(sheet, ".information .name")
    if direct_text(title).casefold() != name.casefold():
        raise ValueError("Unexpected character")
    subtitle = text(required(sheet, ".level-race-class"))
    if not re.search(r",\s*" + re.escape(realm) + r"(?:,|$)", subtitle, re.I):
        raise ValueError("Unexpected realm")
    parsers = {"profile": profile, "talents": talents,
               "mounts-and-companions": collections, "reputation": reputation,
               "achievements": categories, "statistics": categories, "match-history": match_history}
    return parsers[section](soup)
