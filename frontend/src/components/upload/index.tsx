/**
 * 文档上传与解析组件
 *
 * 支持上传 Excel 报表（.xlsx/.xls），自动调用后端解析引擎提取数据，
 * 运行合规校验，展示 findings 和任务建议。
 */
import { useState, useCallback } from 'react';
import { Upload, Button, Modal, Card, Tag, Space, Alert, Progress, List, Typography, Badge, Tooltip, App } from 'antd';
import {
  InboxOutlined, FileExcelOutlined,
  CheckCircleOutlined, WarningOutlined, CloseCircleOutlined,
  ReloadOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import type { UploadCheckResult, TaskSuggestion, ComplianceFinding } from '@/types';
import { uploadApi } from '@/api';
import { RISK_COLORS, RISK_LABELS } from '@/types';

const { Dragger } = Upload;
const { Text, Paragraph } = Typography;

const SEVERITY_TAG_COLORS: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'blue',
};
const SEVERITY_LABELS: Record<string, string> = {
  high: '高风险',
  medium: '中风险',
  low: '低风险',
};

interface UploadPanelProps {
  enterpriseId: string;
  enterpriseName?: string;
  visible: boolean;
  onClose: () => void;
  onTasksUpdated: () => void;
}

export default function UploadPanel({
  enterpriseId,
  enterpriseName: _enterpriseName,
  visible,
  onClose,
  onTasksUpdated,
}: UploadPanelProps) {
  const { message } = App.useApp();
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadCheckResult | null>(null);
  const [confirmingTasks, setConfirmingTasks] = useState<Set<string>>(new Set());
  const [creatingTasks, setCreatingTasks] = useState(false);

  // ── 上传文件处理 ──
  const handleUpload = useCallback(async (file: File) => {
    setUploading(true);
    setResult(null);
    try {
      const res = await uploadApi.uploadDocuments(enterpriseId, file);
      const data = res.data.data;
      if (data) {
        setResult(data);
        const total = data.findings?.total ?? 0;
        if (total === 0) {
          message.success('解析完成，未发现不合规项');
        } else {
          message.info(`解析完成，发现 ${total} 条不合规项`);
        }
      }
    } catch {
      message.error('文件上传或解析失败');
    } finally {
      setUploading(false);
    }
    return false; // 阻止 antd Upload 默认上传行为
  }, [enterpriseId, message]);

  // ── 确认完成任务 ──
  const handleConfirmComplete = useCallback(async (taskId: string) => {
    setConfirmingTasks((prev) => new Set(prev).add(taskId));
    try {
      await uploadApi.confirmTask(enterpriseId, taskId, 'complete');
      message.success('任务已标记为完成');
      onTasksUpdated();
      // 从建议列表中移除
      if (result) {
        setResult({
          ...result,
          task_suggestions: result.task_suggestions.filter((t) => t.task_id !== taskId),
        });
      }
    } catch {
      message.error('操作失败');
    } finally {
      setConfirmingTasks((prev) => {
        const next = new Set(prev);
        next.delete(taskId);
        return next;
      });
    }
  }, [enterpriseId, message, onTasksUpdated, result]);

  // ── 创建新任务 ──
  const handleCreateTasks = useCallback(async () => {
    if (!result?.new_tasks_needed?.length) return;
    setCreatingTasks(true);
    try {
      await uploadApi.confirmTask(
        enterpriseId,
        'new', // 新任务占位ID
        'create',
        result.new_tasks_needed,
      );
      message.success(`已创建合规整改任务，关联 ${result.new_tasks_needed.length} 条规则`);
      onTasksUpdated();
      setResult({ ...result, new_tasks_needed: [] });
    } catch {
      message.error('创建任务失败');
    } finally {
      setCreatingTasks(false);
    }
  }, [enterpriseId, message, onTasksUpdated, result]);

  // ── 重置 ──
  const handleReset = useCallback(() => {
    setResult(null);
  }, []);

  // ── 关闭 ──
  const handleClose = useCallback(() => {
    setResult(null);
    onClose();
  }, [onClose]);

  // ── 渲染 Findings 列表 ──
  const renderFindings = (findings: ComplianceFinding[]) => (
    <List
      dataSource={findings}
      renderItem={(f) => (
        <List.Item>
          <List.Item.Meta
            avatar={
              <Tag color={SEVERITY_TAG_COLORS[f.severity]}>
                {SEVERITY_LABELS[f.severity]}
              </Tag>
            }
            title={
              <Space>
                <Text strong>{f.title}</Text>
                <Tag>{f.category}</Tag>
                <Text type="secondary" style={{ fontSize: 12 }}>{f.rule_key}</Text>
              </Space>
            }
            description={
              <div>
                <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 4 }}>
                  {f.description}
                </Paragraph>
                <Text type="success" style={{ fontSize: 12 }}>
                  <CheckCircleOutlined /> {f.suggestion}
                </Text>
              </div>
            }
          />
        </List.Item>
      )}
      style={{ maxHeight: 300, overflow: 'auto' }}
    />
  );

  // ── 渲染任务建议 ──
  const renderTaskSuggestions = (suggestions: TaskSuggestion[]) => {
    const completable = suggestions.filter((s) => s.suggested_action === 'complete');

    if (completable.length === 0) return null;

    return (
      <Card
        title={
          <Space>
            <CheckCircleOutlined style={{ color: '#52c41a' }} />
            <span>可自动完成的任务</span>
            <Badge count={completable.length} style={{ backgroundColor: '#52c41a' }} />
          </Space>
        }
        size="small"
        style={{ marginBottom: 16 }}
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          以下任务的关联合规项在上传材料中均已验证通过，可自动标记为完成：
        </Text>
        {completable.map((s) => (
          <div
            key={s.task_id}
            style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 0', borderBottom: '1px solid #f0f0f0',
            }}
          >
            <Space direction="vertical" size={0}>
              <Text strong>{s.title}</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                关联合规项：{s.tags?.join(', ') || '无'}
              </Text>
            </Space>
            <Button
              type="primary"
              size="small"
              icon={<CheckCircleOutlined />}
              loading={confirmingTasks.has(s.task_id)}
              onClick={() => handleConfirmComplete(s.task_id)}
            >
              标记完成
            </Button>
          </div>
        ))}
      </Card>
    );
  };

  // ── 渲染新建任务建议 ──
  const renderNewTaskSuggestion = (newRules: string[]) => {
    if (newRules.length === 0) return null;

    return (
      <Card
        title={
          <Space>
            <WarningOutlined style={{ color: '#faad14' }} />
            <span>需要新建整改任务</span>
            <Badge count={newRules.length} style={{ backgroundColor: '#faad14' }} />
          </Space>
        }
        size="small"
        style={{ marginBottom: 16 }}
      >
        <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
          以下不合规项尚未关联任何整改任务，建议创建新任务进行跟踪：
        </Text>
        <Space wrap style={{ marginBottom: 12 }}>
          {newRules.map((r) => (
            <Tag key={r} color="orange">{r}</Tag>
          ))}
        </Space>
        <Button
          type="primary"
          danger
          size="small"
          icon={<ThunderboltOutlined />}
          loading={creatingTasks}
          onClick={handleCreateTasks}
        >
          一键创建整改任务
        </Button>
      </Card>
    );
  };

  return (
    <Modal
      title={
        <Space>
          <FileExcelOutlined style={{ color: '#52c41a' }} />
          <span>上传业务报表与凭证材料</span>
        </Space>
      }
      open={visible}
      onCancel={handleClose}
      footer={null}
      width={800}
      destroyOnHidden
    >
      {/* ── 上传区域 ── */}
      {!result && (
        <div style={{ padding: '16px 0' }}>
          <Alert
            message="上传说明"
            description={
              <div>
                <p>请上传包含以下 Sheet 的 Excel 文件（.xlsx/.xls）：</p>
                <ul style={{ paddingLeft: 20, marginBottom: 0 }}>
                  <li><Text code>会计凭证</Text> — 凭证号、日期、摘要、科目编码、借方/贷方金额</li>
                  <li><Text code>试算平衡表</Text> — 科目编码、期初余额、期末余额</li>
                  <li><Text code>财务报表</Text> — 资产负债表 + 利润表各项目</li>
                  <li><Text code>税务台账</Text> — 增值税、企业所得税申报数据</li>
                </ul>
              </div>
            }
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />

          <Dragger
            accept=".xlsx,.xls"
            maxCount={1}
            showUploadList={false}
            disabled={uploading}
            beforeUpload={(file) => {
              handleUpload(file);
              return false;
            }}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">
              {uploading ? '正在解析中...' : '点击或拖拽 Excel 文件到此区域'}
            </p>
            <p className="ant-upload-hint">
              支持 .xlsx / .xls 格式，文件大小不超过 10MB
            </p>
          </Dragger>

          {uploading && (
            <div style={{ textAlign: 'center', marginTop: 16 }}>
              <Progress percent={99} status="active" strokeColor="#52c41a" />
              <Text type="secondary">正在解析文件并运行合规校验...</Text>
            </div>
          )}
        </div>
      )}

      {/* ── 解析结果 ── */}
      {result && (
        <div style={{ padding: '8px 0' }}>
          {/* 解析状态 */}
          <Card size="small" style={{ marginBottom: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space>
                {result.parse_result.success ? (
                  <Tag icon={<CheckCircleOutlined />} color="success">解析成功</Tag>
                ) : (
                  <Tag icon={<CloseCircleOutlined />} color="error">解析失败</Tag>
                )}
                <Text>{result.parse_result.filename}</Text>
              </Space>

              {/* 数据摘要 */}
              {result.parse_result.success && (
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                  <Tag>凭证 {result.parse_result.data_summary.vouchers_count} 笔</Tag>
                  <Tag>科目 {result.parse_result.data_summary.trial_balance_codes} 个</Tag>
                  <Tag>BS项目 {result.parse_result.data_summary.bs_items} 项</Tag>
                  <Tag>IS项目 {result.parse_result.data_summary.inc_items} 项</Tag>
                </div>
              )}

              {/* 警告 */}
              {result.parse_result.warnings?.map((w, i) => (
                <Alert key={i} message={w} type="warning" showIcon style={{ padding: '4px 12px' }} />
              ))}
            </Space>
          </Card>

          {/* 合规校验结果摘要 */}
          {result.findings && (
            <Card
              size="small"
              title={
                <Space>
                  <span>合规校验结果</span>
                  <Badge count={result.findings.total} style={{ backgroundColor: result.findings.total > 0 ? '#ff4d4f' : '#52c41a' }} />
                </Space>
              }
              style={{ marginBottom: 16 }}
            >
              <Space wrap style={{ marginBottom: 12 }}>
                {(['high', 'medium', 'low'] as const).map((sev) => {
                  const count = result.findings.by_severity[sev];
                  if (count === 0) return null;
                  return (
                    <Tag key={sev} color={SEVERITY_TAG_COLORS[sev]}>
                      {SEVERITY_LABELS[sev]}: {count} 条
                    </Tag>
                  );
                })}
                {result.compliance_adjusted && (
                  <Tooltip title="合规调整后风险">
                    <Tag color={RISK_COLORS[result.compliance_adjusted.adjusted_level]}>
                      合规风险: {RISK_LABELS[result.compliance_adjusted.adjusted_level]}
                    </Tag>
                  </Tooltip>
                )}
              </Space>

              {renderFindings(result.findings.items)}
            </Card>
          )}

          {/* 任务操作区 */}
          <div style={{ marginBottom: 16 }}>
            {result.task_suggestions && renderTaskSuggestions(result.task_suggestions)}
            {result.new_tasks_needed && renderNewTaskSuggestion(result.new_tasks_needed)}
          </div>

          {/* 底部操作 */}
          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button icon={<ReloadOutlined />} onClick={handleReset}>
              重新上传
            </Button>
            <Button type="primary" onClick={handleClose}>
              完成
            </Button>
          </Space>
        </div>
      )}
    </Modal>
  );
}
