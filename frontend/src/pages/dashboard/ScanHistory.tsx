/**
 * 驾驶舱最近风险扫描记录表格
 */
import { useNavigate } from 'react-router-dom';
import { Button } from 'antd';
import { RightOutlined } from '@ant-design/icons';
import { RiskBadge, TableContainer } from '@/components/common';
import { RISK_COLORS } from '@/types';
import type { RiskAssessment } from '@/types';

interface ScanHistoryProps {
  assessments: RiskAssessment[];
}

export default function ScanHistory({ assessments }: ScanHistoryProps) {
  const navigate = useNavigate();

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-base font-semibold text-gray-700">最近风险扫描记录</h3>
        <Button
          type="link"
          size="small"
          onClick={() => navigate('/risk-map')}
        >
          查看全部 <RightOutlined />
        </Button>
      </div>

      {assessments.length > 0 ? (
        <TableContainer>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-400 border-b border-gray-100">
                <th className="pb-2 font-medium">评估日期</th>
                <th className="pb-2 font-medium">风险等级</th>
                <th className="pb-2 font-medium">综合评分</th>
                <th className="pb-2 font-medium">四流匹配</th>
                <th className="pb-2 font-medium">私卡占比</th>
                <th className="pb-2 font-medium">成本偏离</th>
              </tr>
            </thead>
            <tbody>
              {assessments.slice(0, 10).map((a) => (
                <tr
                  key={a.id}
                  className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
                  onClick={() => navigate('/risk-map')}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate('/risk-map'); } }}
                >
                  <td className="py-2.5 text-gray-600">
                    {a.assessment_date?.slice(0, 10) || '--'}
                  </td>
                  <td className="py-2.5">
                    <RiskBadge level={a.overall_risk_level} />
                  </td>
                  <td className="py-2.5">
                    <span
                      className="font-medium"
                      style={{ color: RISK_COLORS[a.overall_risk_level] }}
                    >
                      {a.overall_risk_score}
                    </span>
                    <span className="text-gray-400 ml-1">分</span>
                  </td>
                  <td className="py-2.5 text-gray-600">
                    {a.four_flow_match_score != null ? `${Math.round(a.four_flow_match_score)}%` : '--'}
                  </td>
                  <td className="py-2.5 text-gray-600">
                    {a.private_card_ratio != null ? `${Math.round(a.private_card_ratio)}%` : '--'}
                  </td>
                  <td className="py-2.5 text-gray-600">
                    {a.cost_deviation != null ? `${Math.round(a.cost_deviation)}%` : '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableContainer>
      ) : (
        <div className="text-center py-8 text-sm text-gray-400">
          暂无扫描记录，请先执行风险扫描
        </div>
      )}
    </div>
  );
}
