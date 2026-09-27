"""Offline OOXML privacy cleanup; filesystem times are handled by batch.py."""
from copy import copy
from io import BytesIO
import posixpath
from zipfile import ZipFile
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def clear_author_properties(content: bytes, extension: str) -> tuple[bytes, dict]:
    """Compatibility entry point, now clears properties and review metadata."""
    if extension.lower() not in (".docx", ".xlsx"):
        raise ValueError("文档信息清理仅支持 DOCX、XLSX")
    changes = []
    def record(field, count=1):
        if count:
            changes.append({"field": field, "before": "存在", "after": "已清理", "count": count})
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    output = BytesIO()
    with ZipFile(BytesIO(content)) as source, ZipFile(output, "w") as target:
        names = source.namelist()
        expected = "word/document.xml" if extension.lower() == ".docx" else "xl/workbook.xml"
        if expected not in names or "[Content_Types].xml" not in names:
            raise ValueError("文件不是有效的 Office 文档")
        if len(names) != len(set(names)):
            raise ValueError("文档包含重复压缩条目")
        if any("/embeddings/" in n or n.startswith("_xmlsignatures/") for n in names):
            raise ValueError("文档含嵌入附件或数字签名，请先移除后清理，无法保证其内部个人信息已清除")
        removed = {n for n in names if n.startswith(("customXml/", "docProps/thumbnail"))
                   or (n.startswith(("word/", "xl/")) and any(
                       token in n.lower() for token in ("/comments", "/threadedcomments/", "/persons/", "/people.")))}
        record("批注、人员记录、自定义 XML、缩略图", len(removed))
        for info in source.infolist():
            name = info.filename
            if name in removed:
                continue
            data = source.read(info)
            if name.endswith((".xml", ".rels", ".vml")):
                root = etree.fromstring(data, parser)
                if root.getroottree().docinfo.doctype:
                    raise ValueError("不支持含 DTD 的文档")
                changed = False
                if name in ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"):
                    record("文档属性：" + name, sum(bool(c.text or len(c) or c.attrib) for c in root) + len(root.attrib))
                    changed = bool(len(root) or root.attrib or root.text)
                    for child in list(root):
                        root.remove(child)
                    root.attrib.clear()
                    root.text = None
                    if name == "docProps/core.xml":
                        # An explicit empty creator prevents readers injecting their default author.
                        etree.SubElement(root, "{http://purl.org/dc/elements/1.1/}creator")
                elif name.endswith(".rels"):
                    base = posixpath.dirname(posixpath.dirname(name))
                    for rel in list(root):
                        resolved = posixpath.normpath(posixpath.join(base, rel.get("Target", ""))).lstrip("/")
                        if resolved in removed:
                            root.remove(rel)
                            changed = True
                elif name == "[Content_Types].xml":
                    for part in list(root):
                        if part.get("PartName", "").lstrip("/") in removed:
                            root.remove(part)
                            changed = True
                elif name.startswith(("word/", "xl/")):
                    for node in list(root.iter()):
                        if not isinstance(node.tag, str):
                            continue
                        local = etree.QName(node).localname
                        namespace = etree.QName(node).namespace or ""
                        parent = node.getparent()
                        delete = namespace == W and (local in (
                            "del", "moveFrom", "commentRangeStart", "commentRangeEnd", "commentReference",
                            "moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd",
                            "rsids", "docVars", "dataBinding") or local.endswith("PrChange") or local == "tblGridChange")
                        delete = delete or local in ("threadedComment", "person", "personList")
                        delete = delete or (local == "shape" and bool(node.xpath('.//*[local-name()="ClientData" and @ObjectType="Note"]')))
                        if delete and parent is not None:
                            parent.remove(node)
                            record("批注或修订历史")
                            changed = True
                            continue
                        if namespace == W and local in ("ins", "moveTo") and parent is not None:
                            index = parent.index(node)
                            for child in list(node):
                                parent.insert(index, child)
                                index += 1
                            parent.remove(node)
                            record("接受修订并清理身份")
                            changed = True
                            continue
                        for attr in list(node.attrib):
                            key = etree.QName(attr).localname
                            if key in ("author", "initials", "userId", "providerId", "personId", "date", "dateUtc") or key.startswith("rsid"):
                                del node.attrib[attr]
                                record("人员标识及编辑记录")
                                changed = True
                if changed:
                    data = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
            sanitized_info = copy(info)
            sanitized_info.comment = b""
            sanitized_info.extra = b""
            target.writestr(sanitized_info, data)
    return output.getvalue(), {"count": sum(c["count"] for c in changes), "changes": changes}
