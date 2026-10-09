import os
import re
import sys
import logging
import json
import pandas as pd
from dataclasses import asdict
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
from knowledge import KnowledgeStore, StructuredKnowledgeIngestor, similar_cases, recommend_cases
from knowledge.ingredient_qa import IngredientCaseQA
from rag import MOFRAGService

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
            self.active_rag_context: Optional[str] = None
            # 添加CIF文件目录配置
            self.cif_folder = "./cif_files" ######/Users/linzuhong/学习文件/3-博/博四/C2ML/cif_files
            os.makedirs(self.cif_folder, exist_ok=True) 
            # 添加输出目录配置
            self.output_dir = os.path.join(os.path.dirname(config.xlsx_path), "processed_pdfs")
            os.makedirs(self.output_dir, exist_ok=True)
            # 添加时间戳属性
            self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Persistent literature RAG and incremental knowledge graph.
            knowledge_dir = project_root / "ulanggraph" / "output" / "knowledge"
            self.knowledge_store = KnowledgeStore(str(knowledge_dir / "mofh6.db"))
            self.knowledge_ingestor = StructuredKnowledgeIngestor(self.knowledge_store, pubchem_enabled=True)
            self.rag = MOFRAGService(self.knowledge_store, self.client)
            self.ingredient_qa = IngredientCaseQA(self.knowledge_store, self.rag)
            try:
                embedding_status = self.rag.ensure_embeddings()
                if embedding_status["embedded"]:
                    logging.info(
                        "Backfilled %s literature embeddings with %s",
                        embedding_status["embedded"],
                        self.rag.embedding_model,
                    )
            except Exception as embedding_error:
                logging.warning(f"Embedding backfill deferred: {embedding_error}")

    def get_synthesis_info(self, query: str, language: str = "en") -> str:
        """搜索并获取化合物的合成信息"""
        try:
            # 读取元数据文件
            metadata_path = "./datareading/Dataset/metadata.xlsx"  #######/Users/linzuhong/学习文件/3-博/博四/C2ML/datareading/Dataset/metadata.xlsx
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
            temp_dir = "./ulanggraph/temp"  #######"/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/temp" 
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

            ccdc_code = str(compound_data['CCDC_code'].iloc[0]).upper()
            self.active_rag_context = ccdc_code
            doi = str(compound_data['DOI'].iloc[0])
            downloaded_text = project_root / "ulanggraph" / "input" / f"{ccdc_code}.txt"
            if downloaded_text.exists():
                try:
                    self.rag.ingest_document(
                        str(downloaded_text),
                        title=f"{ccdc_code} literature",
                        doi=doi,
                        metadata={"ccdc_code": ccdc_code, "stage": "downloaded"},
                    )
                except Exception as rag_error:
                    logging.warning(f"Downloaded literature could not be indexed for RAG: {rag_error}")
            
            # 清理临时文件（可选）
            # if os.path.exists(temp_file):
            #     os.remove(temp_file)
            
            if language == "zh":
                return (
                    f"\n✅ 文献获取已完成"
                    f"\n🧪 请使用 'workflow {ccdc_code}' 抽取结构化合成条件。"
                )
            return (
                f"\n✅ Literature retrieval completed"
                f"\n🧪 Run 'workflow {ccdc_code}' to extract structured synthesis data."
            )
            
        except Exception as e:
            logging.error(f"Error retrieving synthesis info: {e}")
            return f"\n❌ Error retrieving synthesis information: {str(e)}"
        
    def process_pdf(self, pdf_path: str) -> Optional[dict]:
        """Process uploaded PDF and store its content"""
        try:
            if not os.path.exists(pdf_path):
                logging.error(f"File not found: {pdf_path}")
                return None

            input_dir = "./ulanggraph/input" #####"/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/input"
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

                # Persist page-aware chunks immediately; reprocessing the same path is idempotent.
                self.rag.ingest_document(
                    source_path=pdf_path,
                    text=text,
                    title=metadata.title or pdf_info['filename'],
                    metadata=asdict(metadata)
                )
                
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
        """Handle PDF questions through chunk retrieval instead of full-document prompting."""
        try:
            return self.rag.ask(question, entity_key=self._find_graph_entity(question))
        except Exception as e:
            logging.error(f"Error handling RAG query: {str(e)}")
            return f"Error processing literature query: {str(e)}"

    def _find_graph_entity(self, text: str) -> Optional[str]:
        """Find a graph entity mentioned in user text without another LLM call."""
        candidates = re.findall(r'\b[A-Za-z][A-Za-z0-9_-]{3,}\b', text)
        ignored = {
            'something', 'anything', 'about', 'storage', 'adsorption', 'material',
            'framework', 'compound', 'please', 'could', 'would', 'what', 'which',
        }
        try:
            for candidate in candidates:
                if candidate.lower() in ignored:
                    continue
                resolver = getattr(self.knowledge_store, 'resolve_exact_entity', None)
                if resolver:
                    resolved = resolver(candidate)
                    if resolved:
                        return resolved
                elif self.knowledge_store.graph_context(candidate, limit=1)['nodes']:
                    return candidate
        except Exception as e:
            logging.warning(f"Knowledge graph lookup unavailable: {e}")
        return None

    @staticmethod
    def _is_system_query(text: str) -> bool:
        """Recognize help requests without treating scientific 'properties' questions as help."""
        return any(phrase in text.lower() for phrase in (
            'what can you do', 'capabilities', 'help', 'how to use',
            'show me an example', 'command syntax', 'available commands',
            '你能做什么', '帮助', '怎么使用', '命令格式',
        ))

    @staticmethod
    def _is_material_overview_question(question: str, entity: str) -> bool:
        """A broad material introduction is not a missing specific measurement."""
        remainder = re.sub(re.escape(entity), "", question, flags=re.I)
        remainder = re.sub(r"[^a-z\u4e00-\u9fff]+", " ", remainder.lower()).strip()
        return remainder in {
            "what about", "tell me about", "tell me abou", "describe", "overview",
            "give me an overview of", "introduce", "介绍", "请介绍", "介绍一下",
            "说说", "讲讲", "是什么", "有什么信息",
        }

    def _natural_rag_context(self, question: str) -> Optional[str]:
        """Resolve natural paper questions without requiring a visible RAG command."""
        entity = self._find_graph_entity(question)
        if entity:
            self.active_rag_context = entity
            return entity
        # A CCDC refcode can be asked about before its structured graph is built.
        # RAG will then search only that refcode's document and abstain if absent.
        for code in re.findall(r'(?<![A-Za-z0-9])[A-Z]{6}(?![A-Za-z0-9])', question):
            if code not in {'PLEASE', 'LIGAND', 'METALS', 'SOLVENT'}:
                self.active_rag_context = code
                return code
        if not self.active_rag_context:
            return None
        normalized_question = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '', question.lower())
        try:
            for item in self.knowledge_store.list_suggestions(self.active_rag_context):
                shown = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '', item['question'].lower())
                if shown and normalized_question == shown:
                    return self.active_rag_context
        except Exception as suggestion_error:
            logging.debug(f"Suggestion route lookup unavailable: {suggestion_error}")
        lower = question.lower()
        follow_up_markers = (
            ' it ', ' its ', 'this material', 'this framework', 'this compound',
            'the material', 'the framework', 'what about', 'how about',
            '它', '该材料', '这个材料', '该框架', '这个框架', '那么',
        )
        research_terms = (
            'topology', 'structure', 'framework', 'stability', 'characterization',
            'spectroscopy', 'diffraction', 'mechanism', 'application', 'performance',
            'adsorption', 'catalysis', 'conductivity', 'luminescence', 'magnetic',
            'porosity', 'evidence', 'reported', 'compare', 'limitation',
            'synthesis', 'temperature', 'yield', 'solvent', 'linker', 'crystal',
            'coordination', 'geometry', 'donor', 'nitrate', 'aromatic', 'interaction',
            'assembly', 'metal center', 'bond length', 'bond angle', 'dimensionality',
            'symmetry', 'complex 1', 'complex 2', 'complex 3',
            '拓扑', '结构', '框架', '稳定性', '表征', '光谱', '衍射', '机理',
            '应用', '性能', '吸附', '催化', '导电', '发光', '磁性', '孔隙',
            '证据', '报道', '比较', '局限', '合成', '温度', '产率', '溶剂', '配体', '晶体',
            '配位', '几何', '给体', '硝酸根', '芳环', '相互作用', '组装', '键长', '键角', '维度', '对称性',
        )
        padded = f" {lower} "
        if any(marker in padded for marker in follow_up_markers):
            return self.active_rag_context
        if any(term in lower for term in research_terms):
            return self.active_rag_context
        return None

    def ingest_rag_path(self, path: str) -> str:
        try:
            result = self.rag.ingest_path(path)
            return f"✅ RAG indexing complete: {json.dumps(result, ensure_ascii=False)}"
        except Exception as e:
            return f"❌ RAG indexing failed: {e}"

    def update_graph_from_artifact(self, path: str) -> str:
        try:
            if path.lower().endswith('.md'):
                result = self.knowledge_ingestor.ingest_synthesis_markdown(path)
            elif path.lower().endswith('.json'):
                result = self.knowledge_ingestor.ingest_crystal_json(path)
            else:
                return "❌ Graph update supports .md synthesis tables or .json crystal tables."
            return f"✅ Knowledge graph updated: {json.dumps(result, ensure_ascii=False)}"
        except Exception as e:
            return f"❌ Knowledge graph update failed: {e}"

    def show_similar_mofs(self, code: str, language: str = "en") -> str:
        cases = similar_cases(self.knowledge_store, code, limit=4)
        if not cases:
            return (f"没有找到与 {code.upper()} 合成路线足够相似的已报道材料。"
                    if language == "zh" else
                    f"No reported MOF with a sufficiently similar synthesis route was found for {code.upper()}.")
        lines = [f"{code.upper()} 的相似合成路线：" if language == "zh"
                 else f"Synthesis routes similar to {code.upper()}:"]
        for case in cases:
            shared = case.get("shared") or {}
            reasons = "; ".join(
                f"{field.replace('_', ' ')}: {', '.join(values)}"
                for field, values in shared.items() if values
            )
            lines.append(f"- {case['mof']} ({case['score']:.2f}): {reasons}. "
                         f"{case['paper']}")
        return "\n".join(lines)

    def show_case_recommendation(self, code: str, language: str = "en") -> str:
        result = recommend_cases(self.knowledge_store, code)
        if result["status"] == "unknown_mof":
            return f"MOF not found: {code}" if language == "en" else f"未找到材料：{code}"
        if not result["cases"]:
            return (f"没有足够相似的独立合成案例可供 {code.upper()} 参考。"
                    if language == "zh" else
                    f"No sufficiently similar independent synthesis cases are available for {code.upper()}.")
        lines = [f"{code.upper()} 的已报道合成参考案例：" if language == "zh"
                 else f"Reported synthesis cases relevant to {code.upper()}:"]
        for case in result["cases"]:
            conditions = []
            if case["temperature_c"] is not None:
                conditions.append(f"{case['temperature_c']:g} °C")
            if case["time_hours"] is not None:
                conditions.append(f"{case['time_hours']:g} h")
            if case["solvents"]:
                conditions.append("/".join(case["solvents"]))
            lines.append(f"- {case['mof']} (similarity {case['score']:.2f}): "
                         f"{', '.join(conditions)}; source: {case['paper']}")
        if result["status"] == "limited_cases":
            lines.append("独立案例少于3个，暂不建议数值范围。" if language == "zh" else
                         "Fewer than three independent cases; no numeric range is recommended.")
        else:
            for key, label, unit in (
                ("temperature_range_c", "Temperature", "°C"),
                ("time_range_hours", "Time", "h"),
            ):
                bounds = result.get(key) or []
                if len(bounds) == 2 and all(value is not None for value in bounds):
                    lines.append(f"{label}: {bounds[0]:g}–{bounds[1]:g} {unit}")
            if result.get("solvent_systems"):
                lines.append("Reported solvent systems: " + "; ".join(result["solvent_systems"]))
            lines.append("These are published case ranges, not a predicted guarantee of synthesis success.")
        return "\n".join(lines)

    def show_raw_graph_context(self, key: str) -> str:
        context = self.knowledge_store.graph_context(key)
        if not context['nodes']:
            return f"No graph entity found for: {key}"
        lines = [f"Knowledge graph context for {key}:"]
        for node in context['nodes']:
            lines.append(f"- [{node['node_type']}] {node['label']}: {node['properties']}")
        for edge in context['edges']:
            lines.append(
                f"- {edge['source_label']} --{edge['edge_type']}--> {edge['target_label']}"
                f" {edge['properties'] if edge['properties'] else ''}"
            )
        return '\n'.join(lines)

    def show_graph_context(self, key: str, language: str = "en") -> str:
        """Show a researcher-facing natural-language graph summary."""
        try:
            self.active_rag_context = key.upper()
            summary = self.rag.describe_graph(key, language=language)
            title = "知识图谱解读" if language == "zh" else "knowledge-graph summary"
            next_step = (
                f"💡 可继续输入: suggest questions {key.upper()}" if language == "zh"
                else f"💡 Next: suggest questions {key.upper()}"
            )
            return (
                f"🕸️  {key.upper()} {title}\n"
                f"{'=' * 72}\n{summary}\n{'=' * 72}\n"
                f"{next_step}"
            )
        except Exception as e:
            logging.warning(f"Natural-language graph rendering failed: {e}")
            return self.show_raw_graph_context(key)

    @staticmethod
    def _format_rag_suggestions(
        context_key: str,
        suggestions: List[Dict],
        heading: str = "",
        language: str = "en",
    ) -> str:
        if not suggestions:
            return (
                f"暂时没有为 {context_key} 生成可靠的推荐问题。"
                if language == "zh" else
                f"No sufficiently supported questions were generated for {context_key}."
            )
        default_heading = (
            f"基于 {context_key} 可继续探索：" if language == "zh"
            else f"Questions to explore for {context_key}:"
        )
        lines = [heading or default_heading]
        for index, item in enumerate(suggestions, start=1):
            question = item['question']
            reason = str(item.get('reason') or '').strip()
            lines.append(f"{index}. {question}" + (f"\n   — {reason}" if reason else ""))
        return '\n'.join(lines)

    def suggest_rag_questions(self, context_key: str, language: str = "en") -> str:
        try:
            self.active_rag_context = context_key.upper()
            graph = self.knowledge_store.graph_context(context_key, limit=30)
            structured_edges = {"HAS_SYNTHESIS", "HAS_CRYSTAL_DATA"}
            stage = (
                "workflow"
                if any(edge.get("edge_type") in structured_edges for edge in graph.get("edges", []))
                else "general"
            )
            suggestions = self.rag.suggest_questions(
                context_key, language=language, stage=stage
            )
            if not suggestions:
                return "No evidence-backed questions could be generated for this context."
            return self._format_rag_suggestions(context_key, suggestions, language=language)
        except Exception as e:
            return f"❌ Question suggestion failed: {e}"

    def _create_openai_client(self) -> OpenAI:
        """Initialize OpenAI client with configuration"""
        return OpenAI(
            api_key=self.config.api_key#,
 #           base_url=self.config.base_url
        ) #if self.config.base_url else OpenAI(api_key=self.config.api_key)

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

    def trigger_workflow(self, pdf_path: str, language: str = "en") -> str:
        try:  ################################################################################
            base_output_dir = "./ulanggraph/output"  #########"/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/output"
            input_dir = "./ulanggraph/input"         #########"/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/input"  
            config_path = "./extrfinetune/config.json"#########"/Users/linzuhong/学习文件/3-博/博四/C2ML/extrfinetune/config.json"
            system_file = "./extrfinetune/finetunetable/system198.txt"#########"/Users/linzuhong/学习文件/3-博/博四/C2ML/extrfinetune/finetunetable/system198.txt"
            ccdc_data = "./datareading/des_mate.json"

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
            self.active_rag_context = name.upper()

            # 创建工作流管理器并运行
            workflow_manager = MOFWorkflowManager(
                config_path=config_path,
                output_dir=base_output_dir,
                rag_client=self.client,
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
                    if language == "zh":
                        print("\n📚 下一步：")
                        print("1. 查看结构化合成表：show structure")
                        print(f"2. 查看知识图谱摘要：graph show {name}")
                    else:
                        print("\n📚 Next steps:")
                        print("1. View the structured synthesis table: show structure")
                        print(f"2. View the knowledge-graph summary: graph show {name}")
                    try:
                        suggestions = self.rag.suggest_questions(
                            name, language=language, stage="workflow"
                        )
                        print()
                        print(self._format_rag_suggestions(
                            name,
                            suggestions,
                            language=language,
                            heading=(
                                "结构化分析后可进一步探索：" if language == "zh"
                                else "Further questions enabled by the structured analysis:"
                            ),
                        ))
                    except Exception as suggestion_error:
                        logging.warning(f"Post-workflow question suggestion failed: {suggestion_error}")
                        print(f"3. suggest questions {name}")
                    return ""

                return f"⚠️ Analysis results file not found: {txt_file}"

            return "⚠️ Workflow completed but no output was generated."

        except Exception as e:
            print(f"\n❌ Error in workflow processing: {str(e)}")
            return f"❌ Error in workflow processing: {str(e)}"
    
    def show_structure(self, language: str = "en") -> str:
        """显示最新的结构化结果"""
        try:
            # 修正: 使用正确的结构化输出目录路径
            structure_dir = Path("./ulanggraph/output/final/structure")  ###########"/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/output/final/structure"
            
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
            identifiers = re.findall(r'^# Identifier:\s*(.+?)\s*$', content, flags=re.MULTILINE)
            if identifiers:
                key = identifiers[0].strip()
                print("\n💡 可以继续：" if language == "zh" else "\n💡 Next:")
                print(f"   suggest questions {key}")
                print(f"   graph show {key}")
                example = (
                    f"{key} 的结构–性能关系有哪些文献证据？" if language == "zh"
                    else f"What evidence links the structure of {key} to its reported properties?"
                )
                print(f"   rag ask {example}")
            return ""
            
        except Exception as e:
            return f"❌ Error accessing structured results: {str(e)}"

    def _load_cif_config(self) -> dict:
        """加载 CIF 相关配置"""
        cif_config_path = "./request/config.json"  ###########"/Users/linzuhong/学习文件/3-博/博四/C2ML/request/config.json"
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
            lower = question.lower().strip()
            language = self.rag.language_for(question)

            if lower.startswith('rag ingest '):
                return self.ingest_rag_path(question[len('rag ingest '):].strip())
            if lower.startswith('rag ask '):
                rag_question = question[len('rag ask '):].strip()
                context = self._find_graph_entity(rag_question) or self.active_rag_context
                if context:
                    self.active_rag_context = context
                return self.rag.ask(rag_question, entity_key=context)
            if lower.startswith('ask papers '):
                rag_question = question[len('ask papers '):].strip()
                context = self._find_graph_entity(rag_question) or self.active_rag_context
                if context:
                    self.active_rag_context = context
                return self.rag.ask(rag_question, entity_key=context)
            if lower in {'clear context', 'forget current paper', '清除上下文', '忘记当前文献'}:
                self.active_rag_context = None
                return "Context cleared." if language == "en" else "已清除当前文献上下文。"
            if lower.startswith('suggest questions'):
                context_key = question[len('suggest questions'):].strip()
                if not context_key:
                    return (
                        "请提供 MOF 标识符或研究主题。" if language == "zh"
                        else "Please provide a MOF identifier or research topic."
                    )
                return self.suggest_rag_questions(context_key, language=language)
            if lower == 'graph stats':
                return json.dumps(self.knowledge_store.stats(), ensure_ascii=False, indent=2)
            if lower.startswith('graph raw '):
                return self.show_raw_graph_context(question[len('graph raw '):].strip())
            if lower.startswith('graph show '):
                return self.show_graph_context(
                    question[len('graph show '):].strip(), language=language
                )
            if lower.startswith('graph similar '):
                return self.show_similar_mofs(
                    question[len('graph similar '):].strip(), language=language
                )
            if lower.startswith('graph recommend '):
                return self.show_case_recommendation(
                    question[len('graph recommend '):].strip(), language=language
                )
            if lower.startswith('graph update '):
                return self.update_graph_from_artifact(question[len('graph update '):].strip())

            # 显式工作流命令必须先于知识图谱的自然语言路由。
            # 这样首次下载论文时，即使知识库目录尚未建立也不会被拦截。
            if "how to synthesize" in lower or "synthesis of" in lower:
                # 清理问题文本，提取查询关键词
                search_terms = ['how', 'to', 'synthesize', 'synthesis', 'of', 'the', 'compound', 'material', 'mof']
                query = ' '.join(
                    word for word in lower.split()
                    if word.strip('?.,!') not in search_terms
                ).strip()
                return self.get_synthesis_info(query, language=language)
                
            # 检查下载CIF文件的命令
            if lower.startswith('download cif'):
                ccdc_code = question.split()[-1].upper()
                return self.download_cif(ccdc_code)
                
            # 检查可视化结构的命令
            if lower.startswith('visualize'):
                ccdc_code = question.split()[-1].upper()
                return self.visualize_structure(ccdc_code)
                
            # 检查其他特定命令
            if lower.startswith('process pdf'):
                return None  # 让 main.py 处理输出
            elif lower.startswith('workflow'):
                parts = question.split(None, 1)
                if len(parts) < 2 or not parts[1].strip():
                    return (
                        "请提供 CCDC 编号或已处理 PDF 的路径，例如：workflow ABAYUY"
                        if language == "zh" else
                        "Provide a CCDC code or processed PDF path, for example: workflow ABAYUY"
                    )
                return self.trigger_workflow(parts[1].strip(), language=language)
            elif lower == 'show structure':
                return self.show_structure(language=language)

            if self._is_system_query(question):
                return self._handle_system_query(question)

            ingredient_request = self.ingredient_qa.classify(question)
            if ingredient_request["intent"] == "reagent_to_mof":
                return self.ingredient_qa.answer(
                    question, language=language, extracted=ingredient_request
                )

            natural_context = self._natural_rag_context(question)
            if natural_context:
                if self._is_material_overview_question(question, natural_context):
                    graph = self.knowledge_store.graph_context(natural_context, limit=1)
                    if graph.get("nodes"):
                        return self.rag.describe_graph(natural_context, language=language)
                return self.rag.ask(question, entity_key=natural_context)
                
            # 只有普通问题才进行 PDF 查询或其他处理
            if any(term in question.lower() for term in ['pdf', 'document', 'file', 'paper', '论文', '文献']):
                return self._handle_pdf_query(question)

            # Use enhanced query handler for normal queries
            return self.query_handler.process_query(question)
            
        except Exception as e:
            logging.error(f"Error in get_answer: {e}")
            return f"查询处理出错: {str(e)}"

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
