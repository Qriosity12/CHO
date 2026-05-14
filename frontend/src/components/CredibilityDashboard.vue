<template>
  <div class="credibility-dashboard">
    <!-- 总体可信度卡片 -->
    <div class="total-credibility-card">
      <div class="card-header">
        <span class="title">可信度总评</span>
        <span :class="['total-score', `level-${credibilityData?.total?.level}`]">
          {{ credibilityData?.total?.score != null ? credibilityData.total.score : 'N/A' }}
        </span>
      </div>
      <div class="card-body">
        <div class="action-badge" :class="`action-${credibilityData?.total?.action}`">
          {{ getActionText(credibilityData?.total?.action) }}
        </div>
        <div class="reason-text">{{ credibilityData?.total?.reason || '暂无数据' }}</div>
        
        <!-- 三部分分数展示 -->
        <div class="score-breakdown">
          <div class="score-item">
            <div class="score-label">变量级</div>
            <div class="score-bar">
              <div class="score-fill" :style="{ width: (credibilityData?.total?.variable_score || 0) * 100 + '%' }"></div>
            </div>
            <div class="score-value">{{ credibilityData?.total?.variable_score != null ? credibilityData.total.variable_score : 'N/A' }}</div>
          </div>
          <div class="score-item">
            <div class="score-label">多步预测</div>
            <div class="score-bar">
              <div class="score-fill" :style="{ width: (credibilityData?.total?.multi_step_score || 0) * 100 + '%' }"></div>
            </div>
            <div class="score-value">{{ credibilityData?.total?.multi_step_score != null ? credibilityData.total.multi_step_score : 'N/A' }}</div>
          </div>
          <div class="score-item">
            <div class="score-label">控制级</div>
            <div class="score-bar">
              <div class="score-fill" :style="{ width: (credibilityData?.total?.control_score || 0) * 100 + '%' }"></div>
            </div>
            <div class="score-value">{{ credibilityData?.total?.control_score != null ? credibilityData.total.control_score : 'N/A' }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 两个详细卡片 -->
    <div class="detail-cards">
      <!-- 多步预测可信度 -->
      <div class="detail-card">
        <div class="card-header">
          <span class="title">多步预测可信度</span>
          <span :class="['level-badge', `level-${credibilityData?.multi_step?.level}`]">
            {{ credibilityData?.multi_step?.level }}
          </span>
        </div>
        <div class="card-body">
          <div class="metric-grid">
            <div class="metric-item">
              <div class="metric-label">1步RMSE</div>
              <div class="metric-value">{{ credibilityData?.multi_step?.rmse_1_step != null ? credibilityData.multi_step.rmse_1_step : 'N/A' }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">3步RMSE</div>
              <div class="metric-value">{{ credibilityData?.multi_step?.rmse_3_step != null ? credibilityData.multi_step.rmse_3_step : 'N/A' }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">平均RMSE</div>
              <div class="metric-value">{{ credibilityData?.multi_step?.rmse_horizon != null ? credibilityData.multi_step.rmse_horizon : 'N/A' }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">误差增长率</div>
              <div class="metric-value">{{ credibilityData?.multi_step?.horizon_error_growth != null ? credibilityData.multi_step.horizon_error_growth : 'N/A' }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">关键窗口稳定性</div>
              <div class="metric-value">{{ credibilityData?.multi_step?.decision_window_stability != null ? credibilityData.multi_step.decision_window_stability : 'N/A' }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 控制级可信度 -->
      <div class="detail-card">
        <div class="card-header">
          <span class="title">控制级可信度</span>
          <span :class="['level-badge', `level-${credibilityData?.control?.level}`]">
            {{ credibilityData?.control?.level }}
          </span>
        </div>
        <div class="card-body">
          <div class="metric-grid">
            <div class="metric-item">
              <div class="metric-label">约束违反风险</div>
              <div class="metric-value" :class="getRiskClass(credibilityData?.control?.constraint_violation_risk)">
                {{ credibilityData?.control?.constraint_violation_risk != null ? credibilityData.control.constraint_violation_risk : 'N/A' }}
              </div>
            </div>
            <div class="metric-item">
              <div class="metric-label">补料变化率</div>
              <div class="metric-value">{{ credibilityData?.control?.feed_change_rate != null ? credibilityData.control.feed_change_rate : 'N/A' }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">策略稳定性</div>
              <div class="metric-value">{{ credibilityData?.control?.strategy_stability != null ? credibilityData.control.strategy_stability : 'N/A' }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  credibilityData: Object
})

const getActionText = (action) => {
  const actionMap = {
    'direct_use': '✓ 直接采用',
    'limited_use': '△ 限幅采用',
    'display_only': '⚠ 仅展示'
  }
  return actionMap[action] || action
}

const getVariableLevel = () => {
  if (!props.credibilityData?.variables) return 'N/A'
  const levels = Object.values(props.credibilityData.variables).map(v => v.level)
  const highCount = levels.filter(l => l === 'high').length
  const lowCount = levels.filter(l => l === 'low').length
  
  if (lowCount > 0) return 'low'
  if (highCount === levels.length) return 'high'
  return 'mid'
}

const r2Class = (val) => {
  const v = parseFloat(val)
  if (v >= 0.85) return 'r2-high'
  if (v >= 0.70) return 'r2-mid'
  return 'r2-low'
}

const getRiskClass = (risk) => {
  const r = parseFloat(risk)
  if (r < 0.3) return 'risk-low'
  if (r < 0.6) return 'risk-mid'
  return 'risk-high'
}
</script>

<style scoped>
.credibility-dashboard {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
}

/* 总体可信度卡片 */
.total-credibility-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.card-header .title {
  font-size: 14px;
  font-weight: 600;
}

.total-score {
  font-size: 24px;
  font-weight: 700;
  padding: 4px 12px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.2);
}

.total-score.level-high {
  background: rgba(103, 194, 58, 0.3);
  color: #67c23a;
}

.total-score.level-mid {
  background: rgba(230, 162, 60, 0.3);
  color: #e6a23c;
}

.total-score.level-low {
  background: rgba(245, 108, 108, 0.3);
  color: #f56c6c;
}

.card-body {
  padding: 16px;
}

.action-badge {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 8px;
}

.action-direct_use {
  background: #f0faf0;
  color: #67c23a;
  border: 1px solid #b7eb8f;
}

.action-limited_use {
  background: #fff8ec;
  color: #e6a23c;
  border: 1px solid #ffe58f;
}

.action-display_only {
  background: #fff2f0;
  color: #f56c6c;
  border: 1px solid #ffccc7;
}

.reason-text {
  font-size: 12px;
  color: #606266;
  margin-bottom: 12px;
  line-height: 1.5;
}

.score-breakdown {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.score-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.score-label {
  font-size: 11px;
  color: #909399;
  font-weight: 600;
}

.score-bar {
  height: 6px;
  background: #f0f0f0;
  border-radius: 3px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
  transition: width 0.3s ease;
}

.score-value {
  font-size: 12px;
  font-weight: 600;
  color: #303133;
}

/* 详细卡片 */
.detail-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 12px;
}

.detail-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.detail-card .card-header {
  background: #f5f7fa;
  color: #303133;
  padding: 10px 14px;
  border-bottom: 1px solid #f0f0f0;
}

.detail-card .card-body {
  padding: 12px;
}

.level-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
}

.level-badge.level-high {
  background: #f0faf0;
  color: #67c23a;
}

.level-badge.level-mid {
  background: #fff8ec;
  color: #e6a23c;
}

.level-badge.level-low {
  background: #fff2f0;
  color: #f56c6c;
}

/* 表格 */
.credibility-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.credibility-table thead {
  background: #f5f7fa;
}

.credibility-table th {
  padding: 6px 8px;
  text-align: left;
  font-weight: 600;
  color: #606266;
  border-bottom: 1px solid #f0f0f0;
}

.credibility-table td {
  padding: 6px 8px;
  border-bottom: 1px solid #f5f5f5;
}

.credibility-table .var-name {
  font-weight: 600;
  color: #303133;
}

.credibility-table .score-cell {
  font-weight: 600;
  color: #667eea;
}

.r2-high {
  color: #67c23a;
  font-weight: 600;
}

.r2-mid {
  color: #e6a23c;
  font-weight: 600;
}

.r2-low {
  color: #f56c6c;
  font-weight: 600;
}

/* 指标网格 */
.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
}

.metric-label {
  font-size: 11px;
  color: #909399;
  font-weight: 600;
}

.metric-value {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.risk-low {
  color: #67c23a;
}

.risk-mid {
  color: #e6a23c;
}

.risk-high {
  color: #f56c6c;
}

@media (max-width: 1200px) {
  .detail-cards {
    grid-template-columns: 1fr;
  }
}
</style>

