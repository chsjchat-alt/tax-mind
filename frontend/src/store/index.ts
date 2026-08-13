/**
 * 全局状态出口
 *
 * 按业务领域拆分为独立模块，此处统一 re-export 保持既有 import 兼容：
 *   - enterprise.ts：企业列表 / 当前选中企业 / 合规调整
 *   - risk.ts：风险扫描结果与统一视图选择器
 *   - profile.ts：心理画像结果
 *
 * 新增领域 store 时在对应模块实现，并在下方追加导出。
 */
export { useEnterpriseStore } from './enterprise';
export type { EnterpriseState } from './enterprise';
export { useRiskStore, useRiskViewState } from './risk';
export { useProfileStore } from './profile';
