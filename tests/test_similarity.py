import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from knowledge import KnowledgeStore, refresh_similarity_edges, recommend_cases, similar_cases
from knowledge.similarity import normalize_chemical
from knowledge.chemical_resolver import ChemicalResolver
from knowledge.pubchem_resolver import PubChemResolver, enrich_store, cached_resolutions
from knowledge.similarity import load_profiles, compare
from unittest.mock import patch
from ulanggraph.knowledge_viewer import _research_graph


class SimilarityTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = KnowledgeStore(str(Path(self.tempdir.name) / "knowledge.db"))

    def tearDown(self):
        self.tempdir.cleanup()

    def _mof(self, code, formula, ccdc, metal, linker, solvent, temp, time, chemical_name=""):
        mof = self.store.upsert_node(
            "MOF", code, code, {"Formula": formula, "Number": ccdc,
                                "Chemical_Name": chemical_name}
        )
        recipe = self.store.upsert_node(
            "SynthesisRecipe", code, f"Synthesis of {code}",
            {"temperature": {"raw": temp}, "time": {"raw": time},
             "raw_row": {"metal_source": metal, "organic_linkers": linker,
                         "solvents": solvent, "modulators": "N/A"}},
        )
        self.store.upsert_edge(mof, recipe, "HAS_SYNTHESIS")
        return mof

    def test_aliases_units_and_stale_edges(self):
        self.assertEqual(normalize_chemical("N,N-dimethylformamide"), "dimethylformamide")
        self._mof("AAA", "C8 H4 O4 Zn", 111, "Zn(NO3)2", "H2BDC", "DMF", "120 °C", "2 days", "catena-(terephthalato-zinc)")
        b = self._mof("BBB", "C8 H4 O4 Zn", 222, "Zn(NO3)2", "terephthalic acid", "N,N-dimethylformamide", "125 °C", "48 h", "catena-(terephthalato-zinc)")
        self._mof("CCC", "C4 H4 O6 Cu", 333, "CuCl2", "squaric acid", "water", "120 °C", "48 h")
        result = refresh_similarity_edges(self.store)
        self.assertEqual(result["chemical_edges"], 1)
        self.assertEqual(result["synthesis_edges"], 1)
        cases = similar_cases(self.store, "AAA")
        self.assertEqual([case["mof"] for case in cases], ["BBB"])
        self.assertEqual(cases[0]["time_difference_hours"], 0)
        self.assertIn("terephthalate family", cases[0]["shared"]["linkers"])
        self.assertEqual(recommend_cases(self.store, "AAA")["status"], "limited_cases")
        graph = _research_graph(self.store, "AAA", 10)
        self.assertTrue(any(edge["edge_type"] == "SYNTHESIS_SIMILAR_TO" for edge in graph["edges"]))
        self.assertTrue(any(node["label"] == "BBB" for node in graph["nodes"]))

        # A reimport can replace a recipe; derived edges must be rebuilt, not accumulated.
        self.store.delete_outgoing_edges(b, ["HAS_SYNTHESIS"])
        self.assertEqual(refresh_similarity_edges(self.store)["synthesis_edges"], 0)
        self.assertEqual(similar_cases(self.store, "AAA"), [])

    def test_ambiguous_bdc_and_learned_definitions(self):
        self.assertEqual(
            normalize_chemical("H2BDC", "linkers"),
            "benzene-dicarboxylate (position unspecified)",
        )
        self.assertEqual(
            normalize_chemical("BDC", "linkers", {"Chemical_Name": "bis(μ-isophthalato)-cobalt"}),
            "isophthalate family",
        )
        self.assertEqual(
            normalize_chemical("1,4-H2BDC", "linkers"), "terephthalate family"
        )
        resolver = ChemicalResolver.from_records([
            {"linkers": "2-Mercaptobenzimidazole (MBimH)"},
        ])
        self.assertEqual(
            resolver.normalize("MBimH", "linkers"),
            resolver.normalize("2-Mercaptobenzimidazole (MBimH)", "linkers"),
        )

    def test_pubchem_unique_identity_is_cached_and_used_for_similarity(self):
        self._mof("AAA", "C8 H4 O4 Zn", 111, "Zn(NO3)2", "H2BDC", "acetone", "120 °C", "48 h")
        self._mof("BBB", "C8 H4 O4 Zn", 222, "Zn(NO3)2", "H2BDC", "propan-2-one", "125 °C", "48 h")
        for code, solvent in (("AAA", "acetone"), ("BBB", "propan-2-one")):
            with self.store.connection() as conn:
                recipe_id = conn.execute(
                    "SELECT id FROM nodes WHERE node_type='SynthesisRecipe' AND label=?",
                    (f"Synthesis of {code}",),
                ).fetchone()[0]
            chemical_id = self.store.upsert_node("Chemical", solvent, solvent)
            self.store.upsert_edge(recipe_id, chemical_id, "USES_SOLVENT")

        class FakePubChem:
            def __init__(self):
                self.queries = []

            def resolve(self, query):
                self.queries.append(query)
                return {"query": query, "status": "resolved", "cid": 180,
                        "inchikey": "AAAAAAAAAAAAAA-BBBBBBBBBB-C", "title": "acetone",
                        "molecular_formula": "C3H6O", "candidates": [180]}

        fake = FakePubChem()
        result = enrich_store(self.store, client=fake)
        self.assertEqual(result["resolved"], 2)
        self.assertEqual(set(fake.queries), {"acetone", "propan-2-one"})
        self.assertEqual(enrich_store(self.store, client=fake)["queried"], 0)
        self.assertEqual(len(cached_resolutions(self.store)), 2)
        profiles = load_profiles(self.store)
        score = compare(profiles["AAA"], profiles["BBB"], "CHEMICALLY_SIMILAR_TO")
        self.assertIn("acetone", score["shared"]["solvents"])

    def test_pubchem_multiple_cids_are_not_auto_merged(self):
        client = PubChemResolver()
        with patch.object(client, "_get_json", return_value={"IdentifierList": {"CID": [7, 3]}}) as get:
            outcome = client.resolve("ambiguous ligand")
        self.assertEqual(outcome["status"], "ambiguous")
        self.assertEqual(outcome["candidates"], [3, 7])
        self.assertEqual(get.call_count, 1)

    def test_pubchem_two_step_lookup_requires_matching_cid_and_inchikey(self):
        client = PubChemResolver()
        with patch.object(client, "_get_json", side_effect=[
            {"IdentifierList": {"CID": [180]}},
            {"PropertyTable": {"Properties": [{"CID": 180, "InChIKey":
                "CSCPPACGZOOCGX-UHFFFAOYSA-N", "Title": "Acetone",
                "MolecularFormula": "C3H6O"}]}},
        ]) as get:
            outcome = client.resolve("acetone")
        self.assertEqual(outcome["status"], "resolved")
        self.assertEqual(outcome["cid"], 180)
        self.assertEqual(get.call_count, 2)

        with patch.object(client, "_get_json", side_effect=[
            {"IdentifierList": {"CID": [180]}},
            {"PropertyTable": {"Properties": [{"CID": 181, "InChIKey":
                "CSCPPACGZOOCGX-UHFFFAOYSA-N"}]}},
        ]):
            self.assertEqual(client.resolve("acetone")["status"], "unavailable")

    def test_pubchem_network_failure_is_visible_and_not_cached(self):
        self._mof("AAA", "C8 H4 O4 Zn", 111, "Zn(NO3)2", "H2BDC", "acetone", "120 °C", "48 h")
        recipe = next(row for row in self.store.graph_context("AAA")["nodes"]
                      if row["node_type"] == "SynthesisRecipe")
        chemical = self.store.upsert_node("Chemical", "acetone", "acetone")
        self.store.upsert_edge(recipe["id"], chemical, "USES_SOLVENT")

        class OfflinePubChem:
            def resolve(self, query):
                return {"query": query, "status": "unavailable",
                        "reason": "URLError: DNS lookup failed"}

        outcome = enrich_store(self.store, client=OfflinePubChem())
        self.assertEqual(outcome["queried"], 1)
        self.assertEqual(outcome["unavailable"], 1)
        self.assertTrue(outcome["stopped_early"])
        self.assertEqual(outcome["failed_queries"][0]["query"], "acetone")
        self.assertEqual(cached_resolutions(self.store), {})


if __name__ == "__main__":
    unittest.main()
