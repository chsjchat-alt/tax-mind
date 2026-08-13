import { useState } from 'react';
import { Progress, Tag, Button, Tooltip } from 'antd';
import {
  EditOutlined, ClockCircleOutlined,
  CheckCircleFilled, ExclamationCircleFilled,
  AuditOutlined,
} from '@ant-design/icons';
import { RISK_COLORS, TASK_PRIORITY_LABELS } from '@/types';
import type { RemediationTask } from '@/types';

// 合规标签中文映射
const COMPLIANCE_TAG_LABELS: Record<string, string> = {
  vat_burden_zero: '增值税税负为0',
  vat_burden_low: '增值税税负偏低',
  income_tax_burden_low: '所得税贡献率低',
  ar_spike: '应收异常',
  ap_spike: '应付异常',
  inventory_abnormal: '存货异常',
  current_ratio_abnormal: '流动比率异常',
  asset_liability_ratio_high: '资产负债率高',
  depreciation_insufficient: '折旧不足',
  four_flow_mismatch: '四流不匹配',
  declared_rev_gap: '申报收入差异',
};

// ═══════════════════════════════════════
// ProgressDonut - 进度环形图
// ═══════════════════════════════════════
interface ProgressDonutProps {
  total: number;
  completed: number;
  inProgress: number;
  pending: number;
  overdue: number;
}

