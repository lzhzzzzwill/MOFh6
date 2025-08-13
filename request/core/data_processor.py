import pandas as pd
from typing import Dict, List
from utils.constants import NECESSARY_COLUMNS

class DataProcessor:
    @staticmethod
    def preprocess_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """Preprocess DataFrame with enhanced error handling and data validation"""
        # Verify columns
        existing_columns = [col for col in NECESSARY_COLUMNS if col in df.columns]
        missing_columns = set(NECESSARY_COLUMNS) - set(existing_columns)
        
        if missing_columns:
            print(f"Warning: Missing columns in Excel: {missing_columns}")
        
        # Create a copy of the DataFrame with only necessary columns
        processed_df = df[existing_columns].copy()
        
        # Convert numeric columns to float with validation
        numeric_columns = ['LCD (Å)', 'PLD (Å)', 'Density (g/cm3)', 
                         'Accessible_Surface_Area (m2/cm3)',
                         'Accessible_Surface_Area (m2/g)', 'Volume_Fraction']
        
        for col in numeric_columns:
            if col in processed_df.columns:
                try:
                    processed_df.loc[:, col] = pd.to_numeric(processed_df[col], errors='coerce')
                    # Add validation for reasonable value ranges
                    if processed_df[col].min() < 0:
                        print(f"Warning: Negative values found in {col}")
                except Exception as e:
                    print(f"Warning: Error converting {col} to numeric: {e}")
        
        # Clean synonyms
        if 'Synonyms' in processed_df.columns:
            processed_df['Synonyms'] = processed_df['Synonyms'].fillna('')
            processed_df['Synonyms'] = processed_df['Synonyms'].apply(lambda x: str(x).strip())
        
        return processed_df

    @staticmethod
    def create_context(df: pd.DataFrame, question: str) -> str:
        """Create enhanced context for the query"""
        context = f"Query: {question}\n\nDetailed information:\n"
        
        # Sort DataFrame by CCDC_code for consistent output
        df_sorted = df.sort_values('CCDC_code')
        
        for _, row in df_sorted.iterrows():
            context += f"\nSubstance: {row['CCDC_code']}\n"
            
            # Add identification information
            for id_field in ['Chemical_name', 'Synonyms', 'CCDC_number']:
                if pd.notna(row.get(id_field)):
                    context += f"{id_field}: {row[id_field]}\n"
            
            # Add numerical properties with units
            for col in NECESSARY_COLUMNS[4:]:  # Skip identification columns
                if pd.notna(row.get(col)):
                    # Format numerical values with appropriate precision
                    value = f"{row[col]:.4f}" if isinstance(row[col], float) else str(row[col])
                    context += f"{col}: {value}\n"
        
        return context

    @staticmethod 
    def calculate_statistics(df: pd.DataFrame, column: str) -> Dict:
        """计算指定列的统计信息"""
        if column not in df.columns:
            raise ValueError(f"Column {column} not found in DataFrame")
        
        try:
            stats = {
                'mean': float(df[column].mean()),
                'median': float(df[column].median()),
                'std': float(df[column].std()),
                'min': float(df[column].min()),
                'max': float(df[column].max()),
                'count': int(df[column].count())
            }
            return stats
        except Exception as e:
            logging.error(f"Error calculating statistics for {column}: {e}")
            return {}