import os
import json
import re
import time
from typing import List, Dict, Optional
from openai import OpenAI
from tqdm import tqdm
from extrfinetune.prompt.elsehl import prompt_template
from extrfinetune.file_utils import list_visible_text_files

class AcronymExtractor:
    def __init__(self, config_path: str, input_folder: str, output_folder: str):
        """
        初始化缩写提取器
        :param config_path: 配置文件路径
        :param input_folder: 输入文件夹路径
        :param output_folder: 输出文件夹路径
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.api_key = config.get('openaiapikey')
        #self.base_url = config.get('baseurl')
        self.client = OpenAI(api_key=self.api_key)#, base_url=self.base_url)

        self.input_folder = input_folder
        self.output_folder = output_folder

        os.makedirs(self.output_folder, exist_ok=True)

    def call_openai_api_with_retries(self, messages, model="gpt-4o-2024-08-06", temperature=0, retries=3, delay=5):
        """
        带重试机制的 OpenAI API 调用
        """
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature
                )
                return response
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(delay)
                else:
                    raise e

    def extract_acronyms_and_full_names(self, file_content: str, file_name: str = "") -> List[Dict[str, str]]:
        """
        使用 OpenAI API 提取缩写和全称
        """
        abbreviation_pattern = r'\b(?:H\d*L\d*|L\d+H\d+|L\d+)\b'
        abbreviations = set(re.findall(abbreviation_pattern, file_content))

        if not abbreviations:
            return []

        prompt = prompt_template.replace("{{file_content}}", file_content)

        try:
            response = self.call_openai_api_with_retries(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant for extracting chemical abbreviations and their full names."},
                    {"role": "user", "content": prompt}
                ]
            )
            extraction_result = response.choices[0].message.content.strip()

            results = extraction_result.split('\n\n')

            formatted_results = []
            seen_pairs = set()
            for result in results:
                if result.strip():
                    parts = result.split('\n')
                    abbreviation = parts[0].strip()
                    full_name = parts[1].strip()
                    relationship_type = parts[2].strip()
                    if (abbreviation, full_name) not in seen_pairs:
                        formatted_results.append({
                            "abbreviation": abbreviation,
                            "full_name": full_name,
                            "relationship_type": relationship_type
                        })
                        seen_pairs.add((abbreviation, full_name))
            return formatted_results

        except Exception as e:
            print(f"❌ Error extracting data from {file_name}: {e}")
            return []

    def process_files(self) -> Dict[str, List[Dict[str, str]]]:
        """
        处理目录中的所有文件
        """
        all_results = {}
        files = list_visible_text_files(self.input_folder)

        with tqdm(total=len(files), desc="Processing files", unit="file") as pbar:
            for filename in files:
                file_path = os.path.join(self.input_folder, filename)

                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()

                acronyms = self.extract_acronyms_and_full_names(content, filename)

                if acronyms:
                    filename_without_ext = os.path.splitext(filename)[0]
                    all_results[filename_without_ext] = acronyms

                pbar.update(1)

        return all_results

    def save_results(self, results: Dict[str, List[Dict[str, str]]], output_filename: str = None):
        """
        保存结果到 JSON 文件
        """
        if not results:
            print("❓ No results to save.")
            return

        if not output_filename:
            output_filename = f"acronym_results_{int(time.time())}.json"
        output_path = os.path.join(self.output_folder, output_filename)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            print(f"💾 Results saved to {output_path}")
            return output_path
        except Exception as e:
            print(f"Error saving results to file {output_path}: {e}")
            return None

    def run(self):
        """
        执行完整的处理流程
        """
        results = self.process_files()
        return self.save_results(results)
