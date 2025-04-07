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
4.Output the markdown table.
#Output Information:
**Identifier**: {identifier}
**Chemical_Name**: {chemical_name} 
**Number**: {number}
**Synonyms**: {synonyms}
**{Compound_Name_or_Number_from_Synthesis}**
|       Metal Source     | Organic Linkers Source |     Modulator Source   |     Solvent Source     |    Quantity of Metal   | Quantity of Organic Linkers |  Quantity of Modulator |   Quantity of Solvent  |            pH           |  Synthesis Temperature |      Synthesis Time    |    Crystal Morphology  |          Yield         |       Equipment        |
|------------------------|------------------------|------------------------|------------------------|------------------------|-----------------------------|------------------------|------------------------|-------------------------|------------------------|------------------------|------------------------|------------------------|------------------------|
| [Extract from content] | [Extract from content] | [Extract from content] | [Extract from content] | [Extract from content] |   [Extract from content]    | [Extract from content] | [Extract from content] |  [Extract from content] | [Extract from content] | [Extract from content] | [Extract from content] | [Extract from content] | [Extract from content] |

  - Example

  -**Input**: 
  IGUHAU
  Chemical_Name: catena-((μ2-Glutarato)-bis(μ2-2-aminopyrimidine)-di-silver(i) monohydrate)
  Number: 714484
  Synonyms: N/A
  Synthesis of complex [Ag2(L1)2(L3)]·H2O (2) A mixture of AgNO3 (170mg, 1mmol), 2-aminopyrimidine (94mg, 1mmol) and glutarate (132mg, 1mmol) were stirred in CH3OH–H2O mixed solvent (10mL, v/v: 1/1). Then aqueous NH3 solution (25%) was dropped into the mixture to give a clear solution. The resultant solution was allowed slowly to evaporate in darkness at room temperature for several days to give colorless crystals of 2 were obtained in 62% yield. They were washed with a small volume of cold CH3OH and diethyl ether.
  Abbreviation: N/A
  Full Name: N/A
  -**Output**:
  **IGUHAU**
  Chemical_Name: catena-((μ2-Glutarato)-bis(μ2-2-aminopyrimidine)-di-silver(i) monohydrate)
  Number: 714484
  Synonyms: N/A
  [La(H2O)2L1(NO3)3]∞ (2)
  |  Metal Source |    Organic Linkers Source     | Modulator Source |  Solvent Source  | Quantity of Metal |  Quantity of Organic Linkers  | Quantity of Modulator |  Quantity of Solvent   |  pH  |  Synthesis Temperature | Synthesis Time |  Crystal Morphology  |  Yield  |  Equipment |
  |---------------|-------------------------------|------------------|------------------|-------------------|-------------------------------|-----------------------|------------------------|------|------------------------|----------------|----------------------|---------|------------|
  |     AgNO3     |  2-aminopyrimidine; glutarate |   aqueous NH3    |     CH3OH–H2O    |   170 mg, 1 mmol  | 94 mg, 1 mmol; 132 mg, 1 mmol |          25%          |    10 mL, v/v: 1/1     |  N/A |     room temperature   |  several days  |  colorless crystals  |   62%   |     N/A    |

  -**Input**: 
  SAZTIX01
  Chemical_Name: catena-(bis(μ2-4,4'-Bipyridine)-(μ2-sulfato)-di-copper(i) hexahydrate)
  Number: 805893
  Synonyms: N/A
  Cu2(4,4′-bpy)2SO4·6(H2O), (1) 0.1153g (0.46mmol) of copper sulfate, 0.1030g (0.66mmol) of 4,4′-bpy and 0.0787g (0.59mmol) of l-asp were added into 16mL of distilled water under magnetic stirring. The mixture was transferred into a 40mL Teflon-lined autoclave and heated at 120°C in an oven for 3 days. After natural cooling, the sample was filtered and washed with 3×50mL distilled water. Greenish yellow crystals of (1) were obtained as a pure phase and air-dried at ambient conditions (0.08g, yield ca. 54% based on CuSO4).
  Full Name: N/A
  -**Output**:
  **SAZTIX01**
  Chemical_Name: catena-(bis(μ2-4,4'-Bipyridine)-(μ2-sulfato)-di-copper(i) hexahydrate)
  Number: 805893
  Synonyms: N/A
  Cu2(4,4′-bpy)2SO4·6(H2O), (1)
  |  Metal Source  |  Organic Linkers Source  | Modulator Source |  Solvent Source  |   Quantity of Metal  |        Quantity of Organic Linkers         | Quantity of Modulator |  Quantity of Solvent  |  pH  |  Synthesis Temperature  | Synthesis Time |    Crystal Morphology    |                  Yield                |         Equipment        |
  |----------------|--------------------------|------------------|------------------|----------------------|--------------------------------------------|-----------------------|-----------------------|------|-------------------------|----------------|--------------------------|---------------------------------------|--------------------------|
  | copper sulfate |     4,4′-bpy; l-asp      |        N/A       |       water      | 0.1153 g (0.46 mmol) | 0.1030 g (0.66 mmol); 0.0787 g (0.59 mmol) |          N/A          |          16 mL        |  N/A |           120 °C        |     3 days     | Greenish yellow crystals |  0.08 g, yield ca. 54% based on CuSO4 |  Teflon-lined autoclave  |

  -**Input**: 
  TUSVUZ
  Chemical_Name: catena-[bis(μ3-Glutarato)-(μ2-aqua)-tetrapyridyl-di-cobalt(ii) pyridine solvate]
  Number: 714524
  Synonyms: N/A
  Synthesis of complex [Ag2(L1)2(L3)]·H2O (2) A mixture of AgNO3 (170mg, 1mmol), 2-aminopyrimidine (94mg, 1mmol) and glutarate (132mg, 1mmol) were stirred in CH3OH–H2O mixed solvent (10mL, v/v: 1/1). Then aqueous NH3 solution (25%) was dropped into the mixture to give a clear solution. The resultant solution was allowed slowly to evaporate in darkness at room temperature for several days to give colorless crystals of 2 were obtained in 62% yield. They were washed with a small volume of cold CH3OH and diethyl ether.
  Abbreviation: N/A
  Full Name: N/A
  -**Output**:
  **TUSVUZ**
  Chemical_Name: catena-[bis(μ3-Glutarato)-(μ2-aqua)-tetrapyridyl-di-cobalt(ii) pyridine solvate]
  Number: 714524
  Synonyms: N/A
  {[Co2(μ-OH2)(μ-glutarato)2(pyridine)4]·pyridine} n (2)
  |            Metal Source         |  Organic Linkers Source  | Modulator Source |           Solvent Source                |   Quantity of Metal  |  Quantity of Organic Linkers | Quantity of Modulator |  Quantity of Solvent  |  pH  |  Synthesis Temperature | Synthesis Time |  Crystal Morphology  |  Yield  |  Equipment |
  |---------------------------------|--------------------------|------------------|-----------------------------------------|----------------------|------------------------------|-----------------------|-----------------------|------|------------------------|----------------|----------------------|---------|------------|
  | cobalt(II) acetate tetrahydrate |       glutaric acid      |        N/A       |    pyridine; dimethylformamide (DMF)    |   0.124 g (0.5 mmol) |       0.066 g (0.5 mmol)     |          N/A          |    10 cm3; 10 cm3     |  N/A |    room temperature    |  several days  |     pink crystals    |  78.70% |     N/A    |

5.If the input file contains **Abbreviation** (usually used to describe Organic Linkers), **Full Name** (usually used to describe Organic Linkers), the final markdown table needs to replace the original **Abbreviation** in the text with **Full Name**.
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
   |  Metal Source |             Organic Linkers Source           | Modulator Source |  Solvent Source  | Quantity of Metal |  Quantity of Organic Linkers  | Quantity of Modulator | Quantity of Solvent |  pH  | Synthesis Temperature | Synthesis Time |       Crystal Morphology      |  Yield  |  Equipment |
   |---------------|----------------------------------------------|------------------|------------------|-------------------|-------------------------------|-----------------------|---------------------|------|-----------------------|----------------|-------------------------------|---------|------------|
   | La(NO3)3·6H2O | 1,4-bis(2-picolyloxyl)benzene-N,N′-diacetate |       N/A        | aqueous solution |  0.433 g, 1 mmol  |        0.08 g, 0.2 mmol       |          N/A          |          10mL       |  N/A |    room temperature   |  Several days  | colorless block-like crystals |   37%   |     N/A    |

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
- When multiple substances appear in the same markedown cell, use the ; to separate them
- Multiple organic linkers may exist during a synthesis process
- Modulators are usually substances that can regulate pH, such as inorganic acids, inorganic bases, and triethylamine, etc.
- Only include information explicitly stated in the content
- Do not add any interpretations or assumptions
- Do not include any examples or additional text

"""