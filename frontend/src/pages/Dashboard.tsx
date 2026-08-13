/**
 * 数据驾驶舱
 *
 * 组合入口：数据获取见 useDashboardData，指标卡/图表/扫描记录见 dashboard/ 子组件。
 */
import { Button, Tooltip } from 'antd';
import {
  ThunderboltOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { LoadingSpinner, EmptyState } from '@/components/common';
import SSFQuadrantChart from '@/components/ssf';
import { useDashboardData } from './dashboard/useDashboardData';
import MetricCards from './dashboard/MetricCards';
import ChartsSection from './dashboard/ChartsSection';
import ScanHistory from './dashboard/ScanHistory';

function Dashboard() {
  const {
    currentEnterprise, enterpriseId, entLoading, fetchEnterprises,
    result, isBusy, busyText, scanRisk, loadAllData,
    handleLoadMockData, loadingMock,
    trendData, assessments, assessLoading, pendingTasks,
    deviationIndex, deviationBaseline,
    adjustedRiskLevel, adjustedRiskScore, isLoading,
  } = useDashboardData();

  // ── 无企业选中状态 ──
  if (!currentEnterprise && !entLoading) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-800">数据驾驶舱</h2>
        <EmptyState
          text="请先从顶部选择一家企业，或点击下方按钮加载模拟数据"
          action={
            <Button type="primary" onClick={fetchEnterprises} icon={<ReloadOutlined />}>
              刷新企业列表
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ═══ 顶部操作栏 ═══ */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">数据驾驶舱</h2>
          {currentEnterprise && (
            <p className="text-sm text-gray-500 mt-1">
              {currentEnterprise.name} · {currentEnterprise.industry}
              {currentEnterprise.employee_count ? ` · ${currentEnterprise.employee_count}人` : ''}
              {currentEnterprise.revenue_annual ? ` · 年营收${(currentEnterprise.revenue_annual / 10000).toFixed(0)}万` : ''}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <Tooltip title={loadingMock ? '正在加载模拟数据...' : '为当前企业生成发票、银行流水、合同等模拟数据'}>
            <Button
              type="default"
              icon={loadingMock ? <ReloadOutlined spin /> : <ThunderboltOutlined />}
              onClick={handleLoadMockData}
              loading={loadingMock}
              disabled={!enterpriseId}
            >
              一键加载模拟数据
            </Button>
          </Tooltip>
          <Tooltip title="执行新一轮风险扫描并更新结果">
            <Button
              type="default"
              onClick={() => enterpriseId && scanRisk(enterpriseId)}
              disabled={!enterpriseId || isBusy}
            >
              重新扫描
            </Button>
          </Tooltip>
          <Tooltip title="刷新当前数据">
            <Button
              icon={<ReloadOutlined />}
              onClick={loadAllData}
              disabled={!enterpriseId || isLoading}
            />
          </Tooltip>
        </div>
      </div>

      {/* ═══ 加载中 ═══ */}
      {isLoading ? (
        <LoadingSpinner text={busyText} />
      ) : result ? (
        <>
          {/* ═══ 4个核心指标卡片（可点击跳转） ═══ */}
          <MetricCards
            adjustedRiskLevel={adjustedRiskLevel}
            adjustedRiskScore={adjustedRiskScore}
            fourFlowMatchScore={result.four_flow_match_score}
            deviationIndex={deviationIndex}
            deviationBaseline={deviationBaseline}
            pendingTasks={pendingTasks}
          />

          {/* ═══ 图表区域：趋势图 + 雷达图 ═══ */}
          <ChartsSection
            trendData={trendData}
            assessmentCount={assessments.length}
            assessLoading={assessLoading}
            result={result}
          />

          {/* ═══ SSF 博弈状态四象限定位 ═══ */}
          <SSFQuadrantChart enterpriseId={enterpriseId || undefined} />

          {/* ═══ 最近扫描记录 ═══ */}
          <ScanHistory assessments={assessments} />
        </>
      ) : (
        <EmptyState text="数据加载失败，请重试" />
      )}
    </div>
  );
}

export default Dashboard;
