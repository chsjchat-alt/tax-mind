import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useEnterpriseStore } from '@/store';
import { remediationApi, riskScanApi, complianceCheckApi, enterpriseApi } from '@/api';
import { ProgressDonut, TaskCard, ImprovementFeedback } from '@/components/remediation';
import UploadPanel from '@/components/upload';
import { LoadingSpinner, EmptyState } from '@/components/common';
import {
  Button, Modal, Form, Input, Select, DatePicker, Radio, App, Tag, Collapse, Space, Badge, Checkbox,
} from 'antd';
import { PlusOutlined, AuditOutlined, WarningOutlined, CheckCircleOutlined, InfoCircleOutlined, FileExcelOutlined } from '@ant-design/icons';
import type { RemediationTask, RemediationTaskUpdateResult, ComplianceFinding, ComplianceCheckResult, ComplianceAdjustedRisk } from '@/types';
import dayjs from 'dayjs';

const STATUS_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待处理' },
  { value: 'in_progress', label: '进行中' },
  { value: 'completed', label: '已完成' },
];

function Remediation() {
  const { message } = App.useApp();
  const { currentEnterprise } = useEnterpriseStore();

  const [tasks, setTasks] = useState<RemediationTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<RemediationTask | null>(null);
  const [form] = Form.useForm();

  // 正在提交的任务 ID 集合（用于禁用按钮 + 加载反馈）
  const [updatingTaskIds, setUpdatingTaskIds] = useState<Set<string>>(new Set());

  // 改善反馈数据
  const [initialScore, setInitialScore] = useState(0);
  const [currentScore, setCurrentScore] = useState(0);
  const [scoreTrend, setDeviationTrend] = useState<{ date: string; index: number }[]>([]);

  // ── 合规校验 ──
  const [complianceResult, setComplianceResult] = useState<ComplianceCheckResult | null>(null);
  const [complianceLoading, setComplianceLoading] = useState(false);
  const [selectedFindings, setSelectedFindings] = useState<Set<string>>(new Set());
  const [complianceChecked, setComplianceChecked] = useState(false);
  // 弹窗中是否来自合规校验（避免 render 中调用 form.getFieldValue）
  const [isComplianceSource, setIsComplianceSource] = useState(false);
  const [complianceTagsCount, setComplianceTagsCount] = useState(0);
  // 合规复验已更新反馈分数时，阻止 fetchFeedback 覆盖
  const feedbackUpdatedByCompliance = useRef(false);
  // ── 文档上传弹窗 ──
  const [uploadModalOpen, setUploadModalOpen] = useState(false);

  const enterpriseId = currentEnterprise?.id;

  // ── 加载任务列表 ──
  const fetchTasks = useCallback(() => {
    if (!enterpriseId) return;
    setLoading(true);
    remediationApi.list(enterpriseId, {
      status: statusFilter || undefined,
      limit: 50,
    })
      .then((res) => setTasks(res.data.data?.tasks || []))
      .catch(() => setTasks([]))
      .finally(() => setLoading(false));
  }, [enterpriseId, statusFilter]);

  // ── 加载改善反馈数据 ──
  const fetchFeedback = useCallback(() => {
    if (!enterpriseId) return;
    // 如果合规复验已自行更新了反馈分数，跳过风险扫描的覆盖
    if (feedbackUpdatedByCompliance.current) {
      feedbackUpdatedByCompliance.current = false;
      return;
    }
    // 整改前基准 = 风险扫描历史（最近2次）的原始分
    riskScanApi.list(enterpriseId)
      .then((res) => {
        const assessments = res.data.data?.assessments || [];
        const lastRaw = assessments[assessments.length - 1]?.overall_risk_score || 0;
        const prevRaw = assessments.length >= 2
          ? (assessments[assessments.length - 2]?.overall_risk_score || 0)
          : lastRaw;
        setInitialScore(prevRaw);
        // 整改后分 = 统一消费后端合规调整分（compute_compliance_adjusted_risk），
        // compliance 缺失时回退最新原始分，保证与"双栏展示"口径一致且刷新不漂移。
        enterpriseApi.detail(enterpriseId)
          .then((dres) => {
            const compliance = (dres.data.data as Record<string, unknown>)?.compliance as ComplianceAdjustedRisk | undefined;
            setCurrentScore(compliance?.adjusted_score ?? lastRaw);
          })
          .catch((err) => { console.error('加载合规调整分失败:', err); setCurrentScore(lastRaw); });
      })
      .catch((err) => { console.error('加载历史评估列表失败:', err); });
  }, [enterpriseId]);

  // ── 运行合规校验 ──
  const runComplianceCheck = useCallback(async () => {
    if (!enterpriseId) return;
    setComplianceLoading(true);
    try {
      const res = await complianceCheckApi.run(enterpriseId);
      setComplianceResult(res.data.data ?? null);
      setComplianceChecked(true);
    } catch {
      message.error('合规校验失败，请确认已生成财务数据');
    } finally {
      setComplianceLoading(false);
    }
  }, [enterpriseId, message]);

  useEffect(() => {
    if (!enterpriseId) {
      setTasks([]);
      setInitialScore(0);
      setCurrentScore(0);
      setDeviationTrend([]);
      return;
    }
    fetchTasks();
    fetchFeedback();
  }, [enterpriseId, statusFilter, fetchTasks, fetchFeedback]);

  // ── 按优先级排序 ──
  const sortedTasks = useMemo(() => {
    const order = { high: 0, medium: 1, low: 2 };
    return [...tasks].sort(
      (a, b) => (order[a.priority as keyof typeof order] || 2) - (order[b.priority as keyof typeof order] || 2),
    );
  }, [tasks]);

  // ── 任务统计（memo 化：tasks 变化时自动重算） ──
  const {
    totalCount, completedCount, inProgressCount, pendingCount, overdueCount,
  } = useMemo(() => {
    const now = new Date();
    const total = tasks.length;
    const completed = tasks.filter((t) => t.status === 'completed').length;
    const inProgress = tasks.filter((t) => t.status === 'in_progress').length;
    const pending = tasks.filter((t) => t.status === 'pending').length;
    const overdue = tasks.filter(
      (t) => t.status !== 'completed' && t.due_date && new Date(t.due_date) < now,
    ).length;
    return {
      totalCount: total,
      completedCount: completed,
      inProgressCount: inProgress,
      pendingCount: pending,
      overdueCount: overdue,
    };
  }, [tasks]);

  // ── 新建/编辑 ──
  const openCreateModal = (fromCompliance?: ComplianceFinding[]) => {
    setEditingTask(null);
    form.resetFields();
    setSelectedFindings(new Set());
    if (fromCompliance && fromCompliance.length > 0) {
      const tags = fromCompliance.map((f) => f.rule_key);
      setSelectedFindings(new Set(tags));
      setIsComplianceSource(true);
      setComplianceTagsCount(tags.length);
      form.setFieldsValue({
        title: `[合规整改] ${fromCompliance[0].title.slice(0, 80)}`,
        description: fromCompliance.map((f) => `【${f.severity === 'high' ? '高危' : f.severity === 'medium' ? '关注' : '提示'}】${f.suggestion}`).join('\n\n'),
        priority: fromCompliance.some((f) => f.severity === 'high') ? 'high' : 'medium',
        source: 'compliance',
        compliance_tags: tags.join(','),
      });
    } else {
      setIsComplianceSource(false);
      setComplianceTagsCount(0);
      form.setFieldsValue({ source: 'manual', compliance_tags: '' });
    }
    setModalOpen(true);
  };

  const openEditModal = (task: RemediationTask) => {
    setEditingTask(task);
    setIsComplianceSource(task.source === 'compliance');
    setComplianceTagsCount((task.compliance_tags || []).length);
    form.setFieldsValue({
      title: task.title,
      description: task.description,
      priority: task.priority,
      due_date: task.due_date ? dayjs(task.due_date) : undefined,
      source: task.source || 'manual',
      compliance_tags: (task.compliance_tags || []).join(','),
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!enterpriseId) return;
    try {
      const values = await form.validateFields();
      if (editingTask) {
        await remediationApi.update(editingTask.id, {
          title: values.title,
          description: values.description || '',
          priority: values.priority || 'medium',
        });
        message.success('任务更新成功');
      } else {
        const rawTags = values.source === 'compliance' ? (values.compliance_tags || '') : '';
        await remediationApi.create(enterpriseId, {
          title: values.title,
          description: values.description || '',
          priority: values.priority || 'medium',
          due_date: values.due_date?.format('YYYY-MM-DD'),
          source: values.source || 'manual',
          compliance_tags: values.source === 'compliance'
            ? rawTags.split(',').map((s: string) => s.trim()).filter(Boolean)
            : undefined,
        });
        message.success('任务创建成功');
      }
      setModalOpen(false);
      form.resetFields();
      fetchTasks();
    } catch (e: unknown) {
      const err = e as { errorFields?: unknown[] };
      // 表单校验错误由 antd Form 自动展示，不做额外处理
      if (err?.errorFields) return;
      // API 错误
      const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message;
      message.error(msg || '操作失败，请检查网络连接后重试');
    }
  };

  const handleStatusChange = async (taskId: string, newStatus: string) => {
    // 乐观更新：立即更新本地状态，失败时回滚
    const prevTasks = tasks;
    const targetTask = tasks.find((t) => t.id === taskId);
    setTasks((prev) =>
      prev.map((t) =>
        t.id === taskId
          ? { ...t, status: newStatus as RemediationTask['status'], completed_at: newStatus === 'completed' ? new Date().toISOString() : t.completed_at }
          : t,
      ),
    );
    setUpdatingTaskIds((prev) => new Set(prev).add(taskId));

    try {
      const res = await remediationApi.update(taskId, { status: newStatus });
      const data = res.data?.data as RemediationTaskUpdateResult | undefined;
      // 完成任务 → 后端返回前后对比数据
      if (newStatus === 'completed') {
        if (data?.comparison) {
          const { before, after } = data.comparison;
          // 双栏口径：整改前 = 原始分（original_score / 快照原始分），整改后 = 调整后分
          const beforeScore = before?.compliance_adjusted?.original_score
            ?? before?.overall_risk_score;
          const afterScore = after?.compliance_adjusted?.adjusted_score
            ?? after?.overall_risk_score;
          if (beforeScore != null) setInitialScore(beforeScore);
          if (afterScore != null) setCurrentScore(afterScore);
          if (after?.assessment_date && afterScore != null) {
            setDeviationTrend((prev) => [
              ...prev,
              { date: after.assessment_date ?? '', index: afterScore },
            ]);
          }
        }
        message.success(data?.comparison ? '任务完成，风险已重新评估' : '任务已完成');

        // ── 合规任务完成 → 触发合规复验，实现整改→反馈数据联动 ──
        if (targetTask?.source === 'compliance' && complianceChecked && complianceResult && enterpriseId) {
          const beforeCount = complianceResult.findings_count;
          try {
            const recheck = await complianceCheckApi.run(enterpriseId);
            const afterResult = recheck.data.data as ComplianceCheckResult | undefined;
            if (afterResult) {
              const afterCount = afterResult.findings_count;
              const resolved = beforeCount - afterCount;
              const feedbackMsg = resolved > 0
                ? `合规复验结果：原${beforeCount}条不合规 → 现${afterCount}条，已解决${resolved}条。`
                : `合规复验结果：仍有${afterCount}条不合规，建议继续整改。`;

              await remediationApi.update(taskId, { feedback_notes: feedbackMsg }).catch(() => {});
              setComplianceResult(afterResult);
              setSelectedFindings(new Set());

              // ── 合规复验结果驱动改善效果反馈 ──
              // 将 findings 数量变化映射为风险评分（基线 10 条 = 100 分）
              const maxBaseline = 10;
              const beforeScore = Math.min(100, Math.round(beforeCount / maxBaseline * 100));
              const afterScore = Math.min(100, Math.round(afterCount / maxBaseline * 100));
              // 如果风险重评没有提供对比数据，用合规复验数据填充
              if (!data?.comparison?.before?.overall_risk_score) {
                setInitialScore(beforeScore);
              }
              setCurrentScore(Math.min(afterScore, data?.comparison?.after?.overall_risk_score ?? afterScore));
              setDeviationTrend((prev) => [
                ...prev,
                { date: new Date().toISOString(), index: afterScore },
              ]);
              feedbackUpdatedByCompliance.current = true; // 阻止 fetchFeedback 覆盖
              message.success(
                resolved > 0
                  ? `合规复验完成：已解决 ${resolved} 条不合规问题`
                  : '合规复验完成：仍有不合规条目，请继续整改',
              );
            }
          } catch {
            // 复验失败不影响任务完成主流程
          }
        }
      }

      // ── 合规任务从已完成撤销 → 触发复验，已解决的发现重新出现 ──
      if (
        newStatus !== 'completed'
        && targetTask?.source === 'compliance'
        && targetTask.status === 'completed'
        && complianceChecked
        && complianceResult
        && enterpriseId
      ) {
        const beforeCount = complianceResult.findings_count;
        try {
          const recheck = await complianceCheckApi.run(enterpriseId);
          const afterResult = recheck.data.data as ComplianceCheckResult | undefined;
          if (afterResult) {
            const afterCount = afterResult.findings_count;
            const reverted = afterCount - beforeCount; // 重新出现的发现数
            setComplianceResult(afterResult);
            setSelectedFindings(new Set());
            // 反馈分数回升（发现增多 = 风险升高）
            const maxBaseline = 10;
            const beforeScore = Math.min(100, Math.round(beforeCount / maxBaseline * 100));
            const afterScore = Math.min(100, Math.round(afterCount / maxBaseline * 100));
            setInitialScore(beforeScore);
            setCurrentScore(afterScore);
            setDeviationTrend((prev) => [
              ...prev,
              { date: new Date().toISOString(), index: afterScore },
            ]);
            feedbackUpdatedByCompliance.current = true; // 阻止 fetchFeedback 覆盖
            message.warning(
              reverted > 0
                ? `任务已撤销，${reverted} 条不合规发现重新出现`
                : '任务已撤销',
            );
          }
        } catch {
          // 复验失败不影响状态切换
        }
      }

      // 拉取服务端最新数据确保一致性
      fetchTasks();
      fetchFeedback();
    } catch {
      // 回滚乐观更新
      setTasks(prevTasks);
      message.error('状态更新失败');
    } finally {
      setUpdatingTaskIds((prev) => {
        const next = new Set(prev);
        next.delete(taskId);
        return next;
      });
    }
  };

  const handleProgressChange = async (taskId: string, progress: number) => {
    // ── 乐观更新 + 智能状态联动 ──
    const prevTasks = tasks;
    const targetTask = tasks.find((t) => t.id === taskId);
    const willComplete = progress >= 100;

    setTasks((prev) =>
      prev.map((t) => {
        if (t.id !== taskId) return t;
        // 计算联动后的状态
        let nextStatus = t.status;
        if (willComplete) {
          nextStatus = 'completed' as RemediationTask['status'];
        } else if (progress > 0 && t.status === 'pending') {
          // 进度 > 0 且当前为待处理 → 自动转为进行中
          nextStatus = 'in_progress' as RemediationTask['status'];
        }
        return {
          ...t,
          progress,
          status: nextStatus,
          completed_at: willComplete ? new Date().toISOString() : t.completed_at,
        };
      }),
    );
    setUpdatingTaskIds((prev) => new Set(prev).add(taskId));

    try {
      const updates: { progress: number; status?: string } = { progress };
      if (progress >= 100) {
        updates.status = 'completed';
      } else {
        // 需要让后端也知道进度推进触发的 pending→in_progress 转换
        const task = tasks.find((t) => t.id === taskId);
        if (task && progress > 0 && task.status === 'pending') {
          updates.status = 'in_progress';
        }
      }
      await remediationApi.update(taskId, updates);

      // ── 合规任务完成 → 触发合规复验 ──
      if (willComplete && targetTask?.source === 'compliance' && complianceChecked && complianceResult && enterpriseId) {
        const beforeCount = complianceResult.findings_count;
        try {
          const recheck = await complianceCheckApi.run(enterpriseId);
          const afterResult = recheck.data.data as ComplianceCheckResult | undefined;
          if (afterResult) {
            const afterCount = afterResult.findings_count;
            const resolved = beforeCount - afterCount;
            const feedbackMsg = resolved > 0
              ? `合规复验结果：原${beforeCount}条不合规 → 现${afterCount}条，已解决${resolved}条。`
              : `合规复验结果：仍有${afterCount}条不合规，建议继续整改。`;
            await remediationApi.update(taskId, { feedback_notes: feedbackMsg }).catch(() => {});
            setComplianceResult(afterResult);
            setSelectedFindings(new Set());

            // ── 合规复验结果驱动改善效果反馈 ──
            const maxBaseline = 10;
            const beforeScore = Math.min(100, Math.round(beforeCount / maxBaseline * 100));
            const afterScore = Math.min(100, Math.round(afterCount / maxBaseline * 100));
            setInitialScore((prev) => prev > 0 ? prev : beforeScore);
            setCurrentScore(afterScore);
            setDeviationTrend((prev) => [
              ...prev,
              { date: new Date().toISOString(), index: afterScore },
            ]);
            feedbackUpdatedByCompliance.current = true; // 阻止 fetchFeedback 覆盖
            message.success(
              resolved > 0
                ? `合规复验完成：已解决 ${resolved} 条不合规问题`
                : '合规复验完成：仍有不合规条目，请继续整改',
            );
          }
        } catch {
          // 复验失败不影响主流程
        }
      }

      // 拉取最新数据确保联动统计与后端一致
      fetchTasks();
      fetchFeedback();
    } catch {
      // 回滚乐观更新
      setTasks(prevTasks);
      message.error('进度更新失败');
    } finally {
      setUpdatingTaskIds((prev) => {
        const next = new Set(prev);
        next.delete(taskId);
        return next;
      });
    }
  };

  // ── 无企业 ──
  if (!currentEnterprise) {
    return <EmptyState text="请先从顶部选择一家企业以查看整改追踪" />;
  }

  return (
    <div className="space-y-6">
      {/* ═══ 标题 ═══ */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">整改追踪器</h2>
          <p className="text-sm text-gray-500 mt-1">
            {currentEnterprise.name} · 整改进度 · 效果反馈
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            icon={<FileExcelOutlined />}
            onClick={() => setUploadModalOpen(true)}
            type="default"
          >
            上传报表
          </Button>
          <Button
            icon={<AuditOutlined />}
            onClick={runComplianceCheck}
            loading={complianceLoading}
          >
            合规校验
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openCreateModal()}>
            新建任务
          </Button>
        </div>
      </div>

      {/* ═══ 合规校验结果 ═══ */}
      {complianceChecked && complianceResult && (
        <ComplianceFindingsPanel
          result={complianceResult}
          selectedFindings={selectedFindings}
          onToggleAll={() => {
            if (selectedFindings.size === complianceResult.findings_count) {
              setSelectedFindings(new Set());
            } else {
              setSelectedFindings(new Set(complianceResult.findings.map((f) => f.rule_key)));
            }
          }}
          onToggle={(key) => setSelectedFindings((prev) => {
            const next = new Set(prev);
            next.has(key) ? next.delete(key) : next.add(key);
            return next;
          })}
          onCreateRemediation={() => {
            const findings = complianceResult.findings.filter((f) => selectedFindings.has(f.rule_key));
            openCreateModal(findings);
          }}
        />
      )}

      {/* ═══ 顶部：整体整改进度 ═══ */}
      {totalCount > 0 ? (
        <div className="bg-white rounded-xl border border-gray-200">
          <ProgressDonut
            total={totalCount}
            completed={completedCount}
            inProgress={inProgressCount}
            pending={pendingCount}
            overdue={overdueCount}
          />
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
          <p className="text-sm text-gray-400 mb-2">暂无整改任务</p>
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => openCreateModal()}>
            创建第一个任务
          </Button>
        </div>
      )}

      {/* ═══ 中部：任务列表 ═══ */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold text-gray-700">
            整改任务列表
            {totalCount > 0 && (
              <span className="text-xs text-gray-400 font-normal ml-2">
                共 {totalCount} 项
              </span>
            )}
          </h3>
          <Radio.Group
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            size="small"
          >
            {STATUS_OPTIONS.map((opt) => (
              <Radio.Button key={opt.value} value={opt.value}>{opt.label}</Radio.Button>
            ))}
          </Radio.Group>
        </div>

        {loading ? (
          <LoadingSpinner text="加载任务列表..." />
        ) : sortedTasks.length > 0 ? (
          <div className="space-y-3">
            {sortedTasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                isUpdating={updatingTaskIds.has(task.id)}
                onEdit={openEditModal}
                onStatusChange={handleStatusChange}
                onProgressChange={handleProgressChange}
              />
            ))}
          </div>
        ) : (
          <EmptyState text={statusFilter ? '没有符合筛选条件的任务' : '暂无整改任务'} />
        )}
      </div>

      {/* ═══ 底部：改善效果反馈 ═══ */}
      {(initialScore > 0 || currentScore > 0) && (
        <div>
          <h3 className="text-base font-semibold text-gray-700 mb-3">改善效果反馈</h3>
          <ImprovementFeedback
            initialScore={initialScore}
            currentScore={currentScore}
            scoreTrend={scoreTrend}
          />
        </div>
      )}

      {/* ═══ 新建/编辑弹窗 ═══ */}
      <Modal
        title={editingTask ? '编辑整改任务' : '新建整改任务'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => {
          setModalOpen(false);
          setEditingTask(null);
          setIsComplianceSource(false);
          setComplianceTagsCount(0);
          form.resetFields();
        }}
        okText={editingTask ? '保存更改' : '创建'}
        cancelText="取消"
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="title"
            label="任务标题"
            rules={[{ required: true, message: '请输入任务标题' }]}
          >
            <Input placeholder="如：规范私卡收款流程" maxLength={200} />
          </Form.Item>
          <Form.Item name="description" label="任务描述">
            <Input.TextArea rows={3} placeholder="描述整改任务的具体要求..." maxLength={2000} />
          </Form.Item>
          <Form.Item name="priority" label="优先级" initialValue="medium">
            <Select
              options={[
                { value: 'high', label: '高优先级 — 需立即处理' },
                { value: 'medium', label: '中优先级 — 建议尽快处理' },
                { value: 'low', label: '低优先级 — 可在有余力时处理' },
              ]}
            />
          </Form.Item>
          <Form.Item name="due_date" label="截止日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          {/* 隐藏字段：任务来源和关联合规标签 */}
          <Form.Item name="source" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="compliance_tags" hidden>
            <Input />
          </Form.Item>
          {isComplianceSource && (
            <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 mb-4">
              <div className="flex items-center gap-2 text-sm text-purple-700">
                <AuditOutlined />
                <span className="font-medium">关联合规发现</span>
                <Tag color="purple">{complianceTagsCount} 条</Tag>
              </div>
              <p className="text-xs text-purple-600 mt-1">
                此任务由合规校验自动生成，完成后将触发风险重评以验证整改效果。
              </p>
            </div>
          )}
        </Form>
      </Modal>

      {/* ═══ 文档上传弹窗 ═══ */}
      <UploadPanel
        enterpriseId={enterpriseId || ''}
        enterpriseName={currentEnterprise?.name}
        visible={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        onTasksUpdated={() => {
          fetchTasks();
          fetchFeedback();
        }}
      />
    </div>
  );
}

