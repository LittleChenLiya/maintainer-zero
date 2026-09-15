from __future__ import annotations

from .models import DrillResult, Evidence, Finding, RepoSnapshot
from .simulation import SimulationConfig, SimulationEvent, run_simulation


_RECOVERY_WINDOW_DAYS = 7


def _empty_queue_metrics() -> dict[str, object]:
    """Return explicit not-applicable values for a skipped queue drill."""
    return {
        "simulated_peak_backlog": None,
        "simulated_ending_backlog": None,
        "simulated_service_level": None,
        "simulated_recovery_day": None,
        "simulated_recovery_ending_backlog": None,
        "simulated_recovery_window_days": _RECOVERY_WINDOW_DAYS,
    }


def _queue_evidence(metrics: dict[str, object], note: str) -> list[Evidence]:
    """Expose every queue aggregate as a separately auditable observation."""
    return [
        Evidence("deterministic simulation", "peak_backlog", metrics["simulated_peak_backlog"], f"{note} Peak backlog during the incident window."),
        Evidence("deterministic simulation", "ending_backlog", metrics["simulated_ending_backlog"], f"{note} Backlog at the end of the incident window."),
        Evidence("deterministic simulation", "service_level", metrics["simulated_service_level"], f"{note} Demand serviced over the simulated horizon."),
        Evidence("deterministic simulation", "recovery_day", metrics["simulated_recovery_day"], f"{note} First day on which backlog reaches zero under the assumed recovery capacity."),
        Evidence("deterministic simulation", "recovery_ending_backlog", metrics["simulated_recovery_ending_backlog"], f"{note} Backlog at the end of the assumed recovery window."),
    ]


def _queue_metrics(
    *,
    incident_days: int,
    daily_demand: float,
    baseline_capacity: float,
    outage_delta: float,
    recovery_capacity: float,
    outage_name: str,
    recovery_name: str,
) -> dict[str, object]:
    """Run an incident plus an assumed, bounded recovery window."""
    restore_day = incident_days + 1
    current_capacity = max(0.0, baseline_capacity + outage_delta)
    recovery_delta = recovery_capacity - current_capacity
    queue = run_simulation(
        [
            SimulationEvent(0, outage_name, capacity_delta=outage_delta),
            SimulationEvent(restore_day, recovery_name, capacity_delta=recovery_delta),
        ],
        SimulationConfig(
            days=incident_days + _RECOVERY_WINDOW_DAYS,
            initial_capacity=baseline_capacity,
            daily_demand=daily_demand,
        ),
    )
    incident_rows = [row for row in queue.timeline if row["day"] <= incident_days]
    incident_end = incident_rows[-1]["backlog"] if incident_rows else 0.0
    incident_peak = max((row["backlog"] for row in incident_rows), default=0.0)
    return {
        "simulated_peak_backlog": round(incident_peak, 3),
        "simulated_ending_backlog": round(incident_end, 3),
        "simulated_service_level": round(queue.service_level, 3),
        "simulated_recovery_day": queue.first_zero_backlog_day,
        "simulated_recovery_ending_backlog": round(queue.ending_backlog, 3),
        "simulated_recovery_window_days": _RECOVERY_WINDOW_DAYS,
    }

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
    queue_metrics = _queue_metrics(
        incident_days=days,
        daily_demand=daily_demand,
        baseline_capacity=daily_demand,
        outage_delta=-(daily_demand * share),
        recovery_capacity=daily_demand * 2,
        outage_name="maintainer-unavailable",
        recovery_name="backup-capacity-available",
    )
    metrics = {"departed_maintainer": top_name, "contribution_share": round(share, 3), "backup_maintainers": backups, "estimated_weekly_backlog": backlog, "days": days, **queue_metrics}
    evidence = [
        Evidence("git snapshot", "commits", repo.commits, "Used as the workload proxy."),
        Evidence("git snapshot", "contributor_count", len(repo.contributors), "Used to estimate maintainer redundancy."),
        Evidence("git snapshot", "top_contributor_share", round(share, 3), "Used by the single-point rule."),
        Evidence("drill parameters", "days", days, "The simulated unavailability window."),
        *_queue_evidence(queue_metrics, "Maintainer-unavailability model."),
    ]
    return DrillResult("maintainer-zero", max(0, min(100, score)), "medium" if repo.commits >= 10 else "low", ["使用提交历史近似工作容量；未连接 GitHub Issue API。", f"假设 {top_name} 在整个演练周期不可用。", "恢复窗口假设备用容量可在事故结束后立即达到基线的 2 倍；这不是已验证能力。"], metrics, findings, _timeline([(0, "核心维护者停止响应", "新 PR 和安全 Issue 开始积压"), (7, "审查队列增长", f"预计每周积压约 {backlog} 个工作单元"), (30, "发布压力出现", "若无备用发布人，修复无法可靠上线"), (days, "演练结束", "检查接班人和恢复 Runbook 是否可执行")], days), evidence)

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
    queue_metrics = (
        _queue_metrics(
            incident_days=days,
            daily_demand=max(1.0, min(10.0, count / 2)),
            baseline_capacity=max(1.0, min(10.0, count / 2)),
            outage_delta=-max(1.0, min(10.0, count / 2)),
            recovery_capacity=2 * max(1.0, min(10.0, count / 2)),
            outage_name="dependency-unavailable",
            recovery_name="dependency-fallback-available",
        )
        if applicable
        else _empty_queue_metrics()
    )
    metrics = {"dependency_count": count, "simulated_packages": critical, "applicable": applicable, "days": days, **queue_metrics}
    evidence = [
        Evidence("dependency manifests", "dependency_count", count, "Counted from supported local manifests."),
        Evidence("scenario applicability", "applicable", applicable, "The drill is not applicable when no supported dependency is present."),
        Evidence("drill parameters", "days", days, "The simulated recovery window."),
        *_queue_evidence(queue_metrics, "Dependency-fallback model."),
    ]
    return DrillResult("dependency-yanked", score, "medium" if count else "low", ["按清单文件中的依赖数量估算；没有联网验证包可用性。", "恢复窗口假设备用依赖路径可在事故结束后立即达到基线的 2 倍；这不是已验证能力。"], metrics, findings, _timeline(events, days), evidence)

