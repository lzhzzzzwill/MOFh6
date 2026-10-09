"""Conservative, context-aware chemical names for MOF case comparison.

These keys group related synthesis components; they are not claims of molecular
identity. Raw reagent names remain in the knowledge graph and source tables.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any, Iterable


# Common solvent names are a seed, not the complete matching strategy.
KNOWN_NAMES = {
    "dmf": "dimethylformamide", "n,n-dimethylformamide": "dimethylformamide",
    "dimethyl formamide": "dimethylformamide", "dma": "dimethylacetamide",
    "dmac": "dimethylacetamide", "n,n-dimethylacetamide": "dimethylacetamide",
    "dmso": "dimethyl sulfoxide", "dimethyl sulphoxide": "dimethyl sulfoxide",
    "meoh": "methanol", "ch3oh": "methanol", "etoh": "ethanol",
    "c2h5oh": "ethanol", "ch3ch2oh": "ethanol", "mecn": "acetonitrile",
    "acn": "acetonitrile", "ch3cn": "acetonitrile", "thf": "tetrahydrofuran",
    "h2o": "water", "distilled h2o": "water", "distilled water": "water",
    "deionized water": "water", "ch3cooh": "acetic acid",
}
POSITIONAL_LINKERS = {
    "1,2": "phthalate family", "1,3": "isophthalate family",
    "1,4": "terephthalate family",
}
POSITIONAL_NAMES = {
    "phthalic acid": "phthalate family",
    "isophthalic acid": "isophthalate family",
    "terephthalic acid": "terephthalate family",
}
DEFINITION = re.compile(r"^(.{8,100}?)\s*\(([A-Za-z][A-Za-z0-9'_-]{1,14})\)$")


def _spelling(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("−", "-").replace("–", "-").replace("·", ".")
    text = text.replace("’", "'").replace("‘", "'")
    text = re.sub(r"\s+", " ", text).strip().lower()
    text = re.sub(r"\s*,\s*", ",", text)
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s*\.\s*", ".", text)
    return text.strip(" ;,")


def split_components(value: Any, role: str) -> list[str]:
    text = str(value or "")
    if role == "solvents":
        parts = re.split(r"\s*(?:[;/+]|,\s+)\s*", text)
    else:
        parts = re.split(r"\s*;\s*", text)
    return [part.strip() for part in parts if part.strip()]


class ChemicalResolver:
    """Resolve explicit acronyms and positional linkers without guessing synonyms."""

    def __init__(self, definitions: dict[str, dict[str, str]] | None = None):
        self.definitions = definitions or {}

    @classmethod
    def from_records(cls, records: Iterable[dict[str, Any]]) -> "ChemicalResolver":
        """Learn only unambiguous `full name (ABBR)` definitions in this corpus."""
        possibilities: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for record in records:
            for role, raw in record.items():
                if role not in {"metal_sources", "linkers", "modulators", "solvents"}:
                    continue
                for part in split_components(raw, role):
                    match = DEFINITION.fullmatch(part.strip())
                    if match and not re.search(r"\b(?:mg|mmol|ml|mol|g)\b", match.group(2), re.I):
                        full, acronym = _spelling(match.group(1)), _spelling(match.group(2))
                        if full != acronym:
                            possibilities[role][acronym].add(full)
        definitions = {
            role: {acronym: next(iter(names)) for acronym, names in names_by_role.items()
                   if len(names) == 1}
            for role, names_by_role in possibilities.items()
        }
        return cls(definitions)

    def normalize(self, value: Any, role: str = "", mof_metadata: dict[str, Any] | None = None) -> str:
        text = _spelling(value)
        text = re.sub(r"\s*\([^)]*(?:mmol|mg|ml|g)\b[^)]*\)", "", text, flags=re.I).strip()
        if role == "solvents":
            text = re.sub(r"\b(?:mixture|mixed solvent|solution)\b", "", text).strip()
        definition = DEFINITION.fullmatch(text)
        if definition:
            text = definition.group(1)
        text = self.definitions.get(role, {}).get(text, text)
        if role == "linkers":
            resolved = self._positional_linker(text, mof_metadata or {})
            if resolved:
                return resolved
        return KNOWN_NAMES.get(text, text)

    @staticmethod
    def _positional_linker(text: str, metadata: dict[str, Any]) -> str | None:
        if text in POSITIONAL_NAMES:
            return POSITIONAL_NAMES[text]
        for position, name in POSITIONAL_LINKERS.items():
            if text in {f"{position}-h2bdc", f"benzene-{position}-dicarboxylic acid",
                        f"benzene-{position}-dicarboxylate"}:
                return name
        if text not in {"bdc", "h2bdc", "benzenedicarboxylate", "benzenedicarboxylic acid"}:
            return None
        ccdc_name = _spelling(metadata.get("Chemical_Name"))
        indicators = {
            "isophthalate family": ("isophthalato", "benzene-1,3-dicarboxylato"),
            "terephthalate family": ("terephthalato", "benzene-1,4-dicarboxylato"),
        }
        matches = [name for name, words in indicators.items() if any(word in ccdc_name for word in words)]
        if not matches and (
            "benzene-1,2-dicarboxylato" in ccdc_name
            or re.search(r"(?<!iso)(?<!tere)phthalato", ccdc_name)
        ):
            matches = ["phthalate family"]
        return matches[0] if len(matches) == 1 else "benzene-dicarboxylate (position unspecified)"


DEFAULT_RESOLVER = ChemicalResolver()
