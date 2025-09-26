import json
import pymupdf
import argparse
from loguru import logger
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, Field
import jsonlines
from lingua import LanguageDetector, LanguageDetectorBuilder
from tqdm import tqdm
from typing import Optional, Dict, List, Any, Set
import base64
from dateutil import parser


def clean_unicode_string(text: str) -> str:
    """
    Clean Unicode string by removing surrogates and invalid characters.
    
    Args:
        text: Input text string
        
    Returns:
        Cleaned text safe for UTF-8 encoding
    """
    if not isinstance(text, str):
        return str(text)
    
    try:
        # 首先处理代理字符对
        # 代理字符在Unicode中是0xD800-0xDFFF范围
        cleaned_chars = []
        i = 0
        while i < len(text):
            char = text[i]
            code_point = ord(char)
            
            # 检查是否为代理字符
            if 0xD800 <= code_point <= 0xDFFF:
                # 跳过代理字符
                i += 1
                continue
            
            # 检查是否为有效的可打印字符或允许的空白字符
            if char.isprintable() or char in '\n\r\t':
                cleaned_chars.append(char)
            
            i += 1
        
        cleaned_text = ''.join(cleaned_chars)
        
        # 验证是否可以编码为UTF-8
        try:
            cleaned_text.encode('utf-8')
            return cleaned_text
        except UnicodeEncodeError:
            # 如果仍然有问题，使用更激进的清理方法
            return cleaned_text.encode('utf-8', errors='ignore').decode('utf-8')
            
    except Exception as e:
        logger.warning(f"Failed to clean Unicode string: {e}")
        # 最后的备用方案：直接使用ignore错误
        try:
            return text.encode('utf-8', errors='ignore').decode('utf-8')
        except Exception:
            return ""


