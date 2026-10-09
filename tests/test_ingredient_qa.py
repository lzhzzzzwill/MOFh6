import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from knowledge import KnowledgeStore
from knowledge.ingredient_qa import IngredientCaseQA, _present
from knowledge.pubchem_resolver import cache_resolution, cached_resolutions


class _FakeCompletions:
    def __init__(self):
        self.calls = []
        self.responses = []

    def queue_response(self, intent, **roles):
        self.responses.append(json.dumps({
            "intent": intent,
            **{role: roles.get(role, []) for role in (
                "metal_sources", "linkers", "solvents", "modulators"
            )},
        }))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses.pop(0) if self.responses else json.dumps({
            "intent": "reagent_to_mof",
            "metal_sources": [{"mention": "Co(NO3)2·6H2O",
                               "search_name": "cobalt(II) nitrate hexahydrate"}],
            "linkers": [{"mention": "2-mercaptobenzimidazole",
                         "search_name": "2-mercapto-1H-benzimidazole"}],
            "solvents": [{"mention": "propan-2-one", "search_name": "propan-2-one"}],
            "modulators": [], "metals": ["Co"],
        })
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class _FakeRAG:
    chat_model = "gpt-6-luna"

    def __init__(self):
        self.client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions()))
        self.calls = []

    def retrieve(self, query, top_k=2, document_ids=None):
        self.calls.append((query, list(document_ids or [])))
        return [{"source_path": "/papers/COCASE.txt", "score": .8,
                 "text": "COCASE was synthesized from cobalt nitrate and a ligand."}]


class _FakePubChem:
    def __init__(self):
        self.queries = []

    def resolve(self, query):
        self.queries.append(query)
        if query == "propan-2-one":
            return {"query": query, "status": "resolved", "cid": 180,
                    "inchikey": "CSCPPACGZOOCGX-UHFFFAOYSA-N", "title": "Acetone",
                    "molecular_formula": "C3H6O", "candidates": [180]}
        return {"query": query, "status": "not_found", "candidates": []}


