# PDFtoText MNBVC

高效的 PDF 批量文本与元数据提取工具，支持断点续跑、语言检测、结构化输出。

## 特性

- 支持单个 PDF 或批量文件列表处理
- 输出结构化 JSONL，包含文本、元数据、目录、xref 等
- 可选语言检测（lingua）
- 断点续跑，自动跳过已处理文件
- 日志记录与进度条显示
- 完善的类型注解和异常处理

## 安装

```bash
# 推荐使用 Python 3.10+
pip install -r requirements.txt
```

## 使用方法

### 基本命令

```bash
python main.py -i input.pdf -o output.jsonl
python main.py -i filelist.txt -o output.jsonl
```

### 常用参数

| 参数                | 说明                                 |
|---------------------|--------------------------------------|
| -i, --input         | 输入 PDF 文件或包含 PDF 路径的 txt   |
| -o, --output        | 输出 JSONL 文件（默认 output.jsonl） |
| -l, --log           | 日志文件（默认 log.log）             |
| -m, --max-lines     | 每个输出文件最大行数（默认 100000）  |
| -d, --lan-detect    | 启用语言检测（可选）                 |
| -p, --page-save     | 保存每页图片（base64，体积大，选用）  |
| -r, --resume        | 断点续跑，跳过已处理文件（可选）      |

### 示例

```bash
# 处理单个 PDF
python main.py -i doc.pdf -o result.jsonl

# 批量处理
python main.py -i filelist.txt -o result.jsonl

# 启用语言检测
python main.py -i filelist.txt -o result.jsonl -d

# 断点续跑
python main.py -i filelist.txt -o result.jsonl -r

# 自定义每个文件最大行数（5万行）
python main.py -i filelist.txt -o result.jsonl -m 50000

# 组合使用：语言检测 + 自定义行数 + 断点续跑
python main.py -i filelist.txt -o result.jsonl -d -m 50000 -r
```

## 输入文件格式

- **单个 PDF**：直接传入 PDF 路径
- **文件列表**：txt 文件，每行一个 PDF 路径（相对或绝对）

## 输出格式

- 每行为一个 JSON 对象，字段包括：
  - `file_path`：PDF绝对路径
  - `file_size`：文件大小（MB）
  - `file_available`：文件是否可用
  - `metadata`：PDF元数据（日期自动转为时间戳）
  - `timestamp`：处理时间戳
  - `language`：检测到的语言（如启用）
  - `text`：每页文本内容
  - `xref`：交叉引用类型
  - `toc`：目录结构

### 文件分割

当处理大量文件时，程序会自动分割输出文件：
- 默认每个文件最多 10 万行
- 可通过 `-m/--max-lines` 参数自定义
- 文件命名格式：`output_001.jsonl`, `output_002.jsonl` 等
- 支持断点续跑，自动从上次分割位置继续

## 日志与错误处理

- 日志文件默认 `log.log`
- 自动跳过损坏或不存在的文件，详细记录错误

## 依赖

- pymupdf
- lingua
- tqdm
- loguru
- pydantic
- jsonlines
