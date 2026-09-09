const text = document.querySelector("#text");
const counter = document.querySelector("#counter");
const result = document.querySelector("#result");
const toast = document.querySelector("#toast");
const scanButton = document.querySelector("#scan");
let uploadedFile = null;
let fileKind = null;

const notify = (message, duration = 2400) => {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), duration);
};

text.oninput = () => {
  counter.textContent = `${text.value.length.toLocaleString()} 字符`;
};

document.querySelector("#clear").onclick = () => {
  text.value = "";
  text.placeholder = "请粘贴需要检测的文本，或上传 TXT、DOCX、XLSX 文件……";
  uploadedFile = null;
  fileKind = null;
  document.querySelector("#file").value = "";
  text.oninput();
  result.classList.add("hidden");
};

document.querySelector("#file").onchange = async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const lowerName = file.name.toLowerCase();
  if (lowerName.endsWith(".docx")) fileKind = "docx";
  else if (lowerName.endsWith(".xlsx")) fileKind = "xlsx";
  else fileKind = "txt";

  if (fileKind === "txt") {
    uploadedFile = null;
    text.value = await file.text();
    text.oninput();
    notify(`已载入 ${file.name}`);
    return;
  }

  uploadedFile = file;
  text.value = "";
  text.placeholder = `正在读取 ${file.name}，大文件可能需要一些时间……`;
  text.oninput();
  await scanUploadedFile();
};

async function scanUploadedFile() {
  if (!uploadedFile || !fileKind) return;
  setBusy(true, "读取并检测中…");
  try {
    const form = new FormData();
    form.append("file", uploadedFile);
    const response = await fetch(`/scan-${fileKind}`, { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "文件检测失败");
    text.value = data.text_preview || "";
    text.oninput();
    showResult(data);
  } catch (error) {
    notify(error.message || "文件检测失败", 4000);
  } finally {
    setBusy(false);
  }
}

scanButton.onclick = async () => {
  if (uploadedFile) return scanUploadedFile();
  if (!text.value.trim()) return notify("请先输入文本或上传文件");
  setBusy(true, "检测中…");
  try {
    const response = await fetch("/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text.value, min_level: 1 }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "检测失败");
    showResult(data);
  } catch (error) {
    notify(error.message || "检测失败", 4000);
  } finally {
    setBusy(false);
  }
};

function setBusy(busy, label = "开始检测") {
  scanButton.disabled = busy;
  scanButton.textContent = busy ? label : "开始检测";
}

function showResult(data) {
  result.classList.remove("hidden");
  const badge = document.querySelector("#badge");
  const hint = document.querySelector("#fileHint");
  const replace = document.querySelector("#replace");
  const restore = document.querySelector("#restore");
  const wordTools = document.querySelectorAll(".word-tool");
  badge.className = `badge ${data.sensitive ? "risk" : "safe"}`;
  document.querySelector("#summary").textContent = data.sensitive
    ? `发现 ${data.count.toLocaleString()} 处风险内容`
    : "未发现敏感内容";

  document.querySelector("#matches").innerHTML = data.matches.map((item) => {
    const location = item.sheet ? `${item.sheet}!${item.cell} · ` : "";
    return `<span class="match">${escapeHtml(location)}${escapeHtml(item.matched_text)} · ${escapeHtml(item.category)} · L${item.level}</span>`;
  }).join("");

  if (uploadedFile) {
    const kindName = fileKind === "docx" ? "Word" : "Excel";
    const previewNote = data.text_truncated
      ? ` 文档共 ${data.text_length.toLocaleString()} 个文本字符，页面仅显示前 ${text.value.length.toLocaleString()} 个；检测和替换仍处理全部内容。`
      : "";
    const matchNote = data.matches_truncated ? " 命中列表较长，页面仅显示前 2,000 条。" : "";
    hint.textContent = `${kindName} 文件：${uploadedFile.name}。替换后将下载新文件，原文件不会被覆盖。${previewNote}${matchNote}`;
    hint.classList.remove("hidden");
    replace.textContent = `替换并下载 ${kindName}`;
    restore.textContent = `反向恢复并下载 ${kindName}`;
    wordTools.forEach((button) => button.classList.toggle("hidden", fileKind !== "docx"));
  } else {
    hint.classList.add("hidden");
    replace.textContent = "执行替换";
    restore.textContent = "反向恢复";
    wordTools.forEach((button) => button.classList.add("hidden"));
  }
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

document.querySelector("#replace").onclick = async () => {
  const replacement = document.querySelector("#replacement").value.trim() || "*";
  if (uploadedFile) {
    const form = new FormData();
    form.append("file", uploadedFile);
    notify("正在生成替换后的文件，请稍候…", 3000);
    const response = await fetch(
      `/replace-${fileKind}?replacement=${encodeURIComponent(replacement)}&min_level=1`,
      { method: "POST", body: form },
    );
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      return notify(data.detail || "文件处理失败", 4000);
    }
    saveBlob(await response.blob(), uploadedFile.name.replace(/\.(docx|xlsx)$/i, "_filtered.$1"));
    notify("替换后的文件已保存");
    return;
  }

  const response = await fetch("/replace", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text.value, min_level: 1, replacement }),
  });
  const data = await response.json();
  text.value = data.text;
  text.oninput();
  notify(data.count ? `已替换 ${data.count} 处` : "未发现需要替换的敏感词");
};

