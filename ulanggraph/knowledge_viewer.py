#!/usr/bin/env python3
"""CLI for inspecting the MOFh6 index and refreshing derived similarity edges."""

import argparse
import html
import json
import math
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from knowledge import KnowledgeStore, refresh_similarity_edges, similar_cases, recommend_cases  # noqa: E402
from rag import MOFRAGService  # noqa: E402
from knowledge.pubchem_resolver import enrich_store  # noqa: E402


DEFAULT_DB = PROJECT_ROOT / "ulanggraph" / "output" / "knowledge" / "mofh6.db"
DEFAULT_CONFIG = PROJECT_ROOT / "extrfinetune" / "config.json"


def _properties(value: str) -> Dict[str, Any]:
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _clean_properties(properties: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(properties)
    cleaned.pop("raw_row", None)
    cleaned.pop("source_path", None)
    return cleaned


def show_stats(store: KnowledgeStore) -> None:
    stats = store.stats()
    chunks = stats.get("chunks", 0)
    embedded = stats.get("embedded_chunks", 0)
    coverage = embedded / chunks * 100 if chunks else 0.0
    print("Knowledge-base statistics")
    print("=" * 72)
    for key in (
        "documents", "chunks", "embedded_chunks", "nodes", "edges",
        "questions", "answers", "suggestions",
    ):
        print(f"{key:20s} {stats.get(key, 0)}")
    print(f"{'embedding_coverage':20s} {coverage:.1f}%")
    print(f"{'database':20s} {store.db_path.resolve()}")


def show_documents(store: KnowledgeStore, limit: int) -> None:
    with store.connection() as conn:
        rows = conn.execute(
            """
            SELECT d.id,d.title,d.doi,d.source_path,d.updated_at,
                   COUNT(c.id) AS chunks,
                   SUM(CASE WHEN c.embedding_json IS NOT NULL THEN 1 ELSE 0 END) AS embedded
            FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
            GROUP BY d.id
            ORDER BY d.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    if not rows:
        print("No indexed documents.")
        return
    for row in rows:
        title = row["title"] or Path(row["source_path"]).name
        print(f"[{row['id']}] {title}")
        print(
            f"    chunks: {row['chunks']} | embedded: {row['embedded'] or 0} "
            f"| DOI: {row['doi'] or '-'}"
        )
        print(f"    source: {row['source_path']}")


def show_entities(store: KnowledgeStore, node_type: str, limit: int) -> None:
    sql = "SELECT node_type,label,canonical_key,properties_json FROM nodes"
    params: list[Any] = []
    if node_type:
        sql += " WHERE lower(node_type)=lower(?)"
        params.append(node_type)
    sql += " ORDER BY node_type,label LIMIT ?"
    params.append(limit)
    with store.connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("No matching graph entities.")
        return
    for row in rows:
        props = _clean_properties(_properties(row["properties_json"]))
        suffix = f" | {json.dumps(props, ensure_ascii=False)}" if props else ""
        print(f"[{row['node_type']}] {row['label']} ({row['canonical_key']}){suffix}")


def show_similar(store: KnowledgeStore, entity: str, limit: int, chemical: bool) -> None:
    kind = "CHEMICALLY_SIMILAR_TO" if chemical else "SYNTHESIS_SIMILAR_TO"
    cases = similar_cases(store, entity, kind=kind, limit=limit)
    if not cases:
        if store.resolve_exact_entity(entity) is None:
            print(f"MOF not found in this database: {entity}. Run 'entities --type MOF' "
                  "to see imported CCDC codes.")
        else:
            print(f"No sufficiently similar cases found for {entity}.")
        return
    title = "Chemical" if chemical else "Synthesis"
    print(f"{title} similarity for {entity.upper()} (reported cases):")
    for index, case in enumerate(cases, 1):
        shared = case.get("shared") or {}
        reasons = [
            f"{field.replace('_', ' ')}: {', '.join(values)}"
            for field, values in shared.items() if values
        ]
        print(f"{index}. {case['mof']} | similarity {case['score']:.2f}")
        if reasons:
            print(f"   Shared: {'; '.join(reasons)}")
        conditions = []
        if case.get("temperature_c") is not None:
            conditions.append(f"{case['temperature_c']:g} °C")
        if case.get("time_hours") is not None:
            conditions.append(f"{case['time_hours']:g} h")
        if case.get("solvents"):
            conditions.append("solvents: " + "/".join(case["solvents"]))
        if case.get("modulators"):
            conditions.append("modulators: " + "; ".join(case["modulators"]))
        if conditions:
            print(f"   Reported synthesis: {'; '.join(conditions)}")
        if case.get("paper"):
            print(f"   Source: {case['paper']}")


def show_recommendation(store: KnowledgeStore, entity: str, limit: int) -> None:
    result = recommend_cases(store, entity, limit)
    if result["status"] == "unknown_mof":
        print(f"MOF not found in this database: {entity}. Run 'entities --type MOF' "
              "to see imported CCDC codes.")
        return
    print(f"Synthesis case references for {result['target']}:")
    for index, case in enumerate(result["cases"], 1):
        print(f"{index}. {case['mof']} | chemical similarity {case['score']:.2f}")
        print(f"   Shared: {json.dumps(case.get('shared') or {}, ensure_ascii=False)}")
        conditions = []
        if case["temperature_c"] is not None:
            conditions.append(f"{case['temperature_c']:g} °C")
        if case["time_hours"] is not None:
            conditions.append(f"{case['time_hours']:g} h")
        if case["solvents"]:
            conditions.append("/".join(case["solvents"]))
        print(f"   Reported: {'; '.join(conditions)} | {case['paper']}")
    if result["status"] == "limited_cases":
        print("Fewer than 3 independent, usable cases: no numeric range recommended.")
        return
    for key, name, unit in (
        ("temperature_range_c", "Reference temperature", "°C"),
        ("time_range_hours", "Reference time", "h"),
    ):
        values = result.get(key) or []
        if len(values) == 2 and all(value is not None for value in values):
            print(f"{name}: {values[0]:g}–{values[1]:g} {unit}")
    if result.get("solvent_systems"):
        print("Reported solvent systems: " + "; ".join(result["solvent_systems"]))
    print("Ranges summarize comparable published cases; they do not predict synthesis success.")


def show_graph(store: KnowledgeStore, entity: str, raw_json: bool) -> None:
    graph = store.graph_context(entity, limit=200)
    if raw_json:
        print(json.dumps(graph, ensure_ascii=False, indent=2, default=str))
        return
    if not graph.get("nodes"):
        print(f"No graph record found for {entity}.")
        return
    print(f"Knowledge graph: {entity}")
    print("=" * 72)
    print("Nodes")
    for node in graph["nodes"]:
        props = _clean_properties(node.get("properties") or {})
        suffix = f": {json.dumps(props, ensure_ascii=False, default=str)}" if props else ""
        print(f"- [{node['node_type']}] {node['label']}{suffix}")
    print("Relationships")
    for edge in graph["edges"]:
        props = edge.get("properties") or {}
        suffix = f" {json.dumps(props, ensure_ascii=False, default=str)}" if props else ""
        print(f"- {edge['source_label']} --{edge['edge_type']}--> {edge['target_label']}{suffix}")


def _search_client(config_path: Path):
    try:
        from openai import OpenAI

        config = json.loads(config_path.read_text(encoding="utf-8"))
        return OpenAI(api_key=config["openaiapikey"])
    except Exception as exc:
        print(
            f"Warning: semantic query embedding is unavailable ({exc}); using lexical retrieval.",
            file=sys.stderr,
        )
        return None


def search(store: KnowledgeStore, query: str, top_k: int, config_path: Path) -> None:
    rag = MOFRAGService(store, _search_client(config_path))
    # Read-only inspection: create a query embedding, but never backfill or alter stored chunks.
    hits = rag.retrieve(query, top_k=top_k, ensure_embeddings=False)
    if not hits:
        print("No matching literature chunks.")
        return
    for rank, item in enumerate(hits, start=1):
        source = item.get("doi") or item.get("title") or Path(item["source_path"]).name
        location = []
        if item.get("page"):
            location.append(f"page {item['page']}")
        if item.get("section"):
            location.append(str(item["section"]))
        where = f" ({', '.join(location)})" if location else ""
        preview = " ".join(item["text"].split())[:700]
        print(f"[{rank}] score={item.get('score', 0):.4f} | {source}{where}")
        print(f"    {preview}")


def _overview_graph(store: KnowledgeStore, limit: int) -> Dict[str, Any]:
    """Load a bounded, recent graph slice suitable for interactive rendering."""
    with store.connection() as conn:
        edge_rows = conn.execute(
            """
            SELECT e.source_id,e.target_id,e.edge_type,e.properties_json,
                   s.node_type AS source_type,s.label AS source_label,
                   t.node_type AS target_type,t.label AS target_label
            FROM edges e
            JOIN nodes s ON s.id=e.source_id
            JOIN nodes t ON t.id=e.target_id
            ORDER BY e.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        node_ids = sorted(
            {int(row["source_id"]) for row in edge_rows}
            | {int(row["target_id"]) for row in edge_rows}
        )
        if not node_ids:
            return {"nodes": [], "edges": []}
        marks = ",".join("?" for _ in node_ids)
        node_rows = conn.execute(
            f"SELECT id,node_type,label,properties_json FROM nodes WHERE id IN ({marks})",
            node_ids,
        ).fetchall()
    nodes = [
        {
            "id": int(row["id"]),
            "node_type": row["node_type"],
            "label": row["label"],
            "properties": _properties(row["properties_json"]),
        }
        for row in node_rows
    ]
    edges = [
        {
            "source_id": int(row["source_id"]),
            "target_id": int(row["target_id"]),
            "edge_type": row["edge_type"],
            "properties": _properties(row["properties_json"]),
            "source_type": row["source_type"],
            "source_label": row["source_label"],
            "target_type": row["target_type"],
            "target_label": row["target_label"],
        }
        for row in edge_rows
    ]
    return {"nodes": nodes, "edges": edges}


def _research_graph(store: KnowledgeStore, entity: str, limit: int) -> Dict[str, Any]:
    """Project the storage graph into a MOF-centred researcher-facing view."""
    with store.connection() as conn:
        if entity:
            mof_rows = conn.execute(
                """
                SELECT id,node_type,label,properties_json FROM nodes
                WHERE node_type='MOF' AND (canonical_key=? OR lower(label)=lower(?))
                ORDER BY label LIMIT 1
                """,
                (store.canonicalize(entity), entity),
            ).fetchall()
            if mof_rows:
                nearby = conn.execute(
                    """SELECT DISTINCT n.id,n.node_type,n.label,n.properties_json
                       FROM edges e JOIN nodes n ON n.id=CASE
                           WHEN e.source_id=? THEN e.target_id ELSE e.source_id END
                       WHERE e.edge_type IN ('CHEMICALLY_SIMILAR_TO','SYNTHESIS_SIMILAR_TO')
                         AND (e.source_id=? OR e.target_id=?)
                       ORDER BY n.label LIMIT 8""",
                    (int(mof_rows[0]["id"]), int(mof_rows[0]["id"]), int(mof_rows[0]["id"])),
                ).fetchall()
                mof_rows = list(mof_rows) + list(nearby)
        else:
            mof_rows = conn.execute(
                """
                SELECT id,node_type,label,properties_json FROM nodes
                WHERE node_type='MOF' ORDER BY label LIMIT ?
                """,
                (limit,),
            ).fetchall()
        if not mof_rows:
            return {"nodes": [], "edges": [], "root_ids": []}

        root_ids = [int(row["id"]) for row in mof_rows]
        marks = ",".join("?" for _ in root_ids)
        edge_rows = conn.execute(
            f"""
            SELECT e.source_id,e.target_id,e.edge_type,e.properties_json,
                   s.node_type AS source_type,s.label AS source_label,
                   t.node_type AS target_type,t.label AS target_label
            FROM edges e
            JOIN nodes s ON s.id=e.source_id
            JOIN nodes t ON t.id=e.target_id
            WHERE (
                e.source_id IN ({marks})
                AND e.edge_type IN ('HAS_SYNTHESIS','HAS_LITERATURE_SUMMARY')
            ) OR (
                e.target_id IN ({marks}) AND e.edge_type='REPORTS'
            ) OR (
                e.source_id IN ({marks}) AND e.target_id IN ({marks})
                AND e.edge_type IN ('CHEMICALLY_SIMILAR_TO','SYNTHESIS_SIMILAR_TO')
            )
            ORDER BY e.edge_type,s.label,t.label
            """,
            root_ids * 4,
        ).fetchall()
        node_ids = sorted(
            set(root_ids)
            | {int(row["source_id"]) for row in edge_rows}
            | {int(row["target_id"]) for row in edge_rows}
        )
        node_marks = ",".join("?" for _ in node_ids)
        node_rows = conn.execute(
            f"SELECT id,node_type,label,properties_json FROM nodes WHERE id IN ({node_marks})",
            node_ids,
        ).fetchall()

        nodes = []
        for row in node_rows:
            properties = _properties(row["properties_json"])
            if row["node_type"] == "SynthesisRecipe":
                reagent_rows = conn.execute(
                    """
                    SELECT e.edge_type,e.properties_json,n.label
                    FROM edges e JOIN nodes n ON n.id=e.target_id
                    WHERE e.source_id=? AND e.edge_type IN (
                        'USES_METAL_SOURCE','USES_LINKER','USES_MODULATOR',
                        'USES_SOLVENT','USES_EQUIPMENT'
                    ) ORDER BY e.edge_type,e.edge_key
                    """,
                    (int(row["id"]),),
                ).fetchall()
                grouped: Dict[str, List[str]] = {}
                names = {
                    "USES_METAL_SOURCE": "Metal source",
                    "USES_LINKER": "Organic linker",
                    "USES_MODULATOR": "Modulator",
                    "USES_SOLVENT": "Solvent",
                    "USES_EQUIPMENT": "Equipment",
                }
                for reagent in reagent_rows:
                    edge_properties = _properties(reagent["properties_json"])
                    quantity = edge_properties.get("quantity_raw")
                    value = reagent["label"] + (f" ({quantity})" if quantity else "")
                    grouped.setdefault(names[reagent["edge_type"]], []).append(value)
                properties["synthesis_components"] = grouped
            nodes.append({
                "id": int(row["id"]),
                "node_type": row["node_type"],
                "label": row["label"],
                "properties": properties,
            })

    edges = [
        {
            "source_id": int(row["source_id"]),
            "target_id": int(row["target_id"]),
            "edge_type": row["edge_type"],
            "properties": _properties(row["properties_json"]),
            "source_type": row["source_type"],
            "source_label": row["source_label"],
            "target_type": row["target_type"],
            "target_label": row["target_label"],
        }
        for row in edge_rows
    ]
    return {"nodes": nodes, "edges": edges, "root_ids": root_ids}


def _hover_text(node: Dict[str, Any]) -> str:
    properties = _clean_properties(node.get("properties") or {})
    details = []
    for key, value in list(properties.items())[:10]:
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, default=str)
        details.append(f"{key}: {value}")
    lines = [f"<b>{node['label']}</b>", f"Type: {node['node_type']}"] + details
    return "<br>".join(lines)


def _wrapped(value: Any, width: int = 72) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    clean = re.sub(r"\s+", " ", str(value)).strip()
    return "<br>".join(html.escape(line) for line in textwrap.wrap(clean, width=width))


def _research_hover_text(node: Dict[str, Any]) -> str:
    """Build compact scientific cards instead of exposing storage-level JSON."""
    node_type = node["node_type"]
    properties = node.get("properties") or {}
    lines = [f"<b>{html.escape(node['label'])}</b>"]
    if node_type == "MOF":
        lines.append("<b>CCDC material</b>")
        preferred = (
            "Molecule_Identifier", "CCDC_code", "Number", "Chemical_Name", "Synonyms",
            "Formula", "Crystal_System", "Spacegroup_Symbol", "a", "b", "c",
            "alpha(α)", "beta(β)", "gamma(γ)", "Molecular_Weight", "Color",
            "Melting_Point", "R_Factor", "Solvent_Names", "Publication_Details",
        )
        used = set()
        for key in preferred:
            value = properties.get(key)
            if value not in (None, "", [], {}, "N/A", "NA"):
                lines.append(f"<b>{html.escape(key)}:</b> {_wrapped(value)}")
                used.add(key)
        for key, value in properties.items():
            if key in used or key == "Chemical_Name_HTML" or value in (None, "", [], {}, "N/A", "NA"):
                continue
            lines.append(f"<b>{html.escape(str(key))}:</b> {_wrapped(value)}")
    elif node_type == "SynthesisRecipe":
        lines.append("<b>Synthesis parameters</b>")
        for key, value in (properties.get("synthesis_components") or {}).items():
            lines.append(f"<b>{html.escape(key)}:</b> {_wrapped('; '.join(value))}")
        for key, label in (
            ("temperature", "Temperature"), ("time", "Time"), ("yield", "Yield"),
            ("ph", "pH"), ("morphology", "Morphology"), ("compound", "Product"),
        ):
            value = properties.get(key)
            if isinstance(value, dict):
                value = value.get("raw")
            if value not in (None, "", "N/A", "NA"):
                lines.append(f"<b>{label}:</b> {_wrapped(value)}")
    elif node_type == "CrystalObservation":
        lines.append("<b>Matched crystallography</b>")
        for key, value in properties.items():
            if key in {"raw_row", "source_path"} or value in (None, "", "N/A", "NA"):
                continue
            lines.append(f"<b>{html.escape(str(key))}:</b> {_wrapped(value)}")
    elif node_type == "LiteratureSummary":
        lines.append("<b>Literature findings &amp; applications</b>")
        if properties.get("summary"):
            lines.append(_wrapped(properties["summary"]))
        for item in properties.get("findings") or []:
            lines.append(
                f"<b>{html.escape(str(item.get('category', 'finding')).title())}:</b> "
                f"{_wrapped(item.get('statement', ''))}"
            )
        applications = properties.get("applications") or []
        if not applications:
            lines.append("<b>Applications:</b> none explicitly supported by the extracted evidence")
        for item in applications:
            status = html.escape(str(item.get("status") or "reported"))
            lines.append(
                f"<b>Application · {html.escape(str(item.get('application') or ''))} "
                f"({status}):</b> {_wrapped(item.get('statement', ''))}"
            )
    elif node_type == "Paper":
        lines.append("<b>Source paper</b>")
        if properties.get("doi"):
            lines.append(f"<b>DOI:</b> {_wrapped(properties['doi'])}")
        if properties.get("title"):
            lines.append(f"<b>Title:</b> {_wrapped(properties['title'])}")
    return "<br>".join(lines)


def _research_positions(graph_data: Dict[str, Any]) -> Dict[int, tuple[float, float]]:
    """Place each MOF and its four information cards in a stable local cluster."""
    nodes = {int(node["id"]): node for node in graph_data["nodes"]}
    roots = [int(value) for value in graph_data.get("root_ids") or []]
    columns = max(1, math.ceil(math.sqrt(len(roots))))
    positions: Dict[int, tuple[float, float]] = {}
    neighbors: Dict[int, List[int]] = {root: [] for root in roots}
    for edge in graph_data.get("edges", []):
        source, target = int(edge["source_id"]), int(edge["target_id"])
        if source in neighbors:
            neighbors[source].append(target)
        if target in neighbors:
            neighbors[target].append(source)

    base_offsets = {
        "Paper": (-1.45, 0.9),
        "SynthesisRecipe": (1.45, 0.9),
        "LiteratureSummary": (1.45, -0.95),
    }
    for index, root in enumerate(roots):
        row, column = divmod(index, columns)
        centre = (column * 4.5, -row * 3.7)
        positions[root] = centre
        by_type: Dict[str, List[int]] = {}
        for neighbor in dict.fromkeys(neighbors[root]):
            if neighbor in nodes:
                by_type.setdefault(nodes[neighbor]["node_type"], []).append(neighbor)
        for node_type, ids in by_type.items():
            base_x, base_y = base_offsets.get(node_type, (0.0, -1.6))
            for offset, node_id in enumerate(ids):
                if node_id not in positions:
                    spread = (offset - (len(ids) - 1) / 2) * 0.42
                    positions[node_id] = (centre[0] + base_x + spread, centre[1] + base_y)
    for index, node_id in enumerate(nodes):
        positions.setdefault(node_id, (index % columns * 4.5, -math.ceil(len(roots) / columns) * 3.7 - 1))
    return positions


def visualize_graph(
    store: KnowledgeStore,
    entity: str,
    limit: int,
    output: Path | None,
    raw: bool = False,
) -> None:
    try:
        import networkx as nx
        import plotly.graph_objects as go
    except ImportError as exc:
        raise RuntimeError("Visualization requires networkx and plotly") from exc

    if raw:
        graph_data = (
            store.graph_context(entity, limit=limit)
            if entity
            else _overview_graph(store, limit=limit)
        )
    else:
        graph_data = _research_graph(store, entity, limit)
    if not graph_data.get("nodes"):
        print(f"No graph data found for {entity or 'the database overview'}.")
        return

    network = nx.Graph()
    node_by_id = {int(node["id"]): node for node in graph_data["nodes"]}
    for node_id, node in node_by_id.items():
        network.add_node(node_id, **node)
    for edge in graph_data.get("edges", []):
        source = int(edge["source_id"])
        target = int(edge["target_id"])
        if source in node_by_id and target in node_by_id:
            network.add_edge(source, target, relation=edge["edge_type"])

    positions = (
        nx.spring_layout(network, seed=42, k=max(0.35, 2.2 / max(1, len(network) ** 0.5)))
        if raw else _research_positions(graph_data)
    )
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    similarity_types = {"CHEMICALLY_SIMILAR_TO", "SYNTHESIS_SIMILAR_TO"}
    for source, target in network.edges():
        if not raw and network[source][target].get("relation") in similarity_types:
            continue
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        edge_x.extend((float(x0), float(x1), None))
        edge_y.extend((float(y0), float(y1), None))

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            line={"width": 0.7, "color": "rgba(125,125,125,0.35)"},
            hoverinfo="skip",
            name="Relationships",
            showlegend=False,
        )
    )

    if not raw:
        similarity_styles = {
            "CHEMICALLY_SIMILAR_TO": ("#3276b1", "Chemical similarity"),
            "SYNTHESIS_SIMILAR_TO": ("#d95f02", "Synthesis similarity"),
        }
        for kind, (color, label) in similarity_styles.items():
            line_x: list[float | None] = []
            line_y: list[float | None] = []
            hover_x: list[float] = []
            hover_y: list[float] = []
            hover_text: list[str] = []
            for edge in graph_data.get("edges", []):
                if edge["edge_type"] != kind:
                    continue
                source, target = int(edge["source_id"]), int(edge["target_id"])
                if source not in positions or target not in positions:
                    continue
                x0, y0 = positions[source]
                x1, y1 = positions[target]
                line_x.extend((float(x0), float(x1), None))
                line_y.extend((float(y0), float(y1), None))
                props = edge.get("properties") or {}
                shared = props.get("shared") or {}
                reasons = [
                    f"{key.replace('_', ' ').title()}: {', '.join(values)}"
                    for key, values in shared.items() if values
                ]
                for key, name, unit in (
                    ("temperature_difference_c", "Temperature difference", "°C"),
                    ("time_difference_hours", "Time difference", "h"),
                ):
                    if props.get(key) is not None and kind == "SYNTHESIS_SIMILAR_TO":
                        reasons.append(f"{name}: {props[key]} {unit}")
                hover_x.append(float((x0 + x1) / 2))
                hover_y.append(float((y0 + y1) / 2))
                hover_text.append(
                    f"<b>{html.escape(edge['source_label'])} ↔ {html.escape(edge['target_label'])}</b>"
                    f"<br>{label}: {float(props.get('score', 0)):.2f}"
                    + "".join(f"<br>{html.escape(reason)}" for reason in reasons)
                )
            if line_x:
                figure.add_trace(go.Scatter(
                    x=line_x, y=line_y, mode="lines",
                    line={"width": 2, "color": color, "dash": "dot"},
                    hoverinfo="skip", name=label, legendgroup=kind,
                ))
                figure.add_trace(go.Scatter(
                    x=hover_x, y=hover_y, mode="markers", marker={"size": 8, "color": color},
                    hovertext=hover_text, hoverinfo="text", showlegend=False,
                    legendgroup=kind,
                    hoverlabel={"bgcolor": "white", "font": {"color": "#222", "size": 12}},
                ))

    palette = {
        "MOF": "#d95f02",
        "Paper": "#1b9e77",
        "SynthesisRecipe": "#7570b3",
        "CrystalObservation": "#e7298a",
        "LiteratureSummary": "#2b8cbe",
        "Chemical": "#66a61e",
        "Equipment": "#e6ab02",
        "TextChunk": "#a6761d",
        "SourceArtifact": "#666666",
    }
    node_types = sorted({node["node_type"] for node in node_by_id.values()})
    for node_type in node_types:
        ids = [node_id for node_id, node in node_by_id.items() if node["node_type"] == node_type]
        labels = [node_by_id[node_id]["label"] for node_id in ids]
        card_labels = {
            "Paper": "Paper / DOI",
            "SynthesisRecipe": "Synthesis",
            "LiteratureSummary": "Literature & applications",
        }
        if raw:
            visible_labels = labels if len(node_by_id) <= 60 or node_type == "MOF" else [""] * len(ids)
        elif entity:
            visible_labels = [card_labels.get(node_type, label) for label in labels]
        else:
            visible_labels = labels if node_type == "MOF" else [""] * len(ids)
        figure.add_trace(
            go.Scatter(
                x=[float(positions[node_id][0]) for node_id in ids],
                y=[float(positions[node_id][1]) for node_id in ids],
                mode="markers+text",
                text=visible_labels,
                textposition="top center",
                textfont={"size": 10},
                hovertext=[
                    _hover_text(node_by_id[node_id]) if raw
                    else _research_hover_text(node_by_id[node_id])
                    for node_id in ids
                ],
                hoverinfo="text",
                marker={
                    "size": [22 if node_type == "MOF" else 14 for _ in ids],
                    "color": palette.get(node_type, "#1f78b4"),
                    "line": {"width": 0.5, "color": "rgba(255,255,255,0.7)"},
                },
                hoverlabel={"bgcolor": "white", "font": {"color": "#222", "size": 12}, "align": "left"},
                name=node_type,
            )
        )

    if raw:
        title = f"MOFh6 raw knowledge graph: {entity}" if entity else "MOFh6 raw knowledge graph overview"
    else:
        title = f"MOFh6 research profile: {entity}" if entity else "MOFh6 CCDC-centred research graph"
    figure.update_layout(
        title={"text": title, "x": 0.02},
        template="plotly_white",
        hovermode="closest",
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "x": 0},
        xaxis={"visible": False},
        yaxis={"visible": False},
        height=900,
        annotations=[
            {
                "text": (
                    f"{len(node_by_id)} visible nodes · {network.number_of_edges()} relationships"
                    + (" · raw storage view" if raw else " · hover a node for details")
                ),
                "showarrow": False,
                "xref": "paper",
                "yref": "paper",
                "x": 1,
                "y": 1.04,
                "xanchor": "right",
                "font": {"size": 12, "color": "#666"},
            }
        ],
    )

    if output is None:
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", entity or "overview").strip("-").lower()
        output = (
            PROJECT_ROOT / "ulanggraph" / "output" / "knowledge" / "visualizations"
            / f"{safe_name or 'overview'}.html"
        )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(str(output), include_plotlyjs=True, full_html=True, auto_open=False)
    print(f"Interactive graph written to: {output}")
    print(f"Open it in a browser: open '{output}'")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect the persistent MOFh6 literature index and knowledge graph without starting QA."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to mofh6.db")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("stats", help="Show database and embedding statistics")

    documents = subparsers.add_parser("documents", help="List indexed source documents")
    documents.add_argument("--limit", type=int, default=20)

    entities = subparsers.add_parser("entities", help="List graph nodes")
    entities.add_argument("--type", default="MOF", help="Node type; use an empty string for all types")
    entities.add_argument("--limit", type=int, default=50)

    graph = subparsers.add_parser("graph", help="Show nodes and relationships for one entity")
    graph.add_argument("entity")
    graph.add_argument("--json", action="store_true", help="Print raw graph context as JSON")

    similar = subparsers.add_parser("similar", help="Show related MOFs and reported synthesis cases")
    similar.add_argument("entity", help="CCDC refcode")
    similar.add_argument("--limit", type=int, default=4)
    similar.add_argument("--chemical", action="store_true", help="Rank by material chemistry for case transfer")
    recommend = subparsers.add_parser("recommend", help="Summarize independent synthesis cases")
    recommend.add_argument("entity", help="CCDC refcode")
    recommend.add_argument("--limit", type=int, default=4)
    subparsers.add_parser("refresh-similarity", help="Rebuild derived MOF similarity edges")
    pubchem = subparsers.add_parser("pubchem-enrich", help="Resolve uncached synthesis chemicals with PubChem")
    pubchem.add_argument("--limit", type=int, default=100, help="Maximum new name queries")
    pubchem.add_argument("--refresh", action="store_true", help="Requery cached names")

    search_parser = subparsers.add_parser("search", help="Preview hybrid literature retrieval")
    search_parser.add_argument("query")
    search_parser.add_argument("--top-k", type=int, default=5)
    search_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)

    visualize = subparsers.add_parser("visualize", help="Generate an interactive HTML knowledge graph")
    visualize.add_argument("entity", nargs="?", default="", help="Optional MOF identifier")
    visualize.add_argument(
        "--limit", type=int, default=30,
        help="Maximum MOFs in the research overview (or relationships with --raw)",
    )
    visualize.add_argument("--output", type=Path, help="Destination HTML path")
    visualize.add_argument(
        "--raw", action="store_true",
        help="Show the storage/provenance graph including chemicals, chunks, and artifacts",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error(
            f"knowledge database does not exist: {args.db}. "
            "Run ulanggraph/main.py first or pass --db with the correct path."
        )
    store = KnowledgeStore(str(args.db))
    if args.command in (None, "stats"):
        show_stats(store)
    elif args.command == "documents":
        show_documents(store, max(1, args.limit))
    elif args.command == "entities":
        show_entities(store, args.type, max(1, args.limit))
    elif args.command == "graph":
        show_graph(store, args.entity, args.json)
    elif args.command == "similar":
        show_similar(store, args.entity, max(1, args.limit), args.chemical)
    elif args.command == "recommend":
        show_recommendation(store, args.entity, max(1, args.limit))
    elif args.command == "refresh-similarity":
        print(json.dumps(refresh_similarity_edges(store), ensure_ascii=False))
    elif args.command == "pubchem-enrich":
        result = enrich_store(store, max_new=max(1, args.limit), refresh=args.refresh)
        result["similarity"] = refresh_similarity_edges(store)
        print(json.dumps(result, ensure_ascii=False))
    elif args.command == "search":
        search(store, args.query, max(1, args.top_k), args.config)
    elif args.command == "visualize":
        visualize_graph(store, args.entity.strip(), max(1, args.limit), args.output, args.raw)


if __name__ == "__main__":
    main()
