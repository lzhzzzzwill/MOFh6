import os
import json
import pandas as pd
from datetime import datetime
from tqdm import tqdm
from openai import OpenAI


class FineTunedModelProcessor:
    def __init__(self, config_path: str, test_folder: str, system_file_path: str, output_folder: str):
        """
        初始化微调模型处理器
        :param config_path: 配置文件路径
        :param test_folder: 测试文件夹路径
        :param system_file_path: 系统消息文件路径
        :param output_folder: 输出文件夹路径
        """
        # 从配置文件读取 API 密钥和模型信息
        with open(config_path, 'r') as f:
            config = json.load(f)

        self.api_key = config['openaiapikey']
        self.fine_tuned_model = config['shot198']
        self.model_name = 'shot198'

        # 创建 OpenAI 客户端
        self.client = OpenAI(api_key=self.api_key)

        # 设置路径
        self.test_folder = test_folder
        self.system_file_path = system_file_path

        # 确保输出文件夹存在
        os.makedirs(output_folder, exist_ok=True)

        # 生成输出 Excel 文件路径
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_excel_path = os.path.join(output_folder, f"testpredictions_{self.model_name}_{timestamp}.xlsx")

    def load_system_message(self) -> str:
        """
        加载系统消息
        :return: 系统消息内容
        """
        with open(self.system_file_path, "r", encoding="utf-8") as sys_file:
            return sys_file.read()

    def get_test_files(self) -> list:
        """
        获取测试文件列表
        :return: 文件名列表
        """
        test_files = [f for f in os.listdir(self.test_folder) if f.endswith(".txt")]
        if not test_files:
            raise FileNotFoundError(f"No .txt files found in {self.test_folder}")
        return test_files

    def process_file(self, file_name: str, system_message: str) -> dict:
        """
        处理单个文件
        :param file_name: 文件名
        :param system_message: 系统消息
        :return: 处理结果字典
        """
        file_path = os.path.join(self.test_folder, file_name)
        with open(file_path, "r", encoding="utf-8") as file:
            user_message = file.read()

        # 构建系统和用户的消息
        test_messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        # 调用微调模型进行推理
        response = self.client.chat.completions.create(
            model=self.fine_tuned_model,
            messages=test_messages,
            temperature=0,
        )
        # 获取模型的预测结果
        pred = response.choices[0].message.content

        return {
            "file_name": file_name,
            "input": user_message,
            "prediction": pred
        }

    def process_all_files(self) -> list:
        """
        处理所有文件
        :return: 处理结果列表
        """
        system_message = self.load_system_message()
        test_files = self.get_test_files()

        test_actions_preds = []

        # 外层进度条：遍历文件
        with tqdm(total=len(test_files), desc="Processing files", unit="file") as pbar:
            for file_name in test_files:
                try:
                    result = self.process_file(file_name, system_message)
                    test_actions_preds.append(result)
                except Exception as e:
                    print(f"Error processing file {file_name}: {e}")
                pbar.update(1)

        return test_actions_preds

    def save_to_excel(self, results: list):
        """
        使用 xlsxwriter 引擎保存结果到 Excel
        """
        try:
            # 创建 DataFrame
            results_df = pd.DataFrame(results)[["file_name", "prediction"]]
            results_df["file_name"] = results_df["file_name"].str.replace(".txt", "", regex=False)
            results_df = results_df.sort_values(by="file_name", ascending=True)
            
            # 使用 xlsxwriter 引擎保存
            with pd.ExcelWriter(self.output_excel_path, engine='xlsxwriter') as writer:
                results_df.to_excel(writer, index=False, sheet_name='Sheet1')
                
                # 调整列宽
                worksheet = writer.sheets['Sheet1']
                worksheet.set_column('A:A', 20)  # file_name 列宽
                worksheet.set_column('B:B', 150)  # prediction 列宽，设置较大以容纳长文本

            print(f"预测结果已保存到 '{self.output_excel_path}'")
            
        except Exception as e:
            print(f"Error saving to Excel: {e}")
            raise

    def run(self):
        """
        执行完整的处理流程
        """
        results = self.process_all_files()
        self.save_to_excel(results)
        return results