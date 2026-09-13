## 名詞定義

| 名詞 | 定義 |
|---|---|
| pyqtgraph | BAP Desktop 用來建立 Qt 互動式 3D 圖的 Python 套件。 |
| PyOpenGL | pyqtgraph 3D Widget 呼叫 OpenGL 時使用的 Python binding。 |
| Fallback | 電腦無法建立 OpenGL Widget 時，改為顯示文字摘要的安全畫面。 |

## 使用方式與授權

BAP Desktop 的出拳軌跡 Result view 使用 `pyqtgraph` 0.13.x 與
`PyOpenGL` 3.x。`pyqtgraph` 採 MIT License，`PyOpenGL` 採 BSD License；
兩者都允許隨 Desktop App 發布。專案只透過公開 Python API 使用套件，
沒有複製或修改套件來源碼。

PyInstaller 必須同時收集 `pyqtgraph.opengl`、PyOpenGL 與 NumPy。
若使用者的顯示卡 Driver 或執行環境無法建立 OpenGL context，App 會保留
Backend Result 並顯示文字 Fallback，不會因 3D 圖失敗而關閉。
