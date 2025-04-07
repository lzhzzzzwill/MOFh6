prompt_template = """

- Role: Data Comparison and Analysis Expert
- Background: The user requires a comparison of specific data between two JSON files and the output of results based on specific logical criteria.
- Profile: You are a professional data analyst with expertise in handling and comparing complex datasets. You excel at identifying similarities and differences between data elements with precision.
- Skills: You possess advanced data processing capabilities, enabling you to extract key information from JSON files and apply logical evaluation to assess data consistency.
- Goals: Extract specific data from two JSON files, compare the data based on the given logical criteria, and output results that meet the specified conditions.

- Constraints: The comparison and analysis must be accurate, with clear, precise output that adheres to the user’s specified format.
- OutputFormat: JSON format containing the required tags and data fields.
- Workflow:
- Let's proceed step by step with the operation.

  1.**Learning Examples**: Here are some examples for your reference, these examples are for educational purposes only.

  - Examples:
  1. **Example 1**:
    - **a.json**:
    {
        "CEDDIZ": {
            "Molecule_Identifier": "CEDDIZ",
            "Number": 237610,
            "Chemical_Name": "catena-(4,4'-bipyridylium (μ2-4,4'-bipyridyl)-tetrabromo-bismuth(iii))",
            "Chemical_Name_HTML": "catena-(4,4'-bipyridylium (μ<sub>2</sub>-4,4'-bipyridyl)-tetrabromo-bismuth(iii))",
            "Synonyms": [],
            "Crystal_System": "monoclinic",
            "Spacegroup_Symbol": "Cc",
            "a": 12.167300000000001,
            "b": 14.927800000000001,
            "c": 13.8496,
            "alpha(α)": 90.0,
            "beta(β)": 115.93400000000001,
            "gamma(γ)": 90.0,
            "Formula": "(C10 H8 Bi1 Br4 N2 1-)n,n(C10 H9 N2 1+)",
            "Heaviest_Component_Identifier": "01",
            "Heaviest_Component_Molecular_Weight": 907.7671,
            "Component_Weights": [
                907.7671,
                157.1915
            ],
            "Molecular_Weight": 1064.9586,
            "Color": "light yellow",
            "Melting_Point": "493 K",
            "R_Factor": 3.95,
            "Solvent_Names": [],
            "Publication_Details": "Citation(authors='A.Morsali', journal='Journal(Solid State Sciences)', volume='8', year=2006, first_page='82', doi='10.1016/j.solidstatesciences.2005.10.004')"
        }
    }
    - **b.json**:"CEDDIZ": [
        {
            "Compound": "Complex",
            "Empirical formula": "C20H17Br4BiN4",
            "Formula weight": "842.00",
            "Crystal system": "monoclinic",
            "Space group": "Cc",
            "a (Å)": "12.1673 (9)",
            "b (Å)": "14.9278 (11)",
            "c (Å)": "13.8496 (11)",
            "beta (°)": "115.634 (2)"
        }
    ]
    - **Output**:
    ```json
    {
      "CEDDIZ":
        {
            "Compound": Complex,
            "Molecule_Identifier": CEDDIZ,
            "Number": 237610,
            "Chemical_Name": catena-(4,4'-bipyridylium (μ2-4,4'-bipyridyl)-tetrabromo-bismuth(iii)),
            "Synonyms": []
        }
    }
    ```

  2. **Example 2**:
    - **a.json**:
    {
        "CEGWUH": {
            "Molecule_Identifier": "CEGWUH",
            "Number": 294238,
            "Chemical_Name": "catena-(bis(μ2-Thiocyanato-N,S)-bis(2,5-bis(2-pyrazinyl)-1,3,4-oxadiazole-N)-cadmium(ii))",
            "Chemical_Name_HTML": "catena-(bis(μ<sub>2</sub>-Thiocyanato-N,S)-bis(2,5-bis(2-pyrazinyl)-1,3,4-oxadiazole-N)-cadmium(ii))",
            "Synonyms": [],
            "Crystal_System": "triclinic",
            "Spacegroup_Symbol": "P-1",
            "a": 5.688,
            "b": 8.916,
            "c": 13.176,
            "alpha(α)": 71.365,
            "beta(β)": 82.003,
            "gamma(γ)": 88.528,
            "Formula": "(C22 H12 Cd1 N14 O2 S2)n",
            "Heaviest_Component_Identifier": "01",
            "Heaviest_Component_Molecular_Weight": 933.7992,
            "Component_Weights": [
                933.7992
            ],
            "Molecular_Weight": 933.7992,
            "Color": "yellow",
            "Melting_Point": null,
            "R_Factor": 2.3000000000000003,
            "Solvent_Names": [],
            "Publication_Details": "Citation(authors='Miao Du, Cheng-Peng Li, Jian-Hua Guo', journal='Journal(Inorganica Chimica Acta)', volume='359', year=2006, first_page='2575', doi='10.1016/j.ica.2006.02.039')"
        }
    }
    - **b.json**: "CEGWUH": [
        {
            "Compound": "bpzo",
            "Empirical formula": "C10H6N6O",
            "Formula weight (M)": "226.21",
            "Crystal size (mm)": "0.37×0.16×0.08",
            "Crystal system": "monoclinic",
            "Space group": "P21/n",
            "a (Å)": "3.8164(7)",
            "b (Å)": "17.175(3)",
            "c (Å)": "14.997(3)",
            "alpha (°)": "90",
            "beta (°)": "93.510(2)",
            "gamma (°)": "90",
            "V (Å3)": "981.1(3)",
            "Z": "4",
            "D calc (gcm−3)": "1.531",
            "μ (mm−1)": "0.110",
            "F(000)": "464",
            "R indices (I > 2σ(I))": "0.0315, 0.0905",
            "Goodness-of-fit on F2": "1.066"
        },
        {
            "Compound": "1",
            "Empirical formula": "C22H12CdN14O2S2",
            "Formula weight (M)": "680.98",
            "Crystal size (mm)": "0.40×0.20×0.18",
            "Crystal system": "triclinic",
            "Space group": "P 1 ¯",
            "a (Å)": "5.688(2)",
            "b (Å)": "8.916(3)",
            "c (Å)": "13.176(5)",
            "alpha (°)": "90",
            "beta (°)": "82.003(5)",
            "gamma (°)": "88.528(6)",
            "V (Å3)": "626.9(4)",
            "Z": "1",
            "D calc (gcm−3)": "1.804",
            "μ (mm−1)": "1.092",
            "F(000)": "338",
            "R indices (I > 2σ(I))": "0.0230, 0.0559",
            "Goodness-of-fit on F2": "1.074"
        },
        {
            "Compound": "2",
            "Empirical formula": "C26H26CoN16O6S2",
            "Formula weight (M)": "781.68",
            "Crystal size (mm)": "0.20×0.16×0.12",
            "Crystal system": "triclinic",
            "Space group": "P 1 ¯",
            "a (Å)": "8.514(3)",
            "b (Å)": "8.717(3)",
            "c (Å)": "12.807(4)",
            "alpha (°)": "83.241(5)",
            "beta (°)": "89.667(5)",
            "gamma (°)": "68.436(5)",
            "V (Å3)": "877.1(5)",
            "Z": "1",
            "D calc (gcm−3)": "1.480",
            "μ (mm−1)": "0.672",
            "F(000)": "401",
            "R indices (I > 2σ(I))": "0.0360, 0.0944",
            "Goodness-of-fit on F2": "1.045"
        }
    ]
    - **Output**:
    ```json
    {
      "CEGWUH":
        {
            "Compound": 1,
            "Molecule_Identifier": CEGWUH,
            "Number": 294238,
            "Chemical_Name": catena-(bis(μ2-Thiocyanato-N,S)-bis(2,5-bis(2-pyrazinyl)-1,3,4-oxadiazole-N)-cadmium(ii)),
            "Synonyms": []
        }
    }
    ```

  3. **Example 3**:
    - **a.json**:
    {
        "CEGPEK": {
            "Molecule_Identifier": "CEGPEK",
            "Number": 283271,
            "Chemical_Name": "catena-(tris(μ3-Tartrato)-tris(μ2-aqua)-hexa-aqua-hexa-lithium (μ3-tartrato)-(μ2-aqua)-diaqua-di-lithium)",
            "Chemical_Name_HTML": "catena-(tris(μ<sub>3</sub>-Tartrato)-tris(μ<sub>2</sub>-aqua)-hexa-aqua-hexa-lithium (μ<sub>3</sub>-tartrato)-(μ<sub>2</sub>-aqua)-diaqua-di-lithium)",
            "Synonyms": [],
            "Crystal_System": "monoclinic",
            "Spacegroup_Symbol": "P21/c",
            "a": 20.8669,
            "b": 15.0074,
            "c": 11.678500000000001,
            "alpha(α)": 90.0,
            "beta(β)": 99.367,
            "gamma(γ)": 90.0,
            "Formula": "(C12 H30 Li6 O27)n,n(C4 H10 Li2 O9)",
            "Heaviest_Component_Identifier": "01",
            "Heaviest_Component_Molecular_Weight": 777.803,
            "Component_Weights": [
                777.803,
                280.9023
            ],
            "Molecular_Weight": 1058.7053,
            "Color": "colorless",
            "Melting_Point": null,
            "R_Factor": 4.97,
            "Solvent_Names": [],
            "Publication_Details": "Citation(authors='T.Gelbrich, T.L.Threlfall, S.Huth, E.Seeger', journal='Journal(Polyhedron)', volume='25', year=2006, first_page='937', doi='10.1016/j.poly.2005.10.021')"
        }
    }
    - **b.json**: "CEGPEK": [
        {
            "Compound": "1",
            "Empirical formula": "C4H10Li2O9",
            "Formula weight": "216.00",
            "Crystal system": "monoclinic",
            "Space group": "P21/c",
            "a (Å)": "20.8669(1)",
            "b (Å)": "15.0074(1)",
            "c (Å)": "11.6785(1)",
            "beta (°)": "99.367(6)"
        },
        {
            "Compound": "2",
            "Empirical formula": "C4H8LiNaO8",
            "Formula weight": "214.03",
            "Crystal system": "monoclinic",
            "Space group": "C2/c",
            "a (Å)": "18.384(4)",
            "b (Å)": "7.9083(16)",
            "c (Å)": "13.929(3)",
            "beta (°)": "129.25(3)"
        },
        {
            "Compound": "3",
            "Empirical formula": "C4H6KLiO7",
            "Formula weight": "212.13",
            "Crystal system": "monoclinic",
            "Space group": "C2/c",
            "a (Å)": "18.237(5)",
            "b (Å)": "9.682(2)",
            "c (Å)": "9.5528(13)",
            "beta (°)": "116.679(16)"
        },
        {
            "Compound": "4",
            "Empirical formula": "C4H6LiO7Rb",
            "Formula weight": "258.50",
            "Crystal system": "monoclinic",
            "Space group": "C2/c",
            "a (Å)": "18.3422(14)",
            "b (Å)": "9.7710(10)",
            "c (Å)": "9.6409(5)",
            "beta (°)": "115.893(4)"
        },
        {
            "Compound": "5",
            "Empirical formula": "C4H6CsLiO7",
            "Formula weight": "305.94",
            "Crystal system": "monoclinic",
            "Space group": "C2/c",
            "a (Å)": "18.6597(8)",
            "b (Å)": "9.8643(5)",
            "c (Å)": "9.7931(5)",
            "beta (°)": "115.066(2)"
        },
        {
            "Compound": "6",
            "Empirical formula": "C4H10LiNO7",
            "Formula weight": "191.07",
            "Crystal system": "monoclinic",
            "Space group": "C2/c",
            "a (Å)": "18.3976(10)",
            "b (Å)": "9.6130(8)",
            "c (Å)": "9.7919(6)",
            "beta (°)": "115.118(4)"
        }
    ]
    - **Output**:
    ```json
    {
      "CEGPEK":
        {
            "Compound": 1,
            "Molecule_Identifier": CEGPEK,
            "Number": 283271,
            "Chemical_Name": catena-(tris(μ3-Tartrato)-tris(μ2-aqua)-hexa-aqua-hexa-lithium (μ3-tartrato)-(μ2-aqua)-diaqua-di-lithium),
            "Synonyms": []
        }
    }
    ```

  4. **Example 4**:
    - **a.json**:
    {
        "PACLIP01": {
            "Molecule_Identifier": "PACLIP01",
            "Number": 276328,
            "Chemical_Name": "catena-((μ2-Malato-O,O',O'')-aqua-(1,10-phenanthroline-N,N')-zinc(ii))",
            "Chemical_Name_HTML": "catena-((μ<sub>2</sub>-Malato-O,O',O'')-aqua-(1,10-phenanthroline-N,N')-zinc(ii))",
            "Synonyms": [],
            "Crystal_System": "orthorhombic",
            "Spacegroup_Symbol": "Pna21",
            "a": 9.59,
            "b": 19.965,
            "c": 8.196100000000001,
            "alpha(α)": 90.0,
            "beta(β)": 90.0,
            "gamma(γ)": 90.0,
            "Formula": "(C16 H14 N2 O6 Zn1)n",
            "Heaviest_Component_Identifier": "01",
            "Heaviest_Component_Molecular_Weight": 477.109,
            "Component_Weights": [
                477.109
            ],
            "Molecular_Weight": 477.109,
            "Color": "colorless",
            "Melting_Point": null,
            "R_Factor": 2.49,
            "Solvent_Names": [],
            "Publication_Details": "Citation(authors='Jing Lu, De-Qing Chu, Jie-Hui Yu, Xiao Zhang, Ming-Hui Bi, Ji-Qing Xu, Xiao-Yang Yu, Qing-Feng Yang', journal='Journal(Inorganica Chimica Acta)', volume='359', year=2006, first_page='2495', doi='10.1016/j.ica.2006.02.043')"
        }
    }
    - **b.json**: "PACLIP01": [
        {
            "Complexes": "2",
            "Empirical formula": "C16H14N2O6Co",
            "Formula weight": "389.22",
            "Crystal system": "orthorhombic",
            "Space group": "Pna21",
            "a (Å)": "9.608(2)",
            "b (Å)": "19.855(4)",
            "c (Å)": "8.183(2)",
            "alpha (°)": "96.457(4)",
            "beta (°)": "94.699(4)",
            "gamma (°)": "114.567(4)"
        },
        {
            "Complexes": "3",
            "Empirical formula": "C16H14N2O6Fe",
            "Formula weight": "386.14",
            "Crystal system": "orthorhombic",
            "Space group": "Pna21",
            "a (Å)": "9.586(2)",
            "b (Å)": "20.037(4)",
            "c (Å)": "8.243(2)",
            "alpha (°)": "NA",
            "beta (°)": "NA",
            "gamma (°)": "NA"
        },
        {
            "Complexes": "5",
            "Empirical formula": "C38H47N6O14V",
            "Formula weight": "862.76",
            "Crystal system": "triclinic",
            "Space group": "P 1 ¯",
            "a (Å)": "12.2013(6)",
            "b (Å)": "12.7349(9)",
            "c (Å)": "15.5088(9)",
            "alpha (°)": "NA",
            "beta (°)": "NA",
            "gamma (°)": "NA"
        }
    ]
    - **Output**:
    ```json
    {
      "PACLIP01":
        {
            "Compound": N/A,
            "Molecule_Identifier": N/A,
            "Number": N/A,
            "Chemical_Name": N/A,
            "Synonyms": N/A
        }
    }
    ```

  5. **Example 5**:
    - **a.json**:
    {
        "WUZDIF": {
            "Molecule_Identifier": "WUZDIF",
            "Number": 729497,
            "Chemical_Name": "bis(μ2-2-phenylquinoline-4-carboxylato)-bis(2,2'-bipyridine)-bis(2-phenylquinoline-4-carboxylato)-di-copper(ii)",
            "Chemical_Name_HTML": "bis(μ<sub>2</sub>-2-phenylquinoline-4-carboxylato)-bis(2,2'-bipyridine)-bis(2-phenylquinoline-4-carboxylato)-di-copper(ii)",
            "Synonyms": [],
            "Crystal_System": "triclinic",
            "Spacegroup_Symbol": "P-1",
            "a": 9.5611,
            "b": 12.696,
            "c": 14.421000000000001,
            "alpha(α)": 70.10000000000002,
            "beta(β)": 87.62,
            "gamma(γ)": 87.07000000000001,
            "Formula": "C84 H56 Cu2 N8 O8",
            "Heaviest_Component_Identifier": "01",
            "Heaviest_Component_Molecular_Weight": 1432.482,
            "Component_Weights": [
                1432.482
            ],
            "Molecular_Weight": 1432.482,
            "Color": "colorless",
            "Melting_Point": null,
            "R_Factor": 4.24,
            "Solvent_Names": [],
            "Publication_Details": "Citation(authors='Jun-Jie Wang, Ze Chang, Ai-Shun Zhang, Tong-Liang Hu, Xian-He Bu', journal='Journal(Inorganica Chimica Acta)', volume='363', year=2010, first_page='1377', doi='10.1016/j.ica.2010.01.043')"
        }
    }
    - **b.json**: "WUZDIF": [
        {
            "Complex": "1",
            "Empirical formula": "C66H50Cu2N2O10",
            "Formula weight": "1158.22",
            "Crystal system": "monoclinic",
            "Space group": "P21/c",
            "a (Å)": "13.720(3)",
            "b (Å)": "14.055(3)",
            "c (Å)": "19.209(6)",
            "alpha (°)": "90",
            "beta (°)": "132.691(18)",
            "gamma (°)": "90",
            "Colour": "N/A"
        },
        {
            "Complex": "2",
            "Empirical formula": "C66H49.5N4Cu2O8.75",
            "Formula weight": "1165.73",
            "Crystal system": "triclinic",
            "Space group": "P¯1",
            "a (Å)": "13.265(3)",
            "b (Å)": "13.715(3)",
            "c (Å)": "16.173(3)",
            "alpha (°)": "89.40(3)",
            "beta (°)": "69.20(3)",
            "gamma (°)": "76.26(3)",
            "Colour": "N/A"
        },
        {
            "Complex": "3",
            "Empirical formula": "C84H56N8Cu2O8",
            "Formula weight": "1432.51",
            "Crystal system": "triclinic",
            "Space group": "P¯1",
            "a (Å)": "9.5611(19)",
            "b (Å)": "12.696(3)",
            "c (Å)": "14.421(3)",
            "alpha (°)": "70.10(3)",
            "beta (°)": "87.62(3)",
            "gamma (°)": "87.07(3)",
            "Colour": "N/A"
        },
        {
            "Complex": "4",
            "Empirical formula": "C44H64Cu2O10",
            "Formula weight": "880.08",
            "Crystal system": "triclinic",
            "Space group": "P¯1",
            "a (Å)": "6.9207(14)",
            "b (Å)": "11.386(2)",
            "c (Å)": "14.030(3)",
            "alpha (°)": "79.40(3)",
            "beta (°)": "77.29(3)",
            "gamma (°)": "89.65(3)",
            "Colour": "N/A"
        },
        {
            "Complex": "5",
            "Empirical formula": "C50H72N4Cu2O8",
            "Formula weight": "984.24",
            "Crystal system": "monoclinic",
            "Space group": "C2/c",
            "a (Å)": "23.331(5)",
            "b (Å)": "12.573(3)",
            "c (Å)": "17.537(4)",
            "alpha (°)": "N/A",
            "beta (°)": "111.88(3)",
            "gamma (°)": "N/A",
            "Colour": "N/A"
        },
        {
            "Complex": "6",
            "Empirical formula": "C50H72N2Cu2O8",
            "Formula weight": "956.22",
            "Crystal system": "tetragonal",
            "Space group": "I-4",
            "a (Å)": "15.8746(2)",
            "b (Å)": "15.8746(2)",
            "c (Å)": "9.6164(2)",
            "alpha (°)": "90",
            "beta (°)": "90",
            "gamma (°)": "90",
            "Colour": "N/A"
        },
        {
            "Complex": "7",
            "Empirical formula": "C48H64N2Cu2O8",
            "Formula weight": "924.14",
            "Crystal system": "cubic",
            "Space group": "I-43d",
            "a (Å)": "38.052(4)",
            "b (Å)": "38.052(4)",
            "c (Å)": "38.052(4)",
            "alpha (°)": "N/A",
            "beta (°)": "N/A",
            "gamma (°)": "N/A",
            "Colour": "N/A"
        }
    ]
    - **Output**:
    ```json
    {
      "WUZDIF":
        {
            "Compound": 3,
            "Molecule_Identifier": WUZDIF,
            "Number": 729497,
            "Chemical_Name": bis(μ2-2-phenylquinoline-4-carboxylato)-bis(2,2'-bipyridine)-bis(2-phenylquinoline-4-carboxylato)-di-copper(ii),
            "Synonyms": []
        }
    }
    ```

  2.Process the following documents:
    - **a.json**: {{a_json}}
    - **b.json**: {{b_json}}

  3. Extract the following fields from `a.json`:
     `"Crystal_System"`, `"Spacegroup_Symbol"`, `"a"`, `"b"`, `"c"`, `"alpha(α)"`, `"beta(β)"`, `"gamma(γ)"`, `"Formula"`, `"Component_Weights"`.

  4. Extract the following fields from `b.json`:
     - `"Crystal system"`, `"Space group"`, `"a (Å)"`, `"a (nm)"`, `"b (Å)"`, `"b (nm)"`, `"c (Å)"`, `"c (nm)"`, `"alpha (°)"`, `"beta (°)"`, `"gamma (°)"`, `"Empirical formula"`, `"Formula weight"`.

  5. Now, proceed with the grouping:
     - **Group 1**: Compare the following pairs:
       - `"Crystal_System"` - `"Crystal system"`
       - `"Spacegroup_Symbol"` - `"Space group"`
       - `"a"` - `"a (Å)"`, `"b"` - `"b (Å)"`, `"c"` - `"c (Å)"`
       - `"alpha(α)"` - `"alpha (°)"`, `"beta(β)"` - `"beta (°)"`, `"gamma(γ)"` - `"gamma (°)"`

     - **Group 2**: Compare the following pairs:
       - `"Formula"` - `"Empirical formula"`
       - `"Component_Weights"` - `"Formula weight"`

  6. Unit Conversion Rule:
     - The units for `"a"`, `"b"`, `"c"` may be in Å (angstroms) or nm (nanometers).
     - **Conversion Factor**: 1 nm = 10 Å.
     - When comparing these values between the two JSONs, convert the units if necessary so that the values are in the same unit before comparison.
     - For example, if one value is in nm and the other is in Å, convert the nm value to Å by multiplying by 10.

  7. Compare the similarity of the data in Group 1**:
     - Ensure that the similarity is greater than **90%**.
     - If any floating-point numbers are enclosed within `" "`, ignore the quotation marks and treat them as numbers.
     - Only compare the keys that are present. If a key is missing (typically in `b.json`), skip that comparison.
     - **Apply the Unit Conversion Rule** for `"a"`, `"b"`, `"c"` as specified in step 6.

  8. Compare the similarity of the data in **Group 2**:
     - Ensure that the similarity is greater than **30%**.
     - The most importance in Group 2 is to ensure that the metal elements in the two objects to be compared are completely identical.

  9. If the conditions for **Group 1** are satisfied, skip the comparison for **Group 2**.

  10. If the data meets the similarity requirements, output the result in the specified format:
     - **Output Format**:
    ```json
    {
      "<Molecule Identifier>":
        {
           "Compound": "<Compound>",
           "Molecule_Identifier": "<Molecule Identifier>",
           "Number": "<Number>",
           "Chemical_Name": "<Chemical Name>",
           "Synonyms": "<Synonyms>"
        }
    }
    ```

- **Important Notice**:
- Please strictly follow the output format in step 10 and only output JSON results.
- Please ensure that the output JSON is **valid** and can be parsed by a standard JSON parser.

- **All keys and values (especially string values) must be enclosed in double quotation marks.**
- Do not include any explanation, reasoning, or additional text.
- Provide the final JSON result directly.

"""