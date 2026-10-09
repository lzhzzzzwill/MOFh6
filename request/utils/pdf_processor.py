#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import fitz  # PyMuPDF
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple
import re

# ====== 在这里改输入/输出路径 ======
INPUT_DIR  = Path("/Users/linzuhong/工作文件/25/钢铁voc合作/kgllm/metadata_pdf")     # 输入PDF文件夹（或单个PDF文件）
OUTPUT_DIR = Path("/Users/linzuhong/工作文件/25/钢铁voc合作/kgllm/metadata_txt")  # 输出TXT根目录（绝对路径）
# ==================================

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@dataclass
class PDFMetadata:
    title: Optional[str] = None
    author: Optional[str] = None
    creation_date: Optional[str] = None
    modification_date: Optional[str] = None
    producer: Optional[str] = None
    page_count: int = 0
    file_size: str = "0 KB"

class PDFUtils:
    @staticmethod
    def extract_text_and_metadata(pdf_path: str) -> Tuple[str, PDFMetadata]:
        """从单个PDF提取清洗后的纯文本 + 元数据"""
        try:
            pdf_path = os.path.abspath(pdf_path)
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            doc = fitz.open(pdf_path)
            metadata = doc.metadata or {}
            file_size = os.path.getsize(pdf_path)
            size_str = f"{file_size/1024/1024:.2f} MB" if file_size > 1024*1024 else f"{file_size/1024:.2f} KB"

            pdf_metadata = PDFMetadata(
                title=metadata.get('title'),
                author=metadata.get('author'),
                creation_date=metadata.get('creationDate'),
                modification_date=metadata.get('modDate'),
                producer=metadata.get('producer'),
                page_count=len(doc),
                file_size=size_str
            )

            text_parts = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                try:
                    text = page.get_text("text")
                    if text and text.strip():
                        # Keep explicit page markers so RAG answers can cite PDF pages.
                        text = re.sub(r'\n+', ' ', text)
                        text_parts.append(f"[[PAGE {page_num + 1}]]\n{text}")
                except Exception as e:
                    logging.warning(f"Failed to extract text from page {page_num + 1}: {str(e)}")
                    continue

            doc.close()

            if not text_parts:
                raise ValueError("No text could be extracted from any page")

            # 合并 & 全局空白压缩
            combined_text = '\n\n'.join(text_parts)
            # Preserve page marker boundaries while normalizing spaces per page.
            cleaned_text = re.sub(r'[ \t]+', ' ', combined_text)

            return cleaned_text.strip(), pdf_metadata

        except Exception as e:
            logging.error(f"Error processing PDF: {str(e)}")
            return "", PDFMetadata()

    @staticmethod
    def validate_pdf_path(path: str) -> bool:
        """验证PDF文件路径"""
        try:
            abs_path = os.path.abspath(path)
            return os.path.exists(abs_path) and path.lower().endswith('.pdf')
        except Exception:
            return False

def save_txt(text: str, out_txt_path: Path):
    """把文本安全写入到目标txt路径（自动建父目录）"""
    out_txt_path.parent.mkdir(parents=True, exist_ok=True)
    out_txt_path.write_text(text, encoding="utf-8", errors="ignore")

def process_one_pdf(pdf_file: Path, input_root: Path, output_root: Path):
    """
    处理单个PDF：
    - 使用相对 input_root 的相对路径确定子目录结构
    - 在 output_root 下生成同名 .txt（绝对路径）
    """
    rel = pdf_file.name if input_root.is_file() else pdf_file.relative_to(input_root)
    out_txt = (output_root / rel).with_suffix(".txt")
    logging.info(f"Converting: {pdf_file} -> {out_txt.resolve()}")

    text, _meta = PDFUtils.extract_text_and_metadata(str(pdf_file))
    if not text:
        logging.warning(f"No text extracted: {pdf_file}")
        return
    save_txt(text, out_txt)

def process_folder(input_path: Path, output_root: Path):
    """
    批量处理：
    - 如果 input_path 是单个PDF，则只处理该文件；
    - 如果是文件夹，递归 rglob('*.pdf') 全部处理；
    """
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        process_one_pdf(input_path, input_path, output_root)
    else:
        for pdf in input_path.rglob("*.pdf"):
            process_one_pdf(pdf, input_path, output_root)

    logging.info(f"All done. Output dir: {output_root}")

if __name__ == "__main__":
    in_path = INPUT_DIR.expanduser().resolve()
    out_dir = OUTPUT_DIR.expanduser().resolve()

    if not in_path.exists():
        raise FileNotFoundError(f"Input not found: {in_path}")
    process_folder(in_path, out_dir)
