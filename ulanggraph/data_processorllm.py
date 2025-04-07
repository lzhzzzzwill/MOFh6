from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import re
from ulanggraph.workflow_core import WorkflowBase
import json
from openai import OpenAI
from ulanggraph.prompt.totext import SYSTEM_PROMPT, EXTRACTION_PROMPT

class DataProcessor(WorkflowBase):
    """数据处理类"""
    def __init__(self, config_path: str, output_dir: str):
        super().__init__(config_path, output_dir)
        self.output_dirs = self.create_output_dirs(['synthesis', 'tables', 'comparison', 'final'])
        self._cached_client = None
        self._cached_config = None

    @property
    def config(self) -> dict:
        """Lazy loading of configuration"""
        if self._cached_config is None:
            config_path = Path(self.config_path)
            with open(config_path, 'r', encoding='utf-8') as f:
                self._cached_config = json.load(f)
        return self._cached_config

    @property
    def client(self) -> OpenAI:
        """Lazy loading of OpenAI client"""
        if self._cached_client is None:
            self._cached_client = OpenAI(
                api_key=self.config.get('apikey'),
                base_url=self.config.get('baseurl')
            )
        return self._cached_client

    def find_abbreviations_in_text(self, text: str, abbr_data: list) -> list:
        """
        在文本中查找化学缩写并匹配对应的全称
        """
        found_abbrs = []
        if not text or not abbr_data:
            return found_abbrs

        # 定义化学缩写的正则表达式模式
        patterns = [
            r'\b(?:H\d*L\d*)\b',    # 匹配 HL, H2L, HL2 等
            r'\b(?:L\d+)\b',        # 匹配 L1, L2 等
            r'\b(?:L\d+H\d+)\b',    # 匹配 L1H1, L2H2 等
            r'\bL\b'                # 匹配单个 L
        ]
        
        # 在文本中查找所有可能的缩写
        found_patterns = set()
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            found_patterns.update(match.group() for match in matches)
        
        # 将找到的缩写与缩写数据匹配
        for abbr_info in abbr_data:
            abbr = abbr_info.get('abbreviation', '').replace('Abbreviation: ', '')
            full_name = abbr_info.get('full_name', '').replace('Full Name: ', '')
            
            # 检查这个缩写是否在文本中出现
            if any(re.search(rf'\b{re.escape(abbr)}\b', found, re.IGNORECASE) for found in found_patterns):
                found_abbrs.append({
                    'abbreviation': abbr,
                    'full_name': full_name
                })
        
        return found_abbrs

    def get_compound_info(self, identifier: str, comp_data: dict) -> dict:
        """Extract compound information with enhanced error handling"""
        try:
            if identifier in comp_data:
                if isinstance(comp_data[identifier], dict):
                    if identifier in comp_data[identifier]:
                        return comp_data[identifier][identifier]
                    return comp_data[identifier]
            print(f"Warning: Unexpected data structure for {identifier}")
            return {}
        except Exception as e:
            print(f"Error accessing compound info for {identifier}: {e}")
            return {}

    def extract_synthesis_by_compound(self, synthesis_text: str, compound_name: str, 
                                    identifier: str, compound_info: dict) -> str:
        """
        Extract synthesis method using LLM with highly flexible compound identification
        """
        if not synthesis_text:
            return "No synthesis information available"

        chemical_name = compound_info.get('Chemical_Name', '')
        
        # 使用统一的提示模板
        prompt = EXTRACTION_PROMPT.format(
            compound_name=compound_name,
            identifier=identifier,
            chemical_name=chemical_name,
            synthesis_text=synthesis_text
        )
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini-2024-07-18",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            
            extracted_text = response.choices[0].message.content.strip()
            
            if "No synthesis method found" in extracted_text:
                return f"No synthesis method found for compound {compound_name}"
                
            return extracted_text
            
        except Exception as e:
            print(f"Error extracting synthesis method: {e}")
            return f"Error extracting synthesis method for compound {compound_name}"

    def format_compound_entry(self, identifier: str, compound_info: dict, 
                            synth_data: dict, abbr_data: Optional[dict]) -> list:
        """Format a single compound entry with improved abbreviation matching"""
        entry = []
        
        # Basic information
        entry.append(f"{identifier}")
        entry.append(f"Chemical_Name: {compound_info.get('Chemical_Name', 'N/A')}")
        entry.append(f"Number: {compound_info.get('Number', 'N/A')}")
        entry.append(f"Synonyms: {', '.join(compound_info.get('Synonyms', [])) or 'N/A'}")
        
        # Synthesis information
        target_compound = compound_info.get('Compound', '')
        synthesis_text = synth_data.get(identifier, {}).get('synthesis', '')
        
        if synthesis_text:
            filtered_synthesis = self.extract_synthesis_by_compound(
                synthesis_text,
                target_compound,
                identifier,
                compound_info
            )
            entry.append(filtered_synthesis)
            
            # 处理缩写
            if abbr_data and identifier in abbr_data:
                found_abbrs = self.find_abbreviations_in_text(
                    filtered_synthesis, 
                    abbr_data[identifier]
                )
                if found_abbrs:
                    for abbr in sorted(found_abbrs, key=lambda x: x['abbreviation']):
                        entry.append(f"Abbreviation: {abbr['abbreviation']}")
                        entry.append(f"Full Name: {abbr['full_name']}")
                else:
                    entry.append("\nNo abbreviations found in synthesis text")
            else:
                entry.append("\nNo abbreviations found in synthesis text")
        else:
            entry.append("No synthesis information available")
            entry.append("\nNo abbreviations found in synthesis text")
                
        return entry

    def format_final_output(self, comparison_data: dict, synthesis_data: dict, 
                          abbreviations: Optional[Dict] = None) -> str:
        """Format final output with complete information handling"""
        try:
            final_output = []
            processed_identifiers = set()

            if not comparison_data or not synthesis_data:
                return "Error: Missing required data"
            
            # Process compounds from comparison data
            for identifier in sorted(comparison_data.keys()):
                if identifier not in processed_identifiers:
                    try:
                        compound_info = self.get_compound_info(identifier, comparison_data)
                        if compound_info or identifier in synthesis_data:
                            entry = self.format_compound_entry(
                                identifier,
                                compound_info,
                                synthesis_data,
                                abbreviations
                            )
                            if entry:  # Make sure entry is not empty
                                final_output.append('\n'.join(entry))
                            processed_identifiers.add(identifier)
                    except Exception as e:
                        print(f"Error processing compound {identifier}: {e}")
                        final_output.append(f"{identifier}\nError: {str(e)}")
                        processed_identifiers.add(identifier)

            # Check for missed compounds
            for identifier in sorted(synthesis_data.keys()):
                if identifier not in processed_identifiers:
                    try:
                        compound_info = self.get_compound_info(identifier, comparison_data)
                        entry = self.format_compound_entry(
                            identifier,
                            compound_info,
                            synthesis_data,
                            abbreviations
                        )
                        if entry:  # Make sure entry is not empty
                            final_output.append('\n'.join(entry))
                    except Exception as e:
                        print(f"Error processing compound {identifier}: {e}")
                        final_output.append(f"{identifier}\nError: {str(e)}")

            # 确保至少返回一些内容
            if not final_output:
                return "No compounds were processed successfully"
                
            return '\n\n'.join(final_output)
            
        except Exception as e:
            print(f"Error in format_final_output: {e}")
            return f"Error formatting output: {str(e)}"