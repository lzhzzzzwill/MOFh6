import json
import math
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from rank_bm25 import BM25Okapi
except ImportError:  # Keep the knowledge base usable in minimal installations.
    class BM25Okapi:  # type: ignore
        def __init__(self, corpus: List[List[str]]):
            self.corpus = corpus
            self.document_count = max(1, len(corpus))
            self.document_frequency: Dict[str, int] = {}
            for document in corpus:
                for token in set(document):
                    self.document_frequency[token] = self.document_frequency.get(token, 0) + 1

        def get_scores(self, query: List[str]) -> List[float]:
            scores: List[float] = []
            for document in self.corpus:
                frequencies: Dict[str, int] = {}
                for token in document:
                    frequencies[token] = frequencies.get(token, 0) + 1
                score = 0.0
                for token in query:
                    if token not in frequencies:
                        continue
                    inverse_frequency = math.log(
                        1.0 + self.document_count / (1 + self.document_frequency.get(token, 0))
                    )
                    score += inverse_frequency * (1.0 + math.log(frequencies[token]))
                scores.append(score)
            return scores

from knowledge.store import KnowledgeStore


TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_+()./\-·]*|[\u4e00-\u9fff]+|\d+(?:\.\d+)?")
PAGE_PATTERN = re.compile(r"\[\[PAGE\s+(\d+)\]\]", re.I)
SECTION_PATTERN = re.compile(
    r"^(abstract|introduction|experimental|materials and methods|results(?: and discussion)?|conclusion|references)\b",
    re.I,
)


def _tokens(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text or "")]


