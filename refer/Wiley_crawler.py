#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os
import pandas as pd
import time
import requests
import json
import re
import io
import fitz  # PyMuPDF
import logging
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass
from typing import Optional
from tqdm import tqdm

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# ---------------------- PDFProcessor 类 ----------------------
@dataclass
class ProcessingResult:
    filename: str
    success: bool
    error_message: Optional[str] = None
    output_path: Optional[str] = None

class PDFProcessor:
    def __init__(self):
        """
        去掉多线程与批量处理逻辑，仅保留提取文本的核心函数。
        """
        self.setup_logging()

    def setup_logging(self):
        """Configure logging with rotation"""
        log_file = 'file_processing.log'
        self.logger = logging.getLogger('PDFProcessor')
        self.logger.setLevel(logging.INFO)

        # 清空已有的 handlers，避免重复
        self.logger.handlers = []

        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8'
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
        使用 PyMuPDF (fitz) 从 PDF 中提取文本并进行简单的换行、空格处理。
        """
        text_parts = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                try:
                    text = page.get_text("text")
                    if text.strip():
                        # 替换多余换行符为一个空格
                        text = re.sub(r'\n+', ' ', text)
                        text_parts.append(text)
                except Exception as e:
                    self.logger.warning(f"Failed to extract text from page {page_num + 1}: {str(e)}")
                    continue
            doc.close()

            if not text_parts:
                raise ValueError("No text could be extracted from any page.")

            # 合并并去掉多余空白
            combined_text = ' '.join(text_parts)
            cleaned_text = re.sub(r'\s+', ' ', combined_text)
            return cleaned_text.strip()

        except Exception as e:
            raise ValueError(f"Failed to process PDF: {str(e)}")


# ---------------------- 主逻辑：读取 Excel，逐条下载 -> 合并 -> 转 txt -> 删除多余文件 ----------------------

# 更新后的文件路径，请确保路径正确
parser = argparse.ArgumentParser(description='Wiley Paper Crawler')
parser.add_argument('input_file', help='Input Excel file path')
args = parser.parse_args()
# 1) 读取 Excel
# 修改读取 Excel 的部分
excel_path = args.input_file   # 使用命令行参数中的文件路径
df = pd.read_excel(excel_path)  # 读取Excel文件
# 2) 数据目录
download_dir = './ulanggraph/input' #/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/input

# 读取 client_token
config_path = './refer/config.json' #/Users/linzuhong/学习文件/3-博/博四/C2ML/refer/config.json

# 读取 client_token
try:
    with open(config_path, 'r') as f:
        config = json.load(f)
    client_token = config.get('wileyapikey')
    if not client_token:
        print("未在 config.json 中找到 wileyapikey")
        exit()
except FileNotFoundError:
    print(f"配置文件未找到：{config_path}")
    exit()
except json.JSONDecodeError as e:
    print(f"读取配置文件错误：{e}")
    exit()


# 提取数据
ccdc_code = df.iloc[:, 0].tolist()  # 第一列
article_doi = df.iloc[:, 11].tolist()  # 第二列
article_url = df.iloc[:, 12].tolist()  # 第五列

# 速率限制设置
rate_limit = 3
time_between_requests = 1 / rate_limit

print('开始处理...')

# 每个项目的总步骤数：下载正文(1) + 加标签(1) + 下载补材(1) + 加标签(1) + 合并(1) + 转txt(1) = 6步
project_steps = 6

# 实例化 PDFProcessor
processor = PDFProcessor()

for idx, (code, doi, url) in enumerate(zip(ccdc_code, article_doi, article_url), start=1):
    with tqdm(total=project_steps, desc=f'Processing {code}', unit='step', leave=True) as pbar:
        # 文件路径
        manuscript_pdf_path = os.path.join(download_dir, f"{code}_manuscript_temp.pdf")
        supplementary_pdf_path = os.path.join(download_dir, f"{code}_supplementary_temp.pdf")
        combined_pdf_path = os.path.join(download_dir, f"{code}.pdf")
        txt_file_path = os.path.join(download_dir, f"{code}.txt")

        # 下载正文 PDF
        try:
            article_api_url = f"https://api.wiley.com/onlinelibrary/tdm/v1/articles/{doi}"
            headers = {"Wiley-TDM-Client-Token": client_token}
            resp = requests.get(article_api_url, headers=headers, allow_redirects=True)
            if resp.status_code == 200:
                with open(manuscript_pdf_path, "wb") as f:
                    f.write(resp.content)
                manuscript_downloaded = True
            else:
                manuscript_downloaded = False
                print(f"[{code}] 正文下载失败，状态码: {resp.status_code}")
                pbar.update(1)
                continue
        except Exception as e:
            manuscript_downloaded = False
            print(f"[{code}] 正文下载失败，错误: {e}")
            pbar.update(1)
            continue
        pbar.update(1)

        # 遵守速率限制
        time.sleep(time_between_requests)

        # 给正文 PDF 加“Manuscript”标签
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
                # 插入标签页
                writer.add_page(label_pdf_reader.pages[0])
                for page in manuscript_pdf_reader.pages:
                    writer.add_page(page)
                with open(manuscript_pdf_path, "wb") as f:
                    writer.write(f)
            except Exception as e:
                print(f"[{code}] 添加正文标签失败，错误: {e}")
                pbar.update(1)
                continue
        pbar.update(1)

        # 使用 Selenium 下载补充材料
        supplementary_downloaded = False
        options = ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('useAutomationExtension', False)
        user_agent = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/129.0.6668.59 Safari/537.36")
        options.add_argument(f'user-agent={user_agent}')
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "profile.default_content_setting_values.automatic_downloads": 1,
            'plugins.always_open_pdf_externally': True,
        }
        options.add_experimental_option('prefs', prefs)
        options.add_experimental_option('excludeSwitches', ['enable-logging'])

        try:
            browser = Chrome(options=options)
            browser.get(url)
            # 滚动页面
            for _ in range(5):
                browser.find_element(By.TAG_NAME, 'body').send_keys(Keys.END)
                time.sleep(1)

            success = False
            # 尝试展开补充材料
            try:
                button = browser.find_element(By.XPATH, "//a[@class='accordion__control']")
                browser.execute_script("(arguments[0]).click()", button)
                time.sleep(5)

                table = browser.find_element(By.CLASS_NAME, "support-info__table")
                if table:
                    links = table.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        href = link.get_attribute("href")
                        file_name_match = re.search(r'file=([a-zA-Z0-9_]+_\d+_sm_[\w_]+[.]pdf)', href)
                        if file_name_match:
                            file_name = file_name_match.group(1)
                        else:
                            continue

                        browser2 = Chrome(options=options)
                        browser2.get(href)
                        time.sleep(10)
                        browser2.quit()

                        original_file_path = os.path.join(download_dir, file_name)
                        if os.path.exists(original_file_path):
                            os.rename(original_file_path, supplementary_pdf_path)
                            supplementary_downloaded = True
                            success = True
                            break
                    # 如果 table 中没找到可下载的文件
                    if not success:
                        raise Exception("补充材料下载失败(表格中无有效链接)")
            except Exception:
                pass

            # 如果上面没成功，再检查页面是否有直接下载链接
            if not success:
                try:
                    link_element = browser.find_element(By.XPATH, "//a[@class='linkBehavior']")
                    href = link_element.get_attribute('href')
                    if href:
                        r2 = requests.get(href, stream=True)
                        if r2.status_code == 200:
                            with open(supplementary_pdf_path, 'wb') as ff:
                                for chunk in r2.iter_content(chunk_size=8192):
                                    if chunk:
                                        ff.write(chunk)
                            supplementary_downloaded = True
                except Exception:
                    pass

            browser.quit()
        except Exception as e:
            print(f"[{code}] 补充材料下载失败，错误: {e}")
            pbar.update(1)
            # 不中断，继续往下（也可能没补充材料）
        pbar.update(1)

        # 给补充材料加“Supplementary”标签
        if supplementary_downloaded:
            try:
                label_pdf_stream = io.BytesIO()
                c = canvas.Canvas(label_pdf_stream, pagesize=letter)
                c.setFont("Helvetica", 40)
                c.drawCentredString(300, 500, "Supplementary")
                c.save()
                label_pdf_stream.seek(0)
                label_pdf_reader = PdfReader(label_pdf_stream)
                supplementary_pdf_reader = PdfReader(supplementary_pdf_path)
                writer = PdfWriter()
                writer.add_page(label_pdf_reader.pages[0])
                for page in supplementary_pdf_reader.pages:
                    writer.add_page(page)
                with open(supplementary_pdf_path, "wb") as ff:
                    writer.write(ff)
            except Exception as e:
                print(f"[{code}] 添加补充材料标签失败，错误: {e}")
                pbar.update(1)
                continue
        pbar.update(1)

        # 合并 PDF
        try:
            writer = PdfWriter()
            if manuscript_downloaded:
                m_reader = PdfReader(manuscript_pdf_path)
                for pg in m_reader.pages:
                    writer.add_page(pg)
            if supplementary_downloaded:
                s_reader = PdfReader(supplementary_pdf_path)
                for pg in s_reader.pages:
                    writer.add_page(pg)
            if manuscript_downloaded or supplementary_downloaded:
                with open(combined_pdf_path, "wb") as ff:
                    writer.write(ff)
            else:
                print(f"[{code}] 没有可合并的 PDF 文件。")
                pbar.update(1)
                continue
        except Exception as e:
            print(f"[{code}] 合并 PDF 失败，错误: {e}")
            pbar.update(1)
            continue
        pbar.update(1)

        # 删除临时 PDF
        if os.path.exists(manuscript_pdf_path):
            os.remove(manuscript_pdf_path)
        if os.path.exists(supplementary_pdf_path):
            os.remove(supplementary_pdf_path)

        # 使用 PyMuPDF 提取文本，保存为 .txt
        try:
            extracted_text = processor.extract_text_from_pdf(combined_pdf_path)
            with open(txt_file_path, 'w', encoding='utf-8') as ftxt:
                ftxt.write(extracted_text)
        except Exception as e:
            print(f"[{code}] PDF 转 txt 失败，错误: {e}")
            continue

        # 最后删除合并后的 PDF
        if os.path.exists(combined_pdf_path):
            os.remove(combined_pdf_path)

print("处理完成。除生成的 .txt 文件外，其余文件已删除。")