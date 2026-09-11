# 同仓库趋势历史

机器消费提示：`history-summary.json` 同时提供 `*_since_previous` 与 `*_since_first` 的分数、场景、Finding 数量和高危 Finding 变化；缺失数据不会被当作零。规则升级后应建立新的历史文件，避免把规则变化误报成项目改进或退化。

`simulate --history PATH` 会把当前报告追加到一个本地 JSON 历史文件，并在输出目录生成 `history-summary.json`。历史只保存分数、场景分数、Finding 数量和高危 Finding 数量，不复制仓库内容、原始事件或贡献者记录。

```powershell
maintainer-zero simulate . --scenario all --history .continuity/history.json
```

每次运行都会检查仓库名称和绝对路径是否与历史所有者一致；混入其他仓库会失败。`repository_id` 是这两个字段的稳定短哈希，用于识别而不是公开排名。历史默认只写入用户指定的本地路径，CLI 不上传或修改 GitHub。

趋势摘要包含：规则版本、运行次数、最新记录、相对上一次运行的总分变化、相对首次运行的总分变化、场景分数变化、Finding 数量变化和高危 Finding 数量变化。历史文件会拒绝分数越界、规则版本混用、时间倒退、异常字段和超出数量上限的记录。空历史明确报告 `runs: 0`，而不是推断“没有风险”。

历史是同一仓库、同一规则版本下的审阅辅助材料，不用于跨项目榜单或事故概率估计。规则升级后应在 PR 中审阅分数变化；如需门禁，继续使用 `--baseline` 和显式 `--fail-on-*` 策略。