def _minmax(values: List[float]) -> List[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if math.isclose(low, high):
        return [1.0 if value > 0 else 0.0 for value in values]
    return [(value - low) / (high - low) for value in values]


class MOFRAGService:
    """Persistent hybrid RAG with evidence-backed answers and question suggestions."""

    def __init__(
        self,
        store: KnowledgeStore,
        client: Any = None,
        chat_model: str = "gpt-6-luna",
        embedding_model: str = "text-embedding-3-small",
    ):
        self.store = store
        self.client = client
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self._query_embedding_cache: Dict[str, List[float]] = {}

    @staticmethod
    def language_for(text: str) -> str:
        """Use Chinese only when the user actually writes Chinese."""
        return "zh" if re.search(r"[\u4e00-\u9fff]", text or "") else "en"

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 220) -> List[Dict[str, Any]]:
        pages = PAGE_PATTERN.split(text or "")
        page_parts: List[tuple] = []
        if len(pages) > 1:
            leading = pages[0].strip()
            if leading:
                page_parts.append((None, leading))
            for index in range(1, len(pages), 2):
                page_no = int(pages[index])
                page_text = pages[index + 1] if index + 1 < len(pages) else ""
                page_parts.append((page_no, page_text))
        else:
            page_parts = [(None, text or "")]

        chunks: List[Dict[str, Any]] = []
        current_section: Optional[str] = None
        for page_no, page_text in page_parts:
            cleaned = re.sub(r"\s+", " ", page_text).strip()
            section_match = SECTION_PATTERN.search(cleaned[:120])
            if section_match:
                current_section = section_match.group(1).title()
            start = 0
            while start < len(cleaned):
                end = min(len(cleaned), start + chunk_size)
                if end < len(cleaned):
                    boundary = max(cleaned.rfind(". ", start + chunk_size // 2, end), cleaned.rfind("; ", start + chunk_size // 2, end))
                    if boundary > start:
                        end = boundary + 1
                piece = cleaned[start:end].strip()
                if piece:
                    chunks.append({"page": page_no, "section": current_section, "text": piece})
                if end >= len(cleaned):
                    break
                start = max(start + 1, end - overlap)
        return chunks

    def ingest_document(
        self,
        source_path: str,
        text: Optional[str] = None,
        title: Optional[str] = None,
        doi: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        path = Path(source_path)
        if text is None:
            text = path.read_text(encoding="utf-8", errors="ignore")
        if not doi:
            doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.I)
            doi = doi_match.group(0).rstrip(".,;)") if doi_match else None
        chunks = self.chunk_text(text)
        document_id = self.store.upsert_document(source_path, text, title, doi, metadata)
        chunk_ids = self.store.replace_chunks(document_id, chunks)
        embedding_status = self.ensure_embeddings(document_ids=[document_id])

        paper_key = doi or str(path.resolve())
        paper = self.store.upsert_node(
            "Paper", paper_key, title or path.name,
            {"doi": doi, "source_path": str(path.resolve()), **(metadata or {})},
        )
        for chunk_id, chunk in zip(chunk_ids, chunks):
            chunk_node = self.store.upsert_node(
                "TextChunk", f"chunk:{chunk_id}", f"{path.name} chunk {chunk_id}",
                {"chunk_id": chunk_id, "page": chunk.get("page"), "section": chunk.get("section")},
            )
            self.store.upsert_edge(paper, chunk_node, "CONTAINS", edge_key=str(chunk_id))
        return {
            "document_id": document_id,
            "chunks": len(chunk_ids),
            "embedded": embedding_status["embedded"],
            "embeddings_reused": embedding_status["reused"],
            "embedding_model": self.embedding_model,
            "source": str(path),
        }

    def ingest_path(self, path: str) -> Dict[str, Any]:
        target = Path(path)
        if target.is_file():
            return self.ingest_document(str(target))
        if not target.is_dir():
            raise FileNotFoundError(path)
        files = sorted(
            file for file in target.rglob("*.txt")
            if not file.name.startswith(".") and not any(part.startswith("._") for part in file.parts)
        )
        results = [self.ingest_document(str(file)) for file in files]
        return {
            "documents": len(results),
            "chunks": sum(item["chunks"] for item in results),
            "embedded": sum(item["embedded"] for item in results),
            "embeddings_reused": sum(item["embeddings_reused"] for item in results),
            "embedding_model": self.embedding_model,
            "path": str(target),
        }

    def _embed_texts(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        if self.client is None:
            raise RuntimeError("An OpenAI client is required to create embeddings")
        vectors: List[List[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=batch,
            )
            ordered = sorted(response.data, key=lambda item: getattr(item, "index", 0))
            vectors.extend([list(item.embedding) for item in ordered])
        return vectors

    def ensure_embeddings(
        self,
        document_ids: Optional[List[int]] = None,
    ) -> Dict[str, int]:
        """Embed only new chunks or chunks created with a different model."""
        chunks = self.store.list_chunks(document_ids)
        missing = [
            item for item in chunks
            if not item.get("embedding_json")
            or item.get("embedding_model") != self.embedding_model
        ]
        reused = len(chunks) - len(missing)
        if not missing:
            return {"embedded": 0, "reused": reused, "missing": 0}
        if self.client is None:
            return {"embedded": 0, "reused": reused, "missing": len(missing)}
        vectors = self._embed_texts([item["text"] for item in missing])
        self.store.update_chunk_embeddings(
            {int(item["id"]): vector for item, vector in zip(missing, vectors)},
            self.embedding_model,
        )
        return {"embedded": len(vectors), "reused": reused, "missing": 0}

    @staticmethod
    def _cosine(left: List[float], right: List[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return max(0.0, dot / (left_norm * right_norm))

    def _query_embedding(self, question: str) -> Optional[List[float]]:
        if self.client is None:
            return None
        cache_key = f"{self.embedding_model}:{question.strip()}"
        if cache_key not in self._query_embedding_cache:
            if len(self._query_embedding_cache) >= 256:
                self._query_embedding_cache.clear()
            self._query_embedding_cache[cache_key] = self._embed_texts([question])[0]
        return self._query_embedding_cache[cache_key]

    def _prime_query_embeddings(self, questions: List[str]) -> None:
        """Batch candidate-question embeddings to avoid one API call per suggestion."""
        if self.client is None:
            return
        missing = [
            question for question in questions
            if f"{self.embedding_model}:{question.strip()}" not in self._query_embedding_cache
        ]
        if not missing:
            return
        vectors = self._embed_texts(missing)
        for question, vector in zip(missing, vectors):
            self._query_embedding_cache[f"{self.embedding_model}:{question.strip()}"] = vector

    @staticmethod
    def _tfidf_scores(query: str, texts: List[str]) -> List[float]:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            matrix = TfidfVectorizer(tokenizer=_tokens, token_pattern=None, lowercase=False).fit_transform([query] + texts)
            return cosine_similarity(matrix[0:1], matrix[1:]).ravel().tolist()
        except Exception:
            query_tokens = set(_tokens(query))
            scores = []
            for text in texts:
                text_tokens = set(_tokens(text))
                union = query_tokens | text_tokens
                scores.append(len(query_tokens & text_tokens) / len(union) if union else 0.0)
            return scores

    def retrieve(
        self,
        question: str,
        top_k: int = 6,
        document_ids: Optional[List[int]] = None,
        ensure_embeddings: bool = True,
    ) -> List[Dict[str, Any]]:
        if self.client is not None and ensure_embeddings:
            try:
                self.ensure_embeddings(document_ids=document_ids)
            except Exception:
                # Stored lexical data remains queryable if embedding backfill is temporarily unavailable.
                pass
        chunks = self.store.list_chunks(document_ids)
        if not chunks:
            return []
        tokenized = [_tokens(item["text"]) for item in chunks]
        bm25 = BM25Okapi(tokenized)
        bm25_scores = _minmax([float(value) for value in bm25.get_scores(_tokens(question))])
        tfidf_scores = _minmax(self._tfidf_scores(question, [item["text"] for item in chunks]))

        semantic_scores: Optional[List[float]] = None
        try:
            query_embedding = self._query_embedding(question)
            if query_embedding is not None:
                semantic_scores = []
                for item in chunks:
                    raw = item.get("embedding_json")
                    vector = json.loads(raw) if raw and item.get("embedding_model") == self.embedding_model else []
                    semantic_scores.append(self._cosine(query_embedding, vector))
        except Exception:
            # Retrieval remains available during a transient embedding API failure.
            semantic_scores = None

        query_tokens = set(_tokens(question))
        for index, item in enumerate(chunks):
            title_tokens = set(_tokens((item.get("title") or "") + " " + Path(item["source_path"]).stem))
            entity_boost = 0.15 if query_tokens & title_tokens else 0.0
            if semantic_scores is not None:
                item["semantic_score"] = semantic_scores[index]
                item["bm25_score"] = bm25_scores[index]
                item["tfidf_score"] = tfidf_scores[index]
                item["score"] = (
                    0.65 * semantic_scores[index]
                    + 0.25 * bm25_scores[index]
                    + 0.10 * tfidf_scores[index]
                    + entity_boost
                )
            else:
                item["score"] = 0.55 * bm25_scores[index] + 0.45 * tfidf_scores[index] + entity_boost
        return sorted(chunks, key=lambda item: item["score"], reverse=True)[:top_k]

    def _expand_query(self, question: str) -> str:
        """Expand low-recall multilingual questions into literature search terms."""
        if self.client is None:
            return question
        response = self.client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Convert the user's MOF question into a compact bilingual literature search query. "
                        "Preserve all CCDC codes, chemical names, numbers, and requested properties. "
                        "Return search terms only."
                    ),
                },
                {"role": "user", "content": question},
            ],
        )
        expanded = response.choices[0].message.content.strip()
        return f"{question} {expanded}"

    @staticmethod
    def _domain_query_expansion(question: str) -> str:
        """Add property-specific evidence terms without changing the user's question."""
        lower = question.lower()
        expansions: List[str] = []
        if any(term in lower for term in (
            "gas storage", "gas adsorption", "gas uptake", "co2", "ch4", "h2 storage",
            "气体储存", "气体吸附", "储气", "二氧化碳吸附", "甲烷吸附", "氢气储存",
        )):
            expansions.append(
                "gas adsorption uptake isotherm BET surface area pore porosity "
                "void cavity accessible interpenetration"
            )
        return " ".join([question] + expansions)

    @staticmethod
    def _rescue_property_evidence(
        question: str,
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Keep one narrowly relevant passage when the LLM gate is over-conservative."""
        lower = question.lower()
        gas_question = any(term in lower for term in (
            "gas storage", "gas adsorption", "gas uptake", "co2", "ch4", "h2 storage",
            "气体储存", "气体吸附", "储气", "二氧化碳吸附", "甲烷吸附", "氢气储存",
        ))
        if not gas_question:
            return []
        direct_terms = (
            "gas adsorption", "gas uptake", "adsorption isotherm", "bet surface area",
            "co2 uptake", "ch4 uptake", "h2 uptake",
        )
        structural_terms = (
            "potential voids are filled", "void space is filled", "accessible pore",
            "5-fold interpenetrat", "five-fold interpenetrat",
        )
        direct = [item for item in candidates if any(term in item["text"].lower() for term in direct_terms)]
        if direct:
            return direct[:1]
        indirect = [item for item in candidates if any(term in item["text"].lower() for term in structural_terms)]
        if indirect:
            indirect[0]["evidence_mode"] = "indirect_gas_structure"
        return indirect[:1]

    def _indirect_gas_answer(
        self,
        entity_key: Optional[str],
        evidence: Dict[str, Any],
        language: str,
    ) -> str:
        """Render a guarded absence answer without letting structure become performance."""
        target = entity_key or ("该材料" if language == "zh" else "the target material")
        text = evidence.get("text", "").lower()
        fold = "5-fold " if "5-fold" in text else ""
        source = self._source_label(evidence, 1)
        if language == "zh":
            answer = (
                f"当前索引的 {target} 文献没有报道气体吸附或储存测量，因此无法从该文献判断其"
                "储气量、选择性或工作容量。文献报道了钻石型笼状结构中的大空腔，但这些潜在空隙被"
                f"框架相互穿插所填充，形成 {fold}互穿结构 [1]。这只是结构证据，不能证明存在可达孔隙或气体储存性能。"
            )
            return f"{answer}\n\n来源：\n{source}"
        answer = (
            f"The indexed literature for {target} does not report gas-adsorption or gas-storage "
            "measurements, so its uptake, selectivity, and working capacity cannot be assessed from "
            "this paper. The paper reports large cavities in its diamondoid cages, but states that "
            f"the potential voids are filled by mutual framework interpenetration, producing a {fold}"
            "interpenetrated structure [1]. This is structural evidence only; it does not establish "
            "accessible porosity or gas-storage performance."
        )
        return f"{answer}\n\nSources used:\n{source}"

    @staticmethod
    def _source_label(item: Dict[str, Any], number: int) -> str:
        label = item.get("doi") or item.get("title") or Path(item["source_path"]).name
        page = f", page {item['page']}" if item.get("page") else ""
        section = f", {item['section']}" if item.get("section") else ""
        return f"[{number}] {label}{page}{section}"

    def _rerank_evidence(
        self,
        question: str,
        evidence: List[Dict[str, Any]],
        limit: int,
        target_identity: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Use a strict relevance gate so broad paper context does not swamp the question."""
        if self.client is None or not evidence:
            return evidence[:limit]
        candidates = [
            {
                "index": index,
                "source": self._source_label(item, index),
                "text": item["text"][:900],
            }
            for index, item in enumerate(evidence, start=1)
        ]
        prompt = f"""
Question: {question}
Target identity: {json.dumps(target_identity or {}, ensure_ascii=False)}
Candidate evidence: {json.dumps(candidates, ensure_ascii=False)}

Score each candidate only for its usefulness in answering this exact question:
3 = directly reports the requested result or measurement;
2 = directly relevant structural/contextual evidence, but not the requested measurement;
1 = generic background, merely mentions the material, or concerns another property;
0 = unrelated.

Generic statements about MOFs are not evidence that this target material has gas-storage,
adsorption, catalytic, sensing, drug-delivery, or other application performance.
For a gas-storage or adsorption question, a passage that directly describes the target's
pores, cavities, void filling, accessible space, or interpenetration is relevance 2 even when
it contains no adsorption measurement. A source file named for the target identifies its paper.
When the target identity gives an article compound label, evidence only about other numbered
compounds is relevance 0. A comparison that mixes the target with other compounds is at most 1
unless it clearly separates and directly describes the target.
Score every candidate; do not omit low-scoring candidates from the returned array.
Return only a JSON array with objects {{"index": integer, "relevance": 0|1|2|3}}.
"""
        try:
            response = self.client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": "You are a strict scientific evidence reranker."},
                    {"role": "user", "content": prompt},
                ],
            )
            scores = self._extract_json_list(response.choices[0].message.content)
            # The reranker is instructed to score every candidate. An empty list
            # therefore means that the response could not be parsed, not that all
            # evidence was irrelevant; keep the lexical/vector result as a safe
            # fallback instead of silently discarding the whole answer context.
            if not scores:
                return evidence[:limit]
            by_index = {
                int(item.get("index")): int(item.get("relevance", 0))
                for item in scores
                if str(item.get("index", "")).isdigit()
            }
            selected = []
            for index, item in enumerate(evidence, start=1):
                relevance = by_index.get(index, 0)
                if relevance >= 2:
                    item["rerank_relevance"] = relevance
                    selected.append(item)
            selected.sort(
                key=lambda item: (item.get("rerank_relevance", 0), item.get("score", 0)),
                reverse=True,
            )
            return selected[:limit]
        except Exception:
            return evidence[:limit]

    @staticmethod
    def _question_uses_structured_graph(question: str) -> bool:
        lower = question.lower()
        terms = (
            "synthesis", "temperature", "yield", "solvent", "linker", "ligand",
            "metal source", "modulator", "equipment", "crystal data", "crystallograph",
            "crystal system", "space group",
            "unit cell", "empirical formula", "morphology", "chemical formula",
            "合成", "温度", "产率", "溶剂", "配体", "金属源", "调节剂",
            "设备", "晶系", "空间群", "晶胞", "化学式", "形貌",
        )
        return any(term in lower for term in terms)

    def _target_identity(self, entity_key: Optional[str]) -> Dict[str, Any]:
        """Extract only identity aliases needed to avoid mixing compounds in one paper."""
        identity: Dict[str, Any] = {"entity": entity_key} if entity_key else {}
        if not entity_key:
            return identity
        graph = self.store.graph_context(entity_key, limit=80)
        references = set()
        for node in graph.get("nodes", []):
            properties = node.get("properties") or {}
            if node.get("node_type") == "MOF":
                for source_key, target_key in (
                    ("Formula", "ccdc_formula"),
                    ("Chemical_Name", "ccdc_chemical_name"),
                    ("Number", "ccdc_number"),
                ):
                    value = properties.get(source_key)
                    if value not in (None, "", "N/A", "NA"):
                        identity[target_key] = str(value) if source_key == "Number" else value
            elif node.get("node_type") == "CrystalObservation":
                for key in ("Complex", "Complexes", "Compound"):
                    value = str(properties.get(key) or "").strip()
                    if value:
                        references.add(value)
            elif node.get("node_type") == "SynthesisRecipe":
                compound = str(properties.get("compound") or "").strip()
                match = re.search(r"\(((?:\d+[a-z]?|[ivx]+[a-z]?))\)\s*$", compound, re.I)
                if match:
                    references.add(match.group(1))
        if references:
            identity["article_compound_labels"] = sorted(references)

        ccdc_number = str(identity.get("ccdc_number") or "").strip()
        if ccdc_number:
            source_chunks = [
                item for item in self.store.list_chunks()
                if Path(item["source_path"]).stem.upper() == str(entity_key).upper()
            ]
            source_text = " ".join(item["text"] for item in source_chunks)
            deposition_pattern = re.compile(
                rf"CCDC\s*[-–—]?\s*{re.escape(ccdc_number)}\s*\(([^)]+)\)", re.I
            )
            deposition_labels = set()
            for match in deposition_pattern.finditer(source_text):
                label = match.group(1).strip()
                if re.fullmatch(r"(?:\d+[a-z]?|[ivx]+[a-z]?)", label, re.I):
                    deposition_labels.add(label)
            for match in re.finditer(
                rf"CCDC\s*[-–—]?\s*{re.escape(ccdc_number)}[^.]{{0,180}}?"
                rf"(?:data|entry|deposit(?:ion)?)\s+for\s+(?:compound\s+|complex\s+)?"
                rf"(\d+[a-z]?|[ivx]+[a-z]?)\b",
                source_text,
                re.I,
            ):
                deposition_labels.add(match.group(1).strip())
            if deposition_labels:
                # An explicit CCDC-number mapping in the paper is more authoritative
                # than a previously imported recipe or an ambiguous table label.
                references = deposition_labels
            if references:
                identity["article_compound_labels"] = sorted(references)
        return identity

    @staticmethod
    def _extract_json_object(text: str) -> Dict[str, Any]:
        """Parse one JSON object from a model response without accepting prose as data."""
        cleaned = (text or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if not match:
                return {}
            try:
                value = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}
        return value if isinstance(value, dict) else {}

    def extract_literature_summary(self, context_key: str) -> Dict[str, Any]:
        """Persist target-specific literature findings and applications with evidence links.

        This is an incremental graph-enrichment step, not a user-facing question
        recommendation. An unchanged source document reuses its existing summary.
        """
        target = (context_key or "").strip().upper()
        if not target:
            return {"status": "skipped", "reason": "empty target"}
        if self.client is None:
            return {"status": "skipped", "reason": "LLM client unavailable", "target": target}

        target_identity = self._target_identity(target)
        identity_signature = json.dumps(target_identity, ensure_ascii=False, sort_keys=True)

        with self.store.connection() as conn:
            documents = conn.execute(
                "SELECT id,source_path,title,doi,content_hash FROM documents ORDER BY updated_at DESC"
            ).fetchall()
            document = next(
                (row for row in documents if Path(row["source_path"]).stem.upper() == target),
                None,
            )
            existing = conn.execute(
                "SELECT id,properties_json FROM nodes WHERE node_type='LiteratureSummary' "
                "AND canonical_key=?",
                (self.store.canonicalize(f"literature-summary:{target}"),),
            ).fetchone()

        if document is None:
            return {"status": "skipped", "reason": "matching source document not found", "target": target}
        if existing:
            existing_properties = json.loads(existing["properties_json"] or "{}")
            if (
                existing_properties.get("source_content_hash") == document["content_hash"]
                and existing_properties.get("model") == self.chat_model
                and existing_properties.get("identity_signature") == identity_signature
            ):
                return {
                    "status": "reused",
                    "target": target,
                    "findings": len(existing_properties.get("findings") or []),
                    "applications": len(existing_properties.get("applications") or []),
                }

        query = (
            f"{target} {target_identity.get('ccdc_formula', '')} "
            f"{target_identity.get('ccdc_chemical_name', '')} target compound framework topology "
            "coordination structure characterization "
            "spectroscopy thermal chemical stability physical properties performance application "
            "mechanism limitation conclusion"
        )
        evidence = self.retrieve(query, top_k=16, document_ids=[int(document["id"])])
        if not evidence:
            return {"status": "skipped", "reason": "no indexed evidence", "target": target}

        excerpts = [
            {
                "index": index,
                "page": item.get("page"),
                "section": item.get("section"),
                "text": item["text"][:1800],
            }
            for index, item in enumerate(evidence, start=1)
        ]
        prompt = f"""
Extract target-specific literature knowledge for a MOF knowledge graph.

Target CCDC identifier: {target}
Target identity constraints: {json.dumps(target_identity, ensure_ascii=False)}
Evidence excerpts: {json.dumps(excerpts, ensure_ascii=False)}

Return only one JSON object with this schema:
{{
  "summary": "brief target-specific overview",
  "findings": [
    {{"category": "structure|property|stability|characterization|mechanism|limitation",
      "statement": "one evidence-grounded finding", "evidence_indices": [1]}}
  ],
  "applications": [
    {{"application": "application name", "status": "demonstrated|studied|proposed",
      "statement": "what the paper actually reports", "evidence_indices": [1]}}
  ]
}}

Use only evidence about the target compound. When article_compound_labels are supplied,
exclude findings assigned only to other numbered compounds. Keep at most 8 findings and
5 applications. Do not infer a generic MOF application from pores, topology, composition,
or introductory background. Include an application only when the target paper explicitly
demonstrates, studies, or proposes it for this target; "proposed" must also be explicit.
Omit unsupported categories and applications. Do not include synthesis conditions or raw
crystallographic cell parameters because those are represented elsewhere in the graph.
Every statement must cite at least one valid evidence index.
"""
        response = self.client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": "You extract conservative, evidence-linked MOF literature facts as strict JSON.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        payload = self._extract_json_object(response.choices[0].message.content)
        valid_categories = {
            "structure", "property", "stability", "characterization", "mechanism", "limitation"
        }
        valid_statuses = {"demonstrated", "studied", "proposed"}

        def evidence_indices(item: Dict[str, Any]) -> List[int]:
            result = []
            for value in item.get("evidence_indices") or []:
                try:
                    index = int(value)
                except (TypeError, ValueError):
                    continue
                if 1 <= index <= len(evidence) and index not in result:
                    result.append(index)
            return result

        findings = []
        for item in payload.get("findings") or []:
            if not isinstance(item, dict):
                continue
            statement = str(item.get("statement") or "").strip()
            indices = evidence_indices(item)
            category = str(item.get("category") or "").strip().lower()
            if statement and indices and category in valid_categories:
                findings.append({
                    "category": category,
                    "statement": statement,
                    "evidence_indices": indices,
                })
            if len(findings) >= 8:
                break

        applications = []
        for item in payload.get("applications") or []:
            if not isinstance(item, dict):
                continue
            application = str(item.get("application") or "").strip()
            statement = str(item.get("statement") or "").strip()
            status = str(item.get("status") or "").strip().lower()
            indices = evidence_indices(item)
            if application and statement and indices and status in valid_statuses:
                applications.append({
                    "application": application,
                    "status": status,
                    "statement": statement,
                    "evidence_indices": indices,
                })
            if len(applications) >= 5:
                break

        summary_text = str(payload.get("summary") or "").strip()
        summary_node = self.store.upsert_node(
            "LiteratureSummary",
            f"literature-summary:{target}",
            f"Literature findings for {target}",
            {
                "summary": summary_text,
                "findings": findings,
                "applications": applications,
                "source_document_id": int(document["id"]),
                "source_content_hash": document["content_hash"],
                "identity_signature": identity_signature,
                "model": self.chat_model,
            },
        )
        mof = self.store.upsert_node("MOF", target, target)
        paper_key = document["doi"] or document["source_path"]
        paper = self.store.upsert_node(
            "Paper",
            paper_key,
            document["title"] or Path(document["source_path"]).name,
            {"doi": document["doi"], "source_path": document["source_path"]},
        )
        self.store.upsert_edge(mof, summary_node, "HAS_LITERATURE_SUMMARY")
        self.store.upsert_edge(paper, mof, "REPORTS")
        self.store.delete_outgoing_edges(summary_node, ["SUMMARIZES", "EVIDENCED_BY"])
        self.store.upsert_edge(summary_node, paper, "SUMMARIZES")

        referenced_indices = sorted({
            index
            for item in findings + applications
            for index in item.get("evidence_indices", [])
        })
        for index in referenced_indices:
            item = evidence[index - 1]
            chunk_id = int(item["id"])
            chunk_node = self.store.upsert_node(
                "TextChunk",
                f"chunk:{chunk_id}",
                f"{target} literature evidence {chunk_id}",
                {"chunk_id": chunk_id, "page": item.get("page"), "section": item.get("section")},
            )
            self.store.upsert_edge(
                summary_node,
                chunk_node,
                "EVIDENCED_BY",
                evidence_chunk_id=chunk_id,
                edge_key=str(chunk_id),
            )
        return {
            "status": "created" if existing is None else "updated",
            "target": target,
            "findings": len(findings),
            "applications": len(applications),
            "evidence_chunks": len(referenced_indices),
        }

    def ask(self, question: str, entity_key: Optional[str] = None, top_k: int = 6) -> str:
        language = self.language_for(question)
        output_language = "Chinese" if language == "zh" else "English"
        retrieval_question = question
        if entity_key and entity_key.lower() not in question.lower():
            retrieval_question = f"{entity_key} {question}"
        retrieval_question = self._domain_query_expansion(retrieval_question)
        document_ids = None
        if entity_key:
            with self.store.connection() as conn:
                documents = conn.execute("SELECT id,source_path FROM documents").fetchall()
            document_ids = [int(row["id"]) for row in documents
                            if Path(row["source_path"]).stem.upper() == entity_key.upper()]
        evidence = (
            self.retrieve(retrieval_question, top_k=max(top_k * 2, 10), document_ids=document_ids)
            if document_ids is None or document_ids else []
        )
        if self.client is None:
            raise RuntimeError("An OpenAI client is required for RAG answers")

        entity_graph = self.store.graph_context(entity_key, limit=40) if entity_key else {"nodes": [], "edges": []}
        target_identity = self._target_identity(entity_key)
        graph = (
            entity_graph
            if entity_key and self._question_uses_structured_graph(question)
            else {"nodes": [], "edges": []}
        )
        if entity_key and not entity_graph["nodes"]:
            evidence = [item for item in evidence
                        if Path(item["source_path"]).stem.upper() == entity_key.upper()]
        if evidence and evidence[0].get("score", 0) < 0.15:
            evidence = self.retrieve(
                self._expand_query(retrieval_question), top_k=max(top_k * 2, 10),
                document_ids=document_ids,
            )
        evidence = [item for item in evidence if item.get("score", 0) >= 0.05]
        candidate_evidence = list(evidence)
        evidence = self._rerank_evidence(
            question, evidence, limit=top_k, target_identity=target_identity
        )
        if not evidence:
            evidence = self._rescue_property_evidence(question, candidate_evidence)
        if not evidence and not graph["nodes"]:
            return (
                "已索引的文献中没有找到能够回答该问题的相关证据。"
                if language == "zh" else
                "The indexed literature does not contain relevant evidence for this question."
            )
        if len(evidence) == 1 and evidence[0].get("evidence_mode") == "indirect_gas_structure":
            final = self._indirect_gas_answer(entity_key, evidence[0], language)
            self.store.record_interaction(
                question, final, self.chat_model, evidence, entity_key=entity_key
            )
            return final

        evidence_text = "\n\n".join(
            f"[{index}] SOURCE: {self._source_label(item, index)}\n{item['text']}"
            for index, item in enumerate(evidence, start=1)
        )
        prompt = f"""
Question: {question}

Target identity constraints:
{json.dumps(target_identity, ensure_ascii=False)}

Knowledge graph context:
{json.dumps(graph, ensure_ascii=False, default=str)}

Retrieved literature evidence:
{evidence_text}

Answer the question using only the supplied graph context and literature evidence.
PubChem identifiers in graph properties establish chemical identity only; they do not
establish a synthesis route or prove that a new reagent combination yields a MOF.
Use inline citations such as [1] and [2]. Distinguish explicitly reported facts from inference.
Answer only the scope requested. Do not add synthesis, crystallographic, stability, or general
material background unless it is necessary to answer the question directly.
If the requested property, application, or measurement was not directly studied, start by saying
that it was not reported, then give only clearly labelled indirect structural evidence if useful.
Never infer gas storage, adsorption capacity, porosity, catalysis, sensing, drug delivery, or other
performance merely because the target is a MOF, has cavities, or resembles other MOFs.
For an article containing multiple numbered compounds, use only facts assigned to the target's
article_compound_labels. Do not use another compound as evidence for the target.
When direct performance measurements are absent, do not use "may", "could", "potentially", or
similar speculative language to claim a capability. State the structural observation neutrally
and explicitly say it is not performance evidence.
Do not convert generic statements about a research field into a result for the target material.
If evidence is insufficient or conflicting, say so. Do not invent missing values or capabilities.
OUTPUT LANGUAGE: {output_language}. Write the entire answer only in {output_language},
even when graph properties, retrieved evidence, or earlier interactions use another language.
"""
        response = self.client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are an evidence-grounded MOF literature assistant. "
                        f"You must answer only in {output_language}."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        answer = response.choices[0].message.content.strip()
        sources = "\n".join(self._source_label(item, index) for index, item in enumerate(evidence, start=1))
        final = f"{answer}\n\nSources used:\n{sources}" if sources else answer
        self.store.record_interaction(question, final, self.chat_model, evidence, entity_key=entity_key)
        return final

    @staticmethod
    def _compact_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
        """Remove storage-level nodes and edges before presenting graph data to an LLM."""
        visible_types = {
            "MOF", "Paper", "SynthesisRecipe", "Chemical", "Equipment", "CrystalObservation",
            "LiteratureSummary",
        }
        hidden_edges = {"CONTAINS", "DERIVED_FROM", "EVIDENCED_BY"}
        nodes = []
        for node in graph.get("nodes", []):
            if node.get("node_type") not in visible_types:
                continue
            properties = dict(node.get("properties") or {})
            properties.pop("raw_row", None)
            properties.pop("source_path", None)
            nodes.append({
                "type": node.get("node_type"),
                "label": node.get("label"),
                "properties": properties,
            })
        edges = [
            {
                "source": edge.get("source_label"),
                "relation": edge.get("edge_type"),
                "target": edge.get("target_label"),
                "properties": edge.get("properties") or {},
            }
            for edge in graph.get("edges", [])
            if edge.get("edge_type") not in hidden_edges
            and edge.get("source_type") in visible_types
            and edge.get("target_type") in visible_types
        ]
        return {"nodes": nodes, "relationships": edges}

    @staticmethod
    def _fallback_graph_summary(
        context_key: str, graph: Dict[str, Any], language: str = "en"
    ) -> str:
        compact = MOFRAGService._compact_graph(graph)
        nodes = compact["nodes"]
        if not nodes:
            return (
                f"尚未找到 {context_key} 的知识图谱记录。"
                if language == "zh" else f"No knowledge-graph record was found for {context_key}."
            )
        lines = [
            f"🧪 {context_key} 知识图谱摘要" if language == "zh"
            else f"🧪 {context_key} knowledge summary"
        ]
        for node in nodes:
            if node["type"] == "SynthesisRecipe":
                props = node["properties"]
                if language == "zh":
                    lines.append(
                        f"- 合成条件：温度 {props.get('temperature', {}).get('raw', '未报道')}，"
                        f"时间 {props.get('time', {}).get('raw', '未报道')}，"
                        f"产率 {props.get('yield', {}).get('raw', '未报道')}，"
                        f"晶体形貌 {props.get('morphology') or '未报道'}。"
                    )
                else:
                    lines.append(
                        f"- Synthesis: {props.get('temperature', {}).get('raw', 'not reported')}, "
                        f"{props.get('time', {}).get('raw', 'not reported')}, "
                        f"yield {props.get('yield', {}).get('raw', 'not reported')}; "
                        f"morphology: {props.get('morphology') or 'not reported'}."
                    )
            elif node["type"] == "CrystalObservation":
                props = node["properties"]
                label = props.get('Complex') or props.get('Complexes') or node['label']
                if language == "zh":
                    lines.append(
                        f"- 晶体数据（{label}）：{props.get('Crystal system', '未报道')}晶系，"
                        f"空间群 {props.get('Space group', '未报道')}，"
                        f"化学式 {props.get('Empirical formula') or props.get('Formula') or '未报道'}。"
                    )
                else:
                    lines.append(
                        f"- Crystal data ({label}): {props.get('Crystal system', 'not reported')}; "
                        f"space group {props.get('Space group', 'not reported')}; formula "
                        f"{props.get('Empirical formula') or props.get('Formula') or 'not reported'}."
                    )
        chemicals = [node["label"] for node in nodes if node["type"] == "Chemical"]
        if chemicals:
            label = "图谱中关联的化学品" if language == "zh" else "Associated chemicals"
            lines.append(f"- {label}: {'; '.join(chemicals)}.")
        return "\n".join(lines)

    def describe_graph(self, context_key: str, language: str = "en") -> str:
        """Render backend graph records in the user's interaction language."""
        graph = self.store.graph_context(context_key, limit=120)
        if not graph.get("nodes"):
            return self._fallback_graph_summary(context_key, graph, language)
        if self.client is None:
            return self._fallback_graph_summary(context_key, graph, language)
        compact = self._compact_graph(graph)
        output_language = "Chinese" if language == "zh" else "English"
        prompt = f"""
Target material: {context_key}
Knowledge graph data:
{json.dumps(compact, ensure_ascii=False, default=str)}

Write a concise, natural explanation for a MOF researcher in {output_language}.
Organize only these relevant sections: material overview, synthesis, and crystallography.
Do not add a literature-evidence section or state that a TXT file reports the material.
If one paper contains several compounds, separate the target from the other compounds and never mix parameters.
Use only supplied facts; do not fill in or infer missing values.
Do not expose node IDs, edge names, JSON, file paths, or chunk numbers.
End with 2–3 diverse follow-up directions spanning properties, structure–property relations,
stability, characterization, applications, comparison, or research gaps when supported.
Never suggest gas storage, adsorption, catalysis, sensing, drug delivery, or another application
unless the supplied graph explicitly contains evidence for that application or performance.
"""
        try:
            response = self.client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": "You explain MOF knowledge graphs accurately to researchers."},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return self._fallback_graph_summary(context_key, graph, language)

    @staticmethod
    def _extract_json_list(text: str) -> List[Dict[str, Any]]:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", cleaned)
            if not match:
                return []
            value = json.loads(match.group(0))
        return value if isinstance(value, list) else []

    @staticmethod
    def _questions_are_similar(left: str, right: str) -> bool:
        """Reject exact and close paraphrases across recommendation stages."""
        normalize = lambda value: re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())
        a, b = normalize(left), normalize(right)
        if not a or not b:
            return False
        if a in b or b in a:
            return True
        return SequenceMatcher(None, a, b).ratio() >= 0.72

    def suggest_questions(
        self,
        context_key: str,
        count: int = 5,
        language: str = "en",
        stage: str = "general",
    ) -> List[Dict[str, Any]]:
        if self.client is None:
            raise RuntimeError("An OpenAI client is required for question suggestions")
        graph = self.store.graph_context(context_key, limit=60)
        target_identity = self._target_identity(context_key)
        seed_evidence = self.retrieve(context_key, top_k=8)
        compact_evidence = [
            {
                "source": item.get("doi") or Path(item["source_path"]).name,
                "page": item.get("page"),
                "text": item["text"][:500],
            }
            for item in seed_evidence
        ]
        previous = [item["question"] for item in self.store.list_suggestions(context_key)]
        stage_instructions = {
            "download": (
                "The paper has just been downloaded but structured synthesis extraction has not run. "
                "Do not recommend questions about synthesis recipes, reagents, temperature, time, yield, "
                "or crystal color/morphology. Explore the whole paper instead: framework topology and structure, "
                "characterization methods, properties, mechanisms, stability, structure-property relationships, "
                "applications only when directly studied, comparisons, limitations, and research gaps. "
                "Do not infer generic MOF applications from structure alone."
            ),
            "workflow": (
                "Structured synthesis and crystallographic extraction has completed. Propose deeper questions that "
                "connect multiple facts or documents. Avoid basic lookup questions about ligand names, synthesis "
                "temperature/time/yield, crystal system/space group, or color/morphology. Prefer structure-property "
                "relationships, condition-outcome patterns, evidence conflicts, analog comparisons, stability, "
                "characterization, directly evidenced applications, and testable research hypotheses. "
                "Every question must explicitly name the target context entity. Focus at least four questions on "
                "the target's matched article compound; at most one question may compare it with another compound "
                "from the same paper, and that comparison must label both compounds unambiguously. "
                "Do not ask atom-level or mechanistic questions unless the supplied excerpts contain enough direct "
                "evidence to answer them without placeholders or unsupported chemical interpretation. "
                "Do not imply that a target has gas-storage, adsorption, catalytic, sensing, or other "
                "performance unless the supplied excerpts report relevant experiments or metrics."
            ),
            "general": (
                "Diversify across synthesis, structure, characterization, properties, mechanisms, stability, "
                "applications, comparisons, evidence conflicts, and research gaps."
            ),
        }.get(stage, "Generate diverse evidence-aware research questions.")
        output_language = "Chinese" if language == "zh" else "English"
        prompt = f"""
Context entity or topic: {context_key}
Target identity constraints: {json.dumps(target_identity, ensure_ascii=False)}
Knowledge graph context: {json.dumps(graph, ensure_ascii=False, default=str)}
Available literature excerpts: {json.dumps(compact_evidence, ensure_ascii=False)}
Previously displayed questions (do not repeat or closely paraphrase): {json.dumps(previous, ensure_ascii=False)}
Stage-specific policy: {stage_instructions}

Generate {count + 3} useful questions a MOF researcher may want to ask next.
Cover distinct scientific dimensions rather than producing several variants of the same topic.
Most questions must be answerable from the supplied context; at most one may identify a research gap.
Return only a JSON array. Each item must contain:
{{"question":"...","type":"factual|comparison|exploratory","reason":"..."}}
Write every question and reason in {output_language}.
"""
        response = self.client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {"role": "system", "content": "You recommend evidence-aware research questions for a MOF literature system."},
                {"role": "user", "content": prompt},
            ],
        )
        candidates = self._extract_json_list(response.choices[0].message.content)
        download_banned_terms = (
            "synthesi", "reagent", "temperature", "reaction time", "yield", "crystal color",
            "crystal morphology", "合成", "试剂", "反应物", "温度", "时间", "产率", "晶体颜色", "晶体形貌",
        )
        filtered_candidates: List[Dict[str, Any]] = []
        for item in candidates:
            question = str(item.get("question", "")).strip()
            if not question:
                continue
            if stage == "workflow" and context_key.lower() not in question.lower():
                if language == "zh":
                    question = f"对于 {context_key}，{question}"
                else:
                    question = f"For {context_key}, {question[0].lower() + question[1:]}"
            if stage == "download" and any(term in question.lower() for term in download_banned_terms):
                continue
            if any(self._questions_are_similar(question, old) for old in previous):
                continue
            if any(self._questions_are_similar(question, old["question"]) for old in filtered_candidates):
                continue
            filtered_candidates.append({**item, "question": question})

        self._prime_query_embeddings([item["question"] for item in filtered_candidates])
        ranked: List[Dict[str, Any]] = []
        for item in filtered_candidates:
            question = item["question"]
            hits = self.retrieve(question, top_k=4)
            evidence_count = sum(1 for hit in hits if hit.get("score", 0) >= 0.2)
            if graph["edges"]:
                evidence_count += 1
            exploratory = item.get("type") == "exploratory"
            score = min(1.0, 0.25 + 0.18 * evidence_count + (0.1 if graph["nodes"] else 0.0))
            if evidence_count == 0 and not exploratory:
                continue
            ranked.append({
                "question": question,
                "type": item.get("type", "factual"),
                "reason": item.get("reason", ""),
                "score": round(score, 3),
                "evidence_count": evidence_count,
            })
        ranked.sort(key=lambda item: item["score"], reverse=True)
        result = ranked[:count]
        self.store.save_suggestions(context_key, result)
        return result
