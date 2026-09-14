## 名詞定義

| 名詞 | 定義 |
|---|---|
| Matplotlib | BAP Desktop 用來繪製及操作三維出拳軌跡的 Python 套件。 |
| FigureCanvasQTAgg | 把 Matplotlib 圖形直接放進 PySide6 頁面的 Qt Widget。 |
| Navigation Toolbar | Matplotlib 提供的操作列，讓 user 平移、縮放、重設視角或另存圖片。 |
| Fallback | 電腦無法載入 Matplotlib 3D 圖時，改為顯示文字摘要的安全畫面。 |

## 使用方式與授權

BAP Desktop 的出拳軌跡 Result view 使用 Matplotlib 3.x，並透過
`FigureCanvasQTAgg` 直接內嵌在原本的結果頁面。Matplotlib 採 PSF-based
License，允許隨 Desktop App 發布。專案只透過公開 Python API 使用套件，
沒有複製或修改套件來源碼。

PyInstaller 必須收集 `matplotlib.backends.backend_qtagg`、
`mpl_toolkits.mplot3d`、Matplotlib 資料檔與 NumPy。圖上使用英文短標籤，
避免不同 Windows 電腦缺少相同中文字型而顯示方框。若 Matplotlib 或 Qt
繪圖環境無法建立，App 會保留 Backend Result 並顯示文字 Fallback，
不會因 3D 圖失敗而關閉。
