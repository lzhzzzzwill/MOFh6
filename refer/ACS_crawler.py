#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os
import pandas as pd
import time
import traceback
import requests
import re
import io
from urllib.parse import urlparse

# PDF 处理相关
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# ======= 使用 Chrome 而非 Edge =======
from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# PyMuPDF（用于文本提取）
import fitz  # PyMuPDF
import logging
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass
from typing import Optional, List

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


# ========== 主脚本：下载正文 & 补充材料 -> 合并 PDF -> 输出 TXT -> 最终仅保留 TXT ==========
parser = argparse.ArgumentParser(description='ACS Paper Crawler')
parser.add_argument('input_file', help='Input Excel file path')
args = parser.parse_args()
# 1) 读取 Excel
# 修改读取 Excel 的部分
excel_path = args.input_file   # 使用命令行参数中的文件路径
df = pd.read_excel(excel_path)  # 读取Excel文件
# 2) 数据目录
download_dir = './ulanggraph/input'  

# 3) 自定义请求头
headers = {
    'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/129.0.0.0 Safari/537.36"
}

# 4) 从 DataFrame 中提取信息
ccdc_code = df.iloc[:, 0].tolist()
doi = df.iloc[:, 11].tolist()
article_url = df.iloc[:, 12].tolist()

print('Download Start')

# 实例化 PDFProcessor（用于后面文本提取）
processor = PDFProcessor()

# 用于记录处理状态
status_total = []

