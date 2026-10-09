"""Explainable, incremental similarities between CCDC MOFs and their recipes."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from typing import Any

from .chemical_resolver import DEFAULT_RESOLVER, ChemicalResolver, split_components
from .pubchem_resolver import cached_resolutions

if TYPE_CHECKING:
    from .store import KnowledgeStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


EDGE_TYPES = ("CHEMICALLY_SIMILAR_TO", "SYNTHESIS_SIMILAR_TO")
METALS = {
    "Li", "Na", "K", "Mg", "Ca", "Sr", "Ba", "Sc", "Ti", "V", "Cr", "Mn",
    "Fe", "Co", "Ni", "Cu", "Zn", "Y", "Zr", "Nb", "Mo", "Ag", "Cd", "Sn",
    "Sb", "La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho",
    "Er", "Tm", "Yb", "Lu", "Hf", "Hg", "Pb", "Bi",
}
NULLS = {"", "n/a", "na", "none", "null", "not reported", "unknown"}
ROLE_FIELDS = {
    "metal_sources": "metal_source", "linkers": "organic_linkers",
    "modulators": "modulators", "solvents": "solvents", "equipment": "equipment",
}


def _props(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def normalize_chemical(value: str, role: str = "", mof_metadata: dict[str, Any] | None = None) -> str:
    return DEFAULT_RESOLVER.normalize(value, role, mof_metadata)


def _items(
    value: Any, role: str, metadata: dict[str, Any], resolver: ChemicalResolver,
    resolutions: dict[str, dict[str, Any]], labels: dict[str, str],
) -> set[str]:
    parts = split_components(value, role)
    keys = set()
    for part in parts:
        normalized = resolver.normalize(part, role, metadata)
        if normalized in NULLS:
            continue
        record = resolutions.get(normalized) or {}
        key = (
            f"pubchem:{record['inchikey']}"
            if record.get("status") == "resolved" and record.get("inchikey") else normalized
        )
        keys.add(key)
        labels.setdefault(key, normalized)
    return keys


def _number(value: Any, kind: str) -> float | None:
    text = str(value.get("raw", "") if isinstance(value, dict) else value or "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group())
    if kind == "temperature" and re.search(r"(?:^|\s)K\b", text, re.I):
        number -= 273.15
    if kind == "time":
        if re.search(r"\b(?:d|days?)\b", text, re.I):
            number *= 24
        elif re.search(r"\b(?:min|minutes?)\b", text, re.I):
            number /= 60
    return round(number, 4)


def _metal_elements(formula: Any, metal_source: Any) -> set[str]:
    # CCDC formula is authoritative for the final framework; precursors provide a fallback.
    text = str(formula or metal_source or "")
    return {element for element in re.findall(r"[A-Z][a-z]?", text) if element in METALS}


def _formula_similarity(left: str, right: str) -> float | None:
    def vector(formula: str) -> dict[str, float]:
        result: dict[str, float] = {}
        for element, amount in re.findall(r"([A-Z][a-z]?)\s*(\d+(?:\.\d+)?)?", formula):
            result[element] = result.get(element, 0) + (float(amount) if amount else 1.0)
        total = sum(result.values())
        return {key: value / total for key, value in result.items()} if total else {}

    a, b = vector(left), vector(right)
    if not a or not b:
        return None
    dot = sum(value * b.get(key, 0) for key, value in a.items())
    norm = math.sqrt(sum(value * value for value in a.values())) * math.sqrt(
        sum(value * value for value in b.values())
    )
    return dot / norm if norm else None


def _jaccard(left: set[str], right: set[str]) -> float | None:
    if not left or not right:
        return None
    return len(left & right) / len(left | right)


def _near(left: float | None, right: float | None, scale: float, logarithmic: bool = False) -> float | None:
    if left is None or right is None:
        return None
    if logarithmic:
        left, right = math.log1p(max(0, left)), math.log1p(max(0, right))
    return math.exp(-abs(left - right) / scale)


def load_profiles(store: KnowledgeStore) -> dict[str, dict[str, Any]]:
    """Build one compact profile per MOF from authoritative nodes and recipe edges."""
    with store.connection() as conn:
        rows = conn.execute(
            """
            SELECT m.id,m.label,m.properties_json AS mof_properties,
                   r.properties_json AS recipe_properties,
                   p.label AS paper
            FROM nodes m
            LEFT JOIN edges e ON e.source_id=m.id AND e.edge_type='HAS_SYNTHESIS'
            LEFT JOIN nodes r ON r.id=e.target_id AND r.node_type='SynthesisRecipe'
            LEFT JOIN edges report ON report.target_id=m.id AND report.edge_type='REPORTS'
            LEFT JOIN nodes p ON p.id=report.source_id AND p.node_type='Paper'
            WHERE m.node_type='MOF'
            ORDER BY m.label
            """
        ).fetchall()
    definitions = []
    for row in rows:
        raw = _props(row["recipe_properties"]).get("raw_row") or {}
        definitions.append({role: raw.get(field) for role, field in ROLE_FIELDS.items()})
    resolver = ChemicalResolver.from_records(definitions)
    resolutions = cached_resolutions(store)
    profiles: dict[str, dict[str, Any]] = {}
    for row in rows:
        mof = _props(row["mof_properties"])
        recipe = _props(row["recipe_properties"])
        raw = recipe.get("raw_row") or {}
        code = row["label"]
        profile = {
            "id": int(row["id"]), "mof": code, "ccdc_number": str(mof.get("Number") or ""),
            "formula": mof.get("Formula") or "", "paper": row["paper"] or "",
            "metals": _metal_elements(mof.get("Formula"), raw.get("metal_source")),
            "temperature_c": _number(recipe.get("temperature"), "temperature"),
            "time_hours": _number(recipe.get("time"), "time"),
            "ph": _number(recipe.get("ph"), "ph"),
            "component_labels": {},
        }
        for role, field in ROLE_FIELDS.items():
            profile[role] = _items(
                raw.get(field), role, mof, resolver, resolutions, profile["component_labels"]
            )
        # A MOF may have multiple recipes. Prefer the one with most usable fields.
        richness = sum(bool(profile[role]) for role in ROLE_FIELDS) + sum(
            profile[key] is not None for key in ("temperature_c", "time_hours", "ph")
        )
        profile["richness"] = richness
        if code not in profiles or richness > profiles[code]["richness"]:
            profiles[code] = profile
    return profiles


def compare(left: dict[str, Any], right: dict[str, Any], kind: str) -> dict[str, Any] | None:
    chemistry = kind == "CHEMICALLY_SIMILAR_TO"
    weights = (
        {"metals": .35, "linkers": .30, "metal_sources": .15, "formula": .15, "solvents": .05}
        if chemistry else
        {"metals": .15, "metal_sources": .17, "linkers": .23, "solvents": .13,
         "modulators": .07, "equipment": .05, "temperature_c": .12, "time_hours": .08}
    )
    components: dict[str, float] = {}
    shared: dict[str, list[str]] = {}
    for field, weight in weights.items():
        if field == "temperature_c":
            value = _near(left[field], right[field], 40)
        elif field == "time_hours":
            value = _near(left[field], right[field], 1, logarithmic=True)
        elif field == "formula":
            value = _formula_similarity(left[field], right[field])
        else:
            value = _jaccard(left[field], right[field])
            if value is not None and left[field] & right[field]:
                shared[field] = sorted(
                    left["component_labels"].get(key)
                    or right["component_labels"].get(key)
                    or key for key in left[field] & right[field]
                )
        if value is not None:
            components[field] = round(value, 4)
    # A nearby temperature alone is not a meaningful synthesis analogy.
    if not shared.get("metals") or not any(
        shared.get(field) for field in ("metal_sources", "linkers")
    ):
        return None
    score = sum(weights[field] * value for field, value in components.items())
    return {
        "score": round(score, 4), "version": "mof-sim-v2", "components": components,
        "shared": shared, "temperature_difference_c": (
            round(abs(left["temperature_c"] - right["temperature_c"]), 2)
            if left["temperature_c"] is not None and right["temperature_c"] is not None else None
        ),
        "time_difference_hours": (
            round(abs(left["time_hours"] - right["time_hours"]), 2)
            if left["time_hours"] is not None and right["time_hours"] is not None else None
        ),
    }


def refresh_similarity_edges(store: KnowledgeStore, top_k: int = 3, minimum: float = .60) -> dict[str, int]:
    """Recompute bounded derived edges after every structured graph import."""
    profiles = load_profiles(store)
    values = list(profiles.values())
    proposed: dict[tuple[int, int, str], dict[str, Any]] = {}
    for kind in EDGE_TYPES:
        candidates: dict[int, list[tuple[float, int, dict[str, Any]]]] = {}
        for index, left in enumerate(values):
            for right in values[index + 1:]:
                if kind == "SYNTHESIS_SIMILAR_TO" and (
                    not left["richness"] or not right["richness"]
                ):
                    continue
                result = compare(left, right, kind)
                threshold = min(minimum, .48) if kind == "CHEMICALLY_SIMILAR_TO" else minimum
                if result is None or result["score"] < threshold:
                    continue
                a, b = sorted((left["id"], right["id"]))
                candidates.setdefault(a, []).append((result["score"], b, result))
                candidates.setdefault(b, []).append((result["score"], a, result))
        # Keep an edge if either endpoint selects it among its top neighbours.
        for source, ranked in candidates.items():
            for _, target, result in sorted(ranked, key=lambda item: (-item[0], item[1]))[:top_k]:
                a, b = sorted((source, target))
                proposed[(a, b, kind)] = result
    now = _now()
    with store.connection() as conn:
        conn.execute("DELETE FROM edges WHERE edge_type IN (?,?)", EDGE_TYPES)
        conn.executemany(
            """INSERT INTO edges(source_id,target_id,edge_type,edge_key,properties_json,created_at,updated_at)
               VALUES(?,?,?,'mof-sim-v2',?,?,?)""",
            [(a, b, kind, json.dumps(props, ensure_ascii=False, sort_keys=True), now, now)
             for (a, b, kind), props in proposed.items()],
        )
    counts = Counter(kind for _, _, kind in proposed)
    return {"mofs": len(profiles), "chemical_edges": counts[EDGE_TYPES[0]],
            "synthesis_edges": counts[EDGE_TYPES[1]]}


def similar_cases(store: KnowledgeStore, code: str, kind: str = "SYNTHESIS_SIMILAR_TO", limit: int = 4) -> list[dict[str, Any]]:
    if kind not in EDGE_TYPES:
        raise ValueError(f"Unsupported similarity kind: {kind}")
    profiles = load_profiles(store)
    target = profiles.get(code.upper())
    if target is None:
        return []
    with store.connection() as conn:
        rows = conn.execute(
            """SELECT e.source_id,e.target_id,e.properties_json,s.label AS source,t.label AS target
               FROM edges e JOIN nodes s ON s.id=e.source_id JOIN nodes t ON t.id=e.target_id
               WHERE e.edge_type=? AND (e.source_id=? OR e.target_id=?)""",
            (kind, target["id"], target["id"]),
        ).fetchall()
    results = []
    for row in rows:
        other_code = row["target"] if row["source_id"] == target["id"] else row["source"]
        other = profiles.get(other_code)
        if other is None:
            continue
        result = {"mof": other_code, "paper": other["paper"],
                  "temperature_c": other["temperature_c"], "time_hours": other["time_hours"],
                  "metal_sources": sorted(other["component_labels"].get(key, key) for key in other["metal_sources"]),
                  "linkers": sorted(other["component_labels"].get(key, key) for key in other["linkers"]),
                  "solvents": sorted(other["component_labels"].get(key, key) for key in other["solvents"]),
                  "modulators": sorted(other["component_labels"].get(key, key) for key in other["modulators"]),
                  **_props(row["properties_json"])}
        results.append(result)
    return sorted(results, key=lambda item: (-item["score"], item["mof"]))[:limit]


def recommend_cases(store: KnowledgeStore, code: str, limit: int = 4) -> dict[str, Any]:
    """Transfer reported conditions only from independent, chemically related cases."""
    profiles = load_profiles(store)
    target = profiles.get(code.upper())
    if target is None:
        return {"target": code.upper(), "status": "unknown_mof", "cases": []}
    candidates = similar_cases(store, code, kind="CHEMICALLY_SIMILAR_TO", limit=100)
    independent: list[dict[str, Any]] = []
    seen_numbers = {target["ccdc_number"]} if target["ccdc_number"] else set()
    for case in candidates:
        if case["score"] < .60:
            continue
        other = profiles[case["mof"]]
        number = other["ccdc_number"]
        if number and number in seen_numbers:
            continue
        if number:
            seen_numbers.add(number)
        if case["temperature_c"] is None and case["time_hours"] is None:
            continue
        independent.append(case)
        if len(independent) >= limit:
            break
    result: dict[str, Any] = {
        "target": code.upper(), "status": "limited_cases" if len(independent) < 3 else "case_summary",
        "cases": independent,
    }
    if len(independent) < 3:
        return result

    def weighted_quantile(field: str, fraction: float) -> float | None:
        values = sorted(
            (float(case[field]), float(case["score"]) ** 2)
            for case in independent if case[field] is not None
        )
        if len(values) < 3:
            return None
        total = sum(weight for _, weight in values)
        running = 0.0
        for value, weight in values:
            running += weight
            if running / total >= fraction:
                return value
        return values[-1][0]

    result["temperature_range_c"] = [weighted_quantile("temperature_c", .20),
                                      weighted_quantile("temperature_c", .80)]
    result["time_range_hours"] = [weighted_quantile("time_hours", .20),
                                  weighted_quantile("time_hours", .80)]
    systems = Counter()
    for case in independent:
        if case["solvents"]:
            systems["/".join(case["solvents"])] += case["score"] ** 2
    result["solvent_systems"] = [name for name, _ in systems.most_common(3)]
    return result
