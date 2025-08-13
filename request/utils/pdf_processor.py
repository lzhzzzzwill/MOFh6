import os
import sys
import logging
import fitz  # PyMuPDF
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple
import re

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
        """Extract text and metadata from PDF"""
        try:
            # 验证文件路径
            pdf_path = os.path.abspath(pdf_path)
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            # 打开PDF文件
            doc = fitz.open(pdf_path)
            metadata = doc.metadata
            file_size = os.path.getsize(pdf_path)
            size_str = f"{file_size/1024/1024:.2f} MB" if file_size > 1024*1024 else f"{file_size/1024:.2f} KB"
            
            # 提取元数据
            pdf_metadata = PDFMetadata(
                title=metadata.get('title'),
                author=metadata.get('author'),
                creation_date=metadata.get('creationDate'),
                modification_date=metadata.get('modDate'),
                producer=metadata.get('producer'),
                page_count=len(doc),
                file_size=size_str
            )
            
            # 提取文本
            text_parts = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                try:
                    text = page.get_text("text")
                    if text.strip():
                        # 清理文本
                        text = re.sub(r'\n+', ' ', text)
                        text_parts.append(text)
                except Exception as e:
                    logging.warning(f"Failed to extract text from page {page_num + 1}: {str(e)}")
                    continue
            
            doc.close()
            
            if not text_parts:
                raise ValueError("No text could be extracted from any page")
                
            # 合并和清理文本
            combined_text = ' '.join(text_parts)
            cleaned_text = re.sub(r'\s+', ' ', combined_text)
            
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