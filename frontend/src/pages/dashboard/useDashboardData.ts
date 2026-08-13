/**
 * 驾驶舱数据加载 Hook
 *
 * 封装 Dashboard 全部数据获取与派生逻辑：
 *   - 并行加载：最新风险快照 / 历史趋势 / 待办任务 / 画像偏差
 *   - 一键加载模拟数据
 *   - 派生：趋势数据、合规调整后的风险等级与评分
 */
import { useEffect, useState, useCallback, useMemo } from 'react';
import { useEnterpriseStore, useRiskViewState } from '@/store';
import { dataApi, riskScanApi, remediationApi, profileApi } from '@/api';
import { DEVIATION_BASELINE } from '@/types';
import type { RiskAssessment } from '@/types';

export function useDashboardData() {
  const {
    currentEnterprise, compliance, listLoading: entLoading,
    fetchEnterprises,
  } = useEnterpriseStore();
  const { result, isBusy, busyText, scanRisk, fetchLatest } = useRiskViewState();

  // 本地状态
  const [loadingMock, setLoadingMock] = useState(false);
  const [assessments, setAssessments] = useState<RiskAssessment[]>([]);
  const [assessLoading, setAssessLoading] = useState(false);
  const [pendingTasks, setPendingTasks] = useState(0);
  const [deviationIndex, setDeviationIndex] = useState<number | null>(null);
  const [deviationBaseline, setDeviationBaseline] = useState<number>(DEVIATION_BASELINE);

  const enterpriseId = currentEnterprise?.id;

  // ── 加载全部驾驶舱数据（并行请求）──
  const loadAllData = useCallback(async () => {
    if (!enterpriseId) return;

    // 并行发起所有请求：读取最新快照 + 历史趋势 + 待办任务 + 画像数据
    const promises = [
      fetchLatest(enterpriseId),
      riskScanApi.list(enterpriseId)
        .then((res) => setAssessments(res.data.data?.assessments || []))
        .catch(() => setAssessments([])),
      remediationApi.list(enterpriseId, { status: 'pending', limit: 1 })
        .then((res) => setPendingTasks(res.data.data?.total || 0))
        .catch(() => setPendingTasks(0)),
      profileApi.latest(enterpriseId)
        .then((res) => {
          const data = res.data.data;
          setDeviationIndex(data?.deviation_index ?? null);
          if (data?.peer_average) {
            const avg = Object.values(data.peer_average) as number[];
            if (avg.length === 6) {
              setDeviationBaseline(Math.round(avg.reduce((a, b) => a + b, 0) / 6));
            }
          }
        })
        .catch(() => setDeviationIndex(null)),
    ];

    setAssessLoading(true);
    await Promise.allSettled(promises);
    setAssessLoading(false);
  }, [enterpriseId, fetchLatest]);

  // ── 切换企业 → 刷新所有数据 ──
  useEffect(() => {
    if (!enterpriseId) {
      setAssessments([]);
      setPendingTasks(0);
      setDeviationIndex(null);
      return;
    }
    loadAllData();
  }, [enterpriseId, loadAllData]);

  // ── 一键加载模拟数据 ──
  const handleLoadMockData = useCallback(async () => {
    if (!enterpriseId) return;
    setLoadingMock(true);
    try {
      await dataApi.loadMockData(enterpriseId);
      await loadAllData();
    } finally {
      setLoadingMock(false);
    }
  }, [enterpriseId, loadAllData]);

  // ── memoized 趋势数据 ──
  const trendData = useMemo(() => assessments.map((a) => ({
    date: a.assessment_date,
    score: a.overall_risk_score,
    level: a.overall_risk_level,
  })), [assessments]);

  // ── 合规调整后的风险等级（跨模块联动） ──
  const adjustedRiskLevel = useMemo(() => {
    if (compliance?.is_fully_compliant) return 'low';
    return compliance?.adjusted_level ?? result?.overall_risk_level ?? 'low';
  }, [compliance, result]);

  const adjustedRiskScore = useMemo(() => {
    if (compliance?.is_fully_compliant) return 10;
    if (compliance?.adjusted_score != null) return compliance.adjusted_score;
    return result?.overall_risk_score ?? 0;
  }, [compliance, result]);

  // ── 风险扫描中 ──
  const isLoading = isBusy || entLoading || (!!enterpriseId && !result);

  return {
    currentEnterprise,
    enterpriseId,
    entLoading,
    fetchEnterprises,
    result,
    isBusy,
    busyText,
    scanRisk,
    loadAllData,
    handleLoadMockData,
    loadingMock,
    trendData,
    assessments,
    assessLoading,
    pendingTasks,
    deviationIndex,
    deviationBaseline,
    adjustedRiskLevel,
    adjustedRiskScore,
    isLoading,
  };
}
