# PDFtoText MNBVC 工具

一个高效的 PDF 文本提取工具，用于批量处理 PDF 文件并输出结构化的 JSONL 格式数据。

## 🚀 功能特性

- **批量处理**: 支持单个 PDF 文件或文件列表批量处理
- **结构化输出**: 提取文本、元数据、目录、交叉引用等信息
- **语言检测**: 可选的多语言文本检测功能
- **断点续跑**: 支持中断后从上次位置继续处理
- **健壮性**: 完善的错误处理和日志记录
- **进度显示**: 实时进度条和处理统计
- **类型安全**: 完整的类型注解和数据验证

## 📦 安装

### 环境要求
- Python 3.12+
- uv (推荐) 或 pip

### 使用 uv 安装 (推荐)
```bash
# 创建虚拟环境
uv venv --python 3.12

# 激活虚拟环境 (可选，uv run 会自动激活)
source .venv/bin/activate  # Linux/macOS
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
uv sync
```

### 使用 pip 安装
```bash
pip install -r requirements.txt
```

## 🔧 使用方法

### 基本用法

```bash
# 处理单个 PDF 文件
uv run main.py -i document.pdf -o output.jsonl

# 处理文件列表
uv run main.py -i filelist.txt -o output.jsonl

# 启用语言检测
uv run main.py -i filelist.txt -o output.jsonl -d

# 断点续跑
uv run main.py -i filelist.txt -o output.jsonl --resume
```

### 完整参数说明

```bash
uv run main.py [OPTIONS]

选项:
  -i, --input_file TEXT     输入文件 (必需)
                           - 单个 PDF 文件路径
                           - 包含 PDF 文件路径列表的 txt 文件
  
  -o, --output_file TEXT    输出 JSONL 文件路径 (默认: output.jsonl)
  
  -l, --log_file TEXT       日志文件路径 (默认: log.log)
  
  -d, --lan_detect         启用语言检测 (可选)
  
  --resume                 断点续跑模式，跳过已处理的文件
  
  -h, --help               显示帮助信息
```

### 输入文件格式

#### 单个 PDF 文件
```bash
uv run main.py -i /path/to/document.pdf -o output.jsonl
```

#### 文件列表 (txt 格式)
创建一个 `filelist.txt` 文件，每行一个相对路径：
```
pdf1.pdf
subfolder/pdf2.pdf
another/pdf3.pdf
```

然后运行：
```bash
uv run main.py -i filelist.txt -o output.jsonl
```

## 📄 输出格式

输出为 JSONL 格式，每行一个 JSON 对象，包含以下字段：

```json
{
  "file_path": "/absolute/path/to/document.pdf",
  "file_size": 2.45,
  "file_available": true,
  "metadata": {
    "format": "PDF 1.4",
    "title": "Document Title",
    "author": "Author Name",
    "subject": "Document Subject",
    "keywords": "keyword1, keyword2",
    "creator": "Creator Software",
    "producer": "Producer Software",
    "creationDate": 1704067200,
    "modDate": 1704067200,
    "trapped": "",
    "encryption": "None"
  },
  "timestamp": "1704067200",
  "language": "english",
  "text": [
    "Page 1 content...",
    "Page 2 content...",
    "Page 3 content..."
  ],
  "xref": [
    "Font",
    "Image",
    "Form"
  ],
  "toc": [
    "1|||Chapter 1: Introduction|||1",
    "2|||1.1 Overview|||3",
    "2|||1.2 Methodology|||5",
    "1|||Chapter 2: Results|||10"
  ]
}
```

### 字段说明

| 字段 | 类型 | 描述 |
|------|------|------|
| `file_path` | string | PDF 文件的绝对路径 |
| `file_size` | float | 文件大小 (MB) |
| `file_available` | boolean | 文件是否可用 |
| `metadata` | object | PDF 元数据信息 |
| `timestamp` | string | 处理时间戳 |
| `language` | string | 检测到的语言 (需启用 -d 选项) |
| `text` | array | 每页提取的文本内容 |
| `xref` | array | 交叉引用表条目 |
| `toc` | array | 目录结构 |

## 🔍 语言检测

启用语言检测功能 (`-d` 选项) 会自动检测 PDF 文本的主要语言：

```bash
uv run main.py -i document.pdf -o output.jsonl -d
```

支持的语言包括但不限于：
- 中文 (chinese)
- 英文 (english)
- 日文 (japanese)
- 韩文 (korean)
- 法文 (french)
- 德文 (german)
- 等等...

## 🔄 断点续跑

当处理大量文件时，可以使用 `--resume` 选项在中断后继续处理：

```bash
# 首次运行
uv run main.py -i large_filelist.txt -o output.jsonl

# 如果中断，可以续跑
uv run main.py -i large_filelist.txt -o output.jsonl --resume
```

程序会自动检测已处理的文件并跳过，只处理未完成的部分。

## 📊 日志和监控

### 日志文件
程序会生成详细的日志文件 (默认 `log.log`)，包含：
- 处理进度信息
- 错误和警告信息
- 性能统计数据
- 文件处理状态

### 实时监控
运行时会显示：
- 进度条
- 处理速度
- 成功/失败统计

## ⚠️ 错误处理

程序具有完善的错误处理机制：

1. **文件不存在**: 自动跳过并记录日志
2. **PDF 损坏**: 记录错误并继续处理下一个文件
3. **编码错误**: 处理 Unicode 编码问题
4. **内存不足**: 优雅处理大文件

## 🛠️ 故障排除

### 常见问题

1. **ModuleNotFoundError**
   ```bash
   # 确保安装了所有依赖
   uv sync
   ```

2. **Permission denied**
   ```bash
   # 检查文件权限
   chmod +r input.pdf
   ```

3. **Memory error**
   ```bash
   # 处理大文件时，考虑分批处理
   split -l 100 large_filelist.txt batch_
   ```

### 性能优化建议

1. **大文件处理**: 对于大量文件，建议分批处理
2. **语言检测**: 仅在需要时启用，会影响处理速度
3. **存储空间**: 确保有足够的磁盘空间存储输出文件

## 🧪 测试

项目包含基本的测试用例，可以验证核心功能：

```bash
# 运行基本功能测试
python -c "
from main import pdf_metadata_refine, PDFContent
print('Testing metadata refinement...')
result = pdf_metadata_refine({'creationDate': 'D:20240101120000'})
assert isinstance(result['creationDate'], int)
print('✅ All tests passed!')
"
```

## 📈 性能指标

在标准配置下的性能参考：
- **处理速度**: 约 2-10 文件/秒 (取决于文件大小)
- **内存使用**: 通常 < 500MB
- **支持文件大小**: 理论上无限制，建议单文件 < 100MB

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📝 许可证

本项目采用 MIT 许可证。

## 📞 联系方式

如有问题或建议，请通过以下方式联系：
- 提交 GitHub Issue
- 发送邮件至维护者

---

## 🎯 快速开始示例

```bash
# 1. 克隆项目
git clone <repository-url>
cd pdftotext_mnbvc

# 2. 安装依赖
uv sync

# 3. 准备测试文件
echo "test.pdf" > filelist.txt

# 4. 运行处理
uv run main.py -i filelist.txt -o result.jsonl -d

# 5. 查看结果
head -1 result.jsonl | jq .
```

开始你的 PDF 文本提取之旅吧！🚀
