from io import BytesIO

from docx import Document

from sensitive_filter import SensitiveWordFilter
from sensitive_filter.docx_handler import document_text, replace_docx, scan_docx


engine = SensitiveWordFilter([{"word": "示例敏感词", "category": "测试", "level": 1}])
document = Document()
paragraph = document.add_paragraph("正文：")
paragraph.add_run("示例").bold = True
paragraph.add_run("敏感词")

# 多行、合并和嵌套表格覆盖曾经因对象 ID 复用而漏读的场景。
table = document.add_table(rows=120, cols=2)
expected_table_matches = 0
for index, row in enumerate(table.rows):
    row.cells[0].text = f"第 {index} 行"
    row.cells[1].text = f"表格示例敏感词 {index}"
    expected_table_matches += 1
merged = table.cell(0, 0).merge(table.cell(0, 1))
merged.text = "合并单元格示例敏感词"
nested = table.cell(1, 0).add_table(rows=1, cols=1)
nested.cell(0, 0).text = "嵌套表示例敏感词"
expected_table_matches += 1

document.sections[0].header.paragraphs[0].text = "页眉示例敏感词"
document.sections[0].footer.paragraphs[0].text = "页脚示例敏感词"
source = BytesIO()
document.save(source)

expected_total = 1 + expected_table_matches + 2
scanned = scan_docx(source.getvalue(), engine)
assert scanned["count"] == expected_total, (scanned["count"], expected_total)
assert scanned["text_length"] > 1_000

output, result = replace_docx(source.getvalue(), engine)
assert result["count"] == expected_total
filtered = Document(BytesIO(output))
filtered_text = document_text(filtered)
assert "示例敏感词" not in filtered_text
assert filtered_text.count("*****") == expected_total
assert filtered.paragraphs[0].runs[1].bold is True

# 页面只返回有限预览，但文末命中仍必须被检测和替换。
large_document = Document()
large_document.add_paragraph("普通内容" * 55_000)
large_document.add_paragraph("文末示例敏感词")
large_source = BytesIO()
large_document.save(large_source)
large_scan = scan_docx(large_source.getvalue(), engine)
assert large_scan["text_length"] > 200_000
assert large_scan["text_truncated"] is True
assert large_scan["count"] == 1
large_output, large_result = replace_docx(large_source.getvalue(), engine)
assert large_result["count"] == 1
assert "示例敏感词" not in document_text(Document(BytesIO(large_output)))
print("DOCX paragraphs/tables/merged/nested scan and replace passed")
