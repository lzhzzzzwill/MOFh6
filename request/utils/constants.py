from enum import Enum

class QueryType(Enum):
    DIRECT = "direct"
    RANGE = "range"
    COMPARISON = "comparison"
    MULTIPLE = "multiple"
    PROPERTY_ANALYSIS = "property_analysis"
    SEARCH = "search"
    GENERAL = "general"

NECESSARY_COLUMNS = [
    'CCDC_code', 'CCDC_number', 'Chemical_name', 'Synonyms',
    'LCD (Å)', 'PLD (Å)', 'Density (g/cm3)',
    'Accessible_Surface_Area (m2/cm3)',
    'Accessible_Surface_Area (m2/g)', 'Volume_Fraction'
]

FIELD_MAPPING = {
    # Volume related
    'volume fraction': 'Volume_Fraction',
    'volumefraction': 'Volume_Fraction',
    'volume': 'Volume_Fraction',
    'porosity': 'Volume_Fraction',
    'void fraction': 'Volume_Fraction',
    'void': 'Volume_Fraction',
    
    # Density related
    'density': 'Density (g/cm3)',
    
    # Pore size related
    'lcd': 'LCD (Å)',
    'largest cavity diameter': 'LCD (Å)',
    'cavity diameter': 'LCD (Å)',
    'pld': 'PLD (Å)',
    'pore limiting diameter': 'PLD (Å)',
    'pore diameter': 'PLD (Å)',
    
    # Surface area related
    'surface area': 'Accessible_Surface_Area (m2/cm3)',
    'accessible surface area': 'Accessible_Surface_Area (m2/cm3)',
    'asa': 'Accessible_Surface_Area (m2/cm3)',
    'surface area per volume': 'Accessible_Surface_Area (m2/cm3)',
    'volumetric surface area': 'Accessible_Surface_Area (m2/cm3)',
    'surface area per mass': 'Accessible_Surface_Area (m2/g)',
    'gravimetric surface area': 'Accessible_Surface_Area (m2/g)',
    'mass surface area': 'Accessible_Surface_Area (m2/g)',
    
    # Name related
    'name': 'Chemical_name',
    'chemical name': 'Chemical_name',
    'compound name': 'Chemical_name',
    'synonym': 'Synonyms',
    'synonyms': 'Synonyms',
    'other names': 'Synonyms',
    'alternative names': 'Synonyms'
}