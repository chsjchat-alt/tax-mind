/**
 * 驾驶舱图表区域：风险趋势折线图 + 七维风险雷达图
 */
import { RiskRadar, RiskTrendChart } from '@/components/charts';
import type { RiskScanResult } from '@/types';

export interface TrendPoint {
  date: string;
  score: number;
  level: string;
}

interface ChartsSectionProps {
  trendData: TrendPoint[];
  assessmentCount: number;
  assessLoading: boolean;
  result: RiskScanResult | null;
}

export default function ChartsSection({
  trendData, assessmentCount, assessLoading, result,
}: ChartsSectionProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* 风险趋势折线图 */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold text-gray-700">风险趋势（近{assessmentCount}次评估）</h3>
          {assessLoading && (
            <span className="text-xs text-gray-400">加载中...</span>
          )}
        </div>
        {assessmentCount >= 1 ? (
          <RiskTrendChart assessments={trendData} />
        ) : (
          <div className="flex items-center justify-center h-[280px] text-sm text-gray-400">
            暂无历史评估数据，请先执行风险扫描
          </div>
        )}
      </div>

      {/* 七维风险雷达图 */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="text-base font-semibold text-gray-700 mb-3">风险维度分布</h3>
        {result?.dimension_scores && Object.keys(result.dimension_scores).length > 0 ? (
          <RiskRadar scores={result.dimension_scores} />
        ) : (
          <div className="flex items-center justify-center h-[320px] text-sm text-gray-400">
            暂无维度数据
          </div>
        )}
      </div>
    </div>
  );
}
