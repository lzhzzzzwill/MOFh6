from pathlib import Path
import json
import re
from typing import Optional, Dict, Any, Union
from datetime import datetime
import pandas as pd
from ulanggraph.workflow_core import WorkflowBase

class FileProcessor(WorkflowBase):
    """文件处理类"""
    def __init__(self, config_path: str, output_dir: str):
        super().__init__(config_path, output_dir)
        
    def read_file(self, file_path: Path) -> Union[dict, pd.DataFrame]:
        """
        根据文件类型读取文件内容
        """
        suffix = file_path.suffix.lower()
        
        if suffix == '.json':
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        elif suffix in ['.xlsx', '.xls']:
            return pd.read_excel(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}")

    def get_synthesis_data(self, excel_path: Path) -> dict:
        """
        从Excel文件中提取合成数据并转换为字典格式
        """
        df = self.read_file(excel_path)
        
        # 将DataFrame转换为所需的字典格式
        synthesis_data = {}
        for _, row in df.iterrows():
            if 'file_name' in row and 'prediction' in row:
                # 移除文件扩展名（如果存在）
                file_name = row['file_name']
                if isinstance(file_name, str):
                    file_name = file_name.replace('.txt', '')
                
                synthesis_data[file_name] = {
                    'synthesis': row['prediction'] if pd.notna(row['prediction']) else ''
                }
                
        return synthesis_data

    def check_abbreviations(self, text: str) -> bool:
        """检查文本中是否包含缩写模式"""
        patterns = [
            r'\b(?:H\d*L\d*)\b',
            r'\b(?:L\d+)\b',
            r'\b(?:L\d+H\d+)\b'
        ]
        return any(re.search(pattern, text) for pattern in patterns)

    def save_json(self, data: dict, file_path: Path):
        """保存JSON文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)