export default Remediation;

// ══════════════════════════════════════════════════
// ComplianceFindingsPanel — 合规校验发现面板
// ══════════════════════════════════════════════════

const SEVERITY_CONFIG: Record<string, { color: string; icon: typeof WarningOutlined; label: string }> = {
  high: { color: '#DC2626', icon: WarningOutlined, label: '高危' },
  medium: { color: '#F59E0B', icon: InfoCircleOutlined, label: '关注' },
  low: { color: '#3B82F6', icon: CheckCircleOutlined, label: '提示' },
};

const CATEGORY_LABELS: Record<string, string> = {
  tax: '税务', accounting: '会计', financial: '财务', invoice: '发票',
};

function ComplianceFindingsPanel({
  result, selectedFindings, onToggleAll, onToggle, onCreateRemediation,
}: {
  result: ComplianceCheckResult;
  selectedFindings: Set<string>;
  onToggleAll: () => void;
  onToggle: (key: string) => void;
  onCreateRemediation: () => void;
}) {
  const { findings, findings_count, by_severity, by_category } = result;
  const allSelected = selectedFindings.size === findings_count;
  const anySelected = selectedFindings.size > 0;

  return (
    <Collapse
      defaultActiveKey={['findings']}
      className="bg-white rounded-xl border border-gray-200 overflow-hidden"
      items={[{
        key: 'findings',
        label: (
          <div className="flex items-center gap-3 justify-between w-full pr-4">
            <div className="flex items-center gap-2">
              <AuditOutlined className="text-purple-600" />
              <span className="font-semibold text-gray-700">合规校验结果</span>
              <Badge count={findings_count} color="#8B5CF6" className="ml-1" />
            </div>
            <div className="flex items-center gap-3">
              <Space size={4}>
                {by_severity.high > 0 && <Tag color="red">高危 {by_severity.high}</Tag>}
                {by_severity.medium > 0 && <Tag color="orange">关注 {by_severity.medium}</Tag>}
                {by_severity.low > 0 && <Tag color="blue">提示 {by_severity.low}</Tag>}
              </Space>
              <Space size={4}>
                {Object.entries(by_category).map(([cat, n]) => (
                  <Tag key={cat} className="text-xs">{CATEGORY_LABELS[cat] || cat} {n}</Tag>
                ))}
              </Space>
            </div>
          </div>
        ),
        children: (
          <div className="space-y-3">
            {/* 工具栏 */}
            <div className="flex items-center justify-between pb-2 border-b border-gray-100">
              <Checkbox
                checked={allSelected}
                indeterminate={anySelected && !allSelected}
                onChange={onToggleAll}
              >
                <span className="text-sm text-gray-500">全选</span>
              </Checkbox>
              <Button
                size="small"
                type="primary"
                icon={<PlusOutlined />}
                disabled={!anySelected}
                onClick={onCreateRemediation}
              >
                {anySelected ? `从选中项创建整改任务 (${selectedFindings.size})` : '从选中项创建整改任务'}
              </Button>
            </div>

            {/* 发现列表 */}
            {findings.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                <CheckCircleOutlined className="text-4xl text-green-400 mb-2" />
                <p>未发现不合规条目，企业财务数据符合预设合规标准。</p>
              </div>
            ) : (
              findings.map((finding) => {
                const cfg = SEVERITY_CONFIG[finding.severity] ?? SEVERITY_CONFIG.low;
                return (
                  <div
                    key={finding.rule_key}
                    className="border border-gray-100 rounded-lg p-3 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-start gap-3">
                      <Checkbox
                        checked={selectedFindings.has(finding.rule_key)}
                        onChange={() => onToggle(finding.rule_key)}
                        className="mt-1"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Tag color={cfg.color} className="text-xs">{cfg.label}</Tag>
                          <Tag className="text-xs">{CATEGORY_LABELS[finding.category] || finding.category}</Tag>
                          <span className="text-sm font-medium text-gray-800 truncate">
                            {finding.title}
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 leading-relaxed mb-1.5">
                          {finding.description}
                        </p>
                        <div className="text-xs text-purple-600 bg-purple-50 rounded px-2 py-1">
                          <span className="font-medium">建议整改措施：</span>{finding.suggestion}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        ),
      }]}
    />
  );
}
