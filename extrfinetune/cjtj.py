import os
import json
import re
import time
from typing import List, Dict
from openai import OpenAI
from tqdm import tqdm
from datetime import datetime
from extrfinetune.prompt.jtjprompt import prompt_template

class CrystalDataComparator:
    """晶体数据比对类"""
    def __init__(self, config_path: str):
        # 加载配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.api_key = config.get('apikey')
        self.base_url = config.get('baseurl')
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    @staticmethod
    def load_json(file_path: str) -> dict:
        """加载 JSON 文件"""
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)

    @staticmethod
    def extract_json_content(response_text: str) -> dict:
        """从模型回复中提取 JSON 对象"""
        json_match = re.search(r'\{[\s\S]*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                tqdm.write(f"JSON解析错误: {e}")
                tqdm.write(f"完整的模型响应: {response_text}")
                return None
        else:
            tqdm.write("未找到有效的 JSON 数据")
            tqdm.write(f"完整的模型响应: {response_text}")
            return None

    @staticmethod
    def normalize_space_group(value):
        """标准化 Space group 格式"""
        if value:
            return re.sub(r"[\s¯-]", "", value).upper()
        return value

    def call_openai_api_with_retries(self, messages, model="gpt-4o-2024-08-06", retries=3, delay=5):  #gpt-4o-2024-08-06/gpt-4o-mini-2024-07-18
        """调用 OpenAI API 并在失败时重试"""
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0
                )
                return response
            except Exception as e:
                tqdm.write(f"❌ API调用失败 (第 {attempt+1}/{retries} 次)...")
                time.sleep(delay)
        raise Exception("无法连接到 OpenAI API，重试多次后失败。")

    def compare_and_parse_content(self, a_entry: dict, b_entries: List[dict], key: str) -> dict:
        """使用 LLM 模型对比 a.json 和 b.json 的内容并提取数据"""
        prompt = prompt_template.replace("{{a_json}}", json.dumps(a_entry, ensure_ascii=False, indent=4))
        prompt = prompt.replace("{{b_json}}", json.dumps(b_entries, ensure_ascii=False, indent=4))

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional data comparison expert. "
                    "Your task is to compare the provided JSON data and output the result strictly in JSON format. "
                    "Do not include any explanations or extra text. "
                    "Ensure the output is valid JSON that can be parsed by standard JSON parsers. "
                    "All keys and string values must be enclosed in double quotation marks."
                )
            },
            {"role": "user", "content": prompt}
        ]

        response = self.call_openai_api_with_retries(messages)
        reply = response.choices[0].message.content.strip()

        parsed_data = self.extract_json_content(reply)

        if parsed_data:
            return {key: parsed_data}
        return None

    def compare_and_extract(self, a_data: List[dict], b_data: Dict[str, List[dict]]) -> Dict:
        """根据 b.json 的内容，在 a.json 中查找匹配的结果并提取"""
        results = {}

        a_data_sorted = sorted(a_data, key=lambda x: list(x.keys())[0] if isinstance(x, dict) else "")
        b_data_sorted = {k: b_data[k] for k in sorted(b_data)}

        for key, b_entries in tqdm(b_data_sorted.items(), desc="Processing entries", unit="entry"):
            a_entry = None
            for entry in a_data_sorted:
                if isinstance(entry, dict):
                    entry_key = list(entry.keys())[0].strip()
                    if entry_key == key.strip():
                        a_entry = entry[entry_key]
                        break

            if not a_entry:
                continue

            parsed_data = self.compare_and_parse_content(a_entry, b_entries, key)

            if parsed_data:
                results.update(parsed_data)

        return results

    @staticmethod
    def save_combined_json(file_path: str, data: dict):
        """将数据保存为 JSON 文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def process(self, a_json_path: str, b_json_path: str, output_file: str):
        """处理主逻辑"""
        a_data = self.load_json(a_json_path)
        b_data = self.load_json(b_json_path)

        matched_results = self.compare_and_extract(a_data, b_data)

        self.save_combined_json(output_file, matched_results)
        print(f"✅ 数据处理完成，结果已保存到 {output_file}")