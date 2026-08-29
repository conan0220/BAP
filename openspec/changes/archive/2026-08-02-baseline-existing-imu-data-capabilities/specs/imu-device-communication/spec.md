## Purpose

定義既有的命令列行為，用於探索序列埠、監控已解析的 ANROT 裝置輸出，以及傳送持久保存的裝置設定指令。

## ADDED Requirements

### Requirement: 序列埠探索
系統 SHALL 提供一個命令，列舉目前可用的序列埠，並在相關資訊可用時顯示各連接埠的 device name、reported manufacturer 與 access-permission status。

#### Scenario: Serial ports are available
- **WHEN** 操作人員執行連接埠列舉命令，且作業系統回報一個或多個序列埠
- **THEN** 系統會顯示連接埠數量，並為每個回報的連接埠顯示一筆項目

#### Scenario: No serial ports are available
- **WHEN** 操作人員執行連接埠列舉命令，且作業系統未回報任何序列埠
- **THEN** 系統會回報找不到可用的序列埠

### Requirement: 即時序列監控
系統 SHALL 接受一個序列埠與正整數 baud rate，持續讀取該連接埠的可用 bytes，直到遭到中斷或發生存取錯誤，並顯示最近解析的 ANROT binary 與 NMEA measurements，以及觀測到的 frame rate。

#### Scenario: Monitor valid mixed device output
- **WHEN** 選取的連接埠提供支援的 ANROT binary frames 或支援的 NMEA sentences
- **THEN** 系統會定期以最新的 parsed measurements 與每秒解析 frame 的測量數量重新整理顯示

#### Scenario: Reject an invalid monitoring baud rate
- **WHEN** 操作人員提供的 baud rate 不是正整數
- **THEN** 命令會在開啟序列埠前拒絕該值

#### Scenario: Serial monitoring cannot access the port
- **WHEN** 開啟或讀取選取的連接埠引發 serial-access 或 permission error
- **THEN** 系統會回報錯誤，並以 failure status 終止監控命令

### Requirement: 已儲存的裝置指令序列
系統 SHALL 提供一個命令，以 8 data bits、no parity 與 one stop bit 開啟選取的序列埠；停止裝置輸出；傳送操作人員的指令；儲存設定；再重新啟動裝置輸出。當提供的指令尚未包含 carriage return 與 line feed terminator 時，每個指令 SHALL 以該 terminator 結尾。

#### Scenario: Send and save a command successfully
- **WHEN** 裝置以包含 `OK` 的回應確認 output-stop command、operator command、save command 與 output-start command
- **THEN** 系統會依該順序完成序列，並顯示操作人員指令的回應

#### Scenario: Device output does not stop initially
- **WHEN** 裝置未確認 `AT+EOUT=0`
- **THEN** 系統最多嘗試該指令三次；若所有嘗試皆失敗，則以錯誤停止序列

#### Scenario: A later command is not acknowledged
- **WHEN** operator command、`SAVECONFIG` 或 `AT+EOUT=1` 未傳回包含 `OK` 的回應
- **THEN** 系統會回報失敗的步驟，並停止剩餘序列

#### Scenario: Reject an invalid command baud rate
- **WHEN** 操作人員提供的 baud rate 不是正整數
- **THEN** 命令會在開啟序列埠前拒絕該值
