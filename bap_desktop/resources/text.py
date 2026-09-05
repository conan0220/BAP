"""White-label Traditional Chinese text used by the Desktop App UI."""

from __future__ import annotations


APP_TITLE = "BAP｜Boxing Analysis Platform"
LOGIN = "登入"
REGISTER = "註冊"
LOGOUT = "登出"
PASSWORD = "密碼"
SHOW_PASSWORD = "顯示密碼"
REMEMBER_LOGIN = "記住登入狀態"
CREATE_ACCOUNT = "建立帳號"
LOGIN_REJECTED = "Username 或密碼不正確"
SERVER_UNAVAILABLE = "目前無法連線到伺服器，請稍後再試。"
REGISTER_SUCCEEDED = "註冊成功，請使用新帳號登入。"
USERNAME_RULE = "5～64 個字元，只能使用英文、數字、.、_、-"
PASSWORD_RULE = "8～128 個字元，至少包含一個英文字母及一個數字"

HOME_TITLE = "BAP 主畫面"
HOME_DESCRIPTION = "請選擇要使用的功能。拳擊測量項目目前只提供 IMU 來源確認。"
IMU_DIAGNOSTICS = "IMU 連線狀態"
BACK_HOME = "回到主畫面"
PENDING = "待開發"
PUNCH_ITEMS = (
    "出拳次數",
    "出拳速度",
    "出拳力量",
    "出拳軌跡",
    "拳種辨識",
)

DIAGNOSTIC_READY = "準備測試所有 Port"
DIAGNOSTIC_COLLECTING = "IMU 測試中，請稍後。正在收集資料…"
DIAGNOSTIC_ANALYZING = "IMU 測試中，請稍後。正在分析資料…"
DIAGNOSTIC_COMPLETE = "測試完成，以下是目前所有 Port 的結果。"
NO_PORT = "找不到可用的 Port"
RETEST = "重新測試"
EXPORT_CSV = "匯出 CSV"

DISCOVERY_READY = "準備確認 IMU"
DISCOVERY_RUNNING = "正在確認 IMU，請稍後。"
DISCOVERY_SELECT = "請為這個拳擊項目的每個位置指定 IMU。"
DISCOVERY_NOT_FOUND = "找不到可用的 IMU"
DISCOVERY_RETRY = "再次確認"
DISCOVERY_DUPLICATE = "同一顆 IMU 不能同時指定給兩個位置。"
DISCOVERY_INSUFFICIENT = "可用 IMU 數量不足，請檢查裝置後再次確認。"
DISCOVERY_CONFIGURATION_PENDING = "IMU 配置待決定"
IMU_PLACEHOLDER = "請選擇掃描到的 IMU"
SERVER_CONNECTED = "伺服器已連線"

UPDATE_CHECKING = "正在背景檢查更新…"
UPDATE_LATEST = "已是最新版本"
UPDATE_OFFLINE = "目前無法檢查更新，不影響其他功能。"
UPDATE_INVALID = "目前無法取得有效的更新資訊。"
UPDATE_DOWNLOAD = "立即更新"
UPDATE_LATER = "稍後"
UPDATE_DOWNLOADING = "正在下載更新…"
UPDATE_INSTALLING = "更新已下載，正在啟動安裝程式。BAP 將自動重新啟動…"
UPDATE_FAILED = "更新失敗，現有版本不受影響。請稍後再試。"