for name, doi_code, url in zip(ccdc_code, doi, article_url):
    status = []
    code = name

    manuscript_pdf_path = os.path.join(download_dir, f"{code}_manuscript_temp.pdf")
    supplementary_pdf_path = os.path.join(download_dir, f"{code}_supplementary_temp.pdf")
    combined_pdf_path = os.path.join(download_dir, f"{code}.pdf")  # 最终文件：code.pdf
    txt_file_path = os.path.join(download_dir, f"{code}.txt")      # 输出文本

    manuscript_downloaded = False
    supplementary_downloaded = False

    # ========== 第 1 步：下载正文 PDF ==========
    href1 = f"https://sci.bban.top/pdf/{doi_code}.pdf?download=true"
    href2 = f"https://sci.bban.top/pdf/{doi_code}.pdf"
    href3 = f"https://sci.bban.top/pdf/{doi_code.upper()}.pdf"
    href4 = f"https://sci.bban.top/pdf/{doi_code.lower()}.pdf"
    href_list = [href1, href2, href3, href4]

    parsed_url = urlparse(href1)
    path = parsed_url.path
    filename = path.split('/')[-1]
    original_file_path = os.path.join(download_dir, filename)

    for href_o in href_list:
        response = requests.get(href_o, stream=True, headers=headers)
        if response.status_code == 200:
            with open(original_file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print(name + f" File downloaded: {original_file_path}")

            if os.path.exists(original_file_path):
                os.rename(original_file_path, manuscript_pdf_path)
                print(name + f" Renamed to: {manuscript_pdf_path}")
                manuscript_downloaded = True
                status.append('下载正文成功')
            else:
                print(name + " 下载的文件未找到。")
            break
        else:
            print(name + f" 正文下载失败，状态码：{response.status_code}")
            print(name + f" 正文下载地址：{href_o}")
            time.sleep(10)

    # ========== 第 2 步：给正文 PDF 添加“Manuscript”标签 ==========
    if manuscript_downloaded:
        try:
            label_pdf_stream = io.BytesIO()
            c = canvas.Canvas(label_pdf_stream, pagesize=letter)
            c.setFont("Helvetica", 40)
            c.drawCentredString(300, 500, "Manuscript")
            c.save()
            label_pdf_stream.seek(0)

            label_pdf_reader = PdfReader(label_pdf_stream)
            manuscript_pdf_reader = PdfReader(manuscript_pdf_path)
            writer = PdfWriter()

            writer.add_page(label_pdf_reader.pages[0])
            for page in manuscript_pdf_reader.pages:
                writer.add_page(page)

            with open(manuscript_pdf_path, "wb") as f:
                writer.write(f)
        except Exception as e:
            status.append('添加正文标签失败')
            print(f"{code} 添加正文标签失败, 错误: {e}")
            continue

    # ========== 第 3 步：下载补充材料 PDF（Selenium + Chrome）==========
    chrome_options = ChromeOptions()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True
    }
    chrome_options.add_experimental_option('prefs', prefs)

    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('useAutomationExtension', False)

    user_agent = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/129.0.6668.59 Safari/537.36")
    chrome_options.add_argument(f'user-agent={user_agent}')

    supplementary_files = []  # 如果出现多个补充文件，可保存在这里
    processed_urls = set()

    from selenium.webdriver import Chrome
    try:
        browser = Chrome(options=chrome_options)
        browser.get(url)
        # 模拟下拉，加载所有内容
        for i in range(5):
            browser.find_element(By.TAG_NAME, 'body').send_keys(Keys.END)
            time.sleep(1)

        # 这里举例：假设补充材料链接的 class_name 是 'suppl-anchor'
        elements = browser.find_elements(By.CLASS_NAME, 'suppl-anchor')
        print(f"{code} Found {len(elements)} supplementary anchors")

        for element in elements:
            href_value = element.get_attribute('href')
            if not href_value or not href_value.endswith('.pdf'):
                continue
            if href_value in processed_urls:
                continue

            processed_urls.add(href_value)
            print(f"{code} Found PDF link: {href_value}")

            # 用第二个 Chrome 实例来下载
            browser2 = Chrome(options=chrome_options)
            browser2.get(href_value)
            time.sleep(10)  # 等待下载
            browser2.quit()

            original_file_name = href_value.split('/')[-1]
            supp_orig_path = os.path.join(download_dir, original_file_name)
            if os.path.exists(supp_orig_path):
                new_supp_name = f"{code}_supp_temp_{len(supplementary_files):02d}.pdf"
                new_supp_path = os.path.join(download_dir, new_supp_name)
                os.rename(supp_orig_path, new_supp_path)
                print(f"{code} Supplementary renamed to: {new_supp_path}")

                # 给补充材料 PDF 添加 "Supplementary" 标签
                try:
                    label_pdf_stream = io.BytesIO()
                    c = canvas.Canvas(label_pdf_stream, pagesize=letter)
                    c.setFont("Helvetica", 40)
                    c.drawCentredString(300, 500, "Supplementary")
                    c.save()
                    label_pdf_stream.seek(0)

                    label_pdf_reader = PdfReader(label_pdf_stream)
                    supplementary_pdf_reader = PdfReader(new_supp_path)
                    writer = PdfWriter()

                    writer.add_page(label_pdf_reader.pages[0])
                    for page in supplementary_pdf_reader.pages:
                        writer.add_page(page)

                    with open(new_supp_path, "wb") as sf:
                        writer.write(sf)
                except Exception as e:
                    print(f"{code} Failed to add Supplementary label: {e}")

                supplementary_files.append(new_supp_path)
                supplementary_downloaded = True
            else:
                print(f"{code} 该补充材料文件未在本地找到: {original_file_name}")

        browser.quit()
    except Exception as e:
        print(f"{code} 下载补充材料失败: {e}")
        traceback.print_exc()

    # ========== 第 4 步：合并 PDF ========== 
    try:
        writer = PdfWriter()

        # 合并正文
        if manuscript_downloaded:
            if os.path.exists(manuscript_pdf_path):
                reader_manu = PdfReader(manuscript_pdf_path)
                for page in reader_manu.pages:
                    writer.add_page(page)

        # 合并补充材料
        for supp_file in supplementary_files:
            if os.path.exists(supp_file):
                reader_supp = PdfReader(supp_file)
                for page in reader_supp.pages:
                    writer.add_page(page)

        # 如果有任何 PDF（正文或补充），输出到 combined_pdf_path
        if manuscript_downloaded or len(supplementary_files) > 0:
            with open(combined_pdf_path, "wb") as f_out:
                writer.write(f_out)
            print(f"{code} 合并 PDF 完成 -> {combined_pdf_path}")
            status.append('Download and Merge Successful')
        else:
            print(f"{code} 无可合并的 PDF 文件")
            status.append('No PDF to merge')

    except Exception as e:
        print(f"{code} 合并 PDF 失败，错误: {e}")
        status.append('Failed to merge PDFs')

    # 删除临时文件
    if manuscript_downloaded and os.path.exists(manuscript_pdf_path):
        os.remove(manuscript_pdf_path)
    for sf in supplementary_files:
        if os.path.exists(sf):
            os.remove(sf)

    # ========== 第 5 步：使用 PyMuPDF 提取文本 => 仅保留 .txt ==========
    if os.path.exists(combined_pdf_path):
        try:
            extracted_text = processor.extract_text_from_pdf(combined_pdf_path)
            with open(txt_file_path, 'w', encoding='utf-8') as txt_file:
                txt_file.write(extracted_text)
            print(f"{code} PDF -> TXT 转换完成: {txt_file_path}")
            status.append('Extracted txt successfully')
        except Exception as e:
            print(f"{code} PDF 转文本失败: {e}")
            status.append('Failed to extract txt')

        # 删除合并后的 PDF，仅保留 .txt
        os.remove(combined_pdf_path)

    status_total.append(status)

# ========== 将处理结果写入 Excel ==========
data = {
    'ccdc_code': ccdc_code,
    'article_doi': doi,
    'article_url': article_url,
    'status': status_total
}
df_status = pd.DataFrame(data)
df_status.to_excel(os.path.join(download_dir, 'result.xlsx'), index=False)
print('所有操作完成，仅保留同名 .txt 文件，其余 PDF 已删除。')