export function ProgressDonut({
  total, completed, inProgress, overdue,
}: ProgressDonutProps) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="flex flex-col sm:flex-row items-center gap-6 p-5">
      {/* 环形图 */}
      <div className="relative shrink-0">
        <Progress
          type="circle"
          percent={pct}
          size={140}
          strokeColor={{
            '0%': '#10B981',
            '100%': '#059669',
          }}
          trailColor="#f1f5f9"
          format={() => (
            <div className="text-center">
              <span className="text-2xl font-extrabold text-gray-800">{pct}%</span>
              <br />
              <span className="text-[10px] text-gray-400">完成率</span>
            </div>
          )}
        />
      </div>

      {/* 统计数字 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 flex-1">
        <div className="text-center">
          <p className="text-2xl font-bold text-gray-800">{total}</p>
          <p className="text-xs text-gray-400">总任务</p>
        </div>
        <div className="text-center">
          <CheckCircleFilled className="text-green-500 mb-0.5" />
          <p className="text-2xl font-bold text-green-600">{completed}</p>
          <p className="text-xs text-gray-400">已完成</p>
        </div>
        <div className="text-center">
          <ClockCircleOutlined className="text-blue-500 mb-0.5" />
          <p className="text-2xl font-bold text-blue-600">{inProgress}</p>
          <p className="text-xs text-gray-400">进行中</p>
        </div>
        <div className="text-center">
          <ExclamationCircleFilled
            className={overdue > 0 ? 'text-red-500' : 'text-gray-300'}
          />
          <p className={`text-2xl font-bold ${overdue > 0 ? 'text-red-600' : 'text-gray-400'}`}>
            {overdue}
          </p>
          <p className="text-xs text-gray-400">已逾期</p>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// TaskCard - 整改任务卡片
// ═══════════════════════════════════════
const STATUS_OPTIONS: { value: string; label: string; color: string }[] = [
  { value: 'pending', label: '待处理', color: '#94a3b8' },
  { value: 'in_progress', label: '进行中', color: '#3B82F6' },
  { value: 'completed', label: '已完成', color: '#10B981' },
];

interface TaskCardProps {
  task: RemediationTask;
  isUpdating?: boolean;
  onEdit: (task: RemediationTask) => void;
  onStatusChange: (taskId: string, status: string) => void;
  onProgressChange: (taskId: string, progress: number) => void;
}

export function TaskCard({
  task, isUpdating, onEdit, onStatusChange, onProgressChange,
}: TaskCardProps) {
  const [expanded, setExpanded] = useState(false);
  const isCompleted = task.status === 'completed';

  // 检查是否逾期
  const isOverdue =
    !isCompleted &&
    task.due_date &&
    new Date(task.due_date) < new Date();

  const priorityColor =
    task.priority === 'high' ? RISK_COLORS.high :
    task.priority === 'medium' ? RISK_COLORS.medium :
    RISK_COLORS.low;

  const statusInfo = STATUS_OPTIONS.find((s) => s.value === task.status) || STATUS_OPTIONS[0];

  // 状态流转
  const nextStatus = isCompleted ? 'pending'
    : task.status === 'pending' ? 'in_progress'
    : 'completed';

  return (
    <div
      className={`
        bg-white rounded-xl border p-4 transition-all duration-300
        ${expanded ? 'shadow-lg ring-1 ring-primary/20' : 'hover:shadow-md'}
        ${isOverdue ? 'border-red-300 bg-red-50/30' : isCompleted ? 'border-green-200 bg-green-50/20' : 'border-gray-200'}
      `}
      style={{ borderLeftColor: priorityColor, borderLeftWidth: 3 }}
    >
      {/* 头部 */}
      <div className="flex items-start gap-3">
        {/* 状态切换按钮 */}
        <Tooltip title={isCompleted ? '标记为待处理' : task.status === 'pending' ? '开始处理' : '标记完成'}>
          <div
            className={`mt-0.5 w-6 h-6 rounded-full border-2 flex items-center justify-center cursor-pointer shrink-0 transition-all ${
              isCompleted ? 'border-green-500 bg-green-500 hover:bg-green-600' :
              task.status === 'in_progress' ? 'border-blue-400 bg-blue-100 hover:bg-blue-200' :
              'border-gray-300 hover:border-blue-400 hover:bg-blue-50'
            }`}
            onClick={() => onStatusChange(task.id, nextStatus)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onStatusChange(task.id, nextStatus); } }}
            aria-label={isCompleted ? '标记为待处理' : task.status === 'pending' ? '开始处理' : '标记完成'}
          >
            {isCompleted && <span className="text-white text-xs font-bold">✓</span>}
            {task.status === 'in_progress' && (
              <div className="w-2.5 h-2.5 rounded-full bg-blue-500" />
            )}
          </div>
        </Tooltip>

        <div className="flex-1 min-w-0">
          {/* 标题行 */}
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <h4
              className={`text-sm font-semibold cursor-pointer hover:text-primary transition-colors ${
                isCompleted ? 'text-gray-400 line-through' : 'text-gray-800'
              }`}
              onClick={() => setExpanded(!expanded)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(!expanded); } }}
            >
              {task.title}
            </h4>
            <Tag color={statusInfo.color} className="text-[10px]">{statusInfo.label}</Tag>
            <Tag
              color={task.priority === 'high' ? 'red' : task.priority === 'medium' ? 'gold' : 'green'}
              className="text-[10px]"
            >
              {TASK_PRIORITY_LABELS[task.priority] || task.priority}
            </Tag>
            {task.source === 'compliance' && (
              <Tag color="purple" className="text-[10px]">
                <AuditOutlined className="mr-0.5" />合规校验
              </Tag>
            )}
            {task.compliance_tags && task.compliance_tags.length > 0 && task.compliance_tags.map((tag) => (
              <Tag key={tag} color="geekblue" className="text-[10px]">
                {COMPLIANCE_TAG_LABELS[tag] || tag}
              </Tag>
            ))}
            {isOverdue && (
              <Tag color="red" className="text-[10px]">已逾期</Tag>
            )}
          </div>

          {/* 描述 */}
          {expanded && task.description && (
            <p className="text-xs text-gray-500 mt-1 mb-2">{task.description}</p>
          )}

          {/* 日期信息 */}
          <div className="flex items-center gap-3 text-[10px] text-gray-400 mt-1">
            {task.due_date && (
              <Tooltip title={isOverdue ? '已超过截止日期' : '截止日期'}>
                <span className={isOverdue ? 'text-red-500 font-medium' : ''}>
                  截止：{String(task.due_date).slice(0, 10)}
                </span>
              </Tooltip>
            )}
            {task.completed_at && (
              <span>完成于：{String(task.completed_at).slice(0, 10)}</span>
            )}
          </div>

          {/* 效果反馈备注（已完成合规任务） */}
          {isCompleted && task.feedback_notes && (
            <div className="mt-2 text-xs text-purple-700 bg-purple-50 border border-purple-200 rounded-md p-2">
              <AuditOutlined className="mr-1" />
              {task.feedback_notes}
            </div>
          )}

          {/* 进度条 + 快捷按钮 */}
          {!isCompleted && (
            <div
              className="mt-3 flex items-center gap-3"
              onClick={(e) => e.stopPropagation()}
            >
              <Progress
                percent={task.progress}
                size="small"
                style={{ flex: 1 }}
                status={isUpdating ? 'active' : 'normal'}
                strokeColor={
                  task.progress >= 75 ? RISK_COLORS.low :
                  task.progress >= 40 ? RISK_COLORS.medium :
                  RISK_COLORS.high
                }
              />
              <div className="flex gap-1 shrink-0">
                {[25, 50, 75, 100].map((pct) => (
                  <Button
                    key={pct}
                    size="small"
                    type={task.progress >= pct ? 'primary' : 'default'}
                    loading={isUpdating && task.progress !== pct}
                    disabled={isUpdating}
                    onClick={() => onProgressChange(task.id, pct)}
                    style={{ minWidth: 38, fontSize: 10, padding: '0 4px' }}
                  >
                    {pct}%
                  </Button>
                ))}
              </div>
            </div>
          )}

          {/* 更新中提示条 */}
          {isUpdating && (
            <div className="mt-2 text-[10px] text-blue-500 flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
              正在保存...
            </div>
          )}
        </div>

        {/* 编辑按钮 */}
        <Tooltip title="编辑任务">
          <Button
            type="text"
            size="small"
            icon={<EditOutlined className="text-gray-400" />}
            onClick={() => onEdit(task)}
          />
        </Tooltip>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// ImprovementFeedback - 改善效果反馈
