from __future__ import annotations

from .models import DrillResult, Finding, RepoSnapshot
from .simulation import SimulationConfig, SimulationEvent, run_simulation

def _validate_days(days: int) -> int:
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("days must be a non-negative integer")
    return days

def _timeline(events, days: int):
    """Keep only events that occur inside the requested drill window."""
    return [{"day": d, "event": e, "impact": i} for d, e, i in events if 0 <= d <= days]

def maintainer_zero(repo: RepoSnapshot, days: int = 90) -> DrillResult:
    days = _validate_days(days)
    people = sorted(repo.contributors.items(), key=lambda x: x[1], reverse=True)
    top_name, top_commits = people[0] if people else ("unknown", 0)
    total = max(repo.commits, 1)
    share = top_commits / total
    backups = sum(1 for _, count in people if count >= max(2, total * 0.05))
    score = round(100 * (0.45 * min(1, max(0, (backups - 1) / 3)) + 0.25 * bool(repo.codeowners) + 0.30 * bool(repo.release_files)))
    findings = []
    if share >= 0.60:
        findings.append(Finding("high", "核心维护单点", f"{top_name} 贡献了 {share:.0%} 的提交；模拟其离开 {days} 天。", "为关键目录增加第二位 CODEOWNER，并记录发布权限交接。", "maintainer-zero.core-owner"))
    if not repo.codeowners:
        findings.append(Finding("medium", "没有 CODEOWNERS", "无法在核心模块上自动分配接班审查人。", "创建 .github/CODEOWNERS，覆盖发布、安全和核心目录。", "maintainer-zero.codeowners"))
    if not repo.release_files:
        findings.append(Finding("medium", "发布恢复路径不明确", "未发现常见发布配置或发布工作流。", "补充可在本地执行的发布 Runbook 和备用凭证流程。", "maintainer-zero.release-path"))
    backlog = round(max(1, repo.commits / max(1, days) * 7) * (1 + share * 3))
    daily_demand = max(0.1, repo.commits / max(days + 1, 1))
    queue = run_simulation(
        [SimulationEvent(0, "maintainer-unavailable", capacity_delta=-(daily_demand * share))],
        SimulationConfig(days=days, initial_capacity=daily_demand, daily_demand=daily_demand),
    )
    metrics = {"departed_maintainer": top_name, "contribution_share": round(share, 3), "backup_maintainers": backups, "estimated_weekly_backlog": backlog, "days": days, "simulated_peak_backlog": round(queue.peak_backlog, 3), "simulated_ending_backlog": round(queue.ending_backlog, 3), "simulated_service_level": round(queue.service_level, 3), "simulated_recovery_day": queue.first_zero_backlog_day}
    return DrillResult("maintainer-zero", max(0, min(100, score)), "medium" if repo.commits >= 10 else "low", ["使用提交历史近似工作容量；未连接 GitHub Issue API。", f"假设 {top_name} 在整个演练周期不可用。"], metrics, findings, _timeline([(0, "核心维护者停止响应", "新 PR 和安全 Issue 开始积压"), (7, "审查队列增长", f"预计每周积压约 {backlog} 个工作单元"), (30, "发布压力出现", "若无备用发布人，修复无法可靠上线"), (days, "演练结束", "检查接班人和恢复 Runbook 是否可执行")], days))

def dependency_yanked(repo: RepoSnapshot, days: int = 30) -> DrillResult:
    days = _validate_days(days)
    count = len(repo.dependencies)
    critical = repo.dependencies[:min(3, count)]
    score = 100 if count == 0 else max(20, 100 - min(70, count * 8))
    if count:
        findings = [Finding("high" if count >= 5 else "medium", "依赖撤包冲击", f"模拟关键依赖不可用：{', '.join(critical)}。", "锁定来源和版本，准备替代包，并定期验证冷构建。", "dependency-yanked.package")]
        applicable = True
        events = [(0, "上游包被撤下", "新环境无法完成安装"), (1, "锁文件重建失败", "发布和安全修复流水线受阻"), (days, "演练结束", "验证缓存、镜像和替代依赖")]
    else:
        findings = [Finding("info", "没有可演练的清单依赖", "未发现 package.json 或 requirements 文件中的依赖；撤包场景不适用。", "确认项目是否通过其他清单或构建系统声明依赖。", "dependency-yanked.not-applicable")]
        applicable = False
        events = [(0, "场景跳过", "当前采集范围没有可模拟的依赖")]
    metrics = {"dependency_count": count, "simulated_packages": critical, "applicable": applicable, "days": days}
    return DrillResult("dependency-yanked", score, "medium" if count else "low", ["按清单文件中的依赖数量估算；没有联网验证包可用性。"], metrics, findings, _timeline(events, days))

def ci_outage(repo: RepoSnapshot, days: int = 14) -> DrillResult:
    days = _validate_days(days)
    count = len(repo.workflows)
    release = bool(repo.release_files)
    score = max(10, 100 - count * 5 - (25 if release else 0))
    finding = Finding("high" if release else "medium", "CI / 发布链路中断", f"模拟 CI 不可用 {days} 天；发现 {count} 个工作流。", "提供本地测试与发布命令，并记录备用 Runner、凭证和人工审批流程。", "ci-outage.pipeline")
    return DrillResult("ci-outage", min(100, score), "medium" if count else "low", ["只从仓库文件推断流水线；未调用 GitHub 配额或 Secrets API。"], {"workflow_count": count, "release_path_detected": release, "days": days}, [finding], _timeline([(0, "CI 服务不可用", "合并验证转为人工"), (3, "未验证变更堆积", "发布节奏开始下降"), (days, "演练结束", "检查本地 fallback 和凭证轮换文档")], days))

SCENARIOS = {"maintainer-zero": maintainer_zero, "dependency-yanked": dependency_yanked, "ci-outage": ci_outage}
