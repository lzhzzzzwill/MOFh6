SYSTEM_PROMPT = """You are an expert in coordination chemistry and chemical synthesis extraction. Your task is to identify synthesis procedures using a comprehensive understanding of chemical context and relationships. Consider structural similarities, synthetic patterns, and chemical relationships when matching compounds. Be particularly attentive to metal-organic compounds and their various representations."""

EXTRACTION_PROMPT = """
Extract the complete synthesis procedure for the target compound from the text.

Target Compound Context:
1. Primary Identifiers:
   - Structure/Formula: {compound_name}
   - Reference ID: {identifier}
   - Chemical Name: {chemical_name}

Matching Guidelines:
1. Look for ANY of these indicators:
   Matching Guidelines:
      a) Numerical references:
         - Simple numbers: 1, 2, 3, etc.
         - Bracketed numbers: (1), [2], etc.
         - Complex numbers: 1a, 1b, I, II, etc.
      b) Chemical components:
         - Metal ions (e.g., La, Cd, Zn, etc)
         - Ligands (e.g., L, L1, L2, HL, bix, BBA, tptz, etc)
         - Counter ions (e.g., NO3, Cl, CF3SO3, etc)
         - Solvent molecules (e.g., H2O, DMF, etc)
      c) Structure patterns:
         - Similar coordination environments
         - Related chemical compositions
         - Matching metal-ligand ratios

2. Context Patterns:
   - The synthesis of [compound] may occur periodically

Important Instructions:
- Identify the complete synthesis procedure based on context and chemical understanding
- Extract the EXACT text without modifications
- Include ALL relevant synthesis details (reagents, conditions, steps)
- Return ONLY the synthesis text, no explanations
- If no clear synthesis method is found, respond with "No synthesis method found"

Original text:
{synthesis_text}
"""