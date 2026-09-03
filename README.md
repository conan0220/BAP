# BAP（Boxing Analysis Platform）

BAP 包含 PySide6 Desktop App 與 FastAPI Backend。開發者平常只需要在 feature branch 開發；Pull Request 的 CI 會建立並測試正式格式的 Candidate，人工 Merge 後才由 CD 交付同一份 Candidate。

## 初次準備

~~~powershell
uv sync --all-extras --group dev
~~~

## 快速預覽 Desktop App UI

在 repository 根目錄執行：

~~~powershell
.\open_BAP.cmd
~~~

open_BAP.cmd 只會啟動目前 source code 的 UI，不會 Build Installer、不會使用 SSH，也不會部署 Backend。如果 .venv 不存在，腳本會提示先準備開發環境。

## 日常開發流程

~~~mermaid
flowchart LR
    A["同步 master"] --> B["建立 feature branch"]
    B --> C["修改與本機測試"]
    C --> D["Commit 並 push"]
    D --> E["建立 Pull Request"]
    E --> F{"CI Gate"}
    F -->|失敗| C
    F -->|通過| G["人工 Merge"]
    G --> H["CD 自動交付已測 Candidate"]
~~~

### 1. 從最新 master 開 branch

~~~powershell
git switch master
git pull --ff-only origin master
git switch -c feature/<功能名稱>
~~~

### 2. 修改、預覽與測試

~~~powershell
.\open_BAP.cmd
.\.venv\Scripts\python.exe -m pytest
~~~

### 3. Commit 並 push feature branch

~~~powershell
git add <檔案>
git commit -m "<修改摘要>"
git push -u origin feature/<功能名稱>
~~~

### 4. 建立 Pull Request 並等待 CI

Pull Request 必須以 master 為目標。Required check 是 **CI Gate**。

- CI 失敗：回 feature branch 修正，再 push。
- 同一個 PR push 新 commit：舊的 PR workflow 會自動取消。
- 只有文件變更：不使用 Windows Runner，但 CI Gate 仍會完成。
- 程式有變更：CI 建立 Backend ZIP 與 Desktop Installer，從 Artifact 建立測試環境並執行真實 HTTP E2E。

### 5. 人工 Merge

CI Gate 通過且人工 review 完成後，開發者才到 GitHub 按下 Merge。不要直接 push 到 master，也不使用 auto-merge。

Merge 後的 CD 會下載同一份已測 Candidate，依 scope 自動部署 Backend 或發布 Desktop Release；開發者不需要在本機執行 SCP、SSH 或正式 Build。

管理者設定、Server Initialize、Artifact I/O、Rollback 與通知方式請見 [CI/CD 操作指南](docs/guides/ci-cd.md)。
