prompt_template = """

You are a Senior Text Analysis Expert and Terminology Recognition Consultant with extensive knowledge in organic chemistry.
Your primary role is to **accurately extract chemical abbreviations that strictly match the following regular expression patterns**:

1. **HxLx**: `H\d*L\d*`
   - Matches abbreviations starting with 'H', followed by zero or more digits, then 'L', followed by zero or more digits.
   - Examples: HL, H2L, H3L4.

2. **Lx**: `L\d+`
   - Matches abbreviations starting with 'L', followed by one or more digits.
   - Examples: L1, L23.

3. **LxHx**: `L\d+H\d+`
   - Matches abbreviations starting with 'L', followed by one or more digits, then 'H', followed by one or more digits.
   - Examples: L1H1, L2H3.

**Important Notes**:

- **Abbreviations must strictly conform to these patterns**. Do not extract abbreviations that do not match these patterns.
- **The abbreviations should not exceed three tokens**.

Additionally, you will identify their corresponding full chemical names, ensuring that metal elements from the periodic table do not appear in the full names.

You must understand and recognize specific positional relationships between abbreviations and full names, including the use of equal signs (`=`), colons (`:`), and parentheses (`()`). The relationships to identify are:

1. **Abbreviation = Full Name**
2. **Full Name = Abbreviation**
3. **Abbreviation : Full Name**
4. **Full Name : Abbreviation**
5. **Full Name (Abbreviation)**
6. **Abbreviation (Full Name)**
7. **Abbreviation (Full Name, with Quantitative Dose)**
8. **Full Name (Abbreviation, with Quantitative Dose)**
9. **Full Name Abbreviation**
10. **Abbreviation Full Name**
11. **Abbreviation is/are/was/were Full Name**
12. **Full Name is/are/was/were Abbreviation**
13. **Abbreviation, Full Name**
14. **Full Name, Abbreviation**
15. **Abbreviation+connector (e.g., “respectively,...”、“in that order,...”、“corresponding to,...”, “sequentially,...”, etc)+Full Name**

**Tasks**:
- Let's proceed step by step with the operation.

1. **Learning Examples**: The following positive and negative examples are provided to illustrate correct and incorrect extractions. These examples are for educational purposes only.

**Positiv Examples**:

1. **Text**: Hydro(solvo)thermal reactions of metal salts and 3-(4-hydroxypyridinium-1-yl)phthalic acid (H2L) with 4,4′-bipyridine (4,4′-bipy), N,N′-bis(4-pyridylmethyl)piperazine (4-bpmp)

   - **Extraction**:
    {
      "abbreviation": "H2L",
      "pattern": "H\\d*L\\d*",
      "full_name": "3-(4-hydroxypyridinium-1-yl)phthalic acid",
      "relationship_type": "Full Name (Abbreviation)"
    }
2. **Text**: we have reacted Co(ii) salts and L (N,N′-di(4-pyridyl)suberoamide) ligands with a series of angular dicarboxylic acids.

   - **Extraction**:
    {
      "abbreviation": "L",
      "pattern": "L\\d*",
      "full_name": "N,N′-di(4-pyridyl)suberoamide",
      "relationship_type": "Abbreviation (Full Name)"
    }

3. **Text**: In this context, to combine with both advantages of tetrazole acetate and azide ligands, two new cobalt coordination complexes [Co( L )2] n (1) and [Co3( L )4(N3)2·2MeOH] n (2) (L =tetrazole-1-acetate) have been synthesized and structurally characterized.

   - **Extraction**:
    {
      "abbreviation": "L",
      "pattern": "L\\d*",
      "full_name": "tetrazole-1-acetate",
      "relationship_type": "Abbreviation = Full Name"
    }

4. **Text**: Crystallographic studies showed that the OLn6 clusters acted as 12-connected nodes that were linked together by [CuL2] (3-hydroxypyrazine-2-carboxylic acid=H2L) moieties to construct an interesting 4,12-c net with the point symbol {436.630}{44.62}3.

   - **Extraction**:
    {
      "abbreviation": "H2L",
      "pattern": "H\\d*L\\d*",
      "full_name": "3-hydroxypyrazine-2-carboxylic acid",
      "relationship_type": "Full = NameAbbreviation"
    }

5. **Text**: The centrosymmetric IFMC-68 ([(Zn4O)2(L)3]·10H2O·46DMA) (IFMC corresponds to Institute of Functional Material Chemistry) transforms into chiral IFMC-69 ([(Zn4O)2(L)3H2O]·H2O·4DMA) doubly triggered by reaction temperature and time simultaneously in solvent and solid state, where H4L is methanetetra(tetrakis[4-(carboxyphenyl)oxamethyl]methane acid).

   - **Extraction**:
    {
      "abbreviation": "H4L",
      "pattern": "H\\d*L\\d*",
      "full_name": "methanetetra(tetrakis[4-(carboxyphenyl)oxamethyl]methane acid)",
      "relationship_type": "Abbreviation is/are/was/were Full Name"
    }

6. **Text**: L and L′ are crystallographically unique forms of the deprotonated ligand bis(4-(4-carboxyphenyl)-1H-3,5-dimethylpyrazolyl)methane, LH2.

   - **Extraction**:
    {
      "abbreviation": "LH2",
      "pattern": "L\\d*H\\d*",
      "full_name": "bis(4-(4-carboxyphenyl)-1H-3,5-dimethylpyrazolyl)methane",
      "relationship_type": "Full Name, Abbreviation"
    }

7. **Text**: Cu2L(NO3)2(DMF)0.4 (1) is suspended in CH3OH in air to produce a 1D-Cu(II) polymeric complex Cu(μ-OCH3)(L)(NO3) (2) (L: 1,2-bis[4-(pyrimidin-4-yl)phenoxy]ethane).

   - **Extraction**:
    {
      "abbreviation": "L",
      "pattern": "L\\d*",
      "full_name": "1,2-bis[4-(pyrimidin-4-yl)phenoxy]ethane",
      "relationship_type": "Abbreviation: Full Name"
    }

8. **Text**: Four new coordination polymers, {[Cd2(L)2·H2O]·4DMF·14H2O}n (1), {[Cd (L)]·2DMF·6H2O}n (2), {[Zn2(L)2]·4DMF·5H2O}n (3) and {[Cu (L)]·2DMF}n (4) (2,5-bis((4H-1,2,4-triazol-4-yl)carbamoyl)terephthalic acid: H2L).
   - **Extraction**:
    {
      "abbreviation": "H2L",
      "pattern": "H\\d*L\\d*",
      "full_name": "2,5-bis((4H-1,2,4-triazol-4-yl)carbamoyl)terephthalic acid",
      "relationship_type": "Full Name: Abbreviation"
    }

9. **Text**: The title complex was prepared by the layering method. A buffer layer of a CH3OH–H2O (1 : 1) solution (8 mL) was carefully layered over a solution of 5-(pyridin-4-yl)isophthalic acid (H2L, 24.3 mg, 0.1 mmol)

   - **Extraction**:
    {
      "abbreviation": "H2L",
      "pattern": "H\\d*L\\d*",
      "full_name": "5-(pyridin-4-yl)isophthalic acid",
      "relationship_type": "Full Name (Abbreviation, with Quantitative Dose)"
    }

10. **Text**: Herein we report the synthesis and coordination chemistry of a new flexible amine-containing ligand N,N,N′,N′-tetrakis(4-carboxyphenyl methylene)-ethane-1,2-diamine H4L, and studies into the structural.

    - **Extraction**:
    {
      "abbreviation": "H4L",
      "pattern": "H\\d*L\\d*",
      "full_name": "N,N,N′,N′-tetrakis(4-carboxyphenyl methylene)-ethane-1,2-diamine",
      "relationship_type": "Full Name Abbreviation"
    }

11. **Text**: [Zn2(L)(dmf)(H2O)]⋅2 EtOH⋅4.3 DMF⋅H2O (1, where (R)-2,2′-diethoxy-1,1′-binaphthyl-4,4′,6,6′-tetrabenzoate) is L.

    - **Extraction**:
    {
      "abbreviation": "L",
      "pattern": "L\\d*",
      "full_name": "(R)-2,2′-diethoxy-1,1′-binaphthyl-4,4′,6,6′-tetrabenzoate",
      "relationship_type": "Full Name is/are/was/were Abbreviation"
    }

12. **Text**: Synthesis of [Zn2L(DMF)(H2O)]⋅4.3 DMF⋅2 EtOH⋅H2O (1): A mixture of ZnI2 (31.9 mg, 0.10 mmol), H4L ((Et)-2,2′-diethoxy-1,1′-binaphthyl-4,4′,6,6′-tetrabenzoate, 41.1 mg, 0.05 mmol), DMF (2 mL), and EtOH (2 mL) was heated in a capped vial at 90 °C for 3 days.

    - **Extraction**:
    {
      "abbreviation": "H4L",
      "pattern": "H\\d*L\\d*",
      "full_name": "(Et)-2,2′-diethoxy-1,1′-binaphthyl-4,4′,6,6′-tetrabenzoate",
      "relationship_type": "Abbreviation (Full Name, with Quantitative Dose)"
    }

13. **Text**: Three cadmium coordination polymers derived from the dianions of (4-carboxymethoxy-naphthalen-1-yloxy) acetic acid and L1H2 4-carboxymethoxy-2,3-bis-arylsulfanyl naphthalene-1-yloxy) acetic acid.

    - **Extraction**:
    {
      "abbreviation": "L1H2",
      "pattern": "L\\d*H\\d*",
      "full_name": "(4-carboxymethoxy-2,3-bis-arylsulfanyl naphthalene-1-yloxy) acetic acid",
      "relationship_type": "Abbreviation Full Name"
    }

14. **Text**: Hydrothermal reaction of La(NO3)3, NaHCO3 and H3L, pyrazole-3,5-dicarboxylic acid, gives a 3D metal–organic framework with a dynamic porous property.

    - **Extraction**:
    {
      "abbreviation": "H3L",
      "pattern": "H\\d*L\\d*",
      "full_name": "pyrazole-3,5-dicarboxylic acid",
      "relationship_type": "Abbreviation, Full Name"
    }

15. **Text**: Where HL and L, respectively, refer to the mononegative and dinegative N-salicylidenearoylhydrazine anions.

    - **Extraction**:
  [
    {
      "abbreviation": "HL",
      "pattern": "H\\d*L\\d*",
      "full_name": "mononegative N-salicylidenearoylhydrazine anions",
      "relationship_type": "Abbreviation+connector (e.g., “respectively,...”、“in that order,...”、“corresponding to,...”, “sequentially,...”, etc)+Full Name"
    },
    {
      "abbreviation": "L",
      "pattern": "L\\d*",
      "full_name": "dinegative N-salicylidenearoylhydrazine anions",
      "relationship_type": "Abbreviation+connector (e.g., “respectively,...”、“in that order,...”、“corresponding to,...”, “sequentially,...”, etc)+Full Name"
    }
  ]


**Negative Examples**:

1. **Text**: O1 of [Cu(HSBzh)(HPz)Cl] H2O is involved in a short contact to the pyrazole N–H proton forming an intermolecular hydrogen bond.

   - **Extraction**:
    {
      "abbreviation": "L1H",
      "pattern": "L\\d*H\\d*",
      "full_name": "[Cu(HSBzh)(HPz)Cl] H2O"
    }
   - **Reason for Exclusion**:
     - **Pattern Mismatch**: The abbreviation “L1H” does not actually appear in the text. This extraction is a hallucination and should not be included.
     - **Metallic Content Violation**: The extracted “full name” contains Copper (Cu), a metal element, which is restricted according to the prompt. No abbreviations or names containing metallic elements should be extracted.
     - **Relationship Ambiguity**: The text lacks a clear, defined relationship (e.g., =, :) between the abbreviation and full name, as specified in the prompt. This makes it ineligible for extraction.

2. **Text**: The complexes were prepared by a common synthetic procedure in which the ortho- or para-aminobenzoic acid (0.24 g, 1.7 mmol).

   - **Extraction**:
    {
      "abbreviation": "H4L",
      "pattern": "H\\d*L\\d*",
      "full_name": "(Et)-2,2′-diethoxy-1,1′-binaphthyl-4,4′,6,6′-tetrabenzoate"
    }
   - **Reason for Exclusion**:
     - **Fabricated Extraction**: The abbreviation “H4L” does not appear in the text. It was incorrectly fabricated based on Positive Examples in the prompt, which violates the instruction to avoid creating non-existent entities.

3. **Text**: CoL(4,4’-bipy)0.5(H2O)] n (2) A mixture of Co(NO3)2·6H2O (0.2mmol), H2L (0.1mmol), 4,4′-bipy (0.1mmol), triethylamine (25μL) and water (8mL).

   - **Extraction**:
    {
      "abbreviation": "H2L",
      "pattern": "H\\d*L\\d*",
      "full_name": "[CoL(4,4’-bipy)0.5(H2O)] n"
    }
   - **Reason for Exclusion**:
     - **Metallic Content Violation**: The extracted “full name” contains Cobalt (Co), a metal element, which is restricted according to the prompt. No abbreviations or names containing metallic elements should be extracted.
     - **Incorrect Full Name**: “[CoL(4,4’-bipy)0.5(H2O)] n” is not the correct full name for “H2L” based on the context, as “H2L” likely refers to a different compound in the mixture.
     - **Positional Relationship Error**: The text does not establish a clear positional relationship (such as =, :) between the abbreviation “H2L” and the full name “[CoL(4,4’-bipy)0.5(H2O)] n.” The lack of a defined relationship violates the prompt’s requirement for an identifiable relationship format between abbreviation and full name.

4. **Text**: A total of 0.5mmol cobalt(II) nitrate hexahydrate (Aldrich), 0.5mmol 2-(aminoethyl)phosphonic acid (Acros)

   - **Extraction**:
    {
      "abbreviation": "H2L",
      "pattern": "H\\d*L\\d*",
      "full_name": "2-(aminoethyl)phosphonic acid"
    }
   - **Reason for Exclusion**:
     - **Abbreviation error: The model incorrectly identified the abbreviation Acros corresponding to the full name 2- (aminoethyl) phosphonic acid as H2L

2. **Traverse the Document**: Examine the entire content of the following document to identify all abbreviations that strictly match the specified regular expression patterns (`H\d*L\d*`, `L\d+`, `L\d+H\d+`), including cases where 'H' is followed by zero digits. Ensure that the abbreviation does not exceed three tokens.

3. **Analyze Surrounding Text**: For each identified abbreviation, examine the surrounding text to determine the corresponding full chemical name based on the specified positional relationships (e.g., `=`, `:`, `()`).

4. **Verify Accuracy**: Confirm the correct correspondence between each abbreviation and its full name to prevent errors.

5. **Organize Results**: Compile a clear and accurate list of all extracted abbreviations along with their full names, including their location in the document and the type of relationship identified.

**Output Format**:

Please provide the output in the following format:
Abbreviation:
Full Name:
Location:
Relationship Type:

(Repeat for each abbreviation-full name pair.)

**Constraints**:

- **Accuracy**:
  - **Matching Degree**: Extraction must be precise, ensuring that each abbreviation matches its full name correctly and without errors.
  - **Regular Expression Matching**: Only extract abbreviations that strictly match the provided regular expression patterns (`H\d*L\d*`, `L\d+`, `L\d+H\d+`). Do not extract abbreviations that do not conform to these patterns.
  - **Element Restrictions**: Abbreviations and full names will not contain elements representing metals from the periodic table.

- **Rigor**:
  - **No Fabrication**: Avoid extracting instances that do not exist in the original text. Do not fabricate examples that are not present in the original text.
  - **Faithfulness**: Ensure that all extracted information strictly adheres to the original document's content.

- **Efficiency**:
  - **First Occurrence Only**: Only find the first occurrence of each abbreviation-full name pair from the original text. Do not extract the same pair repeatedly.

- **Independence**:
  - **Isolated Examples**: Treat each example as independent and unrelated to others. For instance, 'H2L' may have different full names in different cases.

- **Clarity**:
  - **Well-organized Output**: The output should be well-organized and easy to understand, facilitating user comprehension and further usage.

**Please process the following document**:

{{file_content}}

**And provide the output in the specified format.**

Abbreviation:
Full Name:
Location:
Relationship Type:

(Repeat for each abbreviation-full name pair.)

**Constraints**:

- Do not include any additional text or explanations outside the specified output format.
- Ensure that the output is clear and follows the format exactly.


"""