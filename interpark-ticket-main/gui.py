"""抢票工具图形界面。

打开后是一排输入框，填好点「保存」写入 settings.json，
点「开始抢票」在后台线程启动抢票逻辑（浏览器会自己弹出来）。
现在不想填也没关系：留空即可，保存后随时能回来补。
"""

import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

import config as appconfig


class App:
    def __init__(self, root):
        self.root = root
        self.vars = {}
        self.worker = None
        # 「接手」信号：脚本开好浏览器后会等它；你点接手就放行
        self.takeover_evt = threading.Event()
        root.title("NOL World 半自动抢票")
        root.geometry("560x720")
        self._build()

    def _build(self):
        cfg = appconfig.load()

        tk.Label(
            self.root,
            text=(
                "用法：点「开始」→ 在弹出的 Chrome 里手动登录、点预订、\n"
                "走到验证码弹出 → 回来点「接手」→ 脚本自动选座/填信息 →\n"
                "响铃后你亲手付款。信息只存本机。"
            ),
            justify="left", fg="#555",
        ).pack(anchor="w", padx=12, pady=(10, 6))

        form = tk.Frame(self.root)
        form.pack(fill="x", padx=12)

        for row, (key, label, _default, secret) in enumerate(appconfig.FIELDS):
            tk.Label(form, text=label, width=20, anchor="e").grid(
                row=row, column=0, sticky="e", padx=(0, 8), pady=3
            )
            var = tk.StringVar(value=str(cfg.get(key, "")))
            entry = tk.Entry(
                form, textvariable=var, width=36,
                show="*" if secret else "",
            )
            entry.grid(row=row, column=1, sticky="w", pady=3)
            self.vars[key] = var

        btns = tk.Frame(self.root)
        btns.pack(fill="x", padx=12, pady=10)
        tk.Button(btns, text="保存", width=10, command=self.on_save).pack(side="left")
        self.start_btn = tk.Button(
            btns, text="开始", width=10, command=self.on_start
        )
        self.start_btn.pack(side="left", padx=8)
        # 接手按钮：默认禁用，脚本开好浏览器等待时才亮
        self.takeover_btn = tk.Button(
            btns, text="接手（我已到验证码）", width=20,
            command=self.on_takeover, state="disabled",
        )
        self.takeover_btn.pack(side="left")

        tk.Label(self.root, text="运行日志：", anchor="w").pack(
            anchor="w", padx=12
        )
        self.logbox = scrolledtext.ScrolledText(self.root, height=10)
        self.logbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def collect(self):
        return {key: var.get().strip() for key, var in self.vars.items()}

    def log(self, msg):
        self.logbox.insert("end", msg + "\n")
        self.logbox.see("end")

    def on_save(self):
        path = appconfig.save(self.collect())
        self.log(f"已保存到 {path}")
        messagebox.showinfo("保存成功", f"配置已写入：\n{path}")

    def on_start(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("正在运行", "已经在跑了。")
            return
        cfg = self.collect()
        appconfig.save(cfg)
        self.takeover_evt.clear()
        self.start_btn.config(state="disabled", text="运行中…")
        self.takeover_btn.config(state="normal")
        self.worker = threading.Thread(target=self._run, args=(cfg,), daemon=True)
        self.worker.start()

    def on_takeover(self):
        # 放行一次；脚本可能多次等待（验证码没过时会再等），所以设完即可
        self.takeover_evt.set()
        self.log("→ 已接手，脚本继续。")

    def _wait_takeover(self):
        # 供 runner 在后台线程调用：阻塞到你点「接手」
        self.takeover_evt.wait()
        self.takeover_evt.clear()

    def _run(self, cfg):
        def status(msg):
            self.root.after(0, lambda: self.log(msg))

        try:
            import runner
            runner.run(cfg, wait_takeover=self._wait_takeover, status=status)
        except Exception as e:
            self.root.after(0, lambda: self.log(f"运行出错：{e}"))
        finally:
            self.root.after(0, self._reset_buttons)

    def _reset_buttons(self):
        self.start_btn.config(state="normal", text="开始")
        self.takeover_btn.config(state="disabled")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
