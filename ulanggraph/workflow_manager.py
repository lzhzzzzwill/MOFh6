from pathlib import Path
from typing import TypedDict, Dict, Any, List
from datetime import datetime
from langgraph.graph import StateGraph, END
import json
import re
from rank_bm25 import BM25Okapi

from ulanggraph.workflow_core import WorkflowBase
from ulanggraph.file_processor import FileProcessor
from ulanggraph.data_processorllm import DataProcessor
from extrfinetune.cftm import FineTunedModelProcessor
from extrfinetune.ctotable import ElsevierTableExtractor
from extrfinetune.cjtj import CrystalDataComparator
from extrfinetune.chl import AcronymExtractor
from extrfinetune.cstrucout import MOFDataProcessor 
from knowledge import KnowledgeStore, StructuredKnowledgeIngestor
from rag import MOFRAGService

class StateSchema(TypedDict):
    """工作流状态模式"""
    current_step: str
    timestamp: str
    data: Dict[str, Any]
    file_paths: Dict[str, Path]

class MOFWorkflowManager(WorkflowBase):
    """MOF工作流管理器"""
    def __init__(self, config_path: str, output_dir: str, rag_client: Any = None):
        super().__init__(config_path, output_dir)
        self.file_processor = FileProcessor(config_path, output_dir)
        self.data_processor = DataProcessor(config_path, output_dir)
        # Add structure directory to data_processor's output_dirs
        structure_dir = self.data_processor.output_dirs['final'] / 'structure'
        structure_dir.mkdir(exist_ok=True)
        self.data_processor.output_dirs['structure'] = structure_dir
        knowledge_dir = self.output_dir / 'knowledge'
        self.knowledge_store = KnowledgeStore(str(knowledge_dir / 'mofh6.db'))
        self.knowledge_ingestor = StructuredKnowledgeIngestor(self.knowledge_store, pubchem_enabled=True)
        self.rag_service = MOFRAGService(self.knowledge_store, rag_client)


    def process_text_with_bm25(self, text: str, abbreviations: Dict) -> str:
        """
        使用BM25算法处理文本中的缩写
        
        Args:
            text: 需要处理的文本
            abbreviations: 缩写词典数据
        
        Returns:
            处理后的文本
        """
        # 定义缩写模式
        patterns = [
            r'\b(?:H\d*L\d*)\b',    # 匹配 HL, H2L, HL2 等
            r'\b(?:L\d+)\b',        # 匹配 L1, L2 等
            r'\b(?:L\d+H\d+)\b',    # 匹配 L1H1, L2H2 等
            r'\bL\b'                # 匹配单个 L
        ]
        
        # 检查文本中是否存在匹配的模式
        has_patterns = any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
        if not has_patterns:
            return text
                
        # 提取所有可能的缩写
        all_abbreviations = []
        for identifier, abbr_list in abbreviations.items():
            for abbr_info in abbr_list:
                abbr = abbr_info['abbreviation'].replace('Abbreviation: ', '')
                full_name = abbr_info['full_name'].replace('Full Name: ', '')
                all_abbreviations.append((abbr, full_name))
        
        if not all_abbreviations:
            return text
                
        # 创建BM25语料库
        corpus = [abbr for abbr, _ in all_abbreviations]
        bm25 = BM25Okapi([list(abbr.lower()) for abbr in corpus])
        
        # 处理文本中的每个匹配项
        processed_text = text
        found_replacements = []
        
        for pattern in patterns:
            matches = list(re.finditer(pattern, processed_text))
            for match in reversed(matches):  # 从后向前处理，避免替换位置改变
                abbr = match.group()
                # 使用BM25搜索最匹配的缩写
                query = list(abbr.lower())
                scores = bm25.get_scores(query)
                
                # 将numpy数组转换为列表并找到最高分的索引
                scores_list = scores.tolist()
                if scores_list:
                    max_score = max(scores_list)
                    if max_score > 0.5:  # 设置相似度阈值
                        best_match_idx = scores_list.index(max_score)
                        original_abbr, full_name = all_abbreviations[best_match_idx]
                        
                        # 只有当缩写完全匹配时才添加到替换列表
                        if abbr.upper() == original_abbr.upper():
                            found_replacements.append((abbr, full_name))
        
        # 格式化输出
        if found_replacements:
            # 移除现有的缩写注释（如果有）
            lines = processed_text.split('\n')
            cleaned_lines = [line for line in lines 
                        if not (line.startswith('Abbreviation:') or 
                                line.startswith('Full Name:') or 
                                line.startswith('No abbreviations'))]
            
            # 添加新的缩写注释
            for abbr, full_name in sorted(set(found_replacements)):
                cleaned_lines.append(f"Abbreviation: {abbr}")
                cleaned_lines.append(f"Full Name: {full_name}")
                
            return '\n'.join(cleaned_lines)
        
        return text

    def process_synthesis(self, state: StateSchema) -> StateSchema:
        """处理合成数据"""
        print("\n🔄 Processing synthesis data...")
        processor = FineTunedModelProcessor(
            config_path=str(self.config_path),
            test_folder=str(state['file_paths']['input_dir']),
            system_file_path=str(state['file_paths']['system_file']),
            output_folder=str(self.data_processor.output_dirs['synthesis'])
        )
        
        results = processor.run()
        
        synthesis_files = list(self.data_processor.output_dirs['synthesis'].glob(
            f"testpredictions_shot198_{self.timestamp}*.xlsx"))
        
        if not synthesis_files:
            raise RuntimeError("No synthesis output file found")
            
        output_path = max(synthesis_files, key=lambda p: p.stat().st_mtime)
        print(f"✅ Synthesis processing complete. Output saved to: {output_path}")
        
        state['file_paths']['synthesis_output'] = output_path
        state['current_step'] = "extract_tables"
        return state

    def extract_tables(self, state: StateSchema) -> StateSchema:
        """提取表格数据"""
        print("\n🔄 Extracting tables...")
        output_file = self.data_processor.output_dirs['tables'] / f"tables_{self.timestamp}.json"
        
        extractor = ElsevierTableExtractor(
            config_path=str(self.config_path),
            input_folder=str(state['file_paths']['input_dir']),
            output_file=str(output_file)
        )
        
        results = extractor.run()
        state['file_paths']['tables_output'] = output_file
        print(f"✅ Table extraction complete. Output saved to: {output_file}")
        
        state['current_step'] = "compare_data"
        return state

    def compare_data(self, state: StateSchema) -> StateSchema:
        """比较数据"""
        print("\n🔄 Comparing data...")
        comparator = CrystalDataComparator(config_path=str(self.config_path))
        output_file = self.data_processor.output_dirs['comparison'] / f"comparison_{self.timestamp}.json"
        
        comparator.process(
            str(state['file_paths']['ccdc_data']),
            str(state['file_paths']['tables_output']),
            str(output_file)
        )
        
        state['file_paths']['comparison_output'] = output_file
        print(f"✅ Data comparison complete. Output saved to: {output_file}")
        
        state['current_step'] = "process_abbreviations"
        return state

    def process_abbreviations(self, state: StateSchema) -> StateSchema:
        """处理缩写"""
        print("\n🔄 Processing abbreviations...")
        try:
            # 获取合成数据
            synthesis_data = self.file_processor.get_synthesis_data(
                state['file_paths']['synthesis_output']
            )
            
            # 调用缩写提取器
            extractor = AcronymExtractor(
                config_path=str(self.config_path),
                input_folder=str(state['file_paths']['input_dir']),
                output_folder=str(self.data_processor.output_dirs['final'])
            )
            
            # 运行提取器并获取结果
            raw_results = extractor.run()
            
            # 检查返回值类型
            if isinstance(raw_results, str):
                print(f"⚠️ Unexpected result type from extractor: {raw_results}")
                # 尝试加载保存的JSON文件
                acronym_files = list(self.data_processor.output_dirs['final'].glob('acronym_results_*.json'))
                if acronym_files:
                    latest_file = max(acronym_files, key=lambda p: p.stat().st_mtime)
                    with open(latest_file, 'r', encoding='utf-8') as f:
                        raw_results = json.load(f)
                    print(f"✅ Successfully loaded results from {latest_file}")
                else:
                    print("❌ No acronym files found")
                    state['current_step'] = "generate_final_output"
                    return state
            
            # 处理和格式化结果
            formatted_results = {}
            if raw_results and isinstance(raw_results, dict):
                for identifier, abbr_list in raw_results.items():
                    if identifier and abbr_list:
                        # 确保每个缩写都有正确的格式
                        formatted_abbrs = []
                        for abbr in abbr_list:
                            if isinstance(abbr, dict):
                                # 如果已经是字典格式，验证并标准化格式
                                abbreviation = abbr.get('abbreviation', '')
                                full_name = abbr.get('full_name', '')
                                if abbreviation and not abbreviation.startswith('Abbreviation: '):
                                    abbreviation = f"Abbreviation: {abbreviation}"
                                if full_name and not full_name.startswith('Full Name: '):
                                    full_name = f"Full Name: {full_name}"
                                formatted_abbrs.append({
                                    'abbreviation': abbreviation,
                                    'full_name': full_name
                                })
                            elif isinstance(abbr, (list, tuple)) and len(abbr) == 2:
                                # 如果是元组或列表格式，转换为标准格式
                                formatted_abbrs.append({
                                    'abbreviation': f"Abbreviation: {abbr[0]}",
                                    'full_name': f"Full Name: {abbr[1]}"
                                })
                        
                        if formatted_abbrs:
                            formatted_results[identifier] = formatted_abbrs
            
            # 保存格式化后的结果
            if formatted_results:
                output_file = self.data_processor.output_dirs['final'] / f"acronym_results_{int(datetime.now().timestamp())}.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(formatted_results, f, indent=4, ensure_ascii=False)
                
                state['data']['abbreviations'] = formatted_results
                print(f"✅ Processed {len(formatted_results)} compounds with abbreviations")
                print(f"💾 Abbreviations saved to: {output_file}")
            else:
                print("⚠️ No valid abbreviations were extracted")
            
            state['current_step'] = "generate_final_output"
            return state
            
        except Exception as e:
            print(f"❌ Error in abbreviation processing: {str(e)}")
            if 'abbreviations' not in state['data']:
                state['data']['abbreviations'] = {}
            state['current_step'] = "generate_final_output"
            return state

    def generate_final_output(self, state: StateSchema) -> StateSchema:
        """生成最终输出"""
        print("\n🔄 Generating final output...")
        try:
            output_file = self.data_processor.output_dirs['final'] / f"final_output_{self.timestamp}.txt"
            
            comparison_data = self.file_processor.read_file(state['file_paths']['comparison_output'])
            synthesis_data = self.file_processor.get_synthesis_data(state['file_paths']['synthesis_output'])
            
            final_output = self.data_processor.format_final_output(
                comparison_data,
                synthesis_data,
                state['data'].get('abbreviations')
            )
            
            if final_output is None:
                final_output = "Error: No output generated"
            elif not isinstance(final_output, str):
                final_output = str(final_output)
                
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(final_output)
                
            state['file_paths']['final_output'] = output_file
            print(f"✅ Final output generated and saved to: {output_file}")
            
            state['current_step'] = "post_process_final_output"
            return state
            
        except Exception as e:
            print(f"❌ Error generating final output: {e}")
            error_output = self.data_processor.output_dirs['final'] / f"final_output_error_{self.timestamp}.txt"
            with open(error_output, 'w', encoding='utf-8') as f:
                f.write(f"Error occurred: {str(e)}")
            state['file_paths']['final_output'] = error_output
            state['current_step'] = "post_process_final_output"
            return state

    def post_process_final_output(self, state: StateSchema) -> StateSchema:
        """处理最终输出文件"""
        print("\n🔄 Post-processing final output...")
        try:
            if 'final_output' not in state['file_paths']:
                print("❌ No final output file found in state")
                state['current_step'] = END
                return state

            # 创建txt子文件夹
            txt_output_dir = self.data_processor.output_dirs['final'] / 'txt'
            txt_output_dir.mkdir(exist_ok=True)
            print(f"📁 Created TXT output directory: {txt_output_dir}")

            # 读取原始输出文件
            output_file = state['file_paths']['final_output']
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 读取缩写数据
            acronym_files = list(self.data_processor.output_dirs['final'].glob('acronym_results_*.json'))
            
            # 初始化processed_outputs列表
            processed_files = []

            # 处理每个段落并按文件分组
            sections = content.split('\n\n')
            file_sections = {}

            for section in sections:
                if not section.strip():
                    continue
                    
                # 获取标识符（文件名）
                identifier = section.split('\n')[0].strip()

                # 创建输出文件名
                output_filename = f"{identifier}_{self.timestamp}.txt"
                output_path = txt_output_dir / output_filename
                
                # 保存内容到文件
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(section)
                
                processed_files.append(output_path)
                print(f"💾 Processed output for {identifier} saved to: {output_path}")

            # 保存一个汇总信息文件
            summary_file = self.data_processor.output_dirs['final'] / f"processing_summary_{self.timestamp}.txt"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"Processing Summary\n")
                f.write(f"Timestamp: {self.timestamp}\n")
                f.write(f"Total files processed: {len(processed_files)}\n")
                f.write("\nProcessed Files:\n")
                for file in processed_files:
                    f.write(f"- {file.name}\n")

            # 更新状态
            state['file_paths']['processed_outputs'] = processed_files
            state['file_paths']['summary_file'] = summary_file
            
            print(f"📁 Generated {len(processed_files)} individual output files in {txt_output_dir}")
            print(f"📋 Summary saved to: {summary_file}")

            state['current_step'] = "process_to_structure"
            return state

        except Exception as e:
            print(f"❌ Error in post processing: {e}")
            state['current_step'] = "process_to_structure"
            return state
            
    def process_to_structure(self, state: StateSchema) -> StateSchema:
        """Convert processed output files to structured Markdown format"""
        print("\n🔄 Converting outputs to structured Markdown format...")
        try:
            if 'processed_outputs' not in state['file_paths'] or not state['file_paths']['processed_outputs']:
                print("❌ No processed output files found")
                state['current_step'] = END
                return state

            # Get the directory containing processed txt files
            txt_dir = state['file_paths']['processed_outputs'][0].parent
            
            # Initialize MOF data processor
            mof_processor = MOFDataProcessor(str(self.config_path))
            
            # Set output markdown file path
            structure_output = self.data_processor.output_dirs['structure'] / f"structure_output_{self.timestamp}.md"
            
            try:
                print(f"📝 Processing files from: {txt_dir}")
                print(f"📂 Found {len(state['file_paths']['processed_outputs'])} files to process")
                
                mof_processor.process_directory(
                    str(txt_dir),
                    str(structure_output)
                )
                
                state['file_paths']['structure_output'] = structure_output
                print(f"✅ Structure processing complete. Output saved to: {structure_output}")
                
            except Exception as e:
                print(f"❌ Error during structure processing: {e}")
                raise
            
            state['current_step'] = "update_knowledge_base"
            return state

        except Exception as e:
            print(f"❌ Error in structure processing: {e}")
            state['current_step'] = "update_knowledge_base"
            return state

    def update_knowledge_base(self, state: StateSchema) -> StateSchema:
        """Incrementally index source texts and structured synthesis/crystal artifacts."""
        print("\n🧠 Updating persistent RAG index and knowledge graph...")
        summary: Dict[str, Any] = {}
        try:
            input_dir = state['file_paths'].get('input_dir')
            if input_dir:
                summary['rag'] = self.rag_service.ingest_path(str(input_dir))

            identifiers = set()
            structure_output = state['file_paths'].get('structure_output')
            if structure_output and Path(structure_output).exists():
                structure_text = Path(structure_output).read_text(encoding='utf-8')
                identifiers.update(
                    value.strip().upper()
                    for value in re.findall(r'^# Identifier:\s*(.+)$', structure_text, flags=re.M)
                )

            tables_output = state['file_paths'].get('tables_output')
            if tables_output and Path(tables_output).exists():
                tables_data = json.loads(Path(tables_output).read_text(encoding='utf-8'))
                if isinstance(tables_data, dict):
                    identifiers.update(str(key).strip().upper() for key in tables_data)

            ccdc_data = state['file_paths'].get('ccdc_data')
            if ccdc_data and Path(ccdc_data).exists() and identifiers:
                summary['ccdc_graph'] = self.knowledge_ingestor.ingest_ccdc_metadata(
                    str(ccdc_data), sorted(identifiers)
                )

            if tables_output and Path(tables_output).exists():
                comparison_output = state['file_paths'].get('comparison_output')
                summary['crystal_graph'] = self.knowledge_ingestor.ingest_crystal_json(
                    str(tables_output),
                    selection_path=str(comparison_output) if comparison_output else None,
                    ccdc_path=str(ccdc_data) if ccdc_data else None,
                )

            if structure_output and Path(structure_output).exists():
                compound_labels = {}
                for identifier in identifiers:
                    identity = self.rag_service._target_identity(identifier)
                    labels = identity.get('article_compound_labels') or []
                    if labels:
                        compound_labels[identifier] = labels
                summary['synthesis_graph'] = self.knowledge_ingestor.ingest_synthesis_markdown(
                    str(structure_output), compound_labels=compound_labels
                )

            literature_results = []
            for identifier in sorted(identifiers):
                try:
                    literature_results.append(
                        self.rag_service.extract_literature_summary(identifier)
                    )
                except Exception as exc:
                    literature_results.append({
                        'status': 'error', 'target': identifier, 'reason': str(exc)
                    })
            if literature_results:
                summary['literature_graph'] = literature_results

            summary['stats'] = self.knowledge_store.stats()
            state['data']['knowledge_update'] = summary
            state['file_paths']['knowledge_db'] = self.knowledge_store.db_path
            print(f"✅ Knowledge base updated: {summary['stats']}")
        except Exception as e:
            state['data']['knowledge_update_error'] = str(e)
            print(f"⚠️ Knowledge base update failed without discarding workflow outputs: {e}")
        state['current_step'] = END
        return state

    def create_workflow(self) -> StateGraph:
        """创建工作流图"""
        workflow = StateGraph(state_schema=StateSchema)
        
        # Add all nodes
        workflow.add_node("process_synthesis", self.process_synthesis)
        workflow.add_node("extract_tables", self.extract_tables)
        workflow.add_node("compare_data", self.compare_data)
        workflow.add_node("process_abbreviations", self.process_abbreviations)
        workflow.add_node("generate_final_output", self.generate_final_output)
        workflow.add_node("post_process_final_output", self.post_process_final_output)
        workflow.add_node("process_to_structure", self.process_to_structure)  # Add new node
        workflow.add_node("update_knowledge_base", self.update_knowledge_base)
        
        # Set workflow sequence
        workflow.set_entry_point("process_synthesis")
        workflow.add_edge("process_synthesis", "extract_tables")
        workflow.add_edge("extract_tables", "compare_data")
        workflow.add_edge("compare_data", "process_abbreviations")
        workflow.add_edge("process_abbreviations", "generate_final_output")
        workflow.add_edge("generate_final_output", "post_process_final_output")
        workflow.add_edge("post_process_final_output", "process_to_structure")  # Add new edge
        workflow.add_edge("process_to_structure", "update_knowledge_base")
        workflow.add_edge("update_knowledge_base", END)
        
        return workflow.compile()

    def run(self, input_dir: str, system_file: str, ccdc_data: str):
        """运行完整工作流"""
        print("\n🚀 Starting MOF workflow...")
        
        initial_state: StateSchema = {
            "current_step": "process_synthesis",
            "timestamp": self.timestamp,
            "data": {},
            "file_paths": {
                'input_dir': Path(input_dir),
                'system_file': Path(system_file),
                'ccdc_data': Path(ccdc_data)
            }
        }
        
        
        workflow = self.create_workflow()
        try:
            final_state = workflow.invoke(initial_state)
            print(f"\n✨ Workflow completed successfully!")
            print(f"📄 Final output saved to: {final_state['file_paths']['final_output']}")
            return final_state
        except Exception as e:
            print(f"\n❌ Workflow failed: {str(e)}")
            raise
