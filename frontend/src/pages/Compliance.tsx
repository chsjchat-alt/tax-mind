import { useEffect, useState, useMemo } from 'react';
import { useEnterpriseStore } from '@/store';
import { complianceApi } from '@/api';
import {
  TaxPreferencePanel, PlanComparisonTable, InterventionLayerCard,
  InterventionNarrativePanel,
  generatePlans,
} from '@/components/compliance';
import { LoadingSpinner, EmptyState } from '@/components/common';
import type { TaxPreferenceResult, InterventionResult, InterventionLayer } from '@/types';
import { Tag } from 'antd';

// ── 默认干预层（当后端数据不足5层时补齐） ──
const DEFAULT_LAYERS: InterventionLayer[] = [
  {
    layer: 4,
    name: '社会规范校准',
    theory: '社会规范理论',
    visual_type: '同行业对比',
    content: '展示同行业、同规模企业的税收负担率和合规水平，利用社会规范效应激发企业的合规动机。当企业主看到"同规模企业平均税负率是XX%，您的税负率仅为YY%"时，会产生从众压力。',
  },
  {
    layer: 5,
    name: '自我效能建设',
    theory: '自我效能理论',
    visual_type: '分步行动指南',
    content: '提供清晰的、可执行的整改步骤，降低"不知道从哪里开始"的焦虑。将复杂的合规任务分解为每月的具体行动项，让企业主建立"我能做到"的信心。',
  },
];

function Compliance() {
  const { currentEnterprise } = useEnterpriseStore();

  const [preference, setPreference] = useState<TaxPreferenceResult | null>(null);
  const [intervention, setIntervention] = useState<InterventionResult | null>(null);
  const [loading, setLoading] = useState(false);

  // 五层干预展开状态
  const [expandedLayers, setExpandedLayers] = useState<Set<number>>(new Set());

  const enterpriseId = currentEnterprise?.id;

  useEffect(() => {
    if (!enterpriseId) {
      setPreference(null);
      setIntervention(null);
      return;
    }
    setLoading(true);
    // 独立请求，避免一个失败导致全部重置
    complianceApi.taxPreference(enterpriseId)
      .then((res) => { setPreference(res.data.data); })
      .catch(() => { setPreference(null); });
    complianceApi.intervention(enterpriseId)
      .then((res) => { setIntervention(res.data.data); })
      .catch(() => { setIntervention(null); })
      .finally(() => setLoading(false));
  }, [enterpriseId]);

  const toggleLayer = (layer: number) => {
    setExpandedLayers((prev) => {
      const next = new Set(prev);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  };

  // 合并干预层：后端数据 + 补齐默认层
  const allLayers = useMemo(() => {
    const existing = intervention?.layers || [];
    const existingNums = new Set(existing.map((l) => l.layer));
    const supplement = DEFAULT_LAYERS.filter((l) => !existingNums.has(l.layer));
    const merged = [...existing, ...supplement];
    merged.sort((a, b) => a.layer - b.layer);
    return merged;
  }, [intervention]);

  // 三套方案
  const plans = useMemo(
    () => generatePlans(currentEnterprise?.risk_level || 'low'),
    [currentEnterprise?.risk_level],
  );

  // ── 无企业 ──
  if (!currentEnterprise) {
    return <EmptyState text="请先从顶部选择一家企业以使用合规导航仪" />;
  }

  // ── 加载中 ──
  if (loading) {
    return <LoadingSpinner text="正在加载合规数据..." />;
  }

  return (
    <div className="space-y-8">
      {/* ═══ 标题 ═══ */}
      <div>
        <h2 className="text-2xl font-bold text-gray-800">合规导航仪</h2>
        <p className="text-sm text-gray-500 mt-1">
          {currentEnterprise.name} · 优惠校验 · 合规路径 · 合规干预
        </p>
      </div>

      {/* ═══ 第一部分：税收优惠校验 ═══ */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <div className="w-1 h-5 rounded-full bg-green-500" />
          <h3 className="text-lg font-semibold text-gray-700">税收优惠校验</h3>
        </div>

        {preference ? (
          <TaxPreferencePanel
            preference={preference}
            enterpriseName={currentEnterprise.name}
          />
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
            <p className="text-sm text-gray-400">暂无税收优惠数据，请先生成风险扫描</p>
          </div>
        )}
      </section>

      {/* ═══ 第二部分：合规路径建议 ═══ */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <div className="w-1 h-5 rounded-full bg-blue-500" />
          <h3 className="text-lg font-semibold text-gray-700">合规路径建议</h3>
          <span className="text-xs text-gray-400 ml-2">
            基于风险等级「{
              currentEnterprise.risk_level === 'critical' ? '严重风险' :
              currentEnterprise.risk_level === 'high' ? '高风险' :
              currentEnterprise.risk_level === 'medium_high' ? '中高风险' :
              currentEnterprise.risk_level === 'medium' ? '中风险' : '低风险'
            }」推荐
          </span>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <PlanComparisonTable plans={plans} />
        </div>
      </section>

      {/* ═══ 第三部分：五层合规干预 ═══ */}
      {intervention ? (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <div className="w-1 h-5 rounded-full bg-purple-500" />
            <h3 className="text-lg font-semibold text-gray-700">五层合规干预策略</h3>
          </div>

          {/* 干预概览 */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-gray-700">
                  合规干预策略 · 基于风险等级与合规调整
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  按风险等级与合规调整结果确定干预层级顺序
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">优先维度:</span>
                <Tag color="blue" className="text-xs">{intervention.priority_bias !== 'none' ? intervention.priority_bias : '无'}</Tag>
              </div>
            </div>
          </div>

          {/* 五层干预卡片 */}
          <div className="space-y-3">
            {allLayers.map((layer) => (
              <InterventionLayerCard
                key={layer.layer}
                layer={layer.layer}
                name={layer.name}
                theory={layer.theory}
                visualType={layer.visual_type}
                content={layer.content}
                isExpanded={expandedLayers.has(layer.layer)}
                onToggle={() => toggleLayer(layer.layer)}
              />
            ))}
          </div>

          {/* 干预解读 — 四模块结构化排版 */}
          {intervention.business_narrative && (
            <div className="mt-4">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-1 h-5 rounded-full bg-purple-500" />
                <h3 className="text-base font-semibold text-gray-700">干预解读</h3>
              </div>
              <InterventionNarrativePanel
                intervention={intervention}
                enterpriseName={currentEnterprise.name}
                riskLevel={currentEnterprise.risk_level || 'low'}
              />
            </div>
          )}
        </section>
      ) : (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <div className="w-1 h-5 rounded-full bg-purple-500" />
            <h3 className="text-lg font-semibold text-gray-700">五层合规干预策略</h3>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
            <p className="text-sm text-gray-400">暂无干预策略数据，请先完成风险扫描</p>
          </div>
        </section>
      )}
    </div>
  );
}

export default Compliance;
