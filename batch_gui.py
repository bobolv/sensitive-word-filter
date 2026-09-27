"""Run on Windows: python batch_gui.py. No server or network required."""
import os
import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from sensitive_filter.batch import replace_batch, load_batch_engine


def main():
    root = tk.Tk()
    root.title("离线批量正向替换 / 反向恢复 · 保留文件时间")
    root.geometry("950x750")
    sources = []
    events = queue.Queue()
    words = tk.StringVar(value=str(Path(os.getenv(
        "SENSITIVE_WORDLIST", Path(__file__).parent / "data" / "words.json")).resolve()))
    output = tk.StringVar()
    replacement = tk.StringVar(value="*")
    mode = tk.StringVar(value="replace")
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="支持 TXT / MD / CSV（UTF-8）、DOCX、XLSX；全部在本机处理。\n"
              "输出保留输入文件的创建时间和修改时间，自动避开同名文件。").pack(anchor="w")
    controls = []

    def row(label, variable, browse=None):
        line = ttk.Frame(frame)
        line.pack(fill="x", pady=5)
        ttk.Label(line, text=label, width=12).pack(side="left")
        entry = ttk.Entry(line, textvariable=variable)
        entry.pack(side="left", fill="x", expand=True)
        controls.append(entry)
        if browse:
            button = ttk.Button(line, text="选择", command=browse)
            button.pack(side="right")
            controls.append(button)

    def choose(variable, directory=False):
        value = filedialog.askdirectory() if directory else filedialog.askopenfilename(
            filetypes=[("词库 JSON", "*.json")])
        if value:
            variable.set(value)

    row("本地词库", words, lambda: choose(words))
    row("输出目录", output, lambda: choose(output, True))
    row("默认替换内容", replacement)
    modes = ttk.Frame(frame)
    modes.pack(fill="x", pady=5)
    for label, value in [("正向替换", "replace"), ("反向恢复", "restore")]:
        button = ttk.Radiobutton(modes, text=label, variable=mode, value=value)
        button.pack(side="left")
        controls.append(button)
    ttk.Label(frame, text="反向恢复按词库“替换词 → 原词”处理，不使用默认替换内容；通用星号遮盖无法恢复。\n"
              "原文中本来就有的同名替换词也会被恢复。下方明细按“实际原文 → 输出内容”汇总。").pack(anchor="w")

    listing = tk.Listbox(frame, height=9)
    def select_files():
        selected = filedialog.askopenfilenames(filetypes=[
            ("支持的文件", "*.txt *.md *.csv *.docx *.xlsx")])
        for filename in selected:
            if filename not in sources:
                sources.append(filename)
                listing.insert("end", filename)

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=6)
    add = ttk.Button(buttons, text="批量导入文件", command=select_files)
    add.pack(side="left")
    clear = ttk.Button(buttons, text="清空列表", command=lambda: (sources.clear(), listing.delete(0, "end")))
    clear.pack(side="left")
    listing.pack(fill="both", expand=True)
    log = tk.Text(frame, height=10, state="disabled")
    status = tk.StringVar(value="等待选择文件")

    def start(clear_authors=False):
        if not sources or not output.get().strip():
            return messagebox.showerror("缺少输入", "请选择文件和输出目录")
        if not clear_authors and mode.get() == "replace" and (not replacement.get() or len(replacement.get()) > 20):
            return messagebox.showerror("参数无效", "替换内容需为 1–20 个字符")
        try:
            engine = None if clear_authors else load_batch_engine(Path(words.get()), mode.get())
        except Exception as exc:
            return messagebox.showerror("词库读取失败", str(exc))
        selected, folder, substitute = list(sources), Path(output.get()), replacement.get()
        selected_mode = "clear_authors" if clear_authors else mode.get()
        if selected_mode in ("restore", "clear_authors"):
            substitute = "*"
        for control in controls:
            control.configure(state="disabled")
        status.set("正在本机处理，请稍候…")
        def work():
            results = replace_batch(selected, folder, engine, substitute,
                                    progress=lambda item: events.put(("item", item)), mode=selected_mode)
            events.put(("done", results))
        threading.Thread(target=work, daemon=True).start()

    run = ttk.Button(frame, text="按所选模式处理并输出全部文件", command=start)
    run.pack(pady=8)
    clean = ttk.Button(frame, text="单独删除文档属性和个人信息（Word / Excel）", command=lambda: start(True))
    clean.pack(pady=4)
    ttk.Label(frame, text="三个入口均自动清理文档属性、批注及修订记录；接受修订，保留当前正文。\n"
              "单独清理另存为 _cleaned 文件，无需词库；正文、图片中的个人信息仍需检查或词库替换。").pack(anchor="w")
    controls.extend([add, clear, run, clean])
    ttk.Label(frame, textvariable=status).pack(anchor="w")
    log.pack(fill="both", expand=True)

    def poll():
        while not events.empty():
            kind, value = events.get_nowait()
            if kind == "done":
                ok = sum(item["ok"] for item in value)
                status.set(f"完成：成功 {ok} 个，失败 {len(value) - ok} 个；成功文件的时间已校验。")
                for control in controls:
                    control.configure(state="normal")
            else:
                message = (f"成功：{value['output']}（{value['count']} 处）" if value["ok"]
                           else f"失败：{value['source']}：{value['error']}")
                if value["ok"]:
                    action = {"restore": "恢复", "replace": "替换", "clear_authors": "清理信息"}[value["mode"]]
                    message = f"[{action}] " + message
                    for change in value["changes"]:
                        before = json.dumps(change["before"], ensure_ascii=False)
                        after = json.dumps(change["after"], ensure_ascii=False)
                        field = f"{change['field']}：" if "field" in change else ""
                        message += f"\n    {field}{before} → {after}（{change['count']} 处）"
                    if not value["changes"]:
                        message += "\n    没有发生内容变更。"
                    if value["mode"] != "clear_authors":
                        for item in value["privacy"]["changes"]:
                            message += f"\n    [信息清理] {item['field']}：{item['count']} 项"
                log.configure(state="normal")
                log.insert("end", message + "\n")
                log.see("end")
                log.configure(state="disabled")
        root.after(100, poll)

    def close():
        if str(run["state"]) == "disabled":
            messagebox.showinfo("处理中", "请等待处理完成后关闭窗口。")
        else:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    poll()
    root.mainloop()


if __name__ == "__main__":
    main()
