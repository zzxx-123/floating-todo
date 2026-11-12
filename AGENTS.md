# AGENTS.md — 悬浮待办 / Floating Todo

## 项目

- Python + customtkinter 的桌面待办卡片应用，Windows 为主。
- 入口 `app.pyw`；主包 `floating_todo/`；启动脚本在 `launchers/`。
- 测试：`.venv\Scripts\python.exe -m pytest tests -q --ignore=tests/gui_smoke.py`（`tests/gui_smoke.py` 是手动 GUI 冒烟脚本，不属于自动化测试）。
- 当前 44 项测试全部通过（2026-11-12 验证）。

## 开发环境（虚拟环境）

- 项目级 venv 在 `.venv/`（Python 3.13.2，系统解释器 `D:\Programs\python\Python3.13.2\python.exe`），已在 `.gitignore` 里忽略。
- 依赖：`customtkinter 5.2.2`、`Pillow 12.3.0`，另装了 `pytest 9.2.0` 供测试使用。
- 新建同类项目时的标准做法：
  `py -3.13 -m venv .venv` → `.venv\Scripts\python.exe -m pip install -r requirements.txt pytest`
- 依赖清单只写运行期依赖到 `requirements.txt`，测试依赖不写进去（或另开 `requirements-dev.txt`）。
- VS Code 配置在 `.vscode/`：解释器指向 `.venv`，`Ctrl+Shift+P → Tasks: Run Test Task` 跑 pytest，F5 直接调试 `app.pyw`。

## 仓库

- GitHub：https://github.com/zzxx-123/floating-todo （private）
- 默认分支 `main`；单人项目，改动直接提交到 `main`，不强制走 PR。

## Git 约定

- 提交信息用 Conventional Commits 前缀 + 中文描述：`feat:` / `fix:` / `docs:` / `chore:` / `refactor:` / `test:`。
- 一个逻辑改动对应一个 commit；提交前先跑一次测试。
- 未经用户明确要求，禁止 `git push --force`、`git reset --hard` 到已推送的提交、或任何历史重写。

## 本机环境要点

- git 2.50（`D:\Programs\Git`），全局已配置 `url.https://x-access-token:<token>@github.com/.insteadOf`，因此**在普通 workspace-write 沙箱里 `git push` / `git fetch` 可直接成功**，不需要额外授权。
- gh CLI：`C:\Users\zz\AppData\Local\Programs\gh\bin\gh.exe`，已登录账号 `zzxx-123`（凭据在 keyring）。旧终端里 PATH 可能还没刷新，用绝对路径最稳。
- 新建仓库并推送：
  `git init -b main; git add -A; git commit -m "chore: 初始化仓库"; gh repo create <name> --private --source . --push`
- 沙箱下 git 联网命令常会额外打印 `sh.exe: *** fatal error - couldn't create signal pipe` —— 这是 MSYS 子进程的噪音，**以退出码和实际输出为准**，不要据此判断失败。
- 若要改全局 git 配置或安装软件（工作区之外），需要 danger-full-access 授权。
- **沙箱下跑 pytest 会假失败**：Python `tempfile.mkdtemp()` 用 `0o700` 建目录，在 workspace-write 沙箱里这个目录没有沙箱 SID 的继承 ACE，写入报 `[WinError 5] 拒绝访问`，导致 `tmp_path` 相关用例（`test_storage.py` 等）8 failed / 7 errors。**这不是代码问题**，用 `danger-full-access` 重跑即 `44 passed`。同理 `pip` / `ensurepip` 也必须提权执行。
- 依赖安装直连 PyPI 会 TLS 中断，用 `--proxy http://127.0.0.1:7897 -i https://pypi.org/simple`（清华源在该环境下报 "from versions: none"，不可用）。
