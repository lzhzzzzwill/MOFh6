"""Cached PubChem PUG REST identifiers for structured synthesis chemicals."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .chemical_resolver import ChemicalResolver, KNOWN_NAMES, split_components

if TYPE_CHECKING:
    from .store import KnowledgeStore


BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
EDGE_ROLES = {
    "USES_METAL_SOURCE": "metal_sources",
    "USES_LINKER": "linkers",
    "USES_MODULATOR": "modulators",
    "USES_SOLVENT": "solvents",
}
INCHIKEY_PATTERN = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
ELEMENTS = set(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni "
    "Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe "
    "Cs Ba La Ce Pr Nd Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg "
    "Tl Pb Bi Po At Rn".split()
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cached_resolutions(store: KnowledgeStore) -> dict[str, dict[str, Any]]:
    with store.connection() as conn:
        rows = conn.execute(
            "SELECT query,status,cid,inchikey,title,molecular_formula,checked_at "
            "FROM chemical_resolutions"
        ).fetchall()
    return {row["query"]: dict(row) for row in rows}


def cache_resolution(store: KnowledgeStore, outcome: dict[str, Any]) -> None:
    """Persist a definitive PubChem result; transient failures must be retried."""
    if outcome.get("status") not in {"resolved", "ambiguous", "not_found"}:
        return
    with store.connection() as conn:
        conn.execute(
            """INSERT INTO chemical_resolutions
               (query,status,cid,inchikey,title,molecular_formula,candidates_json,checked_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(query) DO UPDATE SET status=excluded.status,cid=excluded.cid,
               inchikey=excluded.inchikey,title=excluded.title,
               molecular_formula=excluded.molecular_formula,
               candidates_json=excluded.candidates_json,checked_at=excluded.checked_at""",
            (outcome["query"], outcome["status"], outcome.get("cid"), outcome.get("inchikey"),
             outcome.get("title"), outcome.get("molecular_formula"),
             json.dumps(outcome.get("candidates", [])), _now()),
        )


def _candidate_query(name: str, role: str, resolver: ChemicalResolver) -> str | None:
    normalized = resolver.normalize(name, role)
    if not normalized or normalized in {"n/a", "na", "unknown", "none", "null"}:
        return None
    if "family" in normalized or "position unspecified" in normalized:
        return None
    # Short undefined article codes (e.g. HL1, BPNO) are not chemical names.
    raw = name.strip()
    if re.fullmatch(r"[A-Z][A-Z0-9_'-]{1,10}", raw) and normalized not in set(KNOWN_NAMES.values()):
        parts = re.findall(r"[A-Z][a-z]?", raw)
        formula = bool(parts) and all(part in ELEMENTS for part in parts)
        formula = formula and bool(re.fullmatch(r"(?:[A-Z][a-z]?\d*)+", raw))
        if not formula or (not any(char.isdigit() for char in raw) and len(parts) > 2):
            return None
    return normalized


class PubChemResolver:
    def __init__(self, timeout: float = 6.0, request_interval: float = 0.26):
        self.timeout = timeout
        self.request_interval = request_interval
        self._last_request = 0.0

    def _get_json(self, url: str) -> dict[str, Any]:
        wait = self.request_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
        request = Request(url, headers={"User-Agent": "MOFh6/1.0 (chemical identity lookup)",
                                        "Accept": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            raise ValueError("PubChem returned an unexpected response")
        return data

    def resolve(self, query: str) -> dict[str, Any]:
        encoded = quote(query, safe="")
        url = f"{BASE_URL}/compound/name/{encoded}/cids/JSON?name_type=complete"
        try:
            cid_data = self._get_json(url)
        except HTTPError as exc:
            if exc.code == 404:
                return {"query": query, "status": "not_found", "candidates": []}
            return {"query": query, "status": "unavailable", "reason": f"HTTP {exc.code}"}
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            return {"query": query, "status": "unavailable",
                    "reason": f"{type(exc).__name__}: {exc}"[:200]}

        cids = cid_data.get("IdentifierList", {}).get("CID", [])
        cids = sorted({int(value) for value in cids if str(value).isdigit()})
        if not cids:
            return {"query": query, "status": "not_found", "candidates": []}
        if len(cids) != 1:
            return {"query": query, "status": "ambiguous", "candidates": cids[:50]}

        cid = cids[0]
        url = f"{BASE_URL}/compound/cid/{cid}/property/MolecularFormula,InChIKey,Title/JSON"
        try:
            properties = self._get_json(url).get("PropertyTable", {}).get("Properties", [])
        except HTTPError as exc:
            return {"query": query, "status": "unavailable", "reason": f"HTTP {exc.code}"}
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            return {"query": query, "status": "unavailable",
                    "reason": f"{type(exc).__name__}: {exc}"[:200]}
        if len(properties) != 1 or str(properties[0].get("CID", "")) != str(cid):
            return {"query": query, "status": "unavailable", "reason": "invalid_properties"}
        item = properties[0]
        inchikey = str(item.get("InChIKey") or "")
        if not INCHIKEY_PATTERN.fullmatch(inchikey):
            return {"query": query, "status": "unavailable", "reason": "missing_inchikey"}
        return {
            "query": query, "status": "resolved", "cid": cid, "inchikey": inchikey,
            "title": str(item.get("Title") or ""),
            "molecular_formula": str(item.get("MolecularFormula") or ""),
            "candidates": [cid],
        }


def _collect_chemicals(store: KnowledgeStore) -> tuple[list[dict[str, Any]], ChemicalResolver]:
    with store.connection() as conn:
        rows = conn.execute(
            """SELECT DISTINCT n.id,n.label,e.edge_type
               FROM edges e JOIN nodes n ON n.id=e.target_id
               WHERE n.node_type='Chemical' AND e.edge_type IN
               ('USES_METAL_SOURCE','USES_LINKER','USES_MODULATOR','USES_SOLVENT')
               ORDER BY n.label,e.edge_type"""
        ).fetchall()
        recipes = conn.execute(
            "SELECT properties_json FROM nodes WHERE node_type='SynthesisRecipe'"
        ).fetchall()
    definitions = []
    raw_fields = {"metal_sources": "metal_source", "linkers": "organic_linkers",
                  "modulators": "modulators", "solvents": "solvents"}
    for recipe in recipes:
        try:
            raw = json.loads(recipe["properties_json"]).get("raw_row") or {}
        except (TypeError, ValueError):
            continue
        definitions.append({role: raw.get(field) for role, field in raw_fields.items()})
    resolver = ChemicalResolver.from_records(definitions)
    return [dict(row) for row in rows], resolver


def enrich_store(
    store: KnowledgeStore, max_new: int = 12, client: PubChemResolver | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Resolve unique names, persist findings, and stop on network/server failure."""
    client = client or PubChemResolver()
    rows, resolver = _collect_chemicals(store)
    cached = cached_resolutions(store)
    queries: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        role = EDGE_ROLES[row["edge_type"]]
        # A Chemical node may have an abbreviation plus a descriptive name.
        for part in split_components(row["label"], role):
            query = _candidate_query(part, role, resolver)
            if query:
                queries.setdefault(query, []).append(row)
    result = {"candidates": len(queries), "cached": 0, "queried": 0,
              "resolved": 0, "ambiguous": 0, "not_found": 0, "unavailable": 0,
              "failed_queries": [], "stopped_early": False}
    for query in sorted(queries):
        if query in cached and not refresh:
            result["cached"] += 1
            continue
        if result["queried"] >= max_new:
            break
        outcome = client.resolve(query)
        result["queried"] += 1
        if outcome["status"] == "unavailable":
            result["unavailable"] += 1
            reason = str(outcome.get("reason") or "unknown error")
            result["failed_queries"].append({"query": query, "reason": reason})
            if reason.startswith(("URLError", "TimeoutError", "OSError",
                                  "HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504")):
                result["stopped_early"] = True
                break
            continue
        result[outcome["status"]] += 1
        cache_resolution(store, outcome)
        if outcome["status"] == "resolved":
            for row in queries[query]:
                role = EDGE_ROLES[row["edge_type"]]
                if len(split_components(row["label"], role)) != 1:
                    continue
                store.upsert_node(
                    "Chemical", row["label"], row["label"],
                    {"pubchem": {"cid": outcome["cid"], "inchikey": outcome["inchikey"],
                                 "title": outcome["title"], "molecular_formula": outcome["molecular_formula"],
                                 "lookup_query": query}},
                )
    return result
