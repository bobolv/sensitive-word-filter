from io import BytesIO

from docx import Document

from sensitive_filter import SensitiveWordFilter
from sensitive_filter.docx_handler import document_text, replace_docx, scan_docx


engine = SensitiveWordFilter([{"word": "示例敏感词", "category": "测试", "level": 1}])
document = Document()
paragraph = document.add_paragraph("正文：")
paragraph.add_run("示例").bold = True
paragraph.add_run("敏感词")
table = document.add_table(rows=1, cols=1)
table.cell(0, 0).text = "表格示例敏感词"
document.sections[0].header.paragraphs[0].text = "页眉示例敏感词"
document.sections[0].footer.paragraphs[0].text = "页脚示例敏感词"
source = BytesIO()
document.save(source)

scanned = scan_docx(source.getvalue(), engine)
assert scanned["count"] == 4

output, result = replace_docx(source.getvalue(), engine)
assert result["count"] == 4
filtered = Document(BytesIO(output))
filtered_text = document_text(filtered)
assert "示例敏感词" not in filtered_text
assert filtered_text.count("*****") == 4
assert filtered.tables[0].cell(0, 0).text == "表格*****"
assert filtered.paragraphs[0].runs[1].bold is True
print("DOCX scan/replace structural test passed")
