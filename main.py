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
    # {"format": "PDF 1.4", "title": "", "author": "", "subject": "", "keywords": "", "creator": "", "producer": "", "creationDate": "", "modDate": "", "trapped": "", "encryption": "None"}
    for key, value in metadata.items():
        if "Date" in key:  # creationDate, modDate
            try:
                if isinstance(value, str) and value.startswith("D:"):
                    date_part = value[2:16]
                    if len(date_part) >= 14:
                        dt = datetime.strptime(date_part[:14], "%Y%m%d%H%M%S")
                        timestamp = int(dt.timestamp())
                elif isinstance(value, str) and len(value) >= 8:
                    dt = datetime.strptime(value[:8], "%Y%m%d")
                    timestamp = int(dt.timestamp())
                else:
                    timestamp = int(datetime.now().timestamp())
            except Exception as e:
                logger.warning(f"Failed to parse date {key}={value}: {e}")
                timestamp = int(datetime.now().timestamp())

            metadata[key] = timestamp
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
    toc: List[Dict[str, Any]] = Field(
        default_factory=list, description="The table of contents of the PDF file"
    )

    @staticmethod
    def from_file(
        file_path: str, is_lan_detect: bool = False, detector: LanguageDetector = None
    ) -> Optional["PDFContent"]:
        """
        Reads a PDF file and extracts its content.
        
        Args:
            file_path: The absolute path to the PDF file.
            is_lan_detect: Whether to detect the language of the text.
            detector: An optional LanguageDetector instance.
            
        Returns:
            A PDFContent object containing the extracted information, or None if an error occurs.
        """
        file_path = Path(file_path).absolute()
        
        # Early check for file existence
        if not file_path.exists():
            logger.error(f"PDF file does not exist: {file_path}")
            return None
        
        try:
            doc = pymupdf.open(file_path)
            metadata = doc.metadata
            timestamp = int(datetime.now().timestamp())
            text = [page.get_text() for page in doc]
            if is_lan_detect:
                language = str(detector.detect_language_of(" ".join(text)).name).lower()
            else:
                language = "None"
            
            # xref
            xref = []
            for xref_idx in range(1, doc.xref_length()):
                exists, xref_key = doc.xref_get_key(xref_idx, "Subtype")
                if exists and xref_key != "null":
                    xref.append(xref_key)
            xref = list(set(xref))

            # toc - keep as structured data instead of string concatenation
            toc_raw = doc.get_toc()
            toc = [
                {
                    "level": item[0],  # 层级级别 (1, 2, 3, ...)
                    "title": item[1],  # 标题文本
                    "page": item[2],  # 页码
                }
                for item in toc_raw
            ]
            toc = [
                f"{item['level']}|||{item['title']}|||{item['page']}"
                for item in toc
            ]

        except Exception as e:
            logger.exception(f"Error reading PDF file {file_path}: {e}")
            return None

        file_available = True

        if file_available:
            # check metadata info
            metadata = pdf_metadata_refine(metadata)

        return PDFContent(
            file_path=str(file_path),
            file_size=round(Path(file_path).stat().st_size / 1024 / 1024, 2),
            file_available=file_available,
            metadata=metadata,
            timestamp=str(timestamp),
            language=language,
            text=text,
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


def main() -> None:
    """
    Main function to process PDF files and extract content.
    """
    parser = argparse.ArgumentParser(
        description="Extract text and metadata from PDF files and save to JSONL format"
    )
    parser.add_argument(
        "-i",
        "--input_file",
        type=str,
        required=True,
        help="The input file list (txt file with paths) or single PDF file",
    )
    parser.add_argument(
        "-o",
        "--output_file",
        type=str,
        required=False,
        help="The output jsonl file",
        default="output.jsonl",
    )
    parser.add_argument(
        "-l",
        "--log_file",
        type=str,
        required=False,
        help="The log file",
        default="log.log",
    )
    parser.add_argument(
        "-d",
        "--lan_detect",
        action="store_true",
        help="Enable language detection for PDF content",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous processing (skip already processed files)",
    )
    args = parser.parse_args()
    
    input_file = Path(args.input_file).absolute()
    output_file = Path(args.output_file).absolute()
    log_file = Path(args.log_file).absolute()
    lan_detect = args.lan_detect
    resume = args.resume

    # Configure logging
    logger.add(log_file, rotation="500 MB", retention="10 days")
    logger.info(f"Starting PDF processing - Resume: {resume}, Language Detection: {lan_detect}")

    # Validate input file
    if not input_file.exists():
        logger.error(f"Input file does not exist: {input_file}")
        return

    # Build file list
    if input_file.suffix == ".txt":
        try:
            input_list = input_file.read_text(encoding="utf-8").splitlines()
            input_list = [input_file.parent / file.strip() for file in input_list if file.strip()]
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

    # Process files
    success_count = 0
    error_count = 0
    
    with jsonlines.open(output_file, mode="a") as writer:
        for input_file in tqdm(files_to_process, desc="Processing PDFs", leave=False):
            pdf_content = PDFContent.from_file(input_file, lan_detect, detector)
            if pdf_content is None:
                error_count += 1
                continue
            
            try:
                writer.write(pdf_content.to_dict())
                success_count += 1
            except UnicodeEncodeError as e:
                logger.exception(f"UnicodeEncodeError for file {input_file}: {e}")
                error_count += 1
            except Exception as e:
                logger.exception(f"Unexpected error for file {input_file}: {e}")
                error_count += 1

    # Summary
    logger.info(f"Processing completed - Success: {success_count}, Errors: {error_count}")
    print(f"Processing completed - Success: {success_count}, Errors: {error_count}")


if __name__ == "__main__":
    main()
