import sys
import os
import json
from pathlib import Path
from openai import OpenAI

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from ulanggraph.workflow_manager import MOFWorkflowManager


def main():
    """主函数"""
    try:
        # 配置路径
        config_path = project_root / "extrfinetune" / "config.json"
        base_output_dir = project_root / "ulanggraph" / "output"
        input_dir = project_root / "ulanggraph" / "input"
        system_file = project_root / "extrfinetune" / "finetunetable" / "system198.txt"
        ccdc_data = project_root / "datareading" / "des_mate.json"

        # Reuse the existing API-key configuration. The standalone batch entry
        # does not generate question suggestions, but it does need a client to
        # create embeddings for the persistent literature index.
        with config_path.open('r', encoding='utf-8') as config_file:
            config = json.load(config_file)
        rag_client = OpenAI(api_key=config['openaiapikey'])

        # 创建工作流管理器实例
        workflow_manager = MOFWorkflowManager(
            str(config_path), str(base_output_dir), rag_client=rag_client
        )
        
        # 运行工作流
        final_state = workflow_manager.run(
            str(input_dir), str(system_file), str(ccdc_data)
        )
        
        # 检查最终输出
        if final_state and 'file_paths' in final_state and 'final_output' in final_state['file_paths']:
            print("\n📊 Workflow Statistics:")
            print(f"🕒 Start Time: {final_state['timestamp']}")
            print(f"📁 Input Files Processed: {len(list(Path(input_dir).glob('*.txt')))}")
            print(f"📝 Final Output: {final_state['file_paths']['final_output']}")
        else:
            print("\n⚠️ Warning: Incomplete workflow output")
            
    except Exception as e:
        print(f"\n❌ Error in main: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
