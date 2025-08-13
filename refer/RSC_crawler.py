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

# PDF相关
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# PyMuPDF（用于提取文本）
import fitz  # PyMuPDF
import logging
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass
from typing import Optional, List

# BeautifulSoup 用于解析HTML，查找 .pdf 链接
from bs4 import BeautifulSoup

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
        
        # 清除已有的 handlers，避免重复日志
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


# ============ 主脚本 ============

# ---------- 1) 读取 Excel & 设置数据目录 ----------
parser = argparse.ArgumentParser(description='RSC Paper Crawler')
parser.add_argument('input_file', help='Input Excel file path')
args = parser.parse_args()
# 1) 读取 Excel
# 修改读取 Excel 的部分
excel_path = args.input_file   # 使用命令行参数中的文件路径
df = pd.read_excel(excel_path)  # 读取Excel文件
# 2) 数据目录
download_dir = './ulanggraph/input'   #/Users/linzuhong/学习文件/3-博/博四/C2ML/ulanggraph/input

# 自定义请求头（如果需要）
headers = {
    'User-Agent': ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/129.0.0.0 Safari/537.36")
}

# 从 Excel 提取数据
ccdc_code = df.iloc[:, 0].tolist()  # ccdc_code
doi = df.iloc[:, 11].tolist()        # article_doi
article_url = df.iloc[:, 12].tolist()  # article_url (第 5 列)
status_total = []

processor = PDFProcessor()

print("Download Start")

