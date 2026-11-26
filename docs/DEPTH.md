# 可复核的模型和处置边界

分类 AI/ML / 传统ML。

## 功能模块

| 模块 | 业务步骤 | 输出 | 核心实现 | 独立契约与边界测试 |
|---|---|---|---|---|
| M1 | 机台抄表 | ReelTick处理证据 | `src/sheetgrade/machine_reel/contracts.py` `src/sheetgrade/machine_reel/algorithm.py` `src/sheetgrade/machine_reel/service.py` `src/sheetgrade/machine_reel/continuity_proof.py` | `tests/test_machine_reel.py` `tests/test_continuity_proof.py` |
| M2 | 纸种换线 | GradeWindow处理证据 | `src/sheetgrade/grade_change/contracts.py` `src/sheetgrade/grade_change/algorithm.py` `src/sheetgrade/grade_change/service.py` `src/sheetgrade/grade_change/grade_timeline.py` | `tests/test_grade_change.py` `tests/test_grade_timeline.py` |
| M3 | 湿部特征 | WetSignal处理证据 | `src/sheetgrade/wet_signals/contracts.py` `src/sheetgrade/wet_signals/algorithm.py` `src/sheetgrade/wet_signals/service.py` `src/sheetgrade/wet_signals/press_change_detection.py` | `tests/test_wet_signals.py` `tests/test_press_change_detection.py` |
| M4 | 断纸拟合 | BreakFeature处理证据 | `src/sheetgrade/breakpoint_model/contracts.py` `src/sheetgrade/breakpoint_model/algorithm.py` `src/sheetgrade/breakpoint_model/service.py` `src/sheetgrade/breakpoint_model/feature_counterfactual.py` | `tests/test_breakpoint_model.py` `tests/test_feature_counterfactual.py` |
| M5 | 质检处置 | ReleaseCandidate处理证据 | `src/sheetgrade/release_order/contracts.py` `src/sheetgrade/release_order/algorithm.py` `src/sheetgrade/release_order/service.py` `src/sheetgrade/release_order/lab_scenarios.py` | `tests/test_release_order.py` `tests/test_lab_scenarios.py` |
| M6 | 班组对账 | SpoolInspection处理证据 | `src/sheetgrade/spool_audit/contracts.py` `src/sheetgrade/spool_audit/algorithm.py` `src/sheetgrade/spool_audit/service.py` `src/sheetgrade/spool_audit/grade_backtest.py` | `tests/test_spool_audit.py` `tests/test_grade_backtest.py` |

## 边界登记

| 陷阱 | 业务输入 | 处理位置 | 验证锚点 |
|---|---|---|---|
| TRAP-19 | 确认规格越限优先于预测损失，重新排序无影响 | `src/sheetgrade/release_order/algorithm.py` | `tests/test_release_order.py::test_confirmed_quality_breach_precedes_larger_expected_loss` |
| TRAP-23 | 上一纸种结束的分界分钟归相邻窗口 | `src/sheetgrade/grade_change/algorithm.py` | `tests/test_grade_change.py::test_exact_window_end_belongs_to_next_grade` |
| TRAP-25 | 重叠生效版本同时标记，实际切换无法唯一解释 | `src/sheetgrade/grade_change/algorithm.py` | `tests/test_grade_change.py::test_overlapping_effective_windows_are_flagged_on_both_sides` |
| TRAP-32 | 大偏移、常数湿部特征用稳定归约和物理下限 | `src/sheetgrade/wet_signals/algorithm.py` | `tests/test_wet_signals.py::test_welford_stable_for_constant_and_nearly_constant_offset` |
| TRAP-42 | 截止后实验偏差不得进入基线 | `src/sheetgrade/wet_signals/algorithm.py` | `tests/test_wet_signals.py::test_future_calibration_cannot_change_earlier_signal` |
| TRAP-43 | 历史无断纸时质量召回不除零 | `src/sheetgrade/spool_audit/algorithm.py` | `tests/test_spool_audit.py::test_no_observed_breaks_has_unavailable_mass_recall` |
| TRAP-44 | 训练域外读数不自动判为高置信断纸 | `src/sheetgrade/breakpoint_model/algorithm.py` | `tests/test_breakpoint_model.py::test_outside_training_range_is_not_a_high_probability` |
| TRAP-53 | 异常读数拼批前后相同孤立纸卷评分无变化 | `src/sheetgrade/breakpoint_model/algorithm.py` | `tests/test_breakpoint_model.py::test_single_inference_and_mixed_batch_have_identical_scores` |
| TRAP-54 | 模型树深超参变更会建立新的模型指纹 | `src/sheetgrade/breakpoint_model/algorithm.py` | `tests/test_breakpoint_model.py::test_reconfiguration_changes_model_fingerprint` |