class IngredientQATest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = KnowledgeStore(str(Path(self.tempdir.name) / "mofh6.db"))
        self.rag = _FakeRAG()
        self.pubchem = _FakePubChem()

    def tearDown(self):
        self.tempdir.cleanup()

    def _case(self, code, metal, linker, solvent, formula, document=True):
        mof = self.store.upsert_node("MOF", code, code, {"Formula": formula, "Number": code})
        recipe = self.store.upsert_node(
            "SynthesisRecipe", code, f"Synthesis of {code}",
            {"temperature": {"raw": "120 °C"}, "time": {"raw": "24 h"},
             "raw_row": {"metal_source": metal, "organic_linkers": linker,
                         "solvents": solvent, "modulators": "N/A"}},
        )
        self.store.upsert_edge(mof, recipe, "HAS_SYNTHESIS")
        for role, value in (("USES_METAL_SOURCE", metal), ("USES_LINKER", linker),
                            ("USES_SOLVENT", solvent)):
            chemical = self.store.upsert_node("Chemical", value, value)
            self.store.upsert_edge(recipe, chemical, role)
        if document:
            path = Path(self.tempdir.name) / f"{code}.txt"
            self.store.upsert_document(str(path), f"Synthesis of {code}", title=f"{code} paper")

    def test_inventory_question_joins_graph_pubchem_and_candidate_scoped_retrieval(self):
        self._case("COCASE", "Co(NO3)2·6H2O", "2-mercaptobenzimidazole", "acetone", "C12H10CoN2O4")
        self._case("CUCASE", "CuCl2", "terephthalic acid", "water", "C8H4CuO4")
        cache_resolution(self.store, {"query": "acetone", "status": "resolved", "cid": 180,
                                      "inchikey": "CSCPPACGZOOCGX-UHFFFAOYSA-N",
                                      "title": "Acetone", "molecular_formula": "C3H6O"})
        qa = IngredientCaseQA(self.store, self.rag, self.pubchem)
        question = ("I have Co(NO3)2·6H2O and 2-mercaptobenzimidazole in "
                    "propan-2-one; which MOF could I make?")
        classified = qa.classify(question)
        self.assertEqual(classified["intent"], "reagent_to_mof")
        answer = qa.answer(question, extracted=classified)
        self.assertEqual(len(self.rag.client.chat.completions.calls), 1)
        self.assertIn("COCASE", answer)
        self.assertNotIn("CUCASE", answer)
        self.assertIn("Source: COCASE.txt", answer)
        self.assertIn("not the probability", answer)
        self.assertIn("propan-2-one", self.pubchem.queries)
        self.assertEqual(cached_resolutions(self.store)["propan-2-one"]["inchikey"],
                         "CSCPPACGZOOCGX-UHFFFAOYSA-N")
        self.assertEqual(len(self.rag.calls), 1)
        with self.store.connection() as conn:
            target_id = conn.execute("SELECT id FROM documents WHERE source_path LIKE '%COCASE.txt'").fetchone()[0]
        self.assertEqual(self.rag.calls[0][1], [target_id])

    def test_no_match_abstains_instead_of_predicting_a_product(self):
        self._case("CUCASE", "CuCl2", "terephthalic acid", "water", "C8H4CuO4")
        qa = IngredientCaseQA(self.store, self.rag, self.pubchem)
        question = "I have Co(NO3)2·6H2O and 2-mercaptobenzimidazole; which MOF could I make?"
        answer = qa.answer(question)
        self.assertIn("no reported MOF case", answer)
        self.assertNotIn("CUCASE", answer)
        self.assertFalse(self.rag.calls)

    def test_literal_formula_and_acronym_survive_model_name_expansion(self):
        self._case("ADAXEK", "Co(NO3)2·6H2O", "BPNO", "methanol", "C26H16Co2N2O10")
        qa = IngredientCaseQA(self.store, self.rag, self.pubchem)
        answer = qa.answer("I have Co(NO3)2·6H2O and BPNO; which MOF could I make?")
        self.assertIn("ADAXEK", answer)
        self.assertIn("reagent match 1.00", answer)

    def test_chinese_inventory_intent(self):
        # These responses simulate model decisions; this unit test checks routing
        # and prompt forwarding, not the model's language understanding.
        completions = self.rag.client.chat.completions
        completions.queue_response("reagent_to_mof")
        completions.queue_response("other")
        qa = IngredientCaseQA(self.store, self.rag, self.pubchem)
        inventory_question = "我有硝酸锌和对苯二甲酸，可能会合成什么 MOF？"
        named_mof_question = "ABAYUY 是由什么合成的？"
        self.assertEqual(
            qa.classify(inventory_question)["intent"],
            "reagent_to_mof",
        )
        self.assertEqual(qa.classify(named_mof_question)["intent"], "other")
        self.assertEqual([call["messages"][-1] for call in completions.calls], [
            {"role": "user", "content": inventory_question},
            {"role": "user", "content": named_mof_question},
        ])
        self.assertFalse(_present("H2O", "I have Co(NO3)2·6H2O."))
        self.assertTrue(_present("H2O", "I have Co(NO3)2·6H2O and H2O."))

    def test_classifier_failure_keeps_non_case_route_available(self):
        class _Unavailable:
            def create(self, **kwargs):
                raise ConnectionError("test outage")

        self.rag.client.chat.completions = _Unavailable()
        qa = IngredientCaseQA(self.store, self.rag, self.pubchem)
        classified = qa.classify("I have Co(NO3)2·6H2O and BPNO; which MOF could I make?")
        self.assertEqual(classified["intent"], "other")
        self.assertTrue(all(not classified[role] for role in (
            "metal_sources", "linkers", "solvents", "modulators"
        )))


if __name__ == "__main__":
    unittest.main()
