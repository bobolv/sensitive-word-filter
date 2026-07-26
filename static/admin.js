const login = document.querySelector("#login");
const manager = document.querySelector("#manager");
const rows = document.querySelector("#rows");
const toast = document.querySelector("#toast");

const notify = (message, duration = 2600) => {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), duration);
};

function row(entry = { word: "", category: "未分类", level: 1, replacement: "" }) {
  const tr = document.createElement("tr");
  tr.innerHTML = `<td><input class="word"></td><td><input class="category"></td>
    <td><select class="level"><option>1</option><option>2</option><option>3</option></select></td>
    <td><input class="replacement" placeholder="例如：某人员"></td>
    <td><button class="secondary remove">删除</button></td>`;
  tr.querySelector(".word").value = entry.word;
  tr.querySelector(".category").value = entry.category;
  tr.querySelector(".level").value = entry.level;
  tr.querySelector(".replacement").value = entry.replacement || "";
  tr.querySelector(".remove").onclick = () => { tr.remove(); updateCount(); };
  rows.append(tr);
  updateCount();
}

function collectWords() {
  return [...rows.children].map((tr) => ({
    word: tr.querySelector(".word").value.trim(),
    category: tr.querySelector(".category").value.trim() || "未分类",
    level: Number(tr.querySelector(".level").value),
    replacement: tr.querySelector(".replacement").value.trim(),
  })).filter((entry) => entry.word);
}

function validationMessage(entries) {
  const words = new Set();
  const replacements = new Set();
  const allWords = new Set(entries.map((entry) => entry.word.toLocaleLowerCase()));
  for (const entry of entries) {
    const word = entry.word.toLocaleLowerCase();
    const replacement = entry.replacement.toLocaleLowerCase();
    if (words.has(word)) return "敏感词已添加";
    words.add(word);
    if (!replacement) continue;
    if (replacements.has(replacement)) return "替换词存在重复情况，请修改";
    if (allWords.has(replacement)) return "替换词与敏感词存在重复情况，请修改";
    replacements.add(replacement);
  }
  return "";
}

function updateCount() {
  document.querySelector("#wordCount").textContent = `词条列表（${rows.children.length}）`;
}

async function load() {
  const response = await fetch("/admin/words");
  if (!response.ok) return;
  const data = await response.json();
  rows.innerHTML = "";
  data.words.forEach(row);
  login.classList.add("hidden");
  manager.classList.remove("hidden");
  updateCount();
}

document.querySelector("#loginBtn").onclick = async () => {
  const response = await fetch("/admin/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: document.querySelector("#password").value }),
  });
  if (response.ok) load(); else notify("密码错误");
};

document.querySelector("#add").onclick = async () => {
  const addButton = document.querySelector("#add");
  const entry = {
    word: document.querySelector("#newWord").value.trim(),
    category: document.querySelector("#newCategory").value.trim() || "未分类",
    level: Number(document.querySelector("#newLevel").value),
    replacement: document.querySelector("#newReplacement").value.trim(),
  };
  if (!entry.word) return notify("请输入敏感词");
  const proposedWords = [...collectWords(), entry];
  const message = validationMessage(proposedWords);
  if (message) return notify(message);

  addButton.disabled = true;
  addButton.textContent = "正在添加…";
  const response = await fetch("/admin/words", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ words: proposedWords }),
  });
  const data = await response.json().catch(() => ({}));
  addButton.disabled = false;
  addButton.textContent = "添加到词库";
  if (!response.ok) return notify(data.detail || "添加失败");

  row(entry);
  document.querySelector("#newWord").value = "";
  document.querySelector("#newReplacement").value = "";
  document.querySelector("#newWord").focus();
  notify("词条添加并保存成功");
};

document.querySelector("#save").onclick = async () => {
  const words = collectWords();
  const message = validationMessage(words);
  if (message) return notify(message);
  const response = await fetch("/admin/words", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ words }),
  });
  const data = await response.json().catch(() => ({}));
  notify(response.ok ? "保存成功，已立即生效" : (data.detail || "保存失败"));
};

document.querySelector("#logout").onclick = async () => {
  await fetch("/admin/logout", { method: "POST" });
  location.reload();
};

load();
