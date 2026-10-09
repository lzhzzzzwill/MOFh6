import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "request"))

from knowledge import KnowledgeStore, StructuredKnowledgeIngestor
from rag import MOFRAGService
from extrfinetune.file_utils import list_visible_text_files
from request.core.query_system import ChemicalQuerySystem


class _FakeCompletions:
    def create(self, **kwargs):
        prompt = kwargs["messages"][-1]["content"]
        if "Extract target-specific literature knowledge" in prompt:
            content = json.dumps(
                {
                    "summary": "ABAYUY is a zinc coordination framework with a reported diamondoid topology.",
                    "findings": [
                        {
                            "category": "structure",
                            "statement": "The target is reported as a diamondoid coordination framework.",
                            "evidence_indices": [1],
                        }
                    ],
                    "applications": [],
                }
            )
        elif "Score each candidate only for its usefulness" in prompt:
            content = '[{"index":1,"relevance":3}]'
        elif "Generate" in prompt and "useful questions" in prompt:
            if "paper has just been downloaded" in prompt:
                content = (
                    '[{"question":"What topology is reported for ABAYUY?","type":"factual",'
                    '"reason":"The paper discusses framework structure."},'
                    '{"question":"Which characterization methods support the assigned structure?",'
                    '"type":"factual","reason":"The article contains characterization evidence."}]'
                )
            else:
                content = (
                    '[{"question":"How does the ABAYUY structure relate to its properties?",'
                    '"type":"factual","reason":"The graph and paper contain structural evidence."},'
                    '{"question":"How does ABAYUY compare with related frameworks?",'
                    '"type":"comparison","reason":"Cross-document comparison is possible."}]'
                )
        elif "Knowledge graph data" in prompt:
            content = (
                "ABAYUY has a solvothermal synthesis route using a zinc salt and organic linkers "
                "at 170 °C for 4 days, with a reported yield of 72%."
            )
        else:
            content = "DOTHIE was synthesized at room temperature with a reported yield of 74% [1]."
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class _FakeEmbeddings:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        values = kwargs["input"]
        values = [values] if isinstance(values, str) else values
        data = []
        for index, value in enumerate(values):
            lowered = value.lower()
            vector = [
                max(1.0, len(value) / 100.0),
                float(lowered.count("dothie")),
                float(lowered.count("abayuy")),
                float(lowered.count("yield")),
                float(lowered.count("topology")),
            ]
            data.append(SimpleNamespace(index=index, embedding=vector))
        return SimpleNamespace(data=data)


class _FailingEmbeddings:
    def create(self, **kwargs):
        raise ConnectionError("embedding service unavailable")


class _FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeCompletions())
        self.embeddings = _FakeEmbeddings()


class _RoutingStore:
    def graph_context(self, key, limit=80):
        if str(key).upper() == "ABAYUY":
            return {"nodes": [{"id": 1, "label": "ABAYUY"}], "edges": []}
        return {"nodes": [], "edges": []}


class _RoutingRAG:
    language_for = staticmethod(MOFRAGService.language_for)

    def __init__(self):
        self.calls = []

    def ask(self, question, entity_key=None, **kwargs):
        self.calls.append((question, entity_key))
        return f"RAG:{entity_key}:{question}"

    def describe_graph(self, key, language="en"):
        return f"OVERVIEW:{key}:{language}"


class _RoutingQueryHandler:
    def process_query(self, question):
        return f"DATABASE:{question}"


class _RoutingIngredientQA:
    def classify(self, question):
        return {"intent": "reagent_to_mof" if question.startswith("I have cobalt nitrate") else "other"}

    def answer(self, question, language="en", extracted=None):
        return f"CASES:{language}:{question}"


class KnowledgeRAGTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.store = KnowledgeStore(str(self.root / "mofh6.db"))
        self.client = _FakeClient()
        self.rag = MOFRAGService(self.store, self.client)
        self.assertEqual(self.rag.chat_model, "gpt-6-luna")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_incremental_graph_rag_and_interactions(self):
        document = self.root / "DOTHIE.txt"
        document.write_text(
            "[[PAGE 1]] Synthesis of DOTHIE. Co(NO3)2 and benzimidazole were mixed in methanol and water. "
            "The solution stood at room temperature for several days. Pink crystals were obtained in 74% yield.",
            encoding="utf-8",
        )
        first = self.rag.ingest_document(str(document))
        calls_after_first_ingest = self.client.embeddings.calls
        second = self.rag.ingest_document(str(document))
        self.assertEqual(first["chunks"], second["chunks"])
        self.assertEqual(self.store.stats()["chunks"], first["chunks"])
        self.assertEqual(first["embedded"], first["chunks"])
        self.assertEqual(second["embedded"], 0)
        self.assertEqual(second["embeddings_reused"], second["chunks"])
        self.assertEqual(self.client.embeddings.calls, calls_after_first_ingest)
        self.assertEqual(self.store.stats()["embedded_chunks"], first["chunks"])
        stored_chunks = self.store.list_chunks([first["document_id"]])
        self.assertTrue(all(item["embedding_json"] for item in stored_chunks))
        self.assertTrue(all(item["embedding_model"] == "text-embedding-3-small" for item in stored_chunks))

        markdown = self.root / "synthesis.md"
        markdown.write_text(
            """# Identifier: ABAYUY
**ABAYUY**
Chemical_Name: zinc framework
Number: 220650
Synonyms: N/A
[Zn(bpe)(OH-BDC)]n (1)
| Metal Source | Organic Linkers Source | Modulator Source | Solvent Source | Quantity of Metal | Quantity of Organic Linkers | Quantity of Modulator | Quantity of Solvent | pH | Synthesis Temperature | Synthesis Time | Crystal Morphology | Yield | Equipment |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Zn(NO3)2·6H2O | 1,2-bis(4-pyridyl)ethane; 5-hydroxyisophthalate | NaOH | CH3OH | 0.075 g (0.25 mmol) | 0.044 g (0.25 mmol); 0.045 g (0.25 mmol) | 0.020 g | 5 mL | N/A | 170 °C | 4 days | yellow block crystals | 72% | Teflon-lined reactor |

# Identifier: DOTHIE
**DOTHIE**
Chemical_Name: cobalt framework
Number: N/A
Synonyms: N/A
[Co(bim)2(dca)2]n (1)
| Metal Source | Organic Linkers Source | Modulator Source | Solvent Source | Quantity of Metal | Quantity of Organic Linkers | Quantity of Modulator | Quantity of Solvent | pH | Synthesis Temperature | Synthesis Time | Crystal Morphology | Yield | Equipment |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Co(NO3)2·6H2O | benzimidazole | N/A | methanol; water | 0.146 g (0.5 mmol) | 0.117 g (1.0 mmol) | N/A | 15 mL; 15 mL | N/A | room temperature | several days | pink crystals | 74% | N/A |
""",
            encoding="utf-8",
        )
        ingestor = StructuredKnowledgeIngestor(self.store)
        result = ingestor.ingest_synthesis_markdown(str(markdown))
        self.assertEqual(result["records"], 2)
        self.assertTrue(Path(result["json_output"]).exists())

        graph = self.store.graph_context("ABAYUY")
        edge_types = {edge["edge_type"] for edge in graph["edges"]}
        self.assertIn("HAS_SYNTHESIS", edge_types)
        self.assertIn("USES_METAL_SOURCE", edge_types)
        self.assertEqual(self.store.resolve_exact_entity("ABAYUY"), "ABAYUY")
        self.assertIsNone(self.store.resolve_exact_entity("something"))

        identity = self.rag._target_identity("ABAYUY")
        self.assertEqual(identity["article_compound_labels"], ["1"])

        answer = self.rag.ask("What were the DOTHIE synthesis temperature and yield?", entity_key="DOTHIE")
        self.assertIn("74%", answer)
        stats = self.store.stats()
        self.assertEqual(stats["questions"], 1)
        self.assertEqual(stats["answers"], 1)

        suggestions = self.rag.suggest_questions("ABAYUY", count=2)
        self.assertTrue(suggestions)
        self.assertTrue(all("ABAYUY" in item["question"] for item in suggestions))
        self.assertEqual(self.store.stats()["suggestions"], len(suggestions))

        summary = self.rag.describe_graph("ABAYUY")
        self.assertIn("ABAYUY", summary)
        self.assertIn("170", summary)

        discovery = self.rag.suggest_questions(
            "ABAYUY", count=2, language="en", stage="download"
        )
        self.assertTrue(discovery)
        self.assertNotIn("synthesis temperature", " ".join(item["question"] for item in discovery).lower())
        self.assertEqual(self.rag.language_for("graph show ABAYUY"), "en")
        self.assertEqual(self.rag.language_for("请总结 ABAYUY"), "zh")

    def test_visible_text_files_ignore_macos_appledouble(self):
        inputs = self.root / "inputs"
        inputs.mkdir()
        (inputs / "ABAYUY.txt").write_text("valid", encoding="utf-8")
        (inputs / "._ABAYUY.txt").write_bytes(b"\x00\x05\x16\x07\xb0")
        (inputs / ".hidden.txt").write_text("hidden", encoding="utf-8")
        (inputs / "notes.md").write_text("not a txt input", encoding="utf-8")
        self.assertEqual(list_visible_text_files(str(inputs)), ["ABAYUY.txt"])

    def test_synthesis_import_selects_the_ccdc_mapped_compound(self):
        markdown = self.root / "multi.md"
        markdown.write_text(
            """# Identifier: TARGET
Chemical_Name: test framework
Number: 123
Synonyms: N/A
[M(L)] (1)
| pH | Synthesis Temperature |
|---|---|
| 4 | 100 °C |

[M2(L)] (2)
| pH | Synthesis Temperature |
|---|---|
| 8 | 170 °C |
""",
            encoding="utf-8",
        )
        ingestor = StructuredKnowledgeIngestor(self.store)
        records = ingestor.parse_synthesis_markdown(
            str(markdown), compound_labels={"TARGET": ["2"]}
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["compound"], "[M2(L)] (2)")
        self.assertEqual(records[0]["row"]["ph"], "8")

    def test_ccdc_enrichment_and_incremental_literature_summary(self):
        document = self.root / "ABAYUY.txt"
        document.write_text(
            "ABAYUY compound 1 is a zinc coordination framework with a diamondoid topology. "
            "Single-crystal diffraction established its framework structure.",
            encoding="utf-8",
        )
        self.rag.ingest_document(str(document))
        ccdc = self.root / "des_mate.json"
        ccdc.write_text(
            json.dumps(
                [
                    {
                        "ABAYUY": {
                            "Molecule_Identifier": "ABAYUY",
                            "Number": 220650,
                            "Chemical_Name": "catena-zinc framework",
                            "Formula": "(C20 H16 N2 O5 Zn)n",
                            "Crystal_System": "tetragonal",
                            "Spacegroup_Symbol": "I41/acd",
                            "Color": "yellow",
                        }
                    }
                ]
            ),
            encoding="utf-8",
        )
        ingestor = StructuredKnowledgeIngestor(self.store)
        enriched = ingestor.ingest_ccdc_metadata(str(ccdc), ["ABAYUY"])
        self.assertEqual(enriched, {"records": 1, "requested": 1, "missing": 0})
        matched = ingestor._match_ccdc_crystal_row(
            [
                {
                    "Complex": "1", "Empirical formula": "C20H16N2O5Zn",
                    "Crystal system": "tetragonal", "Space group": "I41/acd",
                    "a (Å)": "15.0", "b (Å)": "15.0", "c (Å)": "8.0",
                },
                {
                    "Complex": "2", "Empirical formula": "C16H16ClN10O6Tb",
                    "Crystal system": "monoclinic", "Space group": "C2/c",
                },
            ],
            {
                "Formula": "(C20 H16 N2 O5 Zn)n", "Crystal_System": "tetragonal",
                "Spacegroup_Symbol": "I41/acd", "a": 15.0, "b": 15.0, "c": 8.0,
            },
        )
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["Complex"], "1")

        first = self.rag.extract_literature_summary("ABAYUY")
        second = self.rag.extract_literature_summary("ABAYUY")
        self.assertEqual(first["status"], "created")
        self.assertEqual(first["findings"], 1)
        self.assertEqual(second["status"], "reused")

        graph = self.store.graph_context("ABAYUY", limit=100)
        mof = next(node for node in graph["nodes"] if node["node_type"] == "MOF")
        self.assertEqual(mof["properties"]["Formula"], "(C20 H16 N2 O5 Zn)n")
        summaries = [node for node in graph["nodes"] if node["node_type"] == "LiteratureSummary"]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["properties"]["applications"], [])
        self.assertIn(
            "HAS_LITERATURE_SUMMARY",
            {edge["edge_type"] for edge in graph["edges"]},
        )

    def test_crystal_ingestion_uses_comparator_selection_and_prunes_stale_rows(self):
        raw = self.root / "tables.json"
        raw.write_text(
            json.dumps(
                {
                    "ABAYUY": [
                        {
                            "Complexes": "1", "Empirical formula": "C20H16N2O5Zn",
                            "Crystal system": "tetragonal", "beta (°)": "125.75(11)",
                        },
                        {"Complexes": "2", "Empirical formula": "C19H14CoN4O4", "Crystal system": "monoclinic"},
                        {"Complexes": "3", "Empirical formula": "C19H14CdN4O4", "Crystal system": "orthorhombic"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        selection = self.root / "comparison.json"
        selection.write_text(
            json.dumps({"ABAYUY": {"ABAYUY": {"Compound": "1"}}}),
            encoding="utf-8",
        )
        ingestor = StructuredKnowledgeIngestor(self.store)

        # Simulate a database created by the old implementation, which attached
        # every compound in the paper to the queried CCDC identifier.
        self.assertEqual(ingestor.ingest_crystal_json(str(raw))["records"], 3)
        repaired = ingestor.ingest_crystal_json(str(raw), selection_path=str(selection))
        self.assertEqual(repaired["records"], 1)
        self.assertEqual(repaired["filtered_out"], 2)
        self.assertEqual(repaired["stale_removed"], 2)

        graph = self.store.graph_context("ABAYUY")
        crystals = [node for node in graph["nodes"] if node["node_type"] == "CrystalObservation"]
        self.assertEqual(len(crystals), 1)
        self.assertEqual(crystals[0]["properties"]["Complexes"], "1")
        self.assertEqual(crystals[0]["properties"]["beta (°)"], "90")
        self.assertIn("validation_notes", crystals[0]["properties"])

    def test_gas_questions_do_not_receive_structured_synthesis_context(self):
        self.assertFalse(
            self.rag._question_uses_structured_graph("Say something about ABAYUY in gas storage")
        )
        self.assertTrue(
            self.rag._question_uses_structured_graph("What is the ABAYUY crystal system?")
        )
        expanded = self.rag._domain_query_expansion("Say something about ABAYUY in gas storage")
        self.assertIn("interpenetration", expanded)
        self.assertIn("BET surface area", expanded)
        rescued = self.rag._rescue_property_evidence(
            "Say something about ABAYUY in gas storage",
            [
                {"text": "The synthesis used methanol.", "source_path": "ABAYUY.txt"},
                {
                    "text": "The potential voids are filled by a 5-fold interpenetrating architecture.",
                    "source_path": "ABAYUY.txt",
                },
            ],
        )
        self.assertEqual(len(rescued), 1)
        self.assertIn("potential voids", rescued[0]["text"])
        guarded = self.rag._indirect_gas_answer("ABAYUY", rescued[0], "en")
        self.assertIn("does not report gas-adsorption", guarded)
        self.assertIn("does not establish accessible porosity", guarded)
        self.assertNotIn("may", guarded.lower())

    def test_retrieval_falls_back_when_query_embedding_is_unavailable(self):
        document = self.root / "fallback.txt"
        document.write_text(
            "A zinc framework has a diamondoid topology and was characterized by diffraction.",
            encoding="utf-8",
        )
        self.rag.ingest_document(str(document))
        self.client.embeddings = _FailingEmbeddings()
        hits = self.rag.retrieve("diamondoid topology", top_k=1)
        self.assertEqual(len(hits), 1)
        self.assertIn("diamondoid", hits[0]["text"])

    def test_unknown_ccdc_does_not_borrow_another_materials_literature(self):
        document = self.root / "OTHERX.txt"
        document.write_text(
            "OTHERX was prepared using zinc nitrate and terephthalic acid at 120 °C.",
            encoding="utf-8",
        )
        self.rag.ingest_document(str(document))
        answer = self.rag.ask("What reagents synthesize ACEFUL?", entity_key="ACEFUL")
        self.assertIn("does not contain relevant evidence", answer)
        self.assertNotIn("120 °C", answer)

    def test_natural_questions_route_to_rag_without_prefix(self):
        system = ChemicalQuerySystem.__new__(ChemicalQuerySystem)
        system.knowledge_store = _RoutingStore()
        system.rag = _RoutingRAG()
        system.query_handler = _RoutingQueryHandler()
        system.ingredient_qa = _RoutingIngredientQA()
        system.active_rag_context = None

        direct = system.get_answer("What topology is reported for ABAYUY?")
        self.assertEqual(direct, "RAG:ABAYUY:What topology is reported for ABAYUY?")
        natural = system.get_answer("Say something about ABAYUY in gas storage")
        self.assertEqual(natural, "RAG:ABAYUY:Say something about ABAYUY in gas storage")
        follow_up = system.get_answer("What about its stability?")
        self.assertEqual(follow_up, "RAG:ABAYUY:What about its stability?")
        overview = system.get_answer("what about ABAYUY")
        self.assertEqual(overview, "OVERVIEW:ABAYUY:en")
        typo_overview = system.get_answer("tell me abou ABAYUY")
        self.assertEqual(typo_overview, "OVERVIEW:ABAYUY:en")

        system.active_rag_context = "ACEFUL"
        coordination = system.get_answer(
            "What role do Ag–π interactions involving aromatic rings play in the assembly?"
        )
        self.assertEqual(
            coordination,
            "RAG:ACEFUL:What role do Ag–π interactions involving aromatic rings play in the assembly?",
        )

        database = system.get_answer("Show materials with density above 2")
        self.assertEqual(database, "DATABASE:Show materials with density above 2")

        inventory = system.get_answer("I have cobalt nitrate and a ligand; which MOF could I make?")
        self.assertEqual(inventory,
                         "CASES:en:I have cobalt nitrate and a ligand; which MOF could I make?")
        unknown_code = system.get_answer("ACEFUL 是由什么合成的？")
        self.assertEqual(unknown_code, "RAG:ACEFUL:ACEFUL 是由什么合成的？")

        formatted = system._format_rag_suggestions(
            "ABAYUY",
            [{"question": "What topology is reported?", "reason": "The paper discusses it."}],
        )
        self.assertNotIn("rag ask", formatted.lower())


if __name__ == "__main__":
    unittest.main()
