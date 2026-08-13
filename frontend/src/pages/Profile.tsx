import { useEffect, useMemo } from 'react';
import { useEnterpriseStore, useProfileStore } from '@/store';
import {
  BiasRadarChart, BiasCard, ProfileSummary, DisclaimerBanner,
  determineSizeTier, generateSimulatedProfile,
} from '@/components/profile';
import { LoadingSpinner, EmptyState } from '@/components/common';
import { Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';

// ═══════════════════════════════════════
// 主导偏差 → 差异化建议行动
// ═══════════════════════════════════════
const BIAS_ACTIONS: Record<string, string[]> = {
  control_desire: [
    '将经营收入统一纳入对公账户，减少私卡收款',
    '建立规范的财务审批流程，适度授权',
    '定期请第三方会计师事务所审计资金流水',
  ],
  loss_aversion: [
    '明确区分"合理节税"与"不当避税"的界限',
    '测算合规纳税与企业长期发展的收益比',
    '咨询专业税务顾问，了解合法的税收优惠政策',
  ],
  optimism_bias: [
    '了解金税四期大数据稽查的真实案例，校准风险认知',
    '建立企业内部定期风险自查机制',
    '客观评估被稽查概率，减少侥幸心理',
  ],
  control_illusion: [
    '引入ERP或财务系统，实现业务全流程数字化',
    '由第三方独立审计验证业务链条完整性',
    '确保合同流、发票流、资金流、货物流保持一致',
  ],
  short_termism: [
    '制定3-5年合规发展规划，从最紧迫的环节开始整改',
    '将合规成本纳入年度预算，视为长期发展投资',
    '了解合规企业在融资、补贴、商业合作中的竞争优势',
  ],
  defensiveness: [
    '从最小、最简单的整改任务开始，逐步建立合规信心',
    '将整改过程视为降低个人连带责任风险的机会',
    '与已完成合规整改的同行业企业家交流经验',
  ],
};

function Profile() {
  const { currentEnterprise } = useEnterpriseStore();
  const { result, loading, generating, generateProfile, fetchLatest } = useProfileStore();

  const enterpriseId = currentEnterprise?.id;

  useEffect(() => {
    if (!enterpriseId) return;
    let ignore = false;
    // 先尝试获取最新画像，如果没有则生成
    fetchLatest(enterpriseId).then(() => {
      if (ignore) return;
      const current = useProfileStore.getState().result;
      if (!current) {
        generateProfile(enterpriseId);
      }
    });
    return () => { ignore = true; };
  }, [enterpriseId]);

  // ── 模拟画像数据：按企业行业×规模精准匹配生成 ──
  // 当后端未返回画像时，使用模拟数据作为展示数据回退
  // enterpriseId 作为种子保证同一企业每次生成结果一致，不同企业结果不同
  const simulated = useMemo(() => {
    if (!currentEnterprise) return null;
    const industry = currentEnterprise.industry || '批发零售';
    const revenue = currentEnterprise.revenue_annual ?? 5_000_000;
    const tier = determineSizeTier(revenue);
    return {
      ...generateSimulatedProfile(industry, tier, enterpriseId),
      industry,
      tier,
    };
  }, [currentEnterprise, enterpriseId]);

  // ── 后端数据有效性判断（≥3 个维度为 0 → 视为无效）──
  const backendValid = useMemo(() => {
    if (!result) return false;
    const zeroCount = [
      result.control_desire_score, result.loss_aversion_score,
      result.optimism_bias_score, result.control_illusion_score,
      result.short_termism_score, result.defensiveness_score,
    ].filter((v) => v === 0).length;
    return zeroCount < 3;
  }, [result]);

  // ── 构建六维评分映射 ──
  // 策略：后端有效数据优先，无效时降级使用行业×规模模拟数据
  const scores = useMemo<Record<string, number>>(() => {
    if (result && backendValid) {
      return {
        control_desire: result.control_desire_score,
        loss_aversion: result.loss_aversion_score,
        optimism_bias: result.optimism_bias_score,
        control_illusion: result.control_illusion_score,
        short_termism: result.short_termism_score,
        defensiveness: result.defensiveness_score,
      };
    }
    // 回退：使用行业×规模匹配的模拟数据
    if (simulated) {
      return simulated.scores;
    }
    return {};
  }, [result, simulated, backendValid]);

  // 按得分排序，取前2作为主导偏差
  const sortedBiases = useMemo(
    () => Object.entries(scores).sort(([, a], [, b]) => b - a),
    [scores],
  );

  // ── 无企业 ──
  if (!currentEnterprise) {
    return <EmptyState text="请先从顶部选择一家企业以查看心理画像" />;
  }

  // ── 加载中 ──
  if (loading || generating) {
    return <LoadingSpinner text={generating ? '正在生成心理画像...' : '正在加载画像数据...'} />;
  }

  // ── 无结果时，使用模拟数据直接渲染（跳过空状态） ──
  if (!result && !simulated) {
    return (
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-800">心理画像仪</h2>
        <EmptyState
          text="暂无心理画像数据"
          action={
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              onClick={() => enterpriseId && generateProfile(enterpriseId)}
            >
              生成画像
            </Button>
          }
        />
      </div>
    );
  }

  // 同行基准（优先后端 peer_average，否则使用模拟数据中的同行均值）
  const peerAverage: Record<string, number> = (result?.peer_average && Object.keys(result.peer_average).length === 6)
    ? (result.peer_average as Record<string, number>)
    : (simulated?.peerAverage ?? {});

  const peerBaseline = Object.keys(peerAverage).length >= 6
    ? Math.round(Object.values(peerAverage).reduce((a, b) => a + b, 0) / 6)
    : 43;

  // 主导偏差：后端有效时取后端结果，否则从当前 scores 推导
  const dominantBiases = (result && backendValid && result.dominant_biases?.length)
    ? result.dominant_biases
    : sortedBiases.slice(0, 2).map(([key]) => key);

  // 综合偏差指数：后端有效时取后端值，否则从当前 scores 计算
  const deviationIndex = (result && backendValid) ? result.deviation_index
    : Math.round(Object.values(scores).reduce((a, b) => a + b, 0) / 6);

  // 商业叙事：后端有效时取后端值，否则留空（模拟数据无叙事文本）
  const businessNarrative = (result && backendValid) ? (result.business_narrative ?? '') : '';

  // 行业×规模描述文本
  const industryLabel = simulated?.industry ?? currentEnterprise.industry ?? '未知行业';
  const tierLabel = simulated?.tier
    ? ({ small: '小型', medium: '中型', large: '大型' })[simulated.tier]
    : '未知规模';
  // 判断当前展示的是否为模拟数据
  const isSimulated = !result || !backendValid;

  return (
    <div className="space-y-6">
      {/* ═══ 顶部：画像总结卡 ═══ */}
      <ProfileSummary
        deviationIndex={deviationIndex}
        dominantBiases={dominantBiases}
        businessNarrative={businessNarrative}
        enterpriseName={currentEnterprise.name}
        baseline={peerBaseline}
      />

      {/* ═══ 中部：雷达图（左2/3）+ 主导偏差卡片（右1/3） ═══ */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* 六维偏差雷达图 —— 仅本企业 + 同行均值 */}
        <div className="xl:col-span-2 bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-base font-semibold text-gray-700 mb-2">
            六维偏差雷达图
          </h3>
          <p className="text-xs text-gray-400 mb-1">
            紫色实线 = 本企业（{industryLabel} · {tierLabel}），灰色虚线 = 同行均值
          </p>
          {isSimulated && (
            <p className="text-xs text-amber-600 mb-2">
              （当前为模拟数据，点击"生成画像"可获取基于真实财税数据的评估结果）
            </p>
          )}
          {!isSimulated && <p className="text-xs text-gray-400 mb-2">&nbsp;</p>}
          <BiasRadarChart
            scores={scores}
            peerAverage={peerAverage}
          />
        </div>

        {/* 主导偏差卡片 */}
        <div className="space-y-4">
          <h3 className="text-base font-semibold text-gray-700">主导偏差</h3>
          <p className="text-xs text-gray-400 -mt-3 mb-1">
            得分最高的偏差维度，是行为干预的核心切入点
          </p>
          {dominantBiases.length > 0 ? (
            dominantBiases.slice(0, 2).map((bias) => (
              <BiasCard
                key={bias}
                biasKey={bias}
                score={scores[bias] ?? 0}
                isDominant
                peerAvg={peerAverage[bias]}
              />
            ))
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
              <p className="text-sm text-gray-400">未识别主导偏差</p>
            </div>
          )}

          {/* 建议行动 —— 根据主导偏差动态展示 */}
          <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
            <h4 className="text-xs font-semibold text-blue-800 mb-2">建议行动</h4>
            <ul className="space-y-1.5">
              {dominantBiases.slice(0, 2).flatMap((bias) =>
                (BIAS_ACTIONS[bias] || []).map((action, i) => (
                  <li key={`${bias}-${i}`} className="text-xs text-blue-700 flex items-start gap-1.5">
                    <span className="text-blue-400 mt-0.5 shrink-0">•</span>
                    {action}
                  </li>
                ))
              )}
            </ul>
          </div>
        </div>
      </div>

      {/* ═══ 六维评分详情网格 ═══ */}
      <div>
        <h3 className="text-base font-semibold text-gray-700 mb-3">六维偏差详情</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sortedBiases.map(([key, score]) => (
            <BiasCard
              key={key}
              biasKey={key}
              score={score}
              isDominant={dominantBiases.includes(key)}
              peerAvg={peerAverage[key]}
            />
          ))}
        </div>
      </div>

      {/* ═══ 免责声明 ═══ */}
      <DisclaimerBanner />
    </div>
  );
}

export default Profile;