document.querySelector("#restore").onclick = async () => {
  if (uploadedFile) {
    const form = new FormData();
    form.append("file", uploadedFile);
    notify("正在按词库对应关系恢复文件，请稍候…", 3000);
    const response = await fetch(`/restore-${fileKind}?min_level=1`, {
      method: "POST", body: form,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      return notify(data.detail || "文件恢复失败", 4000);
    }
    saveBlob(await response.blob(), uploadedFile.name.replace(/\.(docx|xlsx)$/i, "_restored.$1"));
    notify("恢复后的文件已保存");
    return;
  }

  if (!text.value.trim()) return notify("请先输入需要恢复的文本");
  const response = await fetch("/restore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text.value, min_level: 1 }),
  });
  const data = await response.json();
  if (!response.ok) return notify(data.detail || "恢复失败");
  text.value = data.text;
  text.oninput();
  notify(data.count ? `已恢复 ${data.count} 处` : "未发现可恢复的替换词");
};

document.querySelector("#toMarkdown").onclick = async () => {
  if (!uploadedFile || fileKind !== "docx") return notify("请先上传 Word 文件");
  const replacement = document.querySelector("#replacement").value.trim() || "*";
  const form = new FormData();
  form.append("file", uploadedFile);
  notify("正在替换敏感词并转换 Markdown，请稍候…", 3000);
  const response = await fetch(
    `/replace-docx-markdown?replacement=${encodeURIComponent(replacement)}&min_level=1`,
    { method: "POST", body: form },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    return notify(data.detail || "Markdown 转换失败", 4000);
  }
  saveBlob(await response.blob(), uploadedFile.name.replace(/\.docx$/i, "_filtered.md"));
  notify("替换后的 Markdown 文件已保存");
};

document.querySelector("#makeTemplate").onclick = async () => {
  if (!uploadedFile || fileKind !== "docx") return notify("请先上传 Word 文件");
  const form = new FormData();
  form.append("file", uploadedFile);
  notify("正在提取标题和表格结构，请稍候…", 3000);
  const response = await fetch("/template-docx", { method: "POST", body: form });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    return notify(data.detail || "模板生成失败", 4000);
  }
  saveBlob(await response.blob(), uploadedFile.name.replace(/\.docx$/i, "_template.docx"));
  notify("编写模板 Word 已保存");
};

document.querySelector("#formatHeadings").onclick = async () => {
  if (!uploadedFile || fileKind !== "docx") return notify("请先上传 Word 文件");
  const form = new FormData();
  form.append("file", uploadedFile);
  notify("正在将标题字体统一为黑体，请稍候…", 3000);
  const response = await fetch("/format-docx-headings", { method: "POST", body: form });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    return notify(data.detail || "标题字体处理失败", 4000);
  }
  saveBlob(await response.blob(), uploadedFile.name.replace(/\.docx$/i, "_headings_heiti.docx"));
  notify("标题已统一为黑体并保存");
};

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = String(value);
  return element.innerHTML;
}
