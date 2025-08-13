from dataclasses import dataclass
from typing import Optional
import json

@dataclass
class Config:
    api_key: str
#    base_url: Optional[str]
    xlsx_path: str

def load_config(config_path: str) -> Config:
    """Load configuration from JSON file with enhanced error handling"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            
            # Validate required fields
            required_fields = ['openaiapikey', 'xlsx_path']
            missing_fields = [field for field in required_fields if field not in config_data]
            if missing_fields:
                raise KeyError(f"Missing required configuration fields: {', '.join(missing_fields)}")
                
            return Config(
                api_key=config_data['openaiapikey'],
#                base_url=config_data.get('baseurl'),
                xlsx_path=config_data['xlsx_path']
            )
    except FileNotFoundError:
        raise RuntimeError(f"Configuration file not found: {config_path}")
    except json.JSONDecodeError:
        raise RuntimeError(f"Invalid JSON in configuration file: {config_path}")
    except Exception as e:
        raise RuntimeError(f"Error loading configuration: {e}")
