# AGENTS.md — 悬浮待办 / Floating Todo

## 项目

- Python + customtkinter 的桌面待办卡片应用，Windows 为主。
- 入口 `app.pyw`；主包 `floating_todo/`；启动脚本在 `launchers/`。
- 测试：`python -m pytest tests -q`（`tests/gui_smoke.py` 是手动 GUI 冒烟脚本，不属于自动化测试）。

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