for name, doi_code, url in zip(ccdc_code, doi, article_url):
    status = []
    code = name
    
    # ---- 主要文件路径 ----
    manuscript_pdf_path = os.path.join(download_dir, f"{code}_manuscript_temp.pdf")
    combined_pdf_path   = os.path.join(download_dir, f"{code}.pdf")
    txt_file_path       = os.path.join(download_dir, f"{code}.txt")
    
    # 临时记录多个补充材料 PDF (若有)
    supplementary_files = []

    # 标志
    manuscript_downloaded = False
    
    # ========== 第 1 步：下载正文 PDF ==========
    candidate_links = [
        f"https://sci.bban.top/pdf/{doi_code}.pdf?download=true",
        f"https://sci.bban.top/pdf/{doi_code}.pdf",
        f"https://sci.bban.top/pdf/{doi_code.upper()}.pdf",
        f"https://sci.bban.top/pdf/{doi_code.lower()}.pdf"
    ]
    
    from urllib.parse import urlparse
    # 仅用来取默认文件名
    parsed_url = urlparse(candidate_links[0])
    path_ = parsed_url.path
    default_filename = path_.split('/')[-1]
    original_file_path = os.path.join(download_dir, default_filename)

    # 尝试下载正文 PDF
    for link in candidate_links:
        resp = requests.get(link, stream=True, headers=headers)
        if resp.status_code == 200:
            # 下载到 original_file_path
            with open(original_file_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print(f"{code} 主文档下载成功 -> {original_file_path}")

            if os.path.exists(original_file_path):
                # 重命名为 _manuscript_temp.pdf
                os.rename(original_file_path, manuscript_pdf_path)
                print(f"{code} 已重命名: {manuscript_pdf_path}")
                manuscript_downloaded = True
                status.append('Manuscript download successful')
            else:
                print(f"{code} 下载的正文文件未找到")
            break
        else:
            print(f"{code} 正文下载失败，状态码: {resp.status_code}；链接: {link}")
            time.sleep(2)

    # ========== 第 2 步：给正文 PDF 打“Manuscript”标签 ==========
    if manuscript_downloaded:
        try:
            label_stream = io.BytesIO()
            c = canvas.Canvas(label_stream, pagesize=letter)
            c.setFont("Helvetica", 40)
            c.drawCentredString(300, 500, "Manuscript")
            c.save()
            label_stream.seek(0)
            
            label_pdf_reader = PdfReader(label_stream)
            manuscript_reader = PdfReader(manuscript_pdf_path)
            writer = PdfWriter()

            # 先插标签页
            writer.add_page(label_pdf_reader.pages[0])
            # 再插正文
            for pg in manuscript_reader.pages:
                writer.add_page(pg)
            with open(manuscript_pdf_path, 'wb') as mf:
                writer.write(mf)
        except Exception as e:
            status.append('添加正文标签失败')
            print(f"{code} 给正文打Manuscript标签失败: {e}")
    
    # ========== 第 3 步：使用 requests+BeautifulSoup 下载多份补充材料 PDF ==========
    # （不使用 Selenium）
    try:
        # 获取文章页面 HTML
        resp_page = requests.get(url, headers=headers)
        resp_page.encoding = 'utf-8'
        soup = BeautifulSoup(resp_page.text, 'html.parser')

        # 所有 <a> 标签，检查 href 是否以 .pdf 结尾
        pdf_links = soup.find_all('a', href=True)
        pdf_urls = [lk['href'] for lk in pdf_links if lk['href'].lower().endswith('.pdf')]

        if pdf_urls:
            print(f"{code} 在HTML中找到补充材料 PDF 链接: {pdf_urls}")
        else:
            print(f"{code} 无补充材料pdf文件")
            status.append('无支撑材料pdf文件')

        # 逐个下载所有补充材料 PDF
        for idx, pdf_url in enumerate(pdf_urls):
            print(f"{code} 补充材料链接: {pdf_url}")
            pdf_resp = requests.get(pdf_url, stream=True, headers=headers)
            if pdf_resp.status_code == 200:
                # 默认名
                supp_filename = urlparse(pdf_url).path.split('/')[-1]
                supp_orig_path = os.path.join(download_dir, supp_filename)
                
                # 保存到本地
                with open(supp_orig_path, 'wb') as sf:
                    for chunk in pdf_resp.iter_content(chunk_size=8192):
                        if chunk:
                            sf.write(chunk)
                print(f"{code} 补充材料已下载 -> {supp_orig_path}")
            else:
                print(f"{code} 补充材料下载失败，状态码: {pdf_resp.status_code}")
                continue

            # 重命名 (可能多文件)
            # 例如: code_supp_temp.pdf / code_supp_temp01.pdf ...
            supp_temp_name = f"{code}_supp_temp{idx:02d}.pdf"
            supp_temp_path = os.path.join(download_dir, supp_temp_name)
            if os.path.exists(supp_orig_path):
                os.rename(supp_orig_path, supp_temp_path)
            else:
                print(f"{code} 补充文件 {supp_orig_path} 不存在")
                continue
            
            # 给它打“Supplementary”标签
            try:
                label_stream = io.BytesIO()
                c = canvas.Canvas(label_stream, pagesize=letter)
                c.setFont("Helvetica", 40)
                c.drawCentredString(300, 500, "Supplementary")
                c.save()
                label_stream.seek(0)
                
                label_pdf_reader = PdfReader(label_stream)
                supp_reader = PdfReader(supp_temp_path)
                writer = PdfWriter()

                writer.add_page(label_pdf_reader.pages[0])
                for pg in supp_reader.pages:
                    writer.add_page(pg)
                with open(supp_temp_path, 'wb') as sf_out:
                    writer.write(sf_out)

                # 保存到 supplementary_files 列表
                supplementary_files.append(supp_temp_path)
                status.append('下载支撑材料成功')
            except Exception as e:
                status.append('添加补充材料标签失败')
                print(f"{code} 给补充材料打Supplementary标签失败: {e}")

    except Exception as e:
        traceback.print_exc()
        status.append('支撑材料下载失败')
        print(f"{code} 支撑材料下载出现错误: {e}")
    
    # ========== 第 4 步：合并正文 + 多个补充材料 PDF -> combined_pdf ==========
    final_exists = False
    try:
        writer = PdfWriter()

        # 合并正文
        if manuscript_downloaded and os.path.exists(manuscript_pdf_path):
            m_reader = PdfReader(manuscript_pdf_path)
            for pg in m_reader.pages:
                writer.add_page(pg)
            final_exists = True

        # 合并所有补充材料 PDF
        for supp_pdf in supplementary_files:
            if os.path.exists(supp_pdf):
                s_reader = PdfReader(supp_pdf)
                for pg in s_reader.pages:
                    writer.add_page(pg)
                final_exists = True

        # 若合并了任何 PDF，就写出 combined_pdf
        if final_exists:
            with open(combined_pdf_path, 'wb') as cf:
                writer.write(cf)
            print(f"{code} 合并PDF完成 -> {combined_pdf_path}")
            status.append('下载并合并成功')
        else:
            print(f"{code} 没有可合并的 PDF 文件")
            status.append('没有可用的PDF文件')

        # 删除正文 & 补充材料的临时 PDF
        if manuscript_downloaded and os.path.exists(manuscript_pdf_path):
            os.remove(manuscript_pdf_path)
        for spdf in supplementary_files:
            if os.path.exists(spdf):
                os.remove(spdf)

    except Exception as e:
        status.append('合并 PDF 失败')
        print(f"{code} 合并 PDF 失败: {e}")

    # ========== 第 5 步：提取文本，只保留 txt ==========
    # 如果 final_exists 为 True & combined_pdf_path 存在，就提取
    if final_exists and os.path.exists(combined_pdf_path):
        try:
            extracted_text = processor.extract_text_from_pdf(combined_pdf_path)
            with open(txt_file_path, 'w', encoding='utf-8') as txtf:
                txtf.write(extracted_text)
            status.append('Extracted txt')
            print(f"{code} PDF -> TXT 提取完成: {txt_file_path}")
        except Exception as e:
            status.append('PDF转文本失败')
            print(f"{code} 提取文本失败: {e}")

        # 删除合并后的 PDF
        os.remove(combined_pdf_path)

    # 记录状态
    status_total.append(status)

# ------ 将处理结果写入 Excel ------
data = {
    'ccdc_code': ccdc_code,
    'article_doi': doi,
    'article_url': article_url,
    'status': status_total
}
df_result = pd.DataFrame(data)
df_result.to_excel(os.path.join(download_dir, 'result.xlsx'), index=False)

print("所有操作完成，仅保留同名 .txt 文件，其余 PDF 都已删除。")