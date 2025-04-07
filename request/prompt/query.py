from typing import Dict

class ChemicalPrompts:
    SYSTEM_PROMPT = """
    You are a specialized chemical database assistant with expertise in:
    1. Querying and analyzing chemical substance properties
    2. Handling various data types including CCDC codes, measurements, and chemical names
    3. Providing detailed property comparisons and analyses
    
    Available properties for analysis:
    - CCDC_code & CCDC_number: Unique identifiers for substances
    - Chemical_name & Synonyms: Full chemical names and alternative names
    - LCD (Å) & PLD (Å): Cavity and pore measurements
    - Density (g/cm3): Material density
    - Accessible_Surface_Area: Both volumetric (m2/cm3) and gravimetric (m2/g)
    - Volume_Fraction: Porosity measurement
    
    Response Guidelines:
    1. Always include units with numerical values
    2. Provide Chemical_name and Synonyms when available
    3. For comparisons, show data for all substances being compared
    4. Be precise with significant figures (generally 4 decimal places)
    5. Format output clearly with appropriate line breaks and sections
    6. When providing property values, explicitly state what the property is
    """

    HELP_INFO: Dict[str, str] = {
        'capabilities': """
I can help you with the following tasks:
1. Direct property queries
   - "What is the PLD of VUJBEI?"
   - "Show me the density of QOWTIG"
   - "What is the name of ABIGEZ06?"
   - "Tell me about VUJBEI"

2. Range searches
   - "Find materials with LCD between 19 and 20 Å"
   - "Show compounds with density between 1.9 and 2.0 g/cm3"
   - "Find PLD range 4.8 to 5.0"

3. Property comparisons
   - "Compare the surface areas of VUJBEI and QOWTIG"
   - "Which has higher density: VUJBEI or QOWTIG?"
   - "What's the difference in LCD between VUJBEI and QOWTIG?"

4. Statistical analysis
   - "What is the average density?"
   - "Which material has the highest surface area?"
   - "Find material with maximum volumetric surface area"
   - "Show material with highest gravimetric surface area"

5. General information
   - "What properties can you tell me about VUJBEI?"
""",
        'syntax': """
Query syntax examples:
1. Direct Property Queries:
   - "VUJBEI PLD" or "What is VUJBEI's density?"
   - "Name of VUJBEI" or "What is VUJBEI called?"
   - "Show all properties of VUJBEI"

2. Range Queries:
   - "Find LCD between 15-20" or "LCD range 15 to 20"
   - "Density between 1.5 and 2.0"
   - "Show materials with PLD from 3 to 5"

3. Comparison Queries:
   - "Compare VUJBEI and QOWTIG density"
   - "Which has higher LCD: VUJBEI or QOWTIG?"
   - "Show difference in surface area between VUJBEI and QOWTIG"

4. Statistical Queries:
   - "Average density" or "Mean surface area"
   - "Highest LCD" or "Lowest PLD"
   - "Maximum volume fraction"
""",
        'examples': """
Example queries and responses:

1. Name Query:
   Q: "What is the name of VUJBEI?"
   A: Chemical name and any available synonyms will be provided

2. Property Query:
   Q: "What is the PLD of VUJBEI?"
   A: The precise PLD value with units will be shown

3. Range Search:
   Q: "Find materials with density between 1.5 and 2.0"
   A: List of materials within the specified range

4. Comparison:
   Q: "Compare surface areas of VUJBEI and QOWTIG"
   A: Detailed comparison of both materials' surface areas

5. Statistical Analysis:
   Q: "What is the average density?"
   A: The mean density value across all materials
"""
    }

    @staticmethod
    def create_extraction_prompt(markdown_table: str, question: str) -> str:
        """Create prompt for OpenAI API with enhanced context"""
        return f"""
        Table content:

        {markdown_table}

        Guidelines for response:
        1. Include complete substance identification:
           - CCDC code
           - CCDC number (if available)
           - Chemical name
           - Synonyms (if available)
        2. Provide all relevant numerical values with their units
        3. For comparison questions:
           - Show data for all substances being compared
           - Highlight key differences
        4. For statistical queries:
           - Show the calculated value with appropriate units
           - Include context (e.g., number of materials considered)
        5. Format response clearly with appropriate sections
        6. Handle zero or missing values appropriately

        User question: {question}
        """

    @staticmethod
    def get_property_info() -> str:
        """Get detailed information about available properties"""
        return "\n".join([
            "Available properties for querying:",
            "1. Identification:",
            "   - CCDC_code: Unique identifier for each substance",
            "   - CCDC_number: Alternative reference number",
            "   - Chemical_name: Full chemical compound name",
            "   - Synonyms: Alternative names or common references",
            "",
            "2. Structural Properties:",
            "   - LCD (Largest Cavity Diameter) in Angstroms (Å)",
            "   - PLD (Pore Limiting Diameter) in Angstroms (Å)",
            "",
            "3. Physical Properties:",
            "   - Density in g/cm3",
            "   - Accessible Surface Area:",
            "     * Volumetric (m2/cm3)",
            "     * Gravimetric (m2/g)",
            "   - Volume Fraction (porosity measure, dimensionless)"
        ])