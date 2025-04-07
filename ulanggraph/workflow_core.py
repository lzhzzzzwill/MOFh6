from pathlib import Path
import json
from datetime import datetime
from typing import Dict

class WorkflowBase:
    """工作流基础类"""
    def __init__(self, config_path: str, output_dir: str):
        self.config_path = Path(config_path)
        self.output_dir = Path(output_dir)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def create_output_dirs(self, dir_names: list) -> Dict[str, Path]:
        """创建输出目录"""
        output_dirs = {}
        for name in dir_names:
            dir_path = self.output_dir / name
            dir_path.mkdir(parents=True, exist_ok=True)
            output_dirs[name] = dir_path
        return output_dirs
    
    def load_config(self) -> dict:
        """加载配置文件"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
