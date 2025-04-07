import os
import json
from openai import OpenAI
from extrfinetune.prompt.sstru1 import prompt_template
from tqdm import tqdm

class MOFDataProcessor:
    def __init__(self, config_path: str):
        """
        初始化处理器
        :param config_path: 配置文件路径
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.client = OpenAI(api_key=config.get('apikey'), base_url=config.get('baseurl'))

    @staticmethod
    def parse_file_to_entries(input_file: str) -> list:
        """
        解析单个 TXT 文件为条目列表
        :param input_file: TXT 文件路径
        :return: 条目列表
        """
        entries = []
        current_entry = {}
        content_lines = []

        key_mapping = {
            'Chemical_Name': 'chemical_name',
            'Number': 'number',
            'Synonyms': 'synonyms',
            'Abbreviation': 'abbreviation',
            'Full Name': 'full_name'
        }

        with open(input_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        for line in lines:
            if line.isupper():  # 新的条目开始
                if current_entry:  # 保存上一个条目
                    if content_lines:
                        current_entry['content'] = ' '.join(content_lines)
                    entries.append(current_entry)
                current_entry = {'identifier': line}
                content_lines = []

            elif ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                if key in key_mapping:
                    current_entry[key_mapping[key]] = value
                else:
                    if 'No synthesis method found' not in line:
                        content_lines.append(line)
            else:
                if 'No abbreviations found' not in line and 'No synthesis method found' not in line:
                    content_lines.append(line)

        if current_entry:  # 添加最后一个条目
            current_entry['content'] = ' '.join(content_lines)
            entries.append(current_entry)

        return entries

    def process_entries(self, entries: list) -> list:
        """
        处理条目列表，调用 GPT 模型生成 Markdown
        :param entries: 条目列表
        :return: 结果列表
        """
        results = []
        for entry in entries:
            content = entry.get('content', '')
            if content and 'No synthesis method found' not in content:
                prompt = prompt_template.replace("{identifier}", entry.get('identifier', ''))
                prompt = prompt.replace("{chemical_name}", entry.get('chemical_name', ''))
                prompt = prompt.replace("{number}", entry.get('number', ''))
                prompt = prompt.replace("{synonyms}", entry.get('synonyms', ''))
                prompt = prompt.replace("{content}", content)
                prompt = prompt.replace("{Abbreviation}", entry.get('abbreviation', ''))
                prompt = prompt.replace("{Full_Name}", entry.get('full_name', ''))

                response = self.client.chat.completions.create(
                    model="gpt-4o-mini-2024-07-18",
                    messages=[{"role": "user", "content": prompt}]
                )

                result_content = response.choices[0].message.content.strip()
                results.append({
                    "Identifier": entry['identifier'],
                    "Markdown": result_content
                })

        return results

    def process_directory(self, input_dir: str, output_file: str):
        """
        处理整个目录中的 TXT 文件
        :param input_dir: 输入目录路径
        :param output_file: 输出文件路径
        """
        all_results = []
        all_entries = 0
        processed_entries = 0

        txt_files = [os.path.join(input_dir, fn) for fn in os.listdir(input_dir) if fn.lower().endswith('.txt')]

        for txt_file in tqdm(txt_files, desc="Processing files"):
            entries = self.parse_file_to_entries(txt_file)
            all_entries += len(entries)
            results = self.process_entries(entries)
            processed_entries += len(results)
            all_results.extend(results)

        with open(output_file, 'w', encoding='utf-8') as f:
            for result in all_results:
                f.write(f"# Identifier: {result['Identifier']}\n")
                f.write(result["Markdown"])
                f.write("\n\n")

        print(f"Found {all_entries} entries in total.")
        print(f"Successfully processed {processed_entries} entries.")
        print(f"Results saved to: {output_file}")