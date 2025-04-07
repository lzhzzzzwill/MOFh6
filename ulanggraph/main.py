import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from ulanggraph.workflow_manager import MOFWorkflowManager


def main():
    """主函数"""
    try:
        # 配置路径
        config_path = "/Users/linzuhong/学习文件/3-博/博四/C2ML/extrfinetune/config.json"
        base_output_dir = "/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/output"
        input_dir = "/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/input"
        system_file = "/Users/linzuhong/学习文件/3-博/博四/C2ML/extrfinetune/finetunetable/system198.txt"
        ccdc_data = "/Users/linzuhong/学习文件/3-博/博四/C2ML/datareading/ccdcdata.json"

        # 创建工作流管理器实例
        workflow_manager = MOFWorkflowManager(config_path, base_output_dir)
        
        # 运行工作流
        final_state = workflow_manager.run(input_dir, system_file, ccdc_data)
        
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