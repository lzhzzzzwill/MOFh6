import sys
import logging
from pathlib import Path
import os#####相对路径

os.chdir(os.path.dirname(__file__))

# 添加项目根目录到 Python 路径（必须在其他本地导入之前）
project_root = Path(__file__).parent / "request"
sys.path.append(str(project_root))

# 现在再导入本地模块
from request.config.config import load_config
from request.core.query_system import ChemicalQuerySystem

def main():
    """Main function with enhanced error handling and user interaction"""
    try:
        print("\n🌟 Initializing MOF Analysis System...\n")
        
        # Load configuration
        config_path = './extrfinetune/config.json' 
        config = load_config(config_path)
        query_system = ChemicalQuerySystem(config)
        
        # Print welcome message
        print("💎 Welcome to MOF Analysis System!")
        print("\n📋 Available Commands:")
        print("📄 'How to synthesize <code/name>' - Obtain the synthesized text")
        print("📄 'process pdf <path>' - Process a PDF document")
        print("🔬 'workflow <path>' - Run analysis workflow on processed PDF")
        print("💾 'show saved' - Show saved documents")
        print("📥 'download cif <code>' - Download CIF file for a CCDC code")
        print("🔮 'visualize <code>' - Visualize crystal structure for a CCDC code")
        print("⏹️  'q!' - Exit the system\n")

        # Main interaction loop (保持原有的循环逻辑不变)
        while True:
            try:
                user_input = input("Query> ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() == 'q!':
                    print("\n👋 Thank you for using MOF Analysis System. Goodbye!")
                    break
                
                if user_input.lower().startswith('process pdf'):
                    _, _, pdf_path = user_input.partition(' pdf ')
                    pdf_path = pdf_path.strip()
                    if not pdf_path:
                        print("\n❌ Please provide a PDF file path")
                        continue
                        
                    result = query_system.process_pdf(pdf_path)
                    # 删除这里的重复打印内容，因为已经在 process_pdf 中打印过了
                    if not result:
                        print("\n❌ Failed to process PDF")

                    continue

                if user_input.lower() == 'show saved':
                    saved_docs = query_system.get_saved_documents()
                    if saved_docs:
                        print("\n📚 Saved Documents:")
                        for doc in saved_docs:
                            print(f"\nFile: {doc['filename']}")
                            print(f"Path: {doc['path']}")
                            print("Preview:")
                            print(doc['preview'])
                    else:
                        print("\n💤 No saved documents found")
                    
                if user_input.lower() == 'list pdfs':
                    if hasattr(query_system, 'pdf_content') and query_system.pdf_content:
                        print("\n📚 Processed Documents:")
                        for path, info in query_system.pdf_content.items():
                            print(f"- {info['filename']}")
                            print(f"  Pages: {info['metadata'].page_count}")
                            print(f"  Size: {info['metadata'].file_size}")
                            print(f"  Path: {path}")
                            print("  💡 Use this path with 'workflow' command to analyze")
                    else:
                        print("\n💤 No PDFs have been processed yet")
                    continue
                
                answer = query_system.get_answer(user_input)
                print(f"\n{answer}\n")
                
            except KeyboardInterrupt:
                print("\n⌨️  Use 'q!' to exit properly")
                continue
            except EOFError:
                print("\n📍 Use 'q!' to exit properly")
                continue
            except Exception as e:
                print(f"\n❌ Error processing query: {e}")
                print("Please try again or type 'help' for examples")
                continue

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Program terminated due to unexpected error: {e}")
        sys.exit(1)
