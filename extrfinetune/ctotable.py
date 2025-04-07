import os
import json
import re
import time
from typing import List, Dict, Optional
from openai import OpenAI
from tqdm import tqdm
from extrfinetune.prompt.elsedatatable import prompt_template

class ElsevierTableExtractor:
    def __init__(self, config_path: str, input_folder: str, output_file: str):
        """
        初始化 Elsevier 表格提取器
        :param config_path: 配置文件路径
        :param input_folder: 输入文件夹路径
        :param output_file: 输出 JSON 文件路径
        """
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.api_key = config.get('apikey')
        self.base_url = config.get('baseurl')

        # 创建 OpenAI 客户端
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.input_folder = input_folder
        self.output_file = output_file
        self.prompt_template = prompt_template

    def preprocess_content(self, content: str) -> str:
        """
        预处理文本，去除 HTML 标签和无关内容
        :param content: 原始文本内容
        :return: 预处理后的文本
        """
        content = re.sub(r'<.*?>', '', content)
        content = re.sub(r'\s+', ' ', content).strip()
        return content

    def extract_json_content(self, response_text: str) -> Optional[List[Dict]]:
        """
        从模型回复中提取纯 JSON 对象
        :param response_text: 模型回复文本
        :return: 解析后的 JSON 内容或 None
        """
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            tqdm.write(f"JSON parsing error: {e}")
            tqdm.write(f"Complete response: {response_text}")

            # 可选：记录错误到文件
            with open("model_response_error.txt", "a", encoding="utf-8") as error_file:
                error_file.write(f"{response_text}\n\n")

            return None

    def call_openai_api(self, messages: List[Dict], model: str = "gpt-4o-mini-2024-07-18", 
                         temperature: float = 0, retries: int = 3, delay: int = 5):
        """
        带重试机制的 OpenAI API 调用
        :param messages: 消息列表
        :param model: 使用的模型
        :param temperature: 温度参数
        :param retries: 重试次数
        :param delay: 重试间隔
        :return: API 响应
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
                tqdm.write(f"API call failed ({attempt+1}/{retries}) attempts...")
                time.sleep(delay)

        raise Exception("Unable to connect to OpenAI API after multiple attempts.")

    def find_and_parse_content(self, content: str, file_name: str) -> Optional[List[Dict]]:
        """
        使用 LLM 模型查找并解析需要处理的文本部分
        :param content: 文件内容
        :param file_name: 文件名
        :return: 解析后的数据列表或 None
        """
        prompt = self.prompt_template.replace("{{file_content}}", content)

        messages = [
            {"role": "system", "content": "You are a professional crystallographic data analyst, please return the data in JSON format."},
            {"role": "user", "content": prompt}
        ]

        with tqdm(total=1, desc=f"Calling for {file_name}", unit="call", leave=False) as inner_pbar:
            response = self.call_openai_api(messages)
            reply = response.choices[0].message.content.strip()
            inner_pbar.update(1)

        parsed_data = self.extract_json_content(reply)

        if parsed_data and isinstance(parsed_data, list):
            valid_data = []
            for entry in parsed_data:
                missing_keys = [key for key, value in entry.items() if not value]
                if len(missing_keys) < 2:
                    valid_data.append(entry)
            return valid_data if valid_data else None

    def process_folder(self) -> Dict[str, List[Dict]]:
        """
        处理文件夹中的所有 .txt 文件
        :return: 处理结果字典
        """
        results = {}
        files = [f for f in os.listdir(self.input_folder) if f.endswith(".txt")]

        with tqdm(total=len(files), desc="Processing files", unit="file") as outer_pbar:
            for filename in files:
                file_path = os.path.join(self.input_folder, filename)
                outer_pbar.set_description(f"Processing {filename}")

                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 预处理内容
                content = self.preprocess_content(content)

                # 查找并解析需要处理的部分
                parsed_data = self.find_and_parse_content(content, filename)

                if parsed_data:
                    filename_without_ext = os.path.splitext(filename)[0]
                    results[filename_without_ext] = parsed_data

                outer_pbar.update(1)

        return results

    def save_to_json(self, results: Dict[str, List[Dict]]):
        """
        保存结果到 JSON 文件
        :param results: 处理结果字典
        """
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            print(f"结果已保存到文件: {self.output_file}")
        except Exception as e:
            print(f"保存文件 {self.output_file} 时出错: {e}")

    def run(self):
        """
        执行完整的处理流程
        :return: 处理结果字典
        """
        results = self.process_folder()
        self.save_to_json(results)
        return results