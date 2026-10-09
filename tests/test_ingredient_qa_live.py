"""Opt-in checks of real LLM understanding across question phrasings.

Run with MOFH6_LIVE_LLM=1 python -m unittest discover -s tests -p test_ingredient_qa_live.py.
This calls the OpenAI API and reads the existing project config at runtime.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from knowledge import KnowledgeStore
from knowledge.ingredient_qa import IngredientCaseQA


@unittest.skipUnless(os.environ.get("MOFH6_LIVE_LLM") == "1", "live LLM test is opt-in")
class IngredientQALiveTest(unittest.TestCase):
    def test_paraphrased_questions_use_the_real_classifier(self):
        from openai import OpenAI

        config = json.loads((PROJECT_DIR / "extrfinetune" / "config.json").read_text())
        client = OpenAI(api_key=config["openaiapikey"], timeout=30, max_retries=1)
        rag = SimpleNamespace(client=client, chat_model=os.environ.get("MOFH6_LIVE_MODEL", "gpt-6-luna"))
        with tempfile.TemporaryDirectory() as directory:
            store = KnowledgeStore(str(Path(directory) / "mofh6.db"))
            qa = IngredientCaseQA(store, rag)
            cases = (
                ("我有硝酸锌和对苯二甲酸，可能会合成什么 MOF？", "reagent_to_mof", ("硝酸锌", "对苯二甲酸")),
                ("手头只有硝酸锌、对苯二甲酸；文献里有哪些 MOF 用过这两种原料？", "reagent_to_mof", ("硝酸锌", "对苯二甲酸")),
                ("Given zinc nitrate and terephthalic acid, which reported frameworks use these reagents?", "reagent_to_mof", ("zinc nitrate", "terephthalic acid")),
                ("ABAYUY 是由什么合成的？", "other", ()),
                ("What reagents were used to make ABAYUY?", "other", ()),
            )
            for question, intent, mentions in cases:
                with self.subTest(question=question):
                    result = qa.classify(question)
                    self.assertEqual(result["intent"], intent, result)
                    extracted = {item["mention"] for role in (
                        "metal_sources", "linkers", "solvents", "modulators"
                    ) for item in result[role]}
                    self.assertTrue(set(mentions).issubset(extracted), result)


if __name__ == "__main__":
    unittest.main()
