#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os
import pandas as pd
import requests
import json
import time
import subprocess
import traceback
import shutil
import re
import io

from urllib.parse import urlparse
from tqdm import tqdm

# Selenium 相关
from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

# PDF 相关
from PyPDF2 import PdfMerger
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# PyMuPDF (fitz) 相关
import fitz
import logging
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass
from typing import Optional

@dataclass
class ProcessingResult:
    filename: str
    success: bool
    error_message: Optional[str] = None
    output_path: Optional[str] = None

class PDFProcessor:
    """
    用于提取 PDF 文本并进行简单的清洗，不使用多线程。
    """
    def __init__(self):
        self.setup_logging()
        
    def setup_logging(self):
        """Configure logging with rotation"""
        log_file = 'file_processing.log'
        self.logger = logging.getLogger('PDFProcessor')
        self.logger.setLevel(logging.INFO)
        
        # 清除已存在的 handlers，避免重复
        self.logger.handlers = []
        
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8'
        )
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        使用 PyMuPDF (fitz) 从 PDF 中提取文本，并用正则去除多余换行/空格。
        """
        text_parts = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                try:
                    text = page.get_text("text")
                    if text.strip():
                        # 将多余的换行符替换为空格
                        text = re.sub(r'\n+', ' ', text)
                        text_parts.append(text)
                except Exception as e:
                    self.logger.warning(f"Failed to extract text from page {page_num + 1}: {str(e)}")
                    continue
            
            doc.close()
            
            if not text_parts:
                raise ValueError("No text could be extracted from any page.")
            
            combined_text = ' '.join(text_parts)
            cleaned_text = re.sub(r'\s+', ' ', combined_text)
            return cleaned_text.strip()
            
        except Exception as e:
            raise ValueError(f"Failed to process PDF: {str(e)}")


# ------------------------------- 下面是合并后的主脚本逻辑 -------------------------------

# ========== 1. Springer 下载配置 ==========
user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.6668.59 Safari/537.36"
max_hits_per_minute = 300  # Springer API的请求速率限制

# 读取 api_key
config_path = './refer/config.json'  # /Users/linzuhong/学习文件/3-博/博四/C2ML/refer/config.json
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
    api_key = config.get('springerapikey')
    if not api_key:
        print("未在 config.json 中找到 springerapikey")
        exit()
except FileNotFoundError:
    print(f"配置文件未找到：{config_path}")
    exit()
except json.JSONDecodeError as e:
    print(f"读取配置文件错误：{e}")
    exit()

# ========== 2. 路径配置 ==========
parser = argparse.ArgumentParser(description='Springer Paper Crawler')
parser.add_argument('input_file', help='Input Excel file path')
args = parser.parse_args()
# 1) 读取 Excel
# 修改读取 Excel 的部分
excel_path = args.input_file   # 使用命令行参数中的文件路径
df = pd.read_excel(excel_path)  # 读取Excel文件
# 2) 数据目录
download_dir = './ulanggraph/input'  #/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/input

ccdc_codes = df.iloc[:, 0].tolist()   # ccdc_code
article_dois = df.iloc[:, 11].tolist() # article_doi
article_urls = df.iloc[:, 12].tolist() # article_url（假设在第5列）

# ========== 4. 实例化 PDFProcessor，用于文本提取 ==========
processor = PDFProcessor()

# ========== 5. 遵守 Springer API 速率限制的计数器 ==========
requests_made = 0

print("开始处理...")

# ========== 6. 逐条处理：下载 -> 合并 -> 提取文本 -> 删除 PDF ==========
for code, doi, url in zip(ccdc_codes, article_dois, article_urls):
    # 这里把所有操作放在 try 中，避免异常中断后面条目的处理
    print(f"\nMining {code}")

    # 设置任务总数（示例）：下载正文(1) + 下载支持材料(1) + doc/docx 转 pdf(1) + 合并 & 提取(1)
    # 仅作参考，不一定严格一一对应
    tasks_total = 4
    task_progress = tqdm(total=tasks_total, desc=f"Processing {code}", unit='task', leave=True)

    # 创建文章的临时子目录
    article_dir = os.path.join(download_dir, code)
    os.makedirs(article_dir, exist_ok=True)

    # 用来收集所有 PDF 文件（包含正文和补充材料）
    pdf_files = []

    try:
        # ---------------------- 任务1：下载正文 PDF（使用 Springer API） ----------------------
        if requests_made >= max_hits_per_minute:
            # 超过速率限制则等待1分钟
            time.sleep(60)
            requests_made = 0

        pdf_filename = f"{code}_manuscript.pdf"
        url_api = f'https://api.springernature.com/meta/v2/json?q=doi:{doi}&api_key={api_key}'

        response = requests.get(url_api)
        requests_made += 1

        if response.status_code == 200:
            # 解析 JSON
            article_data = response.json()
            pdf_url = None
            if 'records' in article_data:
                records = article_data['records']
                if records:
                    record = records[0]
                    if 'url' in record:
                        for url_info in record['url']:
                            if url_info.get('format') == 'pdf':  # 检查是否为 PDF
                                pdf_url = url_info['value']
                                break
            
            if pdf_url:
                # 下载正文 PDF
                pdf_response = requests.get(pdf_url, stream=True)
                if pdf_response.status_code == 200:
                    full_pdf_path = os.path.join(article_dir, pdf_filename)
                    with open(full_pdf_path, 'wb') as pdf_file:
                        for chunk in pdf_response.iter_content(chunk_size=1024):
                            if chunk:
                                pdf_file.write(chunk)
                    pdf_files.append(full_pdf_path)
                else:
                    raise Exception(f"无法下载正文PDF，状态码: {pdf_response.status_code}")
            else:
                raise Exception("未找到正文PDF链接")
        else:
            raise Exception(f"请求 Springer API 失败，状态码: {response.status_code}")

        task_progress.update(1)

        # ---------------------- 任务2：下载支持材料（Selenium） ----------------------
        options = ChromeOptions()
        prefs = {
            "download.default_directory": article_dir,
            "download.prompt_for_download": False,
            "profile.default_content_setting_values.automatic_downloads": 1
        }
        options.add_experimental_option('prefs', prefs)
        options.add_argument('--headless')
        options.add_argument(f'user-agent={user_agent}')
        browser = Chrome(options=options)
        browser.set_page_load_timeout(30)

        try:
            browser.get(url)
            time.sleep(5)
            
            tables = browser.find_elements(By.CLASS_NAME, "c-article-supplementary__item")
            if tables:
                for table in tables:
                    links = table.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        href = link.get_attribute("href")
                        if href.lower().endswith((".pdf", ".docx", ".doc")):
                            # 下载文件到 article_dir
                            parsed_url = urlparse(href)
                            path = parsed_url.path
                            filename = path.split('/')[-1]
                            file_path = os.path.join(article_dir, filename)

                            headers = {'User-Agent': user_agent}
                            file_response = requests.get(href, stream=True, headers=headers)
                            if file_response.status_code == 200:
                                with open(file_path, 'wb') as f:
                                    for chunk in file_response.iter_content(chunk_size=8192):
                                        if chunk:
                                            f.write(chunk)
                                
                                # 如果是 PDF，加入 pdf_files 列表
                                if filename.lower().endswith('.pdf'):
                                    pdf_files.append(file_path)
                                # 如果是 .doc 或 .docx，下一个任务再做转换
                            else:
                                raise Exception(f"下载失败，状态码：{file_response.status_code}")
            browser.quit()
        except Exception as e:
            browser.quit()
            raise e

        task_progress.update(1)

        # ---------------------- 任务3：转换 .doc / .docx -> PDF（unoconv） ----------------------
        for filename in os.listdir(article_dir):
            file_path = os.path.join(article_dir, filename)
            if filename.lower().endswith(('.doc', '.docx')):
                try:
                    # 调用 unoconv 将 doc/docx 转为 pdf
                    subprocess.run(['unoconv', '-f', 'pdf', file_path], check=True)
                    os.remove(file_path)  # 转换后删除原始文件
                    converted_pdf = file_path.rsplit('.', 1)[0] + '.pdf'
                    pdf_files.append(converted_pdf)
                except subprocess.CalledProcessError as err:
                    print(f"转换 {filename} 为 PDF 时出错: {err}")

        task_progress.update(1)

        # ---------------------- 任务4：合并 PDF，并插入标签 ----------------------
        output_pdf_path = os.path.join(download_dir, f"{code}.pdf")  # 合并后的 PDF 放在 download_dir 下
        merger = PdfMerger()

        # 创建 Manuscript 标签页
        manuscript_label_pdf = os.path.join(article_dir, "manuscript_label.pdf")
        c = canvas.Canvas(manuscript_label_pdf, pagesize=letter)
        c.setFont("Helvetica", 20)
        c.drawString(100, 700, "Manuscript")
        c.save()

        merger.append(manuscript_label_pdf)
        os.remove(manuscript_label_pdf)  # 用后即删

        # 添加正文 PDF（pdf_files[0] 理论上是正文）
        if pdf_files:
            merger.append(pdf_files[0])

        # 如果有支持材料 PDF
        if len(pdf_files) > 1:
            # 创建 Supplementary 标签页
            supp_label_pdf = os.path.join(article_dir, "supplementary_label.pdf")
            c = canvas.Canvas(supp_label_pdf, pagesize=letter)
            c.setFont("Helvetica", 20)
            c.drawString(100, 700, "Supplementary")
            c.save()

            merger.append(supp_label_pdf)
            os.remove(supp_label_pdf)  # 用后即删

            # 依次添加所有支持材料 PDF
            for pdf_file in pdf_files[1:]:
                merger.append(pdf_file)

        # 写出合并文件
        with open(output_pdf_path, 'wb') as f_out:
            merger.write(f_out)
        merger.close()

        task_progress.update(1)

        # =============== 在此处用 PDFProcessor 提取文本，并只留 .txt ===============
        try:
            extracted_text = processor.extract_text_from_pdf(output_pdf_path)
            txt_path = os.path.join(download_dir, f"{code}.txt")  # 同目录下存 txt
            with open(txt_path, 'w', encoding='utf-8') as f_txt:
                f_txt.write(extracted_text)
        except Exception as e:
            print(f"[{code}] PDF 转文本失败: {e}")

        # =============== 删除所有 PDF 文件与临时目录，只保留 .txt ===============
        if os.path.exists(output_pdf_path):
            os.remove(output_pdf_path)
        # 删除 article_dir 及其中的所有下载文件
        if os.path.exists(article_dir):
            shutil.rmtree(article_dir)

    except Exception as e:
        print(f"[{code}] 处理过程中出现错误：{e}")
        traceback.print_exc()
    finally:
        task_progress.close()

print("所有文件处理完成。仅保留 .txt 文件，已删除其他文件。")