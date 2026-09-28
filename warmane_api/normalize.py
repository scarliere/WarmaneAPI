"""Conservative conversions: unknown fields and unknown values survive unchanged."""

NUMERIC = {"level", "achievementpoints", "honorablekills", "membercount",
           "pvepoints", "classmask", "racemask", "skill", "item", "points"}


def normalize(value, key=""):
    if key == "professions" and isinstance(value, dict) and "professions" in value:
        return normalize(value["professions"], key)
    if isinstance(value, dict):
        return {k: normalize(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v, key) for v in value]
    if key in {"achievementpoints", "points"} and value is None:
        return 0
    if key == "online":
        if value in (True, 1, "1", "true"):
            return True
        if value in (False, 0, "0", "false"):
            return False
    if key in NUMERIC and isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    return value
