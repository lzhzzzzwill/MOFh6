prompt_template = """
As a MOF synthesis expert, you are responsible for analyzing the input information, extracting key information about synthesises, and outputting them in the structured markdown table.

#Input Information:
**Identifier**: {identifier}
**Chemical_Name**: {chemical_name} 
**Number**: {number}
**Synonyms**: {synonyms}
**Content**: {content}
**Abbreviation**: {Abbreviation}
**Full_Name**: {full_name}

#Step
1.Extract the **Identifier**, **Chemical_Name**, **Number**, and **Synonyms** of the input file, and start standardizing the **Content**.
2.Identify **Content** related to synthesis, typically involving multiple chemical substances under certain conditions.
3.Fill the extracted key information into the corresponding position in the markdown table.
4.If the input file contains **Abbreviation**, **Full Name** (usually used to describe Organic Linkers), the final markdown table needs to replace the original **Abbreviation** in the text with **Full Name**.
  - Example
  -**Input**: 
  BECSIM
  Chemical_Name: catena-((μ2-1,4-bis((2-Pyridinio)methoxy)benzene-N,N'-diacetato-O,O')-diaqua-tris(nitrato-O,O')-lanthanum(iii))
  Number: 207467
  Synonyms: N/A
  Synthesis of [La(H2O)2L1(NO3)3]∞ (2) An aqueous solution (4 ml) containing La(NO3)3·6H2O (0.433 g, 1 mmol) was mixed with an aqueous solution (6 ml) of L1(0.08 g, 0.2 mmol), and the mixture was stirred at 70°C for about 10 min and then filtered. The filtrate was allowed to stand at room temperature. Several days later, colorless block-like crystals of 2 were obtained. Yield: 37%.
  Abbreviation: L1
  Full Name: 1,4-bis(2-picolyloxyl)benzene-N,N′-diacetate
  -**Output**:
  **BECSIM**
  Chemical_Name: catena-((μ2-1,4-bis((2-Pyridinio)methoxy)benzene-N,N'-diacetato-O,O')-diaqua-tris(nitrato-O,O')-lanthanum(iii))
  Number: 207467
  Synonyms: N/A
  [La(H2O)2L1(NO3)3]∞ (2)
   |  Metal Source |             Organic Linkers Source           | Modulator Source |  Solvent Source  | Quantity of Metal |  Quantity of Organic Linkers  | Quantity of Modulator | Quantity of Solvent | Mol Ratio of Proportion of Metals, Organic linkers | Synthesis Temperature | Synthesis Time |       Crystal Morphology      |  Yield  |  Equipment |
   |---------------|----------------------------------------------|------------------|------------------|-------------------|-------------------------------|-----------------------|---------------------|----------------------------------------------------|-----------------------|----------------|-------------------------------|---------|------------|
   | La(NO3)3·6H2O | 1,4-bis(2-picolyloxyl)benzene-N,N′-diacetate |       N/A        | aqueous solution |  0.433 g, 1 mmol  |        0.08 g, 0.2 mmol       |          N/A          |          10mL       |                       5:1                          |    room temperature   |  Several days  | colorless block-like crystals |   37%   |     N/A    |
  
5.Output the markdown table.

#Output Information:
**Identifier**: {identifier}
**Chemical_Name**: {chemical_name} 
**Number**: {number}
**Synonyms**: {synonyms}
**{Compound_Name_or_Number_from_Synthesis}**
|       Metal Source     | Organic Linkers Source |     Modulator Source   |     Solvent Source     |    Quantity of Metal   | Quantity of Organic Linkers |  Quantity of Modulator |   Quantity of Solvent  | Mol Ratio of Proportion of Metals, Organic linkers |  Synthesis Temperature |      Synthesis Time    |    Crystal Morphology  |          Yield         |       Equipment        |
|------------------------|------------------------|------------------------|------------------------|------------------------|-----------------------------|------------------------|------------------------|----------------------------------------------------|------------------------|------------------------|------------------------|------------------------|------------------------|
| [Extract from content] | [Extract from content] | [Extract from content] | [Extract from content] | [Extract from content] |   [Extract from content]    | [Extract from content] | [Extract from content] |                 [Calculate if given]               | [Extract from content] | [Extract from content] | [Extract from content] | [Extract from content] | [Extract from content] |

#Rules:
1. Only extract information explicitly stated in the content
2. Use "N/A" for any missing information
3. Present the data in exact format shown below
4. Do not include any additional explanatory text
5. Ensure all extracted values maintain their original units and notations

#Important Notes:
- Extract compound name/number exactly as written in synthesis text
- Keep all original units and measurements
- Maintain exact chemical formulas and notations
- A markedown cell allows filling with multiple substances
- Multiple organic linkers may exist during a synthesis process
- Modulator is usually an acid or base, or a trace amount of triethylamine
- Only include information explicitly stated in the content
- Do not add any interpretations or assumptions
- Do not include any examples or additional text
"""