// ═══════════════════════════════════════
interface ImprovementFeedbackProps {
  initialScore: number;
  currentScore: number;
  deviationTrend: { date: string; index: number }[];
}

export function ImprovementFeedback({
  initialScore, currentScore, deviationTrend,
}: ImprovementFeedbackProps) {
  const improved = currentScore < initialScore;
  const diff = Math.abs(initialScore - currentScore);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {/* 风险评分对比 */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">整改前后风险评分对比</h3>
        <div className="flex items-center justify-around">
          {/* 整改前 */}
          <div className="text-center">
            <p className="text-xs text-gray-400 mb-2">整改前</p>
            <div
              className="w-24 h-24 rounded-full flex items-center justify-center mx-auto border-4"
              style={{ borderColor: initialScore >= 70 ? RISK_COLORS.high : initialScore >= 40 ? RISK_COLORS.medium : RISK_COLORS.low }}
            >
              <div>
                <p className="text-xl font-bold" style={{
                  color: initialScore >= 70 ? RISK_COLORS.high : initialScore >= 40 ? RISK_COLORS.medium : RISK_COLORS.low,
                }}>
                  {initialScore.toFixed(2)}
                </p>
                <p className="text-[10px] text-gray-400">/100</p>
              </div>
            </div>
            <p className="text-[10px] text-gray-400 mt-2">
              {initialScore >= 70 ? '高风险' : initialScore >= 40 ? '中风险' : '低风险'}
            </p>
          </div>

          {/* 箭头 */}
          <div className="flex flex-col items-center">
            <div className="w-12 h-0.5 bg-gray-300" />
            <span className={`text-sm font-bold ${improved ? 'text-green-500' : 'text-red-500'}`}>
              {improved ? '↓' : '↑'} {diff.toFixed(2)}
            </span>
            <div className="w-12 h-0.5 bg-gray-300" />
          </div>

          {/* 整改后 */}
          <div className="text-center">
            <p className="text-xs text-gray-400 mb-2">整改后</p>
            <div
              className="w-24 h-24 rounded-full flex items-center justify-center mx-auto border-4"
              style={{ borderColor: currentScore >= 70 ? RISK_COLORS.high : currentScore >= 40 ? RISK_COLORS.medium : RISK_COLORS.low }}
            >
              <div>
                <p className="text-xl font-bold" style={{
                  color: currentScore >= 70 ? RISK_COLORS.high : currentScore >= 40 ? RISK_COLORS.medium : RISK_COLORS.low,
                }}>
                  {currentScore.toFixed(2)}
                </p>
                <p className="text-[10px] text-gray-400">/100</p>
              </div>
            </div>
            <p className="text-[10px] text-gray-400 mt-2">
              {currentScore >= 70 ? '高风险' : currentScore >= 40 ? '中风险' : '低风险'}
            </p>
          </div>
        </div>

        <div className="mt-4 text-center">
          <Tag color={improved ? 'success' : 'error'}>
            {improved
              ? `风险评分降低 ${diff.toFixed(2)} 分，整改效果显著`
              : diff === 0 ? '风险评分无变化' : `风险评分上升 ${diff.toFixed(2)} 分，需继续整改`}
          </Tag>
        </div>
      </div>

      {/* 偏差指数趋势 */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">偏差指数变化趋势</h3>
        {deviationTrend.length > 0 ? (
          <div className="space-y-3">
            {deviationTrend.map((item, i) => {
              const prevIndex = i > 0 ? deviationTrend[i - 1].index : item.index;
              const changed = item.index !== prevIndex;
              const better = item.index < prevIndex;

              return (
                <div key={i} className="flex items-center gap-3">
                  <span className="text-xs text-gray-500 w-20">{item.date?.slice(0, 10)}</span>
                  <div className="flex-1">
                    <Progress
                      percent={item.index}
                      size="small"
                      strokeColor={item.index >= 70 ? RISK_COLORS.high : item.index >= 40 ? RISK_COLORS.medium : RISK_COLORS.low}
                      showInfo={false}
                    />
                  </div>
                  <span className="text-sm font-bold w-8 text-right" style={{
                    color: item.index >= 70 ? RISK_COLORS.high : item.index >= 40 ? RISK_COLORS.medium : RISK_COLORS.low,
                  }}>
                    {item.index.toFixed(2)}
                  </span>
                  {changed && (
                    <span className={`text-[10px] w-10 ${better ? 'text-green-500' : 'text-red-500'}`}>
                      {better ? '↓' : '↑'} {Math.abs(item.index - prevIndex).toFixed(2)}
                    </span>
                  )}
                  {!changed && <span className="w-10" />}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex items-center justify-center h-32 text-sm text-gray-400">
            暂无历史趋势数据
          </div>
        )}
      </div>
    </div>
  );
}
