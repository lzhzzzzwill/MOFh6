import os
import re
import sys
import logging
import json
import pandas as pd
from pathlib import Path
from datetime import datetime  
from typing import Optional, Dict, List, Tuple
from openai import OpenAI
from config.config import Config
from core.data_processor import DataProcessor
from core.query_parser import EnhancedQueryHandler
from prompt.query import ChemicalPrompts
from utils.constants import NECESSARY_COLUMNS, FIELD_MAPPING
from utils.pdf_processor import PDFUtils, PDFMetadata
from utils.rdoi import DOIRouter 

from PyQt5.QtWidgets import QApplication
from utils.re_cif import HuggingFaceDatasetDownloader  # CIF文件获取
from utils.vis_cif import CrystalViewer, CrystalViewerApp  # 结构可视化

from ulanggraph.workflow_manager import MOFWorkflowManager  

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class ChemicalQuerySystem:
    def __init__(self, config: Config):
            self.config = config
            self.client = self._create_openai_client()
            self.df = self._load_and_preprocess_data()
            self.prompts = ChemicalPrompts()
            self.query_handler = EnhancedQueryHandler(self.df, self.client)
            self.pdf_content = {}
            # 添加CIF文件目录配置
            self.cif_folder = "/Users/linzuhong/学习文件/3-博/博四/C2ML/cif_files" ######
            os.makedirs(self.cif_folder, exist_ok=True) 
            # 添加输出目录配置
            self.output_dir = os.path.join(os.path.dirname(config.xlsx_path), "processed_pdfs")
            os.makedirs(self.output_dir, exist_ok=True)
            # 添加时间戳属性
            self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def get_synthesis_info(self, query: str) -> str:
        """搜索并获取化合物的合成信息"""
        try:
            # 读取元数据文件
            metadata_path = "/Users/linzuhong/学习文件/3-博/博四/C2ML/datareading/Dataset/metadata.xlsx"  #######
            metadata_df = pd.read_excel(metadata_path)
            
            # 清理查询字符串
            query = query.strip('?.,!').strip()
            
            # 在所有可能的列中搜索匹配
            mask = (
                # CCDC代码：精确匹配，不区分大小写
                metadata_df['CCDC_code'].str.upper() == query.upper()
            ) | (
                # CCDC编号：转换为整数后比较
                (metadata_df['CCDC_number'] == int(query)) if query.isdigit() else False
            ) | (
                # 化学名称：包含匹配，不区分大小写
                metadata_df['Chemical_name'].str.contains(query, case=False, na=False, regex=False)
            ) | (
                # 同义词：精确匹配，不区分大小写
                metadata_df['Synonyms'].str.upper() == query.upper()
            )
            
            compound_data = metadata_df[mask]
            
            if compound_data.empty:
                return f"\n❌ No data found for the query: {query}"
                
            if len(compound_data) > 1:
                print(f"\n💡 Found multiple matches:")
                for _, row in compound_data.iterrows():
                    print(f"- {row['CCDC_code']}: {row['Chemical_name']}")
                return "\n⚠️ Please be more specific in your query."
            
            # 创建临时Excel文件
            temp_dir = "/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/temp"  #######
            os.makedirs(temp_dir, exist_ok=True)
            temp_file = os.path.join(temp_dir, "temp_doi_data.xlsx")

            # 直接使用找到的行创建新的DataFrame
            temp_df = pd.DataFrame([compound_data.iloc[0]])
            temp_df.to_excel(temp_file, index=False)
            
            print(f"\n🔍 Found compound: {compound_data['CCDC_code'].iloc[0]}")
            print(f"📝 DOI: {compound_data['DOI'].iloc[0]}")
            print("📥 Starting download process...")
            
            # 使用DOIRouter处理下载
            router = DOIRouter()
            router.route_and_execute(temp_file)
            
            # 清理临时文件（可选）
            # if os.path.exists(temp_file):
            #     os.remove(temp_file)
            
            return f"\n✅ Synthesis information retrieval initiated\n💡 Please use 'workflow {compound_data['CCDC_code'].iloc[0]}' to analyze the downloaded content"
            
        except Exception as e:
            logging.error(f"Error retrieving synthesis info: {e}")
            return f"\n❌ Error retrieving synthesis information: {str(e)}"
        
    def process_pdf(self, pdf_path: str) -> Optional[dict]:
        """Process uploaded PDF and store its content"""
        try:
            if not os.path.exists(pdf_path):
                logging.error(f"File not found: {pdf_path}")
                return None

            input_dir = "/Users/linzuhong/学习文件/3-博/博四/C2ML/langgraph/input" #####
            os.makedirs(input_dir, exist_ok=True)

            text, metadata = PDFUtils.extract_text_and_metadata(pdf_path)
            if text:
                # 处理特殊字符
                text = text.replace('©', '(c)')
                text = ''.join(char if ord(char) < 128 else ' ' for char in text)
                
                pdf_info = {
                    'text': text,
                    'metadata': metadata,
                    'filename': os.path.basename(pdf_path)
                }
                self.pdf_content[pdf_path] = pdf_info
                
                # 保存到 langgraphdemo 的 input 目录
                pdf_name = os.path.splitext(pdf_info['filename'])[0]
                text_file = os.path.join(input_dir, f"{pdf_name}.txt")
                
                with open(text_file, 'w', encoding='utf-8') as f:
                    f.write(text)
                
                result = {
                    'filename': pdf_info['filename'],
                    'metadata': metadata,
                }
                
                # 在这里添加result检查和提示信息
                if result:
                    print(f"\n✅ Successfully processed: {result['filename']}")
                    print("\n💡 Available commands:")
                    print("1. To analyze the content:")
                    print(f"   workflow {pdf_path}")
                    return result
                
            logging.error("No text could be extracted from PDF")
            return None
                
        except Exception as e:
            logging.error(f"Error processing PDF: {str(e)}")
            return None

    def _save_processed_content(self, pdf_path: str, pdf_info: dict) -> str:
        """Save processed PDF content to file system"""
        try:
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            output_path = os.path.join(self.output_dir, f"{base_name}")
            
            # 保存文本内容
            text_path = f"{output_path}_content.txt"
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write("=== PDF Metadata ===\n")
                f.write(f"Title: {pdf_info['metadata'].title or 'N/A'}\n")
                f.write(f"Author: {pdf_info['metadata'].author or 'N/A'}\n")
                f.write(f"Pages: {pdf_info['metadata'].page_count}\n")
                f.write(f"File Size: {pdf_info['metadata'].file_size}\n")
                f.write("\n=== Content ===\n")
                f.write(pdf_info['text'])

            # 保存路径信息
            pdf_info['saved_path'] = text_path
            
            logging.info(f"Content saved to: {text_path}")
            return text_path
            
        except Exception as e:
            logging.error(f"Error saving content: {str(e)}")
            return ""

    def get_saved_documents(self) -> List[dict]:
        """Get list of saved documents"""
        saved_docs = []
        try:
            for filename in os.listdir(self.output_dir):
                if filename.endswith('_content.txt'):
                    doc_path = os.path.join(self.output_dir, filename)
                    with open(doc_path, 'r', encoding='utf-8') as f:
                        first_lines = ''.join([next(f) for _ in range(5)])
                    saved_docs.append({
                        'filename': filename,
                        'path': doc_path,
                        'preview': first_lines
                    })
        except Exception as e:
            logging.error(f"Error listing saved documents: {str(e)}")
        return saved_docs

    def _handle_pdf_query(self, question: str) -> str:
        """Handle PDF-related queries"""
        if not self.pdf_content:
            return "No PDF documents have been processed yet."
            
        try:
            # Create context from PDF content
            context = "Available documents:\n"
            for path, info in self.pdf_content.items():
                context += f"- {info['filename']} ({info['metadata'].page_count} pages)\n"
            
            # Get response from OpenAI
            prompt = f"""
            Context: {context}
            PDF contents: {[info['text'] for info in self.pdf_content.values()]}
            Question: {question}
            """
            
            response = self._query_openai(prompt)
            return response
        except Exception as e:
            logging.error(f"Error handling PDF query: {str(e)}")
            return f"Error processing PDF query: {str(e)}"

    def _create_openai_client(self) -> OpenAI:
        """Initialize OpenAI client with configuration"""
        return OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        ) if self.config.base_url else OpenAI(api_key=self.config.api_key)

    def _load_and_preprocess_data(self) -> pd.DataFrame:
        """Load and preprocess the Excel data"""
        try:
            df = pd.read_excel(self.config.xlsx_path)
            return DataProcessor.preprocess_dataframe(df)  # 使用静态方法
        except Exception as e:
            raise RuntimeError(f"Error loading Excel file: {e}")

    def _query_openai(self, prompt: str) -> str:
        """Query OpenAI API with error handling"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini-2024-07-18",  # Update this to your specific model
                messages=[
                    {"role": "system", "content": self.prompts.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=1000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")

    def filter_data(self, question: str) -> pd.DataFrame:
        """Filter data based on question type"""
        # Try different query types
        comp_params = QueryParser.parse_comparison_query(question)  # 使用静态方法
        if comp_params:
            field_key, substance1, substance2 = comp_params
            filtered_df = self.df[self.df['CCDC_code'].isin([substance1, substance2])]
            if not filtered_df.empty:
                return filtered_df
        
        direct_params = QueryParser.parse_direct_query(question, self.df)  # 使用静态方法
        if direct_params:
            substance_code, field = direct_params
            filtered_df = self.df[self.df['CCDC_code'] == substance_code]
            if not filtered_df.empty:
                return filtered_df

        range_params = QueryParser.parse_range_query(question)  # 使用静态方法
        if range_params:
            field_key, lower, upper = range_params
            if field_key and field_key in self.df.columns:
                filtered_df = self.df[(self.df[field_key] >= lower) & 
                                    (self.df[field_key] <= upper)]
                if not filtered_df.empty:
                    return filtered_df
        
        return pd.DataFrame()

    def trigger_workflow(self, pdf_path: str) -> str:
        try:  ################################################################################
            base_output_dir = "/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/output"  
            input_dir = "/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/input"
            config_path = "/Users/linzuhong/学习文件/3-博/博四/C2ML/extrfinetune/config.json"
            system_file = "/Users/linzuhong/学习文件/3-博/博四/C2ML/extrfinetune/finetunetable/system198.txt"
            ccdc_data = "/Users/linzuhong/学习文件/3-博/博四/C2ML/datareading/ccdcdata.json"

            os.makedirs(input_dir, exist_ok=True)

            # 确定输入文件路径
            if pdf_path.endswith('.pdf'):  # PDF处理模式
                pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
                text_file = Path(input_dir) / f"{pdf_name}.txt"
                with open(text_file, 'w', encoding='utf-8') as f:
                    f.write(self.pdf_content[pdf_path]['text'])
                name = pdf_name
            else:  # CCDC代码处理模式
                name = pdf_path  # 直接使用输入作为名称（CCDC代码）
                text_file = Path(input_dir) / f"{name}.txt"
                if not os.path.exists(text_file):
                    return f"\n❌ Input file not found: {text_file}"

            # 创建工作流管理器并运行
            workflow_manager = MOFWorkflowManager(
                config_path=config_path,
                output_dir=base_output_dir
            )

            print("\n🔧 Debug information:")
            print(f"Input directory: {input_dir}")
            print(f"Output directory: {base_output_dir}")
            print(f"System file: {system_file}")
            print(f"CCDC data file: {ccdc_data}")
            
            # 文件检查
            print("\n📄 File checks:")
            print(f"Checking input file exists: {os.path.exists(text_file)}")
            if os.path.exists(text_file):
                with open(text_file, 'rb') as f:
                    first_bytes = f.read(50)
                    print(f"First bytes of file: {first_bytes}")
            print(f"Checking system file exists: {os.path.exists(system_file)}")
            print(f"Checking CCDC file exists: {os.path.exists(ccdc_data)}")

            print("\n🚀 Starting workflow processing...")
            
            final_state = workflow_manager.run(
                input_dir=str(input_dir),
                system_file=str(system_file),
                ccdc_data=str(ccdc_data)
            )

            if final_state and 'file_paths' in final_state:
                final_output_path = Path(final_state['file_paths']['final_output'])
                timestamp = '_'.join(final_output_path.stem.split('_')[-2:])
                txt_file = Path(base_output_dir) / "final" / "txt" / f"{name}_{timestamp}.txt"

                if txt_file.exists():
                    with open(txt_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    print(f"\n📄 Analysis Results:\n{'='*80}")
                    print(content)
                    print(f"{'='*80}\n")
                    print("\n2. To view structured results after analysis:")
                    print("   show structure")
                    return ""

                return f"⚠️ Analysis results file not found: {txt_file}"

            return "⚠️ Workflow completed but no output was generated."

        except Exception as e:
            print(f"\n❌ Error in workflow processing: {str(e)}")
            return f"❌ Error in workflow processing: {str(e)}"
    
    def show_structure(self) -> str:
        """显示最新的结构化结果"""
        try:
            # 修正: 使用正确的结构化输出目录路径
            structure_dir = Path("/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/output/final/structure")  ###########
            
            if not structure_dir.exists():
                return "❌ No structured results directory found at: {structure_dir}"
            
            # 获取最新的 md 文件
            md_files = list(structure_dir.glob("structure_output_*.md"))
            if not md_files:
                return "❌ No structured results found in directory"
            
            # 使用文件时间戳来确定最新文件
            latest_file = max(md_files, key=lambda p: p.stat().st_mtime)
            
            with open(latest_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                return "❌ The structured results file is empty."
            
            print(f"\n📊 Structured Analysis Results:\n{'='*80}")
            print(content)
            print(f"{'='*80}")
            return ""
            
        except Exception as e:
            return f"❌ Error accessing structured results: {str(e)}"

    def _load_cif_config(self) -> dict:
        """加载 CIF 相关配置"""
        cif_config_path = "/Users/linzuhong/学习文件/3-博/博四/C2ML/request/config.json"  ###########
        try:
            with open(cif_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading CIF config: {e}")
            raise
   
    def download_cif(self, ccdc_code: str) -> str:
        """下载指定CCDC编号的CIF文件"""
        try:
            cif_config = self._load_cif_config()
            
            downloader = HuggingFaceDatasetDownloader(
                config_path=cif_config,  # 传入配置字典
                download_folder=self.cif_folder
            )
            
            file_name = f"{ccdc_code}.cif"
            success = downloader.download_file(file_name)
            
            if success:
                return f"\n✅ Successfully downloaded CIF file for {ccdc_code}\n💡 To visualize the structure, type:\n   visualize {ccdc_code}"
            else:
                return f"\n❌ Failed to download CIF file for {ccdc_code}"
        except Exception as e:
            logging.error(f"Error downloading CIF file: {e}")
            return f"\n❌ Error downloading CIF file: {str(e)}"

    def visualize_structure(self, ccdc_code: str) -> str:
        """可视化指定CCDC编号的晶体结构"""
        try:
            # 确保使用相同的文件命名格式
            cif_path = os.path.join(self.cif_folder, f"{ccdc_code}.cif")
            
            # 添加调试信息
            print(f"Looking for CIF file at: {cif_path}")
            print(f"File exists: {os.path.exists(cif_path)}")
            
            if not os.path.exists(cif_path):
                return f"\n❌ CIF file not found for {ccdc_code}. Please download it first using 'download cif {ccdc_code}'"
                
            viewer = CrystalViewer(cif_path)
            structure = viewer.read_cif_file()
            
            if structure:
                html_content = viewer.generate_3dmol_html()
                if html_content:
                    app = QApplication([])
                    window = CrystalViewerApp(html_content)
                    window.show()
                    app.exec_()
                    return f"\n✅ Structure visualization completed for {ccdc_code}"
            
            return f"\n❌ Failed to visualize structure for {ccdc_code}"
        except Exception as e:
            logging.error(f"Error visualizing structure: {e}")
            return f"\n❌ Error visualizing structure: {str(e)}"

    def get_answer(self, question: str) -> str:
        try:
            # 首先检查合成相关的查询
            if "how to synthesize" in question.lower() or "synthesis of" in question.lower():
                # 清理问题文本，提取查询关键词
                search_terms = ['how', 'to', 'synthesize', 'synthesis', 'of', 'the', 'compound', 'material', 'mof']
                query = ' '.join(
                    word for word in question.lower().split() 
                    if word.strip('?.,!') not in search_terms
                ).strip()
                return self.get_synthesis_info(query)
                
            # 检查下载CIF文件的命令
            if question.lower().startswith('download cif'):
                ccdc_code = question.split()[-1].upper()
                return self.download_cif(ccdc_code)
                
            # 检查可视化结构的命令
            if question.lower().startswith('visualize'):
                ccdc_code = question.split()[-1].upper()
                return self.visualize_structure(ccdc_code)
                
            # 检查其他特定命令
            if question.lower().startswith('process pdf'):
                return None  # 让 main.py 处理输出
            elif question.lower().startswith('workflow'):
                return self.trigger_workflow(question.split(None, 1)[1])
            elif question.lower() == 'show structure':
                return self.show_structure()
                
            # 只有普通问题才进行 PDF 查询或其他处理
            if any(term in question.lower() for term in ['pdf', 'document', 'file', 'paper']):
                return self._handle_pdf_query(question)

            # 系统查询
            if any(phrase in question.lower() for phrase in [
                'what can you do', 'capabilities', 'help', 'how to use',
                'example', 'syntax', 'properties', 'available data'
            ]):
                return self._handle_system_query(question)

            # Use enhanced query handler for normal queries
            return self.query_handler.process_query(question)
            
        except Exception as e:
            logging.error(f"Error in get_answer: {e}")
            return f"查询处理出错: {str(e)}"

        except Exception as e:
            logging.error(f"Error in get_answer: {str(e)}")
            return f"查询处理出错: {str(e)}"
            
    def _handle_pdf_query(self, question: str) -> str:
        """Handle PDF-related queries"""
        if not self.pdf_content:
            return "No PDF documents have been processed yet."
            
        # Create context from PDF content
        context = "Available documents:\n"
        for path, info in self.pdf_content.items():
            context += f"- {info['filename']} ({info['metadata'].page_count} pages)\n"
        
        # Get response from OpenAI
        prompt = f"""
        Context: {context}
        PDF contents: {[info['text'] for info in self.pdf_content.values()]}
        Question: {question}
        """
        
        response = self._query_openai(prompt)
        return response

    def _handle_system_query(self, question: str) -> str:
        """Handle system-related questions"""
        question = question.lower()
        
        if any(phrase in question for phrase in [
            'what can you do', 'capabilities', 'help',
            'how to use', 'what are your functions',
            'how does this work', 'how do i use'
        ]):
            return self.prompts.HELP_INFO['capabilities']
        
        if any(phrase in question for phrase in [
            'example', 'show me how', 'how to ask',
            'syntax', 'format', 'how should i ask'
        ]):
            return self.prompts.HELP_INFO['examples']
        
        if any(phrase in question for phrase in [
            'properties', 'available data', 'what information',
            'what data', 'fields', 'what can i ask about'
        ]):
            return self.prompts.get_property_info()
        
        return "💤 Not sure what you're asking. Try 'help' for examples."