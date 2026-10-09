import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .store import KnowledgeStore


NULL_VALUES = {"", "n/a", "na", "none", "null", "not reported"}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _present(value: Any) -> bool:
    return _clean(value).lower() not in NULL_VALUES


def _split_cell(value: Any) -> List[str]:
    return [part.strip() for part in re.split(r"\s*;\s*", _clean(value)) if _present(part)]


def _parse_number_unit(value: Any) -> Dict[str, Any]:
    raw = _clean(value)
    result: Dict[str, Any] = {"raw": raw}
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*(°C|K|days?|hours?|hrs?|h|min(?:utes?)?|%|mL|ml|cm3)?", raw, re.I)
    if match:
        result["value"] = float(match.group(1))
        if match.group(2):
            result["unit"] = match.group(2)
    return result


class StructuredKnowledgeIngestor:
    """Incrementally converts MOFh6 structured artifacts into graph nodes and edges."""

    COLUMN_ALIASES = {
        "metal source": "metal_source",
        "organic linkers source": "organic_linkers",
        "modulator source": "modulators",
        "solvent source": "solvents",
        "quantity of metal": "metal_quantity",
        "quantity of organic linkers": "linker_quantity",
        "quantity of modulator": "modulator_quantity",
        "quantity of solvent": "solvent_quantity",
        "ph": "ph",
        "synthesis temperature": "temperature",
        "synthesis time": "time",
        "crystal morphology": "morphology",
        "yield": "yield",
        "equipment": "equipment",
    }

    def __init__(self, store: KnowledgeStore, pubchem_enabled: bool = False):
        self.store = store
        self.pubchem_enabled = pubchem_enabled
        self._ccdc_cache_path: Optional[str] = None
        self._ccdc_cache: Dict[str, Dict[str, Any]] = {}

    def _load_ccdc_records(self, json_path: str) -> Dict[str, Dict[str, Any]]:
        resolved = str(Path(json_path).resolve())
        if self._ccdc_cache_path == resolved:
            return self._ccdc_cache
        payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
        entries = payload if isinstance(payload, list) else [payload]
        records: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for identifier, properties in entry.items():
                if isinstance(properties, dict):
                    records[_clean(identifier).upper()] = properties
        self._ccdc_cache_path = resolved
        self._ccdc_cache = records
        return records

    def ingest_ccdc_metadata(
        self,
        json_path: str,
        identifiers: Iterable[str],
    ) -> Dict[str, int]:
        """Enrich central MOF nodes with authoritative CCDC metadata."""
        wanted = {_clean(value).upper() for value in identifiers if _present(value)}
        if not wanted:
            return {"records": 0, "requested": 0, "missing": 0}
        entries = self._load_ccdc_records(json_path)
        found = set()
        records = 0
        for key in wanted:
            properties = entries.get(key)
            if not properties:
                continue
            enriched = {"CCDC_code": key, **properties}
            self.store.upsert_node("MOF", key, key, enriched)
            found.add(key)
            records += 1
        if found:
            from .similarity import refresh_similarity_edges
            refresh_similarity_edges(self.store)
        return {
            "records": records,
            "requested": len(wanted),
            "missing": len(wanted - found),
        }

    @staticmethod
    def _crystal_reference(item: Dict[str, Any]) -> str:
        for key in ("Complex", "Complexes", "Compound", "compound", "complex"):
            if _present(item.get(key)):
                return _clean(item[key])
        return ""

    @staticmethod
    def _normalized_reference(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())

    @classmethod
    def _select_crystal_rows(
        cls,
        items: List[Dict[str, Any]],
        references: List[str],
    ) -> List[Dict[str, Any]]:
        """Match the comparator-selected compound to its row in a multi-compound table."""
        targets = {cls._normalized_reference(value) for value in references if _present(value)}
        exact = [
            item for item in items
            if cls._normalized_reference(cls._crystal_reference(item)) in targets
        ]
        if exact:
            return exact

        # Fall back to a unique terminal number, e.g. target "1" vs "M=Co (1)".
        target_numbers = {
            match.group(1).lower()
            for value in references
            for match in [re.search(r"(?:^|\()\s*(\d+[a-z]?)\s*\)?$", _clean(value), re.I)]
            if match
        }
        numbered = []
        for item in items:
            match = re.search(
                r"(?:^|\()\s*(\d+[a-z]?)\s*\)?$",
                cls._crystal_reference(item),
                re.I,
            )
            if match and match.group(1).lower() in target_numbers:
                numbered.append(item)
        return numbered if len(numbered) == 1 else []

    @classmethod
    def _selection_map(cls, selection_path: Optional[str]) -> Dict[str, List[str]]:
        if not selection_path or not Path(selection_path).exists():
            return {}
        payload = json.loads(Path(selection_path).read_text(encoding="utf-8"))
        result: Dict[str, List[str]] = {}

        def collect(value: Any, output: List[str]) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key.lower() in {"compound", "compounds", "complex", "complexes"} and _present(child):
                        output.append(_clean(child))
                    else:
                        collect(child, output)
            elif isinstance(value, list):
                for child in value:
                    collect(child, output)

        for identifier, value in payload.items():
            references: List[str] = []
            collect(value, references)
            if references:
                result[_clean(identifier).upper()] = references
        return result

    @staticmethod
    def _normalize_crystal_symmetry(item: Dict[str, Any]) -> Dict[str, Any]:
        """Apply only angle constraints that are fixed by the reported crystal system.

        PDF-to-text conversion often drops empty cells from crystallographic tables.
        Without this guard, a monoclinic beta value from the next compound can shift
        left into a tetragonal row. These assignments are symmetry identities, not
        inferred experimental measurements.
        """
        normalized = dict(item)
        system = _clean(item.get("Crystal system")).lower()
        fixed_angles: Dict[str, str] = {}
        if system in {"cubic", "tetragonal", "orthorhombic"}:
            fixed_angles = {"alpha (°)": "90", "beta (°)": "90", "gamma (°)": "90"}
        elif system == "monoclinic":
            fixed_angles = {"alpha (°)": "90", "gamma (°)": "90"}
        elif system == "hexagonal":
            fixed_angles = {"alpha (°)": "90", "beta (°)": "90", "gamma (°)": "120"}
        corrections = []
        for key, expected in fixed_angles.items():
            current = _clean(normalized.get(key))
            if current.lower() not in NULL_VALUES and current != expected:
                corrections.append(f"{key}: {current} -> {expected} ({system} symmetry)")
            normalized[key] = expected
        if corrections:
            normalized["validation_notes"] = corrections
        return normalized

    @staticmethod
    def _formula_elements(value: Any) -> set[str]:
        return {
            match.group(1)
            for match in re.finditer(r"([A-Z][a-z]?)\s*\d*(?:\.\d+)?", _clean(value))
        }

    @staticmethod
    def _numeric(value: Any) -> Optional[float]:
        match = re.search(r"-?\d+(?:\.\d+)?", _clean(value))
        return float(match.group(0)) if match else None

    @classmethod
    def _match_ccdc_crystal_row(
        cls,
        items: List[Dict[str, Any]],
        ccdc: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Select one table row only when it agrees with authoritative CCDC data."""
        if not items or not ccdc:
            return []
        ccdc_elements = cls._formula_elements(ccdc.get("Formula"))
        ccdc_system = _clean(ccdc.get("Crystal_System")).lower()
        ccdc_space = re.sub(r"[^a-z0-9]+", "", _clean(ccdc.get("Spacegroup_Symbol")).lower())
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for item in items:
            score = 0.0
            row_elements = cls._formula_elements(
                item.get("Empirical formula") or item.get("Formula")
            )
            if ccdc_elements and row_elements:
                if ccdc_elements == row_elements:
                    score += 4.0
                elif len(ccdc_elements & row_elements) / len(ccdc_elements | row_elements) >= 0.8:
                    score += 2.0
            if ccdc_system and _clean(item.get("Crystal system")).lower() == ccdc_system:
                score += 2.0
            row_space = re.sub(
                r"[^a-z0-9]+", "", _clean(item.get("Space group")).lower().split("(no.")[0]
            )
            if ccdc_space and row_space and row_space == ccdc_space:
                score += 2.0
            for ccdc_key, row_key in (("a", "a (Å)"), ("b", "b (Å)"), ("c", "c (Å)")):
                expected = cls._numeric(ccdc.get(ccdc_key))
                observed = cls._numeric(item.get(row_key))
                if expected and observed and abs(expected - observed) / expected <= 0.02:
                    score += 1.5
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        if not scored or scored[0][0] < 5.0:
            return []
        if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.75:
            return []
        return [scored[0][1]]

    @staticmethod
    def _table_row(lines: List[str]) -> Optional[Tuple[List[str], List[str]]]:
        for index, line in enumerate(lines):
            if not line.lstrip().startswith("|") or index + 2 >= len(lines):
                continue
            separator = lines[index + 1]
            if not re.match(r"^\s*\|?[\s:|-]+\|?\s*$", separator):
                continue
            header = [cell.strip() for cell in line.strip().strip("|").split("|")]
            values = [cell.strip() for cell in lines[index + 2].strip().strip("|").split("|")]
            if len(header) == len(values):
                return header, values
        return None

    @staticmethod
    def _compound_label(value: str) -> str:
        match = re.search(r"\(((?:\d+[a-z]?|[ivx]+[a-z]?))\)\s*$", _clean(value), re.I)
        return match.group(1).lower() if match else ""

    def parse_synthesis_markdown(
        self,
        markdown_path: str,
        compound_labels: Optional[Dict[str, List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        text = Path(markdown_path).read_text(encoding="utf-8")
        blocks = re.split(r"(?=^# Identifier:\s*)", text, flags=re.M)
        records: List[Dict[str, Any]] = []
        for block in blocks:
            id_match = re.search(r"^# Identifier:\s*(.+)$", block, re.M)
            if not id_match:
                continue
            identifier = _clean(id_match.group(1)).upper()
            lines = [line.rstrip() for line in block.splitlines()]
            metadata: Dict[str, str] = {}
            for key in ("Chemical_Name", "Number", "Synonyms"):
                match = re.search(rf"^{re.escape(key)}:\s*(.*)$", block, re.M)
                metadata[key] = _clean(match.group(1)) if match else "N/A"
            candidates: List[Dict[str, Any]] = []
            for index, line in enumerate(lines):
                if not line.lstrip().startswith("|") or index + 2 >= len(lines):
                    continue
                separator = lines[index + 1]
                if not re.match(r"^\s*\|?[\s:|-]+\|?\s*$", separator):
                    continue
                header = [cell.strip() for cell in line.strip().strip("|").split("|")]
                values = [cell.strip() for cell in lines[index + 2].strip().strip("|").split("|")]
                if len(header) != len(values):
                    continue
                compound = ""
                for previous in reversed(lines[:index]):
                    candidate = _clean(previous.replace("**", ""))
                    if not candidate or candidate.startswith("#") or candidate.startswith("|"):
                        continue
                    if re.match(r"^(Chemical_Name|Number|Synonyms):", candidate):
                        continue
                    compound = candidate
                    break
                row = {
                    self.COLUMN_ALIASES.get(_clean(key).lower(), _clean(key)): _clean(value)
                    for key, value in zip(header, values)
                }
                candidates.append({"compound": compound, "row": row})

            if not candidates:
                continue
            requested = {
                self._normalized_reference(value)
                for value in (compound_labels or {}).get(identifier, [])
                if _present(value)
            }
            selected = None
            if requested:
                for item in candidates:
                    normalized_compound = self._normalized_reference(item["compound"])
                    normalized_label = self._normalized_reference(
                        self._compound_label(item["compound"])
                    )
                    if any(
                        value == normalized_label
                        or (len(value) > 2 and value in normalized_compound)
                        for value in requested
                    ):
                        selected = item
                        break
            if selected is None and len(candidates) == 1:
                # A single extracted route is safe to attach to this identifier even
                # when the upstream Markdown contains an unresolved name placeholder.
                selected = candidates[0]
            elif selected is None and not requested:
                # Without a target label, choosing the first compound in a paper is unsafe.
                selected = None
            if not selected:
                continue
            if not selected["compound"] or "{" in selected["compound"]:
                labels = (compound_labels or {}).get(identifier, [])
                selected = dict(selected)
                selected["compound"] = (
                    f"{identifier} (compound {labels[0]})" if labels else identifier
                )
            records.append({
                "identifier": identifier,
                "compound": selected["compound"],
                "metadata": metadata,
                "row": selected["row"],
            })
        return records

    @staticmethod
    def _quantities(value: Any) -> List[str]:
        return _split_cell(value)

    def ingest_synthesis_markdown(
        self,
        markdown_path: str,
        compound_labels: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        records = self.parse_synthesis_markdown(markdown_path, compound_labels=compound_labels)
        text = Path(markdown_path).read_text(encoding="utf-8")
        identifiers = {
            _clean(value).upper()
            for value in re.findall(r"^# Identifier:\s*(.+)$", text, flags=re.M)
        }
        companion_path = str(Path(markdown_path).with_suffix('.json'))
        Path(companion_path).write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        node_count = edge_count = 0
        artifact = self.store.upsert_node(
            "SourceArtifact", str(Path(markdown_path).resolve()), Path(markdown_path).name,
            {"path": str(Path(markdown_path).resolve()), "kind": "synthesis_markdown"},
        )
        kept_recipes: Dict[str, List[int]] = {identifier: [] for identifier in identifiers}
        for record in records:
            identifier = record["identifier"]
            row = record["row"]
            mof = self.store.upsert_node("MOF", identifier, identifier, record["metadata"])
            signature = json.dumps({"compound": record["compound"], "row": row}, ensure_ascii=False, sort_keys=True)
            recipe_key = f"{identifier}:{hashlib.sha256(signature.encode()).hexdigest()[:20]}"
            recipe_props = {
                "compound": record["compound"],
                "ph": row.get("ph"),
                "temperature": _parse_number_unit(row.get("temperature")),
                "time": _parse_number_unit(row.get("time")),
                "yield": _parse_number_unit(row.get("yield")),
                "morphology": row.get("morphology"),
                "raw_row": row,
            }
            recipe = self.store.upsert_node("SynthesisRecipe", recipe_key, f"Synthesis of {identifier}", recipe_props)
            kept_recipes.setdefault(identifier, []).append(recipe)
            self.store.upsert_edge(mof, recipe, "HAS_SYNTHESIS")
            self.store.upsert_edge(recipe, artifact, "DERIVED_FROM")
            node_count += 2
            edge_count += 2

            source_chunks = [
                chunk for chunk in self.store.list_chunks()
                if Path(chunk['source_path']).stem.upper() == identifier
            ]
            if source_chunks:
                terms = [
                    value.lower() for value in
                    _split_cell(row.get('metal_source')) + _split_cell(row.get('organic_linkers'))
                ]
                evidence = max(
                    source_chunks,
                    key=lambda chunk: sum(term in chunk['text'].lower() for term in terms)
                    + (2 if 'synth' in chunk['text'].lower() else 0),
                )
                chunk_node = self.store.upsert_node(
                    'TextChunk', f"chunk:{evidence['id']}", f"{identifier} evidence",
                    {'chunk_id': evidence['id'], 'page': evidence.get('page'), 'section': evidence.get('section')},
                )
                paper = self.store.upsert_node(
                    'Paper', evidence.get('doi') or evidence['source_path'],
                    evidence.get('title') or Path(evidence['source_path']).name,
                    {'source_path': evidence['source_path'], 'doi': evidence.get('doi')},
                )
                self.store.upsert_edge(
                    recipe, chunk_node, 'EVIDENCED_BY', evidence_chunk_id=evidence['id']
                )
                self.store.upsert_edge(paper, mof, 'REPORTS')
                edge_count += 2

            groups = [
                ("metal_source", "metal_quantity", "USES_METAL_SOURCE"),
                ("organic_linkers", "linker_quantity", "USES_LINKER"),
                ("modulators", "modulator_quantity", "USES_MODULATOR"),
                ("solvents", "solvent_quantity", "USES_SOLVENT"),
            ]
            for value_key, quantity_key, edge_type in groups:
                values = _split_cell(row.get(value_key))
                quantities = self._quantities(row.get(quantity_key))
                for index, value in enumerate(values):
                    chemical = self.store.upsert_node("Chemical", value, value)
                    props = {"quantity_raw": quantities[index] if index < len(quantities) else None}
                    self.store.upsert_edge(recipe, chemical, edge_type, props, edge_key=str(index))
                    node_count += 1
                    edge_count += 1
            for index, equipment_name in enumerate(_split_cell(row.get("equipment"))):
                equipment = self.store.upsert_node("Equipment", equipment_name, equipment_name)
                self.store.upsert_edge(recipe, equipment, "USES_EQUIPMENT", edge_key=str(index))
                node_count += 1
                edge_count += 1
        stale_removed = 0
        for identifier, recipe_ids in kept_recipes.items():
            mof = self.store.upsert_node("MOF", identifier, identifier)
            stale_removed += self.store.replace_synthesis_links(mof, recipe_ids)
        pubchem = None
        if self.pubchem_enabled:
            from .pubchem_resolver import PubChemResolver, enrich_store
            try:
                pubchem = enrich_store(self.store, max_new=8, client=PubChemResolver(timeout=3))
            except Exception as exc:
                pubchem = {"status": "unavailable", "reason": type(exc).__name__}
        from .similarity import refresh_similarity_edges
        similarity = refresh_similarity_edges(self.store)
        return {
            "records": len(records),
            "nodes_processed": node_count,
            "edges_processed": edge_count,
            "stale_removed": stale_removed,
            "similarity": similarity,
            "pubchem": pubchem,
            "json_output": companion_path,
        }

    def ingest_crystal_json(
        self,
        json_path: str,
        selection_path: Optional[str] = None,
        ccdc_path: Optional[str] = None,
    ) -> Dict[str, int]:
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        selections = self._selection_map(selection_path)
        ccdc_records = self._load_ccdc_records(ccdc_path) if ccdc_path else {}
        artifact = self.store.upsert_node(
            "SourceArtifact", str(Path(json_path).resolve()), Path(json_path).name,
            {"path": str(Path(json_path).resolve()), "kind": "crystal_json"},
        )
        records = filtered_out = unresolved = stale_removed = 0
        for identifier, items in data.items():
            mof_key = _clean(identifier).upper()
            mof = self.store.upsert_node("MOF", mof_key, mof_key)
            source_items = items if isinstance(items, list) else []
            has_authoritative_ccdc = mof_key in ccdc_records
            if has_authoritative_ccdc:
                matched_items = self._match_ccdc_crystal_row(
                    source_items, ccdc_records[mof_key]
                )
                if matched_items:
                    filtered_out += len(source_items) - len(matched_items)
                    source_items = matched_items
                else:
                    unresolved += 1
                    source_items = []
            elif mof_key in selections:
                matched_items = self._select_crystal_rows(source_items, selections[mof_key])
                if matched_items:
                    filtered_out += len(source_items) - len(matched_items)
                    source_items = matched_items
                else:
                    # A comparator decision exists but cannot be mapped safely; do not
                    # attach every compound in the paper to the target CCDC material.
                    unresolved += 1
                    source_items = []
            source_chunks = [
                chunk for chunk in self.store.list_chunks()
                if Path(chunk['source_path']).stem.upper() == mof_key
            ]
            evidence = max(
                source_chunks,
                key=lambda chunk: sum(
                    term in chunk['text'].lower()
                    for term in ('crystal data', 'space group', 'empirical formula', 'unit cell')
                ),
            ) if source_chunks else None
            if evidence:
                paper = self.store.upsert_node(
                    'Paper', evidence.get('doi') or evidence['source_path'],
                    evidence.get('title') or Path(evidence['source_path']).name,
                    {'source_path': evidence['source_path'], 'doi': evidence.get('doi')},
                )
                self.store.upsert_edge(paper, mof, 'REPORTS')
            observation_ids: List[int] = []
            for item in source_items:
                item = self._normalize_crystal_symmetry(item)
                signature = json.dumps(item, ensure_ascii=False, sort_keys=True)
                key = f"{mof_key}:{hashlib.sha256(signature.encode()).hexdigest()[:20]}"
                label = item.get("Complexes") or item.get("Complex") or item.get("Compound") or mof_key
                observation = self.store.upsert_node("CrystalObservation", key, f"{mof_key} crystal data {label}", item)
                observation_ids.append(observation)
                self.store.upsert_edge(mof, observation, "HAS_CRYSTAL_DATA")
                self.store.upsert_edge(observation, artifact, "DERIVED_FROM")
                if evidence:
                    chunk_node = self.store.upsert_node(
                        'TextChunk', f"chunk:{evidence['id']}", f"{mof_key} crystal evidence",
                        {'chunk_id': evidence['id'], 'page': evidence.get('page'), 'section': evidence.get('section')},
                    )
                    self.store.upsert_edge(
                        observation, chunk_node, 'EVIDENCED_BY', evidence_chunk_id=evidence['id']
                    )
                records += 1
            if has_authoritative_ccdc or mof_key in selections:
                stale_removed += self.store.replace_crystal_links(mof, observation_ids)
        return {
            "records": records,
            "filtered_out": filtered_out,
            "unresolved": unresolved,
            "stale_removed": stale_removed,
        }