def ci_outage(repo: RepoSnapshot, days: int = 14) -> DrillResult:
    days = _validate_days(days)
    count = len(repo.workflows)
    release = bool(repo.release_files)
    score = max(10, 100 - count * 5 - (25 if release else 0))
    finding = Finding("high" if release else "medium", "CI / 发布链路中断", f"模拟 CI 不可用 {days} 天；发现 {count} 个工作流。", "提供本地测试与发布命令，并记录备用 Runner、凭证和人工审批流程。", "ci-outage.pipeline")
    daily_demand = max(1.0, min(10.0, float(count or 1)))
    queue_metrics = _queue_metrics(
        incident_days=days,
        daily_demand=daily_demand,
        baseline_capacity=daily_demand,
        outage_delta=-daily_demand,
        recovery_capacity=daily_demand * 2,
        outage_name="ci-unavailable",
        recovery_name="ci-fallback-available",
    )
    evidence = [
        Evidence("repository files", "workflow_count", count, "Counted workflow files under .github/workflows."),
        Evidence("repository files", "release_path_detected", release, "Whether a supported release file was found."),
        Evidence("drill parameters", "days", days, "The simulated CI outage window."),
        *_queue_evidence(queue_metrics, "CI-fallback model."),
    ]
    metrics = {"workflow_count": count, "release_path_detected": release, "days": days, **queue_metrics}
    return DrillResult("ci-outage", min(100, score), "medium" if count else "low", ["只从仓库文件推断流水线；未调用 GitHub 配额或 Secrets API。", "恢复窗口假设备用容量可在事故结束后立即达到基线的 2 倍；这不是已验证能力。"], metrics, [finding], _timeline([(0, "CI 服务不可用", "合并验证转为人工"), (3, "未验证变更堆积", "发布节奏开始下降"), (days, "演练结束", "检查本地 fallback 和凭证轮换文档")], days), evidence)

SCENARIOS = {"maintainer-zero": maintainer_zero, "dependency-yanked": dependency_yanked, "ci-outage": ci_outage}