def pdf_metadata_refine(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Refine PDF metadata by converting date strings to timestamps.

    Args:
        metadata: Raw PDF metadata dictionary

    Returns:
        Dict with date fields converted to timestamps

    Examples:
        >>> metadata = {"creationDate": "D:20240101120000+00'00'"}
        >>> refined = pdf_metadata_refine(metadata)
        >>> isinstance(refined["creationDate"], int)
        True
    """
    # 处理None metadata
    if metadata is None:
        logger.warning("PDF metadata is None, using empty dictionary")
        metadata = {}
    
    # {"format": "PDF 1.4", "title": "", "author": "", "subject": "", "keywords": "", "creator": "", "producer": "", "creationDate": "", "modDate": "", "trapped": "", "encryption": "None"}
    for key, value in metadata.items():
        if "Date" in key:  # creationDate, modDate
            # 保存原始值
            original_value = value
            timestamp = "0"  # 特殊时间戳：1970-01-01 00:00:00 UTC，字符串格式
            try:
                if isinstance(value, str):
                    # 优先使用 dateutil.parser 智能解析各种日期格式
                    try:
                        dt = parser.parse(value, fuzzy=True)
                        timestamp = str(int(dt.timestamp()))
                    except Exception as parse_error:
                        # 如果 dateutil.parser 失败，尝试特殊处理 D: 格式
                        if value.startswith("D:"):
                            # 处理 D:YYYYMMDDHHMMSSOHH'mm' 格式
                            # 例如: D:20240101120000+00'00' 或 D:20240101120000Z
                            try:
                                # 提取日期时间部分 (去掉 D: 前缀)
                                date_part = value[2:]
                                
                                # 处理带时区的格式
                                if "'" in date_part:
                                    # 格式: D:YYYYMMDDHHMMSS+HH'mm' 或 D:YYYYMMDDHHMMSS-HH'mm'
                                    # 移除时区部分，只保留日期时间
                                    date_part = date_part.split("'")[0]
                                    if len(date_part) >= 14:
                                        dt = datetime.strptime(date_part[:14], "%Y%m%d%H%M%S")
                                        timestamp = str(int(dt.timestamp()))
                                elif date_part.endswith('Z'):
                                    # 格式: D:YYYYMMDDHHMMSSZ (UTC时间)
                                    if len(date_part) >= 15:  # 包含Z
                                        dt = datetime.strptime(date_part[:14], "%Y%m%d%H%M%S")
                                        timestamp = str(int(dt.timestamp()))
                                else:
                                    # 简单格式: D:YYYYMMDDHHMMSS
                                    if len(date_part) >= 14:
                                        dt = datetime.strptime(date_part[:14], "%Y%m%d%H%M%S")
                                        timestamp = str(int(dt.timestamp()))
                            except Exception as d_format_error:
                                logger.warning(f"Failed to parse D: format date {key}={value}: {d_format_error}")
                                # 继续使用默认时间戳
                                pass
                        else:
                            # 不是 D: 格式，记录 dateutil.parser 的解析错误
                            logger.warning(f"Failed to parse date with dateutil.parser {key}={value}: {parse_error}")
                            timestamp = f"dateutilparser_error||||{value}"
                # 如果 value 不是字符串或格式不匹配，使用默认的 timestamp
            except Exception as e:
                logger.warning(f"Failed to parse date {key}={value}: {e}")
                # timestamp 保持默认值

            # 如果解析失败（timestamp 仍为 "0"），保存原始值
            if timestamp == "0" and original_value:
                # 处理原始值为字符串格式
                if isinstance(original_value, str):
                    # 清理字符串，移除代理字符和不可见字符
                    cleaned_value = clean_unicode_string(original_value)
                    timestamp = f"no_processed||||{cleaned_value}"
                else:
                    # 非字符串类型，转换为字符串
                    timestamp = f"no_processed||||{str(original_value)}"

            metadata[key] = timestamp
        
        # 清理所有其他字符串字段
        for key, value in metadata.items():
            if isinstance(value, str) and "Date" not in key:
                metadata[key] = clean_unicode_string(value)
    return metadata


class PDFContent(BaseModel):
    """
    A model representing the extracted content from a PDF file.

    Attributes:
        file_path: The absolute path to the PDF file
        file_size: The size of the PDF file in MB
        file_available: Whether the PDF file is available
        metadata: The metadata of the PDF file
        timestamp: The timestamp when the PDF was processed
        language: The detected language of the PDF content
        text: The extracted text content from each page
        xref: The cross-reference table entries
        toc: The table of contents entries
    """

    file_path: str = Field(description="The absolute path to the PDF file", default="")
    file_size: float = Field(description="The size of the PDF file, in MB", default=0.0)
    file_available: bool = Field(
        description="Whether the PDF file is available", default=False
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="The metadata of the PDF file"
    )
    timestamp: str = Field(description="The timestamp of the PDF file", default="")
    language: str = Field(description="The language of the PDF file", default="")
    text: List[str] = Field(
        default_factory=list, description="The text of the PDF file"
    )
    xref: List[str] = Field(
        default_factory=list, description="The xref of the PDF file"
    )
    page: List[str] = Field(
        default_factory=list,
        description="The page image of the PDF file",  # base64 encoded 低分辨率，减少体积
    )
    toc: List[str] = Field(
        default_factory=list, description="The table of contents of the PDF file"
    )

    def _clean_unicode_text(self, text: str) -> str:
        """
        Clean Unicode text by removing surrogates and invalid characters.
        
        Args:
            text: Input text string
            
        Returns:
            Cleaned text safe for UTF-8 encoding
        """
        return clean_unicode_string(text)

    def _extract_text(self, doc: pymupdf.Document) -> List[str]:
        """
        Extracts text from all pages of the PDF document.

        Args:
            doc: The opened pymupdf Document object.
        Returns:
            List of text strings, one per page.
        """
        try:
            text_pages = []
            for page in doc:
                try:
                    # 获取原始文本
                    raw_text = page.get_text()
                    
                    # 如果文本为空或None，跳过
                    if not raw_text:
                        text_pages.append("")
                        continue
                    
                    # 尝试处理编码问题
                    if isinstance(raw_text, str):
                        # 清理代理字符和编码问题
                        cleaned_text = self._clean_unicode_text(raw_text)
                        text_pages.append(cleaned_text)
                    else:
                        # 如果不是字符串，尝试转换
                        text_pages.append(str(raw_text))
                        
                except Exception as e:
                    logger.warning(f"Failed to extract text from page: {e}")
                    text_pages.append("")
                    
            return text_pages
        except Exception as e:
            logger.warning(f"Failed to extract text: {e}")
            return []

    def _extract_xref(self, doc: pymupdf.Document) -> List[str]:
        """
        Extracts xref subtype keys from the PDF document.

        Args:
            doc: The opened pymupdf Document object.
        Returns:
            List of unique xref subtype keys.
        """
        xref = []
        try:
            for xref_idx in range(1, doc.xref_length()):
                exists, xref_key = doc.xref_get_key(xref_idx, "Subtype")
                if exists and xref_key != "null":
                    xref.append(xref_key)
            return list(set(xref))
        except Exception as e:
            logger.warning(f"Failed to extract xref: {e}")
            return []

    def _extract_toc(self, doc: pymupdf.Document) -> List[str]:
        """
        Extracts the table of contents from the PDF document.

        Args:
            doc: The opened pymupdf Document object.
        Returns:
            List of toc entries as formatted strings.
        """
        try:
            toc_raw = doc.get_toc()
            toc = [f"{item[0]}|||{item[1]}|||{item[2]}" for item in toc_raw]
            return toc
        except Exception as e:
            logger.warning(f"Failed to extract TOC: {e}")
            return []

    def _extract_page_images(self, doc: pymupdf.Document) -> List[str]:
        """
        Extracts base64-encoded images for each page in the PDF document.

        Args:
            doc: The opened pymupdf Document object.
        Returns:
            List of base64-encoded images (as strings), one per page.
        """
        page_image = []
        try:
            for page_idx in range(doc.page_count):
                page = doc.load_page(page_idx)
                pixmap = page.get_pixmap()
                page_image.append(base64.b64encode(pixmap.tobytes()).decode("utf-8"))
            return page_image
        except Exception as e:
            logger.warning(f"Failed to extract page images: {e}")
            return []

    def _detect_language(
        self, text: List[str], detector: Optional[LanguageDetector]
    ) -> str:
        """
        Detects the language of the concatenated text using the provided detector.

        Args:
            text: List of text strings from the PDF.
            detector: Optional LanguageDetector instance.
        Returns:
            Detected language as a string, or 'None' if not detected.
        """
        if detector is None:
            return "None"
        try:
            # 检查文本是否为空
            if not text or not any(text):
                return "None"
            
            # 连接文本并检测语言
            combined_text = " ".join(text)
            if not combined_text.strip():
                return "None"
                
            detected_language = detector.detect_language_of(combined_text)
            
            # 检查检测结果是否为None
            if detected_language is None:
                return "None"
                
            return str(detected_language.name).lower()
        except Exception as e:
            logger.warning(f"Failed to detect language: {e}")
            return "None"

    @staticmethod
    def from_file(
        file_path: Path,
        lan_detect: bool = False,
        detector: Optional[LanguageDetector] = None,
        page_save: bool = False,
    ) -> Optional["PDFContent"]:
        """
        Reads a PDF file and extracts its content.
        Args:
            file_path: The  absolute path to the PDF file.
            is_lan_detect: Whether to detect the language of the text.
            detector: An optional LanguageDetector instance.
            page_save: Whether to save page images as base64.
        Returns:
            A PDFContent object containing the extracted information, or None if an error occurs.
        """
        file_path = Path(file_path).absolute()
        if not file_path.exists():
            logger.error(f"PDF file does not exist: {file_path}")
            return None
        
        # 检查文件路径长度
        file_path_str = str(file_path)
        if len(file_path_str) > 260:
            logger.error(f"File path too long ({len(file_path_str)} chars): {file_path}")
            return None
        
        # 检查文件大小
        try:
            file_size = file_path.stat().st_size
            if file_size == 0:
                logger.error(f"PDF file is empty: {file_path}")
                return None
            if file_size > 500 * 1024 * 1024:  # 500MB
                logger.warning(f"PDF file is very large ({file_size / 1024 / 1024:.1f}MB): {file_path}")
        except Exception as e:
            logger.error(f"Failed to get file size for {file_path}: {e}")
            return None
        
        try:
            # 尝试打开 PDF 文件
            doc = pymupdf.open(file_path)
            
            # 检查 PDF 是否有效
            if doc.page_count == 0:
                logger.warning(f"PDF has no pages: {file_path}")
                doc.close()
                return None
                
        except pymupdf.FileDataError as e:
            logger.error(f"PDF file data error for {file_path}: {e}")
            return None
        except pymupdf.FileDataError as e:
            logger.error(f"PDF file format error for {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to open PDF file {file_path}: {e}")
            return None
        
        try:
            metadata = doc.metadata
            timestamp = int(datetime.now().timestamp())
            temp_instance = PDFContent()
            text = temp_instance._extract_text(doc)
            language = (
                temp_instance._detect_language(text, detector)
                if lan_detect
                else "None"
            )
            xref = temp_instance._extract_xref(doc)
            toc = temp_instance._extract_toc(doc)
            page_image = temp_instance._extract_page_images(doc) if page_save else []
            
            # 确保关闭文档
            doc.close()
            
        except Exception as e:
            logger.exception(f"Error processing PDF file {file_path}: {e}")
            try:
                doc.close()
            except:
                pass
            return None
        
        file_available = True
        if file_available:
            metadata = pdf_metadata_refine(metadata)
        return PDFContent(
            file_path=str(file_path),
            file_size=round(Path(file_path).stat().st_size / 1024 / 1024, 2),
            file_available=file_available,
            metadata=metadata,
            timestamp=str(timestamp),
            language=language,
            text=text,
            page=page_image,
            xref=xref,
            toc=toc,
        )

    def to_dict(self) -> dict:
        return self.model_dump()


def get_processed_files(output_file: Path) -> Set[str]:
    """
    Reads the set of processed file paths from the output JSONL file.

    Args:
        output_file: The path to the output JSONL file.

    Returns:
        A set of file paths that have already been processed.
    """
    processed = set()
    if output_file.exists():
        with jsonlines.open(output_file, mode="r") as reader:
            for obj in reader:
                # 假设 file_path 字段唯一标识 PDF
                processed.add(obj.get("file_path", ""))
    return processed


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract text and metadata from PDF files and save to JSONL format"
    )
    parser.add_argument(
        "-i", "--input", type=Path, required=True,
        help="Input file list (txt with paths) or single PDF file"
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("output.jsonl"),
        help="Output JSONL file (default: output.jsonl)"
    )
    parser.add_argument(
        "-l", "--log", type=Path, default=Path("log.log"),
        help="Log file (default: log.log)"
    )
    parser.add_argument(
        "-m", "--max-lines", type=int, default=100000,
        help="Maximum lines per output file (default: 100000)"
    )
    parser.add_argument(
        "-d", "--lan-detect", action="store_true",
        help="Enable language detection for PDF content"
    )
    parser.add_argument(
        "-p", "--page-save", action="store_true",
        help="Save page images for PDF content"
    )
    parser.add_argument(
        "-r", "--resume", action="store_true",
        help="Resume from previous processing (skip already processed files)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_file: Path = args.input.resolve()
    output_file: Path = args.output.resolve()
    log_file: Path = args.log.resolve()
    lan_detect: bool = args.lan_detect
    page_save: bool = args.page_save
    resume: bool = args.resume

    # Configure logging
    logger.add(log_file, rotation="500 MB", retention="10 days")
    logger.info(
        f"Starting PDF processing - Resume: {resume}, Language Detection: {lan_detect}"
    )

    # Validate input file
    if not input_file.exists():
        logger.error(f"Input file does not exist: {input_file}")
        return

    # Build file list
    if input_file.suffix == ".txt":
        try:
            input_list = input_file.read_text(encoding="utf-8").splitlines()
            input_list = [
                input_file.parent / file.strip() for file in input_list if file.strip()
            ]
            logger.info(f"Input file list: {input_file}, {len(input_list)} files")
        except Exception as e:
            logger.error(f"Error reading input file list: {e}")
            return
    else:
        input_list = [input_file]
        logger.info(f"Input file: {input_file}")

    # Setup language detector if needed
    detector = None
    if lan_detect:
        logger.info("Language detection is enabled")
        try:
            detector = (
                LanguageDetectorBuilder.from_all_languages()
                .with_preloaded_language_models()
                .build()
            )
        except Exception as e:
            logger.error(f"Failed to initialize language detector: {e}")
            return
    else:
        logger.info("Language detection is disabled")

    logger.info(f"Output file: {output_file}")

    # Get processed files for resume functionality
    processed_files = set()
    if resume:
        processed_files = get_processed_files(output_file)
        logger.info(f"Resume mode: {len(processed_files)} files already processed")

    # Filter out already processed files
    files_to_process = []
    for file_path in input_list:
        file_path_str = str(Path(file_path).absolute())
        if file_path_str not in processed_files:
            files_to_process.append(file_path)

    logger.info(f"Files to process: {len(files_to_process)}")

    # Process files with line counting and file rotation
    success_count = 0
    error_count = 0
    current_line_count = 0
    current_file_index = 1
    max_lines_per_file = args.max_lines  # 使用命令行参数
    
    # 获取当前输出文件的基础信息
    output_stem = output_file.stem
    output_suffix = output_file.suffix
    output_parent = output_file.parent
    
    # 如果resume模式，需要找到最后一个文件的行数
    if resume:
        # 查找已存在的文件，确定当前文件索引和行数
        existing_files = list(output_parent.glob(f"{output_stem}_*{output_suffix}"))
        if existing_files:
            # 按文件名排序，找到最后一个文件
            existing_files.sort()
            last_file = existing_files[-1]
            # 从文件名中提取索引
            try:
                # 提取文件名中的数字部分
                filename = last_file.stem
                index_str = filename.split('_')[-1]
                current_file_index = int(index_str)
                # 计算最后一个文件的行数
                with jsonlines.open(last_file, mode="r") as reader:
                    current_line_count = sum(1 for _ in reader)
                logger.info(f"Resume: found existing file {last_file} with {current_line_count} lines")
            except (ValueError, IndexError):
                logger.warning(f"Could not parse file index from {last_file}, starting fresh")
                current_file_index = 1
                current_line_count = 0
    
    def get_current_output_file() -> Path:
        """获取当前输出文件路径"""
        # 估算总文件数量，动态设置索引格式
        estimated_total_files = max(10, len(files_to_process) // (max_lines_per_file // 100) + 1)
        # 计算需要的位数：log10(estimated_total_files) + 1，最小2位
        digits = max(2, len(str(estimated_total_files)))
        index_format = f"0{digits}d"
        
        return output_parent / f"{output_stem}_{current_file_index:{index_format}}{output_suffix}"
    
    def switch_to_next_file():
        """切换到下一个输出文件"""
        nonlocal current_file_index, current_line_count
        current_file_index += 1
        current_line_count = 0
        new_file = get_current_output_file()
        logger.info(f"Switching to new output file: {new_file}")
        return new_file

    current_output_file = get_current_output_file()
    
    with jsonlines.open(current_output_file, mode="a") as writer:
        for input_file in tqdm(files_to_process, desc="Processing PDFs", leave=False):
            pdf_content = PDFContent.from_file(
                input_file, lan_detect, detector, page_save
            )
            if pdf_content is None:
                error_count += 1
                continue

            try:
                writer.write(pdf_content.to_dict())
                success_count += 1
                current_line_count += 1
                
                # 检查是否需要切换到下一个文件
                if current_line_count >= max_lines_per_file:
                    # 关闭当前文件
                    writer.close()
                    # 切换到下一个文件
                    current_output_file = switch_to_next_file()
                    # 重新打开新文件
                    writer = jsonlines.open(current_output_file, mode="a")
                    
            except UnicodeEncodeError as e:
                logger.exception(f"UnicodeEncodeError for file {input_file}: {e}")
                error_count += 1
            except Exception as e:
                logger.exception(f"Unexpected error for file {input_file}: {e}")
                error_count += 1

    # Summary
    logger.info(
        f"Processing completed - Success: {success_count}, Errors: {error_count}, Files created: {current_file_index}"
    )
    print(f"Processing completed - Success: {success_count}, Errors: {error_count}, Files created: {current_file_index}")


if __name__ == "__main__":
    main()
