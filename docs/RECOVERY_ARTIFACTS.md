# 恢复工件草稿

`maintainer-zero simulate` 会在输出目录下生成 `recovery/`，也可以用
`--recovery-output PATH` 指定目录：

```text
.continuity/recovery/
├── runbook.md          # 事故前准备、按发现组织的处置清单和验证项
├── CODEOWNERS.draft    # 保守的占位规则，不会覆盖仓库中的 CODEOWNERS
└── issue-drafts.md     # 可复制到 Issue 的草稿，不会调用 GitHub API
```

这些文件是待维护者审阅的建议，不是已经执行的修复证明。CLI 只写入用户指定的输出目录，不修改被分析仓库、不提交 Issue、不改变权限。`CODEOWNERS.draft` 不猜测或复制真实身份，使用占位别名，提交前必须替换并由维护者确认。

报告或场景输入中的 `token=...`、`secret=...`、`password=...` 和 `api-key=...` 形式会在恢复草稿中替换为 `[REDACTED]`。这不是完整的秘密扫描；分享工件前仍应人工检查，并避免把凭证放入仓库文件。

恢复工件适合在 PR 中作为审阅材料。建议完成清单后重新运行同一场景，并将新旧报告通过 `--baseline`（或对应 CI 门禁）比较；分数变化只能说明规则输入下的模型变化，不能证明真实事故已经恢复。
