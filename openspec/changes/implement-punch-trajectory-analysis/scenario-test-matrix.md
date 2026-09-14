## 名詞定義

| 名詞 | 定義 |
|---|---|
| Scenario | OpenSpec 用 user 可觀察行為描述的驗收情境。 |
| 自動測試 | 由 pytest 執行、不需人工操作即可重複驗證的測試。 |
| Artifact smoke test | 從正式 Windows 安裝檔啟動 App，驗證實際封裝後仍能建立 3D Widget 與 fallback。 |

## Scenario-to-test 對照

| Capability | Scenario | 主要自動測試 |
|---|---|---|
| analysis-specification-contract | 前後端使用相同的 version 2 | `tests/backend/test_punch_trajectory.py::test_contract_rejects_placeholder_and_inconsistent_counts` |
| analysis-specification-contract | version 2 Result 仍使用 summary placeholder | `tests/backend/test_punch_trajectory.py::test_contract_rejects_placeholder_and_inconsistent_counts` |
| analysis-specification-contract | Result 的拳數與 trajectories 不一致 | `tests/backend/test_punch_trajectory.py::test_contract_rejects_placeholder_and_inconsistent_counts` |
| desktop-app-shell | 查看拳擊測量項目 | `tests/desktop/test_desktop_ui_design.py::test_home_has_four_available_items_and_one_pending_item` |
| desktop-app-shell | 進入單一拳擊項目 | `tests/desktop/test_desktop_ui_design.py::test_opening_one_item_keeps_exactly_one_feature_page` |
| desktop-app-shell | 出拳軌跡 version 2 可執行 | `tests/backend/test_analysis_registry.py::test_default_production_registry_exposes_only_punch_trajectory_version_two` |
| desktop-app-shell | 完成待開發項目的 IMU 來源選擇 | `tests/desktop/test_desktop_ui_design.py::test_unavailable_capability_does_not_record` |
| desktop-app-shell | 出拳軌跡 Executor 可用 | `tests/backend/test_analysis_registry.py::test_default_production_registry_exposes_only_punch_trajectory_version_two` |
| desktop-ui-design | user 縮小視窗 | `tests/desktop/test_desktop_ui_design.py::test_minimum_window_has_resizable_scrolling_content` |
| desktop-ui-design | user 只使用鍵盤操作視角 | `tests/desktop/test_trajectory_view.py::test_camera_presets_are_keyboard_focusable_and_do_not_change_result` |
| desktop-ui-design | 電腦無法建立 3D 繪圖環境 | `tests/desktop/test_trajectory_view.py::test_matplotlib_failure_uses_text_fallback_without_losing_summary` |
| punch-trajectory-analysis | user 準備校正 | `tests/desktop/test_desktop_ui_design.py::test_two_stage_ready_state_explains_calibration_and_manual_next_step` |
| punch-trajectory-analysis | 校正完成後開始正式測量 | `tests/desktop/test_desktop_ui_design.py::test_two_stage_analysis_calibrates_before_formal_measurement` |
| punch-trajectory-analysis | 校正完成後 user 移動到正式姿勢 | `tests/backend/test_punch_trajectory.py::test_movement_between_calibration_and_measurement_is_not_calibration` |
| punch-trajectory-analysis | 校正期間 IMU 中斷 | `tests/desktop/test_desktop_ui_design.py::test_two_stage_calibration_interruption_returns_to_retry_state` |
| punch-trajectory-analysis | 一場 Session 包含左右手多拳 | `tests/backend/test_punch_trajectory.py::test_executor_returns_contract_valid_isolated_trajectories` |
| punch-trajectory-analysis | 正式資料沒有偵測到出拳 | `tests/backend/test_punch_trajectory.py::test_no_punch_is_a_successful_empty_result` |
| punch-trajectory-analysis | Backend 回傳一拳的有效軌跡 | `tests/backend/test_punch_trajectory.py::test_executor_returns_contract_valid_isolated_trajectories` |
| punch-trajectory-analysis | 軌跡原始點數超過顯示上限 | `tests/backend/test_analysis_sessions_api.py::test_trajectory_result_with_three_hundred_points_round_trips_database` |
| punch-trajectory-analysis | CSV 缺少有效 Quaternion | `tests/backend/test_analysis_sessions_api.py::test_trajectory_failure_keeps_csv_and_retry_reuses_saved_inputs` |
| punch-trajectory-analysis | 校正資料不足 | `tests/backend/test_punch_trajectory.py::test_insufficient_calibration_becomes_safe_contract_error` |
| punch-trajectory-analysis | 首次顯示有效軌跡 Result | `tests/desktop/test_trajectory_view.py::test_view_selects_earliest_punch_and_switches_locally` |
| punch-trajectory-analysis | user 操作 3D 圖 | `tests/desktop/test_trajectory_view.py::test_camera_presets_are_keyboard_focusable_and_do_not_change_result` |
| punch-trajectory-analysis | user 切換手別或拳次 | `tests/desktop/test_trajectory_view.py::test_view_selects_earliest_punch_and_switches_locally` |
| punch-speed-analysis | user 在兩個階段之間移動 | `tests/desktop/test_analysis_recording.py::test_two_stage_recording_adds_two_second_boundary_to_analysis_parameters` |

## 額外防護

- `tests/backend/test_punch_trajectory.py::test_non_finite_sensor_value_never_returns_a_fake_trajectory` 驗證非有限 sensor 值不會產生假軌跡。
- `tests/backend/test_analysis_sessions_api.py` 驗證完整 HTTP Session、資料庫 Result、原始 CSV checksum、失敗後重試。
- `python -m bap_desktop.app --smoke-test` 驗證真正的 Matplotlib Qt Canvas 與強制 fallback；正式 Windows Artifact 仍須再執行相同 smoke test。
