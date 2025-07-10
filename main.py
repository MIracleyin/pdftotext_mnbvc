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


def pdf_metadata_refine(metadata: dict):
    # {"format": "PDF 1.4", "title": "", "author": "", "subject": "", "keywords": "", "creator": "", "producer": "", "creationDate": "", "modDate": "", "trapped": "", "encryption": "None"}
    for key, value in metadata.items():
        if "Date" in key:  # creationDate, modDate
            try:
                if value.startswith("D:"):
                    date_part = value[2:16]
                    if len(date_part) >= 14:
                        dt = datetime.strptime(date_part[:14], "%Y%m%d%H%M%S")
                        timestamp = int(dt.timestamp())
                elif len(value) >= 8:
                    dt = datetime.strptime(value[:8], "%Y%m%d")
                    timestamp = int(dt.timestamp())
                else:
                    timestamp = int(datetime.now().timestamp())
            except Exception as e:
                timestamp = int(datetime.now().timestamp())

            metadata[key] = timestamp
    return metadata


class PDFContent(BaseModel):
    file_path: str = Field(description="The absolute path to the PDF file", default="")
    file_size: float = Field(description="The size of the PDF file, in MB", default=0)
    file_available: bool = Field(
        description="Whether the PDF file is available", default=False
    )
    metadata: dict = Field(description="The metadata of the PDF file", default={})
    timestamp: str = Field(description="The timestamp of the PDF file", default="")
    language: str = Field(description="The language of the PDF file", default="")
    text: list[str] = Field(description="The text of the PDF file", default=[])
    xref: list[str] = Field(description="The xref of the PDF file", default=[])

    @staticmethod
    def from_file(
        file_path: str, is_lan_detect: bool = False, detector: LanguageDetector = None
    ):
        file_path = Path(file_path).absolute()
        try:
            doc = pymupdf.open(file_path)
            metadata = doc.metadata
            timestamp = int(datetime.now().timestamp())
            text = [page.get_text() for page in doc]
            if is_lan_detect:
                language = str(detector.detect_language_of(" ".join(text)).name).lower()
            else:
                language = "None"
            xref = []
            for xref_idx in range(1, doc.xref_length()):
                exists, xref_key = doc.xref_get_key(xref_idx, "Subtype")
                if exists and xref_key != "null":
                    xref.append(xref_key)
            xref = list(set(xref))
        except Exception as e:
            logger.error(f"Error reading PDF file {file_path}: {e}")
            return None

        file_available = True

        if file_available:
            # check metadata info
            metadata = pdf_metadata_refine(metadata)

            # 处理 metadata
        return PDFContent(
            file_path=str(file_path),
            file_size=round(Path(file_path).stat().st_size / 1024 / 1024, 2),
            file_available=file_available,
            metadata=metadata,
            timestamp=str(timestamp),
            language=language,
            text=text,
            xref=xref,
        )

    def to_dict(self) -> dict:
        return self.model_dump()


def get_processed_files(output_file: Path) -> set[str]:
    """读取已处理的文件路径集合"""
    processed = set()
    if output_file.exists():
        with jsonlines.open(output_file, mode="r") as reader:
            for obj in reader:
                # 假设 file_path 字段唯一标识 PDF
                processed.add(obj.get("file_path", ""))
    return processed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i",
        "--input_file",
        type=str,
        required=True,
        help="The input file list",
        default="",
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
        type=bool,
        default=False,
        help="Whether to detect the language of the PDF file",
    )
    args = parser.parse_args()
    input_file = Path(args.input_file).absolute()
    output_file = Path(args.output_file).absolute()
    log_file = Path(args.log_file).absolute()
    lan_detect = args.lan_detect

    logger.add(log_file, rotation="500 MB", retention="10 days")

    if input_file.suffix == ".txt":
        input_list = input_file.read_text().splitlines()
        input_list = [input_file.parent / file for file in input_list]
        logger.info(f"Input file list: {input_file}, {len(input_list)} files")
    else:
        input_list = [input_file]
        logger.info(f"Input file: {input_file}")

    if lan_detect:
        logger.info("Language detection is enabled")
        detector = (
            LanguageDetectorBuilder.from_all_languages()
            .with_preloaded_language_models()
            .build()
        )
    else:
        logger.info("Language detection is disabled")
        detector = None

    logger.info(f"Output file: {output_file}")

    processed_files = get_processed_files(output_file)
    logger.info(f"Already processed {len(processed_files)} files, will skip them.")

    with jsonlines.open(output_file, mode="a") as writer:  # 用 append 模式
        for input_file in tqdm(input_list):
            file_path_str = str(Path(input_file).absolute())
            if file_path_str in processed_files:
                logger.info(f"File {input_file} already processed, will skip it.")
                continue
            pdf_content = PDFContent.from_file(input_file, lan_detect, detector)
            if pdf_content is None:
                logger.error(f"Error reading PDF file {input_file}")
                continue
            try:
                writer.write(pdf_content.to_dict())
            except UnicodeEncodeError as e:
                logger.error(f"UnicodeEncodeError for file {input_file}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error for file {input_file}: {e}")


if __name__ == "__main__":
    main()
