import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Optional[Dict[str, Any]]) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


class KnowledgeStore:
    """SQLite-backed document, graph, provenance, and interaction store."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        # Output folders may be recreated between CLI runs; ensure the parent
        # still exists every time a new connection is opened.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def connection(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            source_path TEXT NOT NULL UNIQUE,
            title TEXT,
            doi TEXT,
            content_hash TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_documents_doi ON documents(doi);

        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            page INTEGER,
            section TEXT,
            text TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            embedding_json TEXT,
            embedding_model TEXT,
            UNIQUE(document_id, content_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY,
            node_type TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            label TEXT NOT NULL,
            properties_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(node_type, canonical_key)
        );
        CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);

        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY,
            source_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            target_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            edge_type TEXT NOT NULL,
            edge_key TEXT NOT NULL,
            properties_json TEXT NOT NULL DEFAULT '{}',
            evidence_chunk_id INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(source_id, target_id, edge_type, edge_key)
        );
        CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);

        CREATE TABLE IF NOT EXISTS chemical_resolutions (
            query TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            cid INTEGER,
            inchikey TEXT,
            title TEXT,
            molecular_formula TEXT,
            candidates_json TEXT NOT NULL DEFAULT '[]',
            checked_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chemical_resolutions_inchikey
            ON chemical_resolutions(inchikey);

        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY,
            raw_question TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            intent TEXT,
            entity_key TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_questions_canonical ON questions(canonical_key);

        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY,
            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            answer_text TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS retrievals (
            answer_id INTEGER NOT NULL REFERENCES answers(id) ON DELETE CASCADE,
            chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            score REAL NOT NULL,
            rank INTEGER NOT NULL,
            PRIMARY KEY(answer_id, chunk_id)
        );

        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY,
            context_key TEXT NOT NULL,
            question TEXT NOT NULL,
            score REAL NOT NULL,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(context_key, question)
        );
        """
        with self.connection() as conn:
            conn.executescript(schema)

    @staticmethod
    def canonicalize(value: str) -> str:
        value = (value or "").strip().lower()
        value = re.sub(r"\s+", " ", value)
        return value

    @staticmethod
    def stable_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()

    def upsert_document(
        self,
        source_path: str,
        text: str,
        title: Optional[str] = None,
        doi: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        source = str(Path(source_path).resolve())
        digest = self.stable_hash(text)
        now = _now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO documents(source_path,title,doi,content_hash,metadata_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(source_path) DO UPDATE SET
                    title=excluded.title, doi=COALESCE(excluded.doi, documents.doi),
                    content_hash=excluded.content_hash, metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (source, title, doi, digest, _json(metadata), now, now),
            )
            return int(conn.execute("SELECT id FROM documents WHERE source_path=?", (source,)).fetchone()[0])

    def replace_chunks(self, document_id: int, chunks: Iterable[Dict[str, Any]]) -> List[int]:
        ids: List[int] = []
        with self.connection() as conn:
            existing = {
                row["content_hash"]: int(row["id"])
                for row in conn.execute(
                    "SELECT id,content_hash FROM chunks WHERE document_id=?", (document_id,)
                ).fetchall()
            }
            retained: List[int] = []
            for index, chunk in enumerate(chunks):
                text = str(chunk.get("text", "")).strip()
                if not text:
                    continue
                digest = self.stable_hash(text)
                values = (
                    index,
                    chunk.get("page"),
                    chunk.get("section"),
                    text,
                    json.dumps(chunk.get("embedding")) if chunk.get("embedding") is not None else None,
                    chunk.get("embedding_model"),
                )
                if digest in existing:
                    chunk_id = existing[digest]
                    conn.execute(
                        """
                        UPDATE chunks SET chunk_index=?,page=?,section=?,text=?,
                            embedding_json=COALESCE(?, embedding_json),
                            embedding_model=COALESCE(?, embedding_model)
                        WHERE id=?
                        """,
                        values + (chunk_id,),
                    )
                else:
                    cur = conn.execute(
                        """
                        INSERT INTO chunks(document_id,chunk_index,page,section,text,content_hash,embedding_json,embedding_model)
                        VALUES(?,?,?,?,?,?,?,?)
                        """,
                        (
                            document_id,
                            index,
                            chunk.get("page"),
                            chunk.get("section"),
                            text,
                            digest,
                            values[4],
                            values[5],
                        ),
                    )
                    chunk_id = int(cur.lastrowid)
                    existing[digest] = chunk_id
                ids.append(chunk_id)
                retained.append(chunk_id)
            if retained:
                marks = ",".join("?" for _ in retained)
                conn.execute(
                    f"DELETE FROM chunks WHERE document_id=? AND id NOT IN ({marks})",
                    [document_id] + retained,
                )
            else:
                conn.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
        return ids

    def update_chunk_embeddings(
        self,
        embeddings: Dict[int, List[float]],
        model: str,
    ) -> None:
        """Persist embeddings without rewriting chunk text or provenance."""
        if not embeddings:
            return
        with self.connection() as conn:
            conn.executemany(
                "UPDATE chunks SET embedding_json=?, embedding_model=? WHERE id=?",
                [
                    (json.dumps(vector, separators=(",", ":")), model, chunk_id)
                    for chunk_id, vector in embeddings.items()
                ],
            )

    def list_chunks(self, document_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        sql = """
        SELECT c.*, d.source_path, d.title, d.doi
        FROM chunks c JOIN documents d ON d.id=c.document_id
        """
        params: List[Any] = []
        if document_ids:
            sql += " WHERE c.document_id IN (%s)" % ",".join("?" for _ in document_ids)
            params.extend(document_ids)
        sql += " ORDER BY c.document_id, c.chunk_index"
        with self.connection() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def upsert_node(
        self, node_type: str, canonical_key: str, label: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> int:
        key = self.canonicalize(canonical_key)
        now = _now()
        with self.connection() as conn:
            existing = conn.execute(
                "SELECT id, properties_json FROM nodes WHERE node_type=? AND canonical_key=?",
                (node_type, key),
            ).fetchone()
            merged = dict(properties or {})
            if existing:
                old = json.loads(existing["properties_json"] or "{}")
                old.update({k: v for k, v in merged.items() if v not in (None, "", "N/A", "NA")})
                conn.execute(
                    "UPDATE nodes SET label=?, properties_json=?, updated_at=? WHERE id=?",
                    (label or key, _json(old), now, existing["id"]),
                )
                return int(existing["id"])
            cur = conn.execute(
                "INSERT INTO nodes(node_type,canonical_key,label,properties_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (node_type, key, label or key, _json(merged), now, now),
            )
            return int(cur.lastrowid)

    def upsert_edge(
        self, source_id: int, target_id: int, edge_type: str,
        properties: Optional[Dict[str, Any]] = None,
        evidence_chunk_id: Optional[int] = None,
        edge_key: str = "default",
    ) -> int:
        now = _now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO edges(source_id,target_id,edge_type,edge_key,properties_json,evidence_chunk_id,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(source_id,target_id,edge_type,edge_key) DO UPDATE SET
                    properties_json=excluded.properties_json,
                    evidence_chunk_id=COALESCE(excluded.evidence_chunk_id, edges.evidence_chunk_id),
                    updated_at=excluded.updated_at
                """,
                (source_id, target_id, edge_type, edge_key, _json(properties), evidence_chunk_id, now, now),
            )
            row = conn.execute(
                "SELECT id FROM edges WHERE source_id=? AND target_id=? AND edge_type=? AND edge_key=?",
                (source_id, target_id, edge_type, edge_key),
            ).fetchone()
            return int(row[0])

    def delete_outgoing_edges(self, source_id: int, edge_types: List[str]) -> int:
        """Delete selected outgoing relationships while preserving their nodes."""
        if not edge_types:
            return 0
        marks = ",".join("?" for _ in edge_types)
        with self.connection() as conn:
            cursor = conn.execute(
                f"DELETE FROM edges WHERE source_id=? AND edge_type IN ({marks})",
                [source_id] + edge_types,
            )
            return int(cursor.rowcount)

    def replace_crystal_links(self, mof_id: int, keep_observation_ids: List[int]) -> int:
        """Remove stale crystal observations previously attached to one MOF."""
        keep = {int(value) for value in keep_observation_ids}
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT target_id FROM edges WHERE source_id=? AND edge_type='HAS_CRYSTAL_DATA'",
                (mof_id,),
            ).fetchall()
            stale = [int(row["target_id"]) for row in rows if int(row["target_id"]) not in keep]
            if not stale:
                return 0
            marks = ",".join("?" for _ in stale)
            conn.execute(
                f"DELETE FROM edges WHERE source_id=? AND edge_type='HAS_CRYSTAL_DATA' "
                f"AND target_id IN ({marks})",
                [mof_id] + stale,
            )
            # Crystal observations are content-addressed. If no MOF points to a stale
            # observation anymore, remove it and let foreign-key cascades clear its
            # artifact/evidence edges as well.
            for node_id in stale:
                still_linked = conn.execute(
                    "SELECT 1 FROM edges WHERE target_id=? AND edge_type='HAS_CRYSTAL_DATA' LIMIT 1",
                    (node_id,),
                ).fetchone()
                if not still_linked:
                    conn.execute(
                        "DELETE FROM nodes WHERE id=? AND node_type='CrystalObservation'",
                        (node_id,),
                    )
            return len(stale)

    def replace_synthesis_links(self, mof_id: int, keep_recipe_ids: List[int]) -> int:
        """Remove synthesis recipes that no longer match a MOF's target identity."""
        keep = {int(value) for value in keep_recipe_ids}
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT target_id FROM edges WHERE source_id=? AND edge_type='HAS_SYNTHESIS'",
                (mof_id,),
            ).fetchall()
            stale = [int(row["target_id"]) for row in rows if int(row["target_id"]) not in keep]
            if not stale:
                return 0
            marks = ",".join("?" for _ in stale)
            conn.execute(
                f"DELETE FROM edges WHERE source_id=? AND edge_type='HAS_SYNTHESIS' "
                f"AND target_id IN ({marks})",
                [mof_id] + stale,
            )
            for node_id in stale:
                still_linked = conn.execute(
                    "SELECT 1 FROM edges WHERE target_id=? AND edge_type='HAS_SYNTHESIS' LIMIT 1",
                    (node_id,),
                ).fetchone()
                if not still_linked:
                    conn.execute(
                        "DELETE FROM nodes WHERE id=? AND node_type='SynthesisRecipe'", (node_id,)
                    )
            return len(stale)

    def resolve_exact_entity(self, value: str) -> Optional[str]:
        """Resolve an explicitly mentioned graph entity without fuzzy substring matches."""
        key = self.canonicalize(value)
        if not key:
            return None
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT label FROM nodes
                WHERE node_type='MOF' AND (canonical_key=? OR lower(label)=?)
                ORDER BY CASE WHEN canonical_key=? THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (key, key, key),
            ).fetchone()
            return str(row["label"]) if row else None

    def graph_context(self, canonical_key: str, limit: int = 80) -> Dict[str, Any]:
        key = self.canonicalize(canonical_key)
        with self.connection() as conn:
            roots = conn.execute(
                "SELECT * FROM nodes WHERE canonical_key=? OR lower(label)=? LIMIT 10", (key, key)
            ).fetchall()
            if not roots:
                roots = conn.execute(
                    "SELECT * FROM nodes WHERE canonical_key LIKE ? OR lower(label) LIKE ? LIMIT 10",
                    (f"%{key}%", f"%{key}%"),
                ).fetchall()
            node_ids = [int(row["id"]) for row in roots]
            edges: List[Dict[str, Any]] = []
            if node_ids:
                marks = ",".join("?" for _ in node_ids)
                first_query = f"""
                    SELECT e.edge_type,e.properties_json,
                           e.source_id,e.target_id,
                           s.node_type source_type,s.label source_label,
                           t.node_type target_type,t.label target_label
                    FROM edges e
                    JOIN nodes s ON s.id=e.source_id JOIN nodes t ON t.id=e.target_id
                    WHERE e.source_id IN ({marks}) OR e.target_id IN ({marks})
                    LIMIT ?
                """
                first_rows = conn.execute(first_query, node_ids + node_ids + [limit]).fetchall()
                related_ids = set(node_ids)
                for row in first_rows:
                    related_ids.update((int(row["source_id"]), int(row["target_id"])))
                related_list = sorted(related_ids)
                related_marks = ",".join("?" for _ in related_list)
                second_query = f"""
                    SELECT e.edge_type,e.properties_json,
                           e.source_id,e.target_id,
                           s.node_type source_type,s.label source_label,
                           t.node_type target_type,t.label target_label
                    FROM edges e
                    JOIN nodes s ON s.id=e.source_id JOIN nodes t ON t.id=e.target_id
                    WHERE e.source_id IN ({related_marks}) OR e.target_id IN ({related_marks})
                    LIMIT ?
                """
                rows = conn.execute(second_query, related_list + related_list + [limit]).fetchall()
                edges = [dict(row) for row in rows]
                for edge in edges:
                    edge["properties"] = json.loads(edge.pop("properties_json") or "{}")
                all_ids = sorted(
                    {int(edge["source_id"]) for edge in edges}
                    | {int(edge["target_id"]) for edge in edges}
                )
                if all_ids:
                    all_marks = ",".join("?" for _ in all_ids)
                    node_rows = conn.execute(
                        f"SELECT * FROM nodes WHERE id IN ({all_marks})", all_ids
                    ).fetchall()
                else:
                    node_rows = roots
            else:
                node_rows = roots
            nodes = [dict(row) for row in node_rows]
            for node in nodes:
                node["properties"] = json.loads(node.pop("properties_json") or "{}")
            return {"nodes": nodes, "edges": edges}

    def record_interaction(
        self,
        question: str,
        answer: str,
        model: str,
        retrieved: List[Dict[str, Any]],
        intent: str = "rag_question",
        entity_key: Optional[str] = None,
    ) -> int:
        canonical = self.canonicalize(question).rstrip("?.!？。！")
        now = _now()
        with self.connection() as conn:
            qcur = conn.execute(
                "INSERT INTO questions(raw_question,canonical_key,intent,entity_key,created_at) VALUES(?,?,?,?,?)",
                (question, canonical, intent, entity_key, now),
            )
            question_id = int(qcur.lastrowid)
            acur = conn.execute(
                "INSERT INTO answers(question_id,answer_text,model,created_at) VALUES(?,?,?,?)",
                (question_id, answer, model, now),
            )
            answer_id = int(acur.lastrowid)
            for rank, item in enumerate(retrieved, start=1):
                conn.execute(
                    "INSERT OR REPLACE INTO retrievals(answer_id,chunk_id,score,rank) VALUES(?,?,?,?)",
                    (answer_id, int(item["id"]), float(item.get("score", 0)), rank),
                )

        qnode = self.upsert_node("CanonicalQuestion", canonical, question, {"intent": intent})
        event = self.upsert_node("QueryEvent", f"question:{question_id}", question, {"created_at": now})
        anode = self.upsert_node("Answer", f"answer:{answer_id}", f"Answer {answer_id}", {"model": model})
        self.upsert_edge(event, qnode, "INSTANCE_OF")
        self.upsert_edge(anode, event, "ANSWERS")
        for item in retrieved:
            chunk_id = int(item["id"])
            chunk_node = self.upsert_node(
                "TextChunk", f"chunk:{chunk_id}", f"Evidence chunk {chunk_id}",
                {"chunk_id": chunk_id, "page": item.get("page"), "source_path": item.get("source_path")},
            )
            self.upsert_edge(anode, chunk_node, "SUPPORTED_BY", {"score": item.get("score")}, edge_key=str(chunk_id))
        if entity_key:
            ctx = self.graph_context(entity_key, limit=1)
            if ctx["nodes"]:
                self.upsert_edge(qnode, int(ctx["nodes"][0]["id"]), "ABOUT")
        return answer_id

    def save_suggestions(self, context_key: str, suggestions: List[Dict[str, Any]]) -> None:
        now = _now()
        with self.connection() as conn:
            for item in suggestions:
                conn.execute(
                    """
                    INSERT INTO suggestions(context_key,question,score,evidence_count,created_at)
                    VALUES(?,?,?,?,?)
                    ON CONFLICT(context_key,question) DO UPDATE SET
                        score=excluded.score,evidence_count=excluded.evidence_count,created_at=excluded.created_at
                    """,
                    (
                        self.canonicalize(context_key),
                        item["question"],
                        float(item.get("score", 0)),
                        int(item.get("evidence_count", 0)),
                        now,
                    ),
                )

    def list_suggestions(self, context_key: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Return previously displayed questions so later stages can avoid repetition."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT question,score,evidence_count,created_at
                FROM suggestions
                WHERE context_key=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (self.canonicalize(context_key), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> Dict[str, int]:
        tables = ["documents", "chunks", "nodes", "edges", "questions", "answers", "suggestions"]
        with self.connection() as conn:
            result = {
                table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }
            result["embedded_chunks"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM chunks WHERE embedding_json IS NOT NULL"
                ).fetchone()[0]
            )
            return result
