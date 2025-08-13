import pandas as pd
import subprocess
import os
import logging
from typing import Dict, Optional

class DOIRouter:
    def __init__(self):
        # Define DOI prefixes for different publishers
        self.publisher_prefixes: Dict[str, str] = {
            "10.1126": "AAAS",
            "10.1021": "ACS",
            "10.1016": "Elsevier",
            "10.1073": "PNAS",
            "10.1039": "RSC",
            "10.1007": "Springer",
            "10.1002": "Wiley"
        }
        
        # Define paths to crawler scripts
        self.crawler_scripts: Dict[str, str] = {
            "ACS": "./refer/ACS_crawler.py",
            "Elsevier": "./refer/Elsevier_crawler.py",
            "RSC": "./refer/RSC_crawler.py",
            "Springer": "./refer/Springer_crawler.py",
            "Wiley": "./refer/Wiley_crawler.py" #/Users/linzuhong/学习文件/3-博/博四/C2ML/refer/Wiley_crawler.py
        }
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('doi_router.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def identify_publisher(self, doi: str) -> Optional[str]:
        """
        Identify the publisher based on DOI prefix
        """
        for prefix, publisher in self.publisher_prefixes.items():
            if doi.startswith(prefix):
                return publisher
        return None

    def route_and_execute(self, input_file: str):
        """
        Route DOIs to appropriate crawler scripts and execute them
        """
        try:
            # Read the input file
            df = pd.read_excel(input_file) if input_file.endswith('.xlsx') else pd.read_csv(input_file)
            
            # Group DOIs by publisher
            grouped_data = {}
            
            for _, row in df.iterrows():
                doi = str(row['DOI']).strip()  # Assuming 'DOI' is the column name
                if not doi or pd.isna(doi):
                    self.logger.warning(f"Skipping invalid DOI: {doi}")
                    continue
                
                publisher = self.identify_publisher(doi)
                if publisher:
                    if publisher not in grouped_data:
                        grouped_data[publisher] = []
                    grouped_data[publisher].append(row)
                else:
                    self.logger.warning(f"Unknown publisher for DOI: {doi}")
            
            # Create temporary files and execute crawlers for each publisher
            for publisher, rows in grouped_data.items():
                temp_df = pd.DataFrame(rows)
                temp_filename = f"temp_{publisher}_data.xlsx"
                temp_df.to_excel(temp_filename, index=False)
                
                crawler_script = self.crawler_scripts.get(publisher)
                if crawler_script and os.path.exists(crawler_script):
                    try:
                        self.logger.info(f"Executing {crawler_script} for {publisher}")
                        subprocess.run(['python', crawler_script, temp_filename], check=True)
                    except subprocess.CalledProcessError as e:
                        self.logger.error(f"Error executing {crawler_script}: {str(e)}")
                    finally:
                        # Clean up temporary file
                        if os.path.exists(temp_filename):
                            os.remove(temp_filename)
                else:
                    self.logger.error(f"Crawler script not found for {publisher}")

        except Exception as e:
            self.logger.error(f"Error processing input file: {str(e)}")
            raise

def main():
    # Example usage
    router = DOIRouter()
    input_file = "./datareading/Dataset/metadata.xlsx"  #/Users/linzuhong/学习文件/3-博/博四/C2ML/datareading/Dataset/metadata.xlsx
    router.route_and_execute(input_file)

if __name__ == "__main__":
    main()