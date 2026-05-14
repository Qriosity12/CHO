<template>
  <div class="inspector-wrap">
    <div class="model-strip">
      <div class="strip-left">
        <span class="strip-brand">预测模型</span>
        <span class="strip-model">模型：{{ modelMeta.model }}</span>
        <span class="strip-meta">特征数：{{ modelMeta.nFeatures || allFeatures.length }}</span>
        <span class="strip-meta">{{ modelMeta.acc }}</span>
        <span class="strip-meta" :style="{ color: modelReady ? '#67c23a' : '#f59e0b' }">
          {{ modelReady ? '● 已连接真实模型' : '○ 演示模式（未训练）' }}
        </span>
        <button v-if="!modelReady" class="strip-btn reconnect-btn" @click="reconnect">⟳ 重新连接</button>
      </div>
      <div class="strip-right">
        <button class="strip-btn active">探查</button>
      </div>
    </div>

    <div class="risk-head">
      <span class="risk-title">预测风险评分</span>
      <span class="risk-current">当前值：{{ currentRisk.toFixed(4) }}</span>
    </div>
    <div class="risk-bar-wrap">
      <div class="risk-bar-bg"></div>
      <div class="risk-bar-now" :style="{ width: (currentRisk * 100).toFixed(1) + '%' }"></div>
      <div class="risk-axis">
        <span>0.0</span><span>0.2</span><span>0.4</span><span>0.6</span><span>0.8</span><span>1.0</span>
      </div>
    </div>

    <div class="inspector-header">
      <span class="insp-title">模型行为探查</span>
      <span class="insp-sub">拖动输入特征，实时观察黑盒模型预测如何响应</span>
    </div>

    <div class="inspector-body">
      <!-- 左侧：特征滑块 -->
      <div class="feature-panel">
        <div class="panel-label">初始输入特征</div>

        <div class="feature-section">
          <div class="fsec-title" style="color:#4a6cf7">状态变量</div>
          <div v-for="feat in stateFeatures" :key="feat.key" class="feat-row">
            <div class="feat-meta">
              <span class="feat-name">初始{{ feat.label }}</span>
              <span class="feat-val">{{ feat.value.toFixed(feat.decimals) }}</span>
            </div>
            <input
              type="range"
              :min="feat.min" :max="feat.max" :step="feat.step"
              v-model.number="feat.value"
              @input="onFeatureChange"
              class="feat-slider state-slider"
            />
            <div class="feat-range-labels">
              <span>{{ feat.min }}</span><span>{{ feat.max }}</span>
            </div>
          </div>
        </div>

        <div class="feature-section">
          <div class="fsec-title" style="color:#f59e0b">控制变量</div>
          <div v-for="feat in controlFeatures" :key="feat.key" class="feat-row">
            <div class="feat-meta">
              <span class="feat-name">初始{{ feat.label }}</span>
              <span class="feat-val">{{ feat.value.toFixed(feat.decimals) }}</span>
            </div>
            <input
              type="range"
              :min="feat.min" :max="feat.max" :step="feat.step"
              v-model.number="feat.value"
              @input="onFeatureChange"
              class="feat-slider control-slider"
            />
            <div class="feat-range-labels">
              <span>{{ feat.min }}</span><span>{{ feat.max }}</span>
            </div>
          </div>
        </div>

        <button class="reset-btn" @click="resetToDefault">↺ 重置默认值</button>
      </div>

      <!-- 右侧：预测输出 + 敏感度 -->
      <div class="output-panel">
        <div class="panel-label">下一步预测输出</div>
        <div class="time-explain">说明：本面板预测的是当前状态在本步补料作用下的下一时间步（即训练数据中相邻采样点之间的间隔）输出。</div>

        <div class="pdp-card">
          <div class="pdp-head">
            <span>偏依赖分析：</span>
            <div class="pdp-selectors">
              <select v-model="selectedPdpFeature" class="pdp-select" @change="renderPdpChart">
                <option v-for="f in allFeatures" :key="f.key" :value="f.key">初始{{ f.shortLabel }}</option>
              </select>
              <span class="pdp-arrow">→</span>
              <select v-model="selectedPdpTarget" class="pdp-select" @change="renderPdpChart">
                <option v-for="o in outputVars" :key="o.key" :value="o.key">预测{{ o.label }}</option>
              </select>
            </div>
          </div>
          <div class="pdp-desc">当前曲线表示：预测{{ selectedPdpTargetLabel }} 对 初始{{ selectedPdpFeatureLabel }} 的偏依赖关系（横轴是初始{{ selectedPdpFeatureLabel }}，纵轴是预测{{ selectedPdpTargetLabel }}）。</div>
          <div class="pdp-desc">不在横轴/纵轴上的所有指标：固定为当前左侧滑块的值。</div>
          <div class="pdp-desc">y 轴数字表示“模型预测的 预测{{ selectedPdpTargetLabel }} 数值”，单位与该指标本身一致（不是百分比）。</div>
          <div class="pdp-desc pdp-slope">{{ pdpSlopeExplain }}</div>
          <div ref="pdpChartRef" class="pdp-chart"></div>
        </div>

        <div class="output-cards">
          <div
            v-for="out in outputVars" :key="out.key"
            class="out-card"
            :class="{ 'flash-up': out.delta > 0.001, 'flash-dn': out.delta < -0.001 }"
          >
            <div class="out-name">预测{{ out.label }}</div>
            <div class="out-val">{{ loading ? '…' : out.predicted.toFixed(out.decimals) }}</div>
            <div class="out-delta" :class="out.delta > 0 ? 'delta-up' : out.delta < 0 ? 'delta-dn' : 'delta-zero'">
              {{ out.delta > 0 ? '▲' : out.delta < 0 ? '▼' : '—' }}
              {{ Math.abs(out.delta).toFixed(out.decimals) }}
            </div>
            <div class="out-bar-wrap">
              <div class="out-bar-fill" :style="{
                width: out.pct + '%',
                background: out.delta > 0.001 ? '#4a6cf7' : out.delta < -0.001 ? '#f56c6c' : '#c0c4cc'
              }"></div>
            </div>
          </div>
        </div>

        <!-- 敏感度矩阵 -->
        <div class="sens-section">
          <div class="panel-label" style="margin-top:12px; margin-bottom:6px">
            敏感度矩阵 — 每个特征对各输出的局部影响方向
          </div>
          <div class="sens-table-wrap">
            <table class="sens-table">
              <thead>
                <tr>
                  <th class="sens-corner">初始特征 \ 预测输出</th>
                  <th v-for="out in outputVars" :key="out.key">预测{{ out.label }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="feat in allFeatures" :key="feat.key">
                  <td class="sens-feat">初始{{ feat.shortLabel }}</td>
                  <td v-for="out in outputVars" :key="out.key" class="sens-cell">
                    <div
                      class="sens-block"
                      :style="getSensStyle(feat.key, out.key)"
                      :title="feat.label + ' → ' + out.label + ': ' + getSensVal(feat.key, out.key).toFixed(4)"
                    >
                      {{ getSensSign(feat.key, out.key) }}
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="sens-legend">
            <span class="leg-item"><span class="leg-box" style="background:#4a6cf7"></span>正相关（+ / ++）</span>
            <span class="leg-item"><span class="leg-box" style="background:#f56c6c"></span>负相关（− / −−）</span>
            <span class="leg-item"><span class="leg-box" style="background:#eee"></span>弱影响（按每个输出内相对强度判定）</span>
          </div>
        </div>

        <div class="tip-card">
          <span class="tip-icon">💡</span>
          <span class="tip-text">拖动左侧滑块改变输入，预测值与敏感度矩阵实时更新，揭示黑盒模型的内部响应规律。</span>
        </div>

        <div class="dist-card">
          <div class="report-head">
            <span class="report-title">训练集原始数据分布</span>
            <span class="dist-sub">查看各指标在训练集中的取值范围、集中区间和离散程度</span>
          </div>
          <div v-if="distributionLoading" class="report-empty">训练集分布加载中…</div>
          <div v-else-if="trainingDistribution.length === 0" class="report-empty">暂无可用训练集分布数据。</div>
          <div v-else class="dist-body">
            <div class="dist-toolbar">
              <select v-model="selectedDistFeature" class="pdp-select dist-select">
                <option v-for="item in trainingDistribution" :key="item.feature" :value="item.feature">{{ getDistributionLabel(item.feature) }}</option>
              </select>
              <div class="dist-mini-stats">
                <div v-for="stat in distributionStats" :key="stat.label" class="dist-stat-chip">
                  <span class="dist-stat-label">{{ stat.label }}</span>
                  <span class="dist-stat-value">{{ stat.value }}</span>
                </div>
              </div>
            </div>
            <div class="dist-chart-grid">
              <div class="dist-chart-card">
                <div class="dist-chart-title">频数分布直方图（{{ getDistributionLabel(selectedDistFeature) }}）</div>
                <div ref="distChartRef" class="dist-chart"></div>
              </div>
            </div>
          </div>
        </div>

        <div class="report-card">
          <div class="report-head">
            <span class="report-title">自动分析报告</span>
            <button class="strip-btn" @click="generateAnalysisReport" :disabled="reportLoading || !modelReady">
              {{ reportLoading ? '生成中…' : '重新生成' }}
            </button>
          </div>

          <div v-if="!analysisReport" class="report-empty">连接真实模型后会自动生成报告。</div>

          <div v-else class="report-body">
            <div class="report-meta">生成时间：{{ analysisReport.generatedAt }}</div>

            <div class="report-summary-box">
              <div class="report-summary-title">一句话结论</div>
              <div class="report-summary-text">{{ analysisReport.summary }}</div>
            </div>

            <div class="report-metrics">
              <span>突变点：<b>{{ analysisReport.changePointCount }}</b></span>
            </div>

            <div class="report-sec">
              <div class="report-sec-title">怎么理解指标？</div>
              <div class="report-line">• 突变点：表示某个输入轻微变化时，输出出现明显跳变，可能存在不稳定区间。</div>
            </div>

            <div class="report-sec">
              <div class="report-sec-title">“n%”这类数字是什么意思？</div>
              <div class="report-line">• {{ analysisReport.percentExplain }}</div>
              <div class="report-line">• 简单理解：在当前输入附近，改变该特征会让该输出发生约这个比例的相对变化，数值越大影响越明显。</div>
            </div>

            <div class="report-sec">
              <div class="report-sec-title">训练集原始数据分布解读</div>
              <div v-if="!analysisReport.distributionNotes || analysisReport.distributionNotes.length === 0" class="report-line">暂无可用分布解读。</div>
              <div v-for="line in analysisReport.distributionNotes" :key="line" class="report-line">• {{ line }}</div>
            </div>

            <div class="report-sec">
              <div class="report-sec-title">突变点检测</div>
              <div v-if="analysisReport.changePoints.length === 0" class="report-line">未发现显著突变点，当前输入邻域预测相对平滑。</div>
              <div v-for="cp in analysisReport.changePoints" :key="cp.id" class="report-line">
                • {{ cp.text }}
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import axios from 'axios'
import * as echarts from 'echarts'

const props = defineProps({
  trainingKey: {
    type: Number,
    default: 0,
  }
})

const stateFeatures = ref([
  { key: 'VCD',   label: '活细胞密度 VCD (×10⁶/mL)', shortLabel: '活细胞密度', value: 5.5,  min: 0,    max: 30,   step: 0.1,  decimals: 2 },
  { key: 'Glc',   label: '葡萄糖 Glc (mM)',          shortLabel: '葡萄糖',   value: 4.0,  min: 0,    max: 20,   step: 0.1,  decimals: 2 },
  { key: 'Gln',   label: '谷氨酰胺 Gln (mM)',        shortLabel: '谷氨酰胺', value: 2.5,  min: 0,    max: 10,   step: 0.05, decimals: 2 },
  { key: 'Amm',   label: '氨 Amm (mM)',              shortLabel: '氨',       value: 0.8,  min: 0,    max: 8,    step: 0.05, decimals: 2 },
  { key: 'Lac',   label: '乳酸 Lac (mM)',            shortLabel: '乳酸',     value: 4.0,  min: 0,    max: 25,   step: 0.1,  decimals: 2 },
  { key: 'Titer', label: '产量 Titer (mg/L)',        shortLabel: '产量',     value: 650,  min: 0,    max: 3000, step: 10,   decimals: 0 },
])

const controlFeatures = ref([
  { key: 'Feed_Glc',  label: '葡萄糖补料 Feed_Glc (mM)',   shortLabel: '葡萄糖补料', value: 0.30, min: 0,   max: 8,   step: 0.05, decimals: 2 },
  { key: 'Feed_Gln',  label: '谷氨酰胺补料 Feed_Gln (mM)', shortLabel: '谷氨酰胺补料', value: 0.25, min: 0,   max: 4,   step: 0.02, decimals: 2 },
  { key: 'temp',      label: '温度 (°C)',                  shortLabel: '温度',       value: 36.5, min: 34,  max: 40,  step: 0.5,  decimals: 1 },
  { key: 'pH',        label: '酸碱度 pH',                  shortLabel: '酸碱度',     value: 7.2,  min: 6.8, max: 7.6, step: 0.05, decimals: 2 },
])

const allFeatures = computed(() => [...stateFeatures.value, ...controlFeatures.value])

const outputVars = ref([
  { key: 'VCD',   label: '活细胞密度', predicted: 5.0,  baseline: 5.0,  delta: 0, pct: 30, decimals: 2 },
  { key: 'Glc',   label: '葡萄糖',     predicted: 5.0,  baseline: 5.0,  delta: 0, pct: 25, decimals: 2 },
  { key: 'Gln',   label: '谷氨酰胺',   predicted: 2.0,  baseline: 2.0,  delta: 0, pct: 20, decimals: 2 },
  { key: 'Amm',   label: '氨',         predicted: 1.0,  baseline: 1.0,  delta: 0, pct: 12, decimals: 2 },
  { key: 'Lac',   label: '乳酸',       predicted: 5.0,  baseline: 5.0,  delta: 0, pct: 20, decimals: 2 },
  { key: 'Titer', label: '产量',       predicted: 500,  baseline: 500,  delta: 0, pct: 17, decimals: 2 },
])

const distributionLoading = ref(false)
const trainingDistribution = ref([])
const selectedDistFeature = ref('VCD')
const distChartRef = ref(null)
const distributionLabelMap = {
  VCD: '活细胞密度 VCD',
  Glc: '葡萄糖 Glc',
  Gln: '谷氨酰胺 Gln',
  Amm: '氨 Amm',
  Lac: '乳酸 Lac',
  Titer: '产量 Titer',
  Feed_Glc: '葡萄糖补料 Feed_Glc',
  Feed_Gln: '谷氨酰胺补料 Feed_Gln',
  temp: '温度 temp',
  pH: '酸碱度 pH',
}
const hiddenDistributionKeys = ['DCD', 'Lysed', 'Stir', 'DO', 'Feed_BRvol', 'Cumulative-Feed_Glc', 'Cumulative-Feed_Gln', 'Cumulative_Feed_Glc', 'Cumulative_Feed_Gln']

const sensitivityMatrix = ref({})
const loading = ref(false)
const pdpChartRef = ref(null)
const selectedPdpFeature = ref('Glc')
const selectedPdpTarget = ref('VCD')
const pdpSlopeExplain = ref('')
const selectedDistFeatureData = computed(() => trainingDistribution.value.find(i => i.feature === selectedDistFeature.value) || null)
const getDistributionLabel = (feature) => distributionLabelMap[feature] || feature
const distributionStats = computed(() => {
  const item = selectedDistFeatureData.value
  if (!item) return []
  return [
    { label: '样本数', value: item.count },
    { label: '最小观测值', value: item.min },
    { label: '中位数', value: item.median },
    { label: '最大观测值', value: item.max },
    { label: '平均值', value: item.mean },
  ]
})
const selectedPdpFeatureLabel = computed(() => allFeatures.value.find(f => f.key === selectedPdpFeature.value)?.shortLabel || selectedPdpFeature.value)
const selectedPdpTargetLabel = computed(() => outputVars.value.find(o => o.key === selectedPdpTarget.value)?.label || selectedPdpTarget.value)
const currentRisk = ref(0.42)
const reportLoading = ref(false)
const analysisReport = ref(null)
const modelMeta = ref({ model: '—', acc: '—', auc: '—', nFeatures: 0 })
const modelReady = ref(false)
const modelStateColumns = ref([])
const modelInputColumns = ref([])
const hiddenFeatureKeys = ['DCD', 'Lysed', 'Feed_BRvol', 'DO', 'Stir']

// 从后端加载真实元信息
const loadInspectorMeta = async () => {
  try {
    const resp = await axios.get('/api/inspector-meta', { timeout: 5000 })
    if (resp.data.success) {
      const d = resp.data
      const modelTypeMap = { rf: '随机森林', nn: '神经网络', gp: '高斯过程' }
      modelMeta.value = {
        model: modelTypeMap[d.model_type] || d.model_type,
        acc: d.avg_r2 !== null ? `R²=${d.avg_r2}` : '—',
        auc: d.avg_r2 !== null ? `R²=${d.avg_r2}` : '—',
        nFeatures: d.n_features || 0
      }
      modelStateColumns.value = d.state_columns || []
      modelInputColumns.value = d.input_columns || []

      const requiredInputKeys = ['VCD', 'Glc', 'Gln', 'Amm', 'Lac', 'Titer', 'Feed_Glc', 'Feed_Gln', 'temp', 'pH']
      const hasRequiredInputs = requiredInputKeys.every(k => (d.input_columns || []).includes(k))
      const hasStateOutputs = (d.state_columns || []).includes('Titer')
      const hasR2 = d.avg_r2 !== null && d.avg_r2 !== undefined
      const hasSessionTrain = d.trained_in_session === undefined ? true : d.trained_in_session === true

      // 额外做一次真实预测探针，避免仅有历史results但模型文件不可用时误判“已连接”
      let probeOk = false
      try {
        const probeResp = await axios.post('/api/predict-next-state', {
          VCD: 5.0, Glc: 5.0, Gln: 2.0, Amm: 1.0, Lac: 5.0, Titer: 500.0,
          DCD: 0.1, Lysed: 0.01,
          Feed_Glc: 0.5, Feed_Gln: 0.2, Feed_BRvol: 0.0,
          temp: 37.0, pH: 7.2, DO: 50.0, Stir: 100.0
        }, { timeout: 5000 })
        probeOk = !!(probeResp.data?.success && probeResp.data?.prediction)
      } catch (_) {
        probeOk = false
      }

      modelReady.value = hasRequiredInputs && hasStateOutputs && hasR2 && probeOk

      // 如果后端返回的状态列，更新 outputVars 与 stateFeatures 显示
      if (d.state_columns && d.state_columns.length) {
        outputVars.value = d.state_columns
          .filter(key => !hiddenFeatureKeys.includes(key))
          .map(key => {
            const existing = outputVars.value.find(o => o.key === key)
            return existing || { key, label: key, predicted: 0, baseline: 0, delta: 0, pct: 10, decimals: 3 }
          })
      }
      return modelReady.value
    }
  } catch (_) {
    // 后端未训练时静默降级
    modelReady.value = false
  }
  return false
}

// 自动轮询，直到后端就绪
const startPolling = () => {
  let attempts = 0
  const maxAttempts = 20
  const timer = setInterval(async () => {
    attempts++
    const ok = await loadInspectorMeta()
    if (ok || attempts >= maxAttempts) {
      clearInterval(timer)
      if (ok) {
        await runPrediction()
        outputVars.value.forEach(out => { out.baseline = out.predicted; out.delta = 0 })
        await nextTick(() => { renderPdpChart() })
        scheduleDeepAnalysis(120)
      }
    }
  }, 3000)
}

const outMax = { VCD: 30, Glc: 20, Gln: 10, Amm: 8, Lac: 25, Titer: 3000, DCD: 10, Lysed: 0.5 }

const defaults = {
  VCD: 5.5, Glc: 4.0, Gln: 2.5, Amm: 0.8, Lac: 4.0, Titer: 650, DCD: 0.1, Lysed: 0.01,
  Feed_Glc: 0.30, Feed_Gln: 0.25, Feed_BRvol: 0.0, temp: 36.5, pH: 7.2, DO: 50, Stir: 100
}

const applyDistributionRanges = () => {
  trainingDistribution.value.forEach(item => {
    const feat = allFeatures.value.find(f => f.key === item.feature)
    if (!feat) return

    const minVal = Number(item.min)
    const maxVal = Number(item.max)
    if (!Number.isFinite(minVal) || !Number.isFinite(maxVal) || maxVal <= minVal) return

    feat.min = Number(minVal.toFixed(feat.decimals))
    feat.max = Number(maxVal.toFixed(feat.decimals))

    if (feat.value < feat.min) feat.value = feat.min
    if (feat.value > feat.max) feat.value = feat.max
    defaults[feat.key] = feat.value
  })
}

const applyInitialSnapshot = (state0 = {}, control0 = {}) => {
  const applyOne = (f, v) => {
    if (typeof v !== 'number' || !Number.isFinite(v)) return

    // 若结果分析初始值逼近或超过上限，动态放大滑条范围，避免“初始就在最右边”
    if (v >= f.max * 0.9) {
      const expandedMax = Math.ceil((v * 1.3) / f.step) * f.step
      f.max = Number(expandedMax.toFixed(f.decimals))
    }

    if (v <= f.min) {
      const expandedMin = Math.floor((v * 0.9) / f.step) * f.step
      f.min = Number(expandedMin.toFixed(f.decimals))
    }

    const adjusted = Math.min(f.max, Math.max(f.min, v))
    f.value = adjusted
    defaults[f.key] = adjusted
  }

  stateFeatures.value.forEach(f => applyOne(f, state0[f.key]))
  controlFeatures.value.forEach(f => applyOne(f, control0[f.key]))
}

const loadInitialFromResultAnalysis = async () => {
  try {
    const resp = await axios.get('/api/trajectories', { timeout: 5000 })
    const state0 = resp.data?.state_trajectory?.[0]
    const control0 = resp.data?.control_trajectory?.[0]
    if (resp.data?.success && state0) {
      applyInitialSnapshot(state0, control0 || {})
      return true
    }
  } catch (_) {
    // 无轨迹时保持默认值
  }
  return false
}

const resetToDefault = () => {
  stateFeatures.value.forEach(f => { f.value = defaults[f.key] })
  controlFeatures.value.forEach(f => { f.value = defaults[f.key] })
  onFeatureChange()
}

const buildInput = (overrides = {}) => {
  const inp = {}
  allFeatures.value.forEach(f => { inp[f.key] = f.value })
  return { ...inp, ...overrides }
}

// 移除物理规则模拟代码

const predict = async (inputObj, timeout = 30000) => {
  const resp = await axios.post('/api/predict-next-state', inputObj, { timeout })
  if (!resp.data.success || !resp.data.prediction) {
    throw new Error('预测接口返回无效结果')
  }
  return resp.data.prediction
}

const runTasksInBatches = async (taskFactories, batchSize = 2) => {
  const results = []
  for (let i = 0; i < taskFactories.length; i += batchSize) {
    const batch = taskFactories.slice(i, i + batchSize).map(task => task())
    results.push(...await Promise.all(batch))
  }
  return results
}

const runPrediction = async () => {
  loading.value = true
  try {
    const result = await predict(buildInput())
    outputVars.value.forEach(out => {
      const newVal = result[out.key] ?? out.predicted
      out.delta = newVal - out.baseline
      out.predicted = newVal
      out.pct = Math.min(100, Math.max(2, (newVal / (outMax[out.key] || 100)) * 100))
    })

    const glc = stateFeatures.value.find(f => f.key === 'Glc')?.value || 0
    const lac = stateFeatures.value.find(f => f.key === 'Lac')?.value || 0
    const amm = stateFeatures.value.find(f => f.key === 'Amm')?.value || 0
    const pH = controlFeatures.value.find(f => f.key === 'pH')?.value || 7.2
    let risk = 0.25 + 0.015 * lac + 0.03 * amm - 0.01 * glc + Math.abs(pH - 7.2) * 0.5
    currentRisk.value = Math.max(0, Math.min(1, risk))

    if (outputVars.value[0].baseline === defaults[outputVars.value[0].key]) {
      outputVars.value.forEach(out => { out.baseline = out.predicted; out.delta = 0 })
    }
    return true
  } catch (err) {
    modelReady.value = false
    console.error('预测失败：', err)
    return false
  } finally {
    loading.value = false
  }
}

const computeSensitivity = async () => {
  const mat = {}

  for (const feat of allFeatures.value) {
    mat[feat.key] = {}
    const range = feat.max - feat.min

    // 多尺度扰动，避免随机森林在局部“平原”导致全是无影响
    const scales = [0.12, 0.3].map(s => Math.max(range * s, feat.step))

    for (const out of outputVars.value) {
      mat[feat.key][out.key] = 0
    }

    for (const delta of scales) {
      const plusVal = Math.min(feat.max, feat.value + delta)
      const minusVal = Math.max(feat.min, feat.value - delta)
      const actualDelta = plusVal - minusVal
      if (actualDelta <= 0) continue

      try {
        const [resPlus, resMinus] = await runTasksInBatches([
          () => predict(buildInput({ [feat.key]: plusVal })),
          () => predict(buildInput({ [feat.key]: minusVal }))
        ], 2)

        for (const out of outputVars.value) {
          const up = resPlus[out.key] ?? 0
          const dn = resMinus[out.key] ?? 0
          const val = (up - dn) / actualDelta
          if (Math.abs(val) > Math.abs(mat[feat.key][out.key])) {
            mat[feat.key][out.key] = val
          }
        }
      } catch (err) {
        console.error(`敏感度计算失败：${feat.key}`, err)
      }
    }
  }

  sensitivityMatrix.value = mat
}

const getSensMaxAbs = () => {
  let maxAbs = 0
  for (const fk of Object.keys(sensitivityMatrix.value || {})) {
    for (const ok of Object.keys(sensitivityMatrix.value[fk] || {})) {
      maxAbs = Math.max(maxAbs, Math.abs(sensitivityMatrix.value[fk][ok] || 0))
    }
  }
  return maxAbs
}

const getOutputSensMaxAbs = (ok) => {
  let maxAbs = 0
  for (const fk of Object.keys(sensitivityMatrix.value || {})) {
    maxAbs = Math.max(maxAbs, Math.abs(sensitivityMatrix.value[fk]?.[ok] || 0))
  }
  return Math.max(maxAbs, 1e-6)
}

const getSensVal = (fk, ok) => sensitivityMatrix.value[fk]?.[ok] ?? 0
const getSensNorm = (fk, ok) => Math.abs(getSensVal(fk, ok)) / getOutputSensMaxAbs(ok)

const getSensSign = (fk, ok) => {
  const v = getSensVal(fk, ok)
  const n = getSensNorm(fk, ok)
  if (n < 0.06) return ''
  if (v > 0) return n > 0.45 ? '++' : '+'
  return n > 0.45 ? '−−' : '−'
}

const getSensStyle = (fk, ok) => {
  const v = getSensVal(fk, ok)
  const intensity = getSensNorm(fk, ok)
  if (intensity < 0.06) return { background: '#f0f0f0', color: '#ccc' }
  const color = v > 0 ? `rgba(74,108,247,${0.18 + intensity * 0.75})` : `rgba(245,108,108,${0.18 + intensity * 0.75})`
  const textColor = intensity > 0.45 ? '#fff' : v > 0 ? '#4a6cf7' : '#f56c6c'
  return { background: color, color: textColor, fontWeight: intensity > 0.25 ? '700' : '500' }
}

const generateAnalysisReport = async () => {
  if (!modelReady.value) return
  reportLoading.value = true
  try {
    const baselineInput = buildInput()
    const baselinePred = await predict(baselineInput)

    const effectList = []
    for (const feat of allFeatures.value) {
      const range = feat.max - feat.min
      const step = Math.max(range * 0.08, feat.step)
      const plusVal = Math.min(feat.max, feat.value + step)
      const minusVal = Math.max(feat.min, feat.value - step)
      const [plusPred, minusPred] = await runTasksInBatches([
        () => predict(buildInput({ [feat.key]: plusVal }), 30000),
        () => predict(buildInput({ [feat.key]: minusVal }), 30000)
      ], 2)

      for (const out of outputVars.value) {
        const p = plusPred[out.key] ?? 0
        const m = minusPred[out.key] ?? 0
        const b = baselinePred[out.key] ?? 0
        const outRange = outMax[out.key] || 1
        // 防止基线接近0时相对变化被无限放大
        const relAmp = Math.abs(p - m) / (Math.abs(b) + outRange * 0.05 + 1e-6)
        const signedRel = (p - m) / (Math.abs(b) + outRange * 0.05 + 1e-6)
        effectList.push({
          feat: feat.shortLabel,
          featKey: feat.key,
          out: out.label,
          outKey: out.key,
          relAmp,
          signedRel,
          p,
          m,
          b,
          currentVal: feat.value,
          minusVal,
          plusVal,
          step,
          decimals: feat.decimals
        })
      }
    }

    const relName = (featName, outName) => `初始${featName} → 预测${outName}`

    const sortedEffects = effectList.slice().sort((a, b) => b.relAmp - a.relAmp)
    const topEffects = sortedEffects.filter(i => i.featKey !== i.outKey).slice(0, 6)

    const ampValues = sortedEffects.map(i => i.relAmp)
    const meanAmp = ampValues.length ? ampValues.reduce((s, v) => s + v, 0) / ampValues.length : 0
    const stdAmp = ampValues.length
      ? Math.sqrt(ampValues.reduce((s, v) => s + (v - meanAmp) ** 2, 0) / ampValues.length)
      : 0
    const threshold = meanAmp + stdAmp * 1.2

    const changePoints = sortedEffects
      .filter(i => i.featKey !== i.outKey)
      .filter(i => i.relAmp > threshold)
      .slice(0, 8)
      .map((i, idx) => {
        const direction = i.signedRel >= 0 ? '上升' : '下降'
        return {
          id: `${i.feat}-${i.out}-${idx}`,
          text: `${relName(i.feat, i.out)} 出现突变：当初始${i.feat}在本次检测中从 ${Number(i.minusVal).toFixed(i.decimals)} 提高到 ${Number(i.plusVal).toFixed(i.decimals)} 时，预测${i.out}倾向${direction}，相对变化幅度约 ${(i.relAmp * 100).toFixed(1)}%。`
        }
      })

    let signConsistent = 0
    for (const feat of allFeatures.value) {
      const vals = outputVars.value.map(o => getSensVal(feat.key, o.key))
      const maxAbs = vals.reduce((m, v) => Math.max(m, Math.abs(v)), 0)
      if (maxAbs < 1e-6) {
        // 全接近0时视为中性一致，不判为不一致
        signConsistent += 0.5
        continue
      }
      const effVals = vals.filter(v => Math.abs(v) >= maxAbs * 0.15)
      if (effVals.length <= 1) {
        signConsistent += 1
      } else {
        const signs = effVals.map(v => Math.sign(v))
        const same = signs.every(v => v === signs[0])
        signConsistent += same ? 1 : 0.4
      }
    }
    const explainConsistency = allFeatures.value.length ? signConsistent / allFeatures.value.length : 0

    const jumpPenalty = Math.min(1, changePoints.length / 8)
    const credibility = Math.max(0.05, Math.min(0.98, 0.6 * explainConsistency + 0.4 * (1 - jumpPenalty)))
    const credibilityLevel = credibility >= 0.75 ? '高' : credibility >= 0.5 ? '中' : '低'

    const feedGlcFeat = controlFeatures.value.find(f => f.key === 'Feed_Glc')
    const feedGlnFeat = controlFeatures.value.find(f => f.key === 'Feed_Gln')
    const glcStep = feedGlcFeat ? Math.max(feedGlcFeat.step, (feedGlcFeat.max - feedGlcFeat.min) * 0.03) : 0.05
    const glnStep = feedGlnFeat ? Math.max(feedGlnFeat.step, (feedGlnFeat.max - feedGlnFeat.min) * 0.03) : 0.02

    const findEffect = (featKey, outKey) => effectList.find(i => i.featKey === featKey && i.outKey === outKey)
    const fmtPct = (v) => {
      if (!Number.isFinite(v) || v <= 0) return '0.0'
      if (v < 0.1) return '<0.1'
      return v.toFixed(1)
    }

    const glcTiterEff = findEffect('Feed_Glc', 'Titer')
    const glnTiterEff = findEffect('Feed_Gln', 'Titer')
    const glcLacEff = findEffect('Feed_Glc', 'Lac')
    const glnAmmEff = findEffect('Feed_Gln', 'Amm')

    const glcTiterPct = Math.abs((glcTiterEff?.signedRel || 0) * 100)
    const glnTiterPct = Math.abs((glnTiterEff?.signedRel || 0) * 100)
    const glcLacPct = Math.abs((glcLacEff?.signedRel || 0) * 100)
    const glnAmmPct = Math.abs((glnAmmEff?.signedRel || 0) * 100)

    const glcToTiter = glcTiterEff?.signedRel || 0
    const glnToTiter = glnTiterEff?.signedRel || 0
    const preferredFeed = Math.abs(glcToTiter) >= Math.abs(glnToTiter) ? 'Feed_Glc' : 'Feed_Gln'
    const preferredDirection = preferredFeed === 'Feed_Glc'
      ? (glcToTiter >= 0 ? '上调' : '下调')
      : (glnToTiter >= 0 ? '上调' : '下调')

    const summary = changePoints.length === 0
      ? `围绕“补料提产”目标，当前输入邻域较平稳；优先对 ${preferredFeed} 做小步${preferredDirection}，再观察产量与副产物联动。`
      : `围绕“补料提产”目标，检测到 ${changePoints.length} 个突变点；补料建议采用更小步长并分段试探，避免跨入跳变区。`

    const beginnerAdvice = []
    const weakFeedSignal = Math.max(glcTiterPct, glnTiterPct, glcLacPct, glnAmmPct) < 0.1

    if (changePoints.length > 0) {
      if (weakFeedSignal) {
        beginnerAdvice.push(`当前虽检测到 ${changePoints.length} 个突变点，但这些突变主要来自其他特征通道；在当前工作点 Feed_Glc / Feed_Gln 的局部响应很弱，不建议直接靠补料通道做主调。`)
      } else {
        beginnerAdvice.push(`当前检测到 ${changePoints.length} 个突变点，优先在“突变较少”的区间内调节补料；本轮先用 ${preferredFeed} 做小步试探（建议步长 ${preferredFeed === 'Feed_Glc' ? glcStep.toFixed(2) : glnStep.toFixed(2)}）。`)
      }
    } else {
      if (weakFeedSignal) {
        beginnerAdvice.push('当前邻域整体平滑，但 Feed_Glc / Feed_Gln 在此点几乎不驱动输出变化，建议先调整到更敏感区间再优化补料。')
      } else {
        beginnerAdvice.push(`当前邻域较平滑，可优先按 ${preferredFeed} 的建议方向（${preferredDirection}）推进，并在每一步后复核预测是否保持同方向。`)
      }
    }

    if (weakFeedSignal) {
      beginnerAdvice.push('当前工作点对 Feed_Glc / Feed_Gln 的局部响应很弱，先微调 Glc/Gln/温度/pH 或切换到训练样本更密集区，再做补料优化。')
    } else if (Math.abs(glcToTiter) > Math.abs(glnToTiter) * 1.2) {
      beginnerAdvice.push(`当前“葡萄糖补料→产量”通道更强（约 ${fmtPct(glcTiterPct)}%/步），建议先以 Feed_Glc 为主，Feed_Gln 作为微调。`)
    } else if (Math.abs(glnToTiter) > Math.abs(glcToTiter) * 1.2) {
      beginnerAdvice.push(`当前“谷氨酰胺补料→产量”通道更强（约 ${fmtPct(glnTiterPct)}%/步），建议先以 Feed_Gln 为主，Feed_Glc 作为微调。`)
    } else {
      beginnerAdvice.push(`当前两条补料通道都有效（Glc 约 ${fmtPct(glcTiterPct)}%/步，Gln 约 ${fmtPct(glnTiterPct)}%/步），建议按副产物约束选择主通道后逐步放量。`)
    }

    if (!weakFeedSignal) {
      if (Math.max(glcLacPct, glnAmmPct) >= 0.8 * Math.max(glcTiterPct, glnTiterPct)) {
        beginnerAdvice.push(`副产物压力偏高：Feed_Glc→乳酸约 ${fmtPct(glcLacPct)}%/步，Feed_Gln→氨约 ${fmtPct(glnAmmPct)}%/步；若乳酸/氨连续上升，下一步优先减半步长。`)
      } else {
        beginnerAdvice.push(`当前副产物代价相对可控，可维持当前步长推进；若出现乳酸或氨异常抬升，再切换到保守步长。`)
      }
    }

    if (credibility < 0.5) {
      beginnerAdvice.push(`当前可信度 ${credibility.toFixed(3)} 偏低，建议每次只改一个补料变量，并用 1~2 步结果确认方向后再放量。`)
    } else {
      beginnerAdvice.push(`当前可信度 ${credibility.toFixed(3)} 可用，建议“先小步验证方向，再逐步放量”，并持续监控敏感度方向是否发生反转。`)
    }

    const stepHint = `步长=每次调节变量时单次改动量；当前建议以 ${preferredFeed} 为主，单步约 ${preferredFeed === 'Feed_Glc' ? glcStep.toFixed(2) : glnStep.toFixed(2)}。若乳酸/氨连续上升则步长减半（${preferredFeed === 'Feed_Glc' ? (glcStep / 2).toFixed(2) : (glnStep / 2).toFixed(2)}），若连续 2~3 步方向稳定可小幅放大到约 ${preferredFeed === 'Feed_Glc' ? Math.min(feedGlcFeat?.max || glcStep * 2, glcStep * 1.5).toFixed(2) : Math.min(feedGlnFeat?.max || glnStep * 2, glnStep * 1.5).toFixed(2)}。`

    const topExample = topEffects[0]
    const percentExplain = topExample
      ? `例如“${(topExample.relAmp * 100).toFixed(1)}%”表示：在当前点附近，当“初始${topExample.feat}”按报告设定的小范围扰动时，“预测${topExample.out}”的变化幅度约为其当前基线的 ${(topExample.relAmp * 100).toFixed(1)}%。`
      : '该百分比表示某输入特征在当前点附近扰动后，目标输出相对其当前基线的变化幅度。'

    const distributionNotes = []
    if (trainingDistribution.value.length > 0) {
      const currentMap = Object.fromEntries(allFeatures.value.map(f => [f.key, f.value]))
      const nearBoundaryItems = []
      const sparseSideItems = []

      for (const item of trainingDistribution.value) {
        const currentVal = currentMap[item.feature]
        if (!Number.isFinite(currentVal)) continue

        const min = Number(item.min)
        const max = Number(item.max)
        const median = Number(item.median)
        if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) continue

        const span = max - min
        const pos = (currentVal - min) / span
        const label = getDistributionLabel(item.feature)

        if (pos <= 0.1 || pos >= 0.9) {
          nearBoundaryItems.push(`${label} 当前值 ${Number(currentVal).toFixed(2)} 已接近训练集边界区间（范围 ${min} ~ ${max}），解释该变量相关预测时应更谨慎。`)
        }

        const histCounts = item.histogram?.counts || []
        const histEdges = item.histogram?.edges || []
        if (histCounts.length > 0 && histEdges.length === histCounts.length + 1) {
          let bucketIdx = histCounts.length - 1
          for (let i = 0; i < histCounts.length; i++) {
            const left = Number(histEdges[i])
            const right = Number(histEdges[i + 1])
            const isLast = i === histCounts.length - 1
            if ((currentVal >= left && currentVal < right) || (isLast && currentVal <= right)) {
              bucketIdx = i
              break
            }
          }
          const maxCount = Math.max(...histCounts, 0)
          const curCount = histCounts[bucketIdx] || 0
          if (maxCount > 0 && curCount <= maxCount * 0.2) {
            sparseSideItems.push(`${label} 当前值所在区间样本相对较少，模型在这一数值附近的经验支撑弱于高频样本区。`)
          }
        }
      }

      distributionNotes.push(...nearBoundaryItems.slice(0, 2))
      distributionNotes.push(...sparseSideItems.slice(0, 2))

      if (distributionNotes.length === 0) {
        distributionNotes.push('当前各主要输入大多位于训练集较常见区间内，模型对这些数值附近的响应通常更容易与历史样本保持一致。')
      }
    }

    analysisReport.value = {
      generatedAt: new Date().toLocaleString(),
      credibility,
      credibilityLevel,
      changePointCount: changePoints.length,
      explainConsistency,
      summary,
      beginnerAdvice,
      stepHint,
      percentExplain,
      distributionNotes,
      relations: topEffects.map(i => `${relName(i.feat, i.out)}：当初始${i.feat}提高时，预测${i.out}${i.signedRel >= 0 ? '倾向上升' : '倾向下降'}（相对变化幅度 ${(i.relAmp * 100).toFixed(1)}%）`),
      changePoints,
    }
  } catch (err) {
    console.error('生成分析报告失败：', err)
    analysisReport.value = null
  } finally {
    reportLoading.value = false
  }
}

const renderPdpChart = async () => {
  if (!pdpChartRef.value) return
  const chart = echarts.getInstanceByDom(pdpChartRef.value) || echarts.init(pdpChartRef.value)

  const feat = allFeatures.value.find(f => f.key === selectedPdpFeature.value)
  if (!feat) return

  const samples = 20
  const tasks = []
  
  // 分批生成采样点预测，避免一次性并发过多导致超时
  for (let i = 0; i < samples; i++) {
    const v = feat.min + (feat.max - feat.min) * i / (samples - 1)
    tasks.push(async () => {
      const pred = await predict(buildInput({ [feat.key]: v }), 30000)
      return { x: Number(v.toFixed(3)), y: Number((pred[selectedPdpTarget.value] ?? 0).toFixed(4)) }
    })
  }

  const points = await runTasksInBatches(tasks, 4)
  const xs = points.map(p => p.x)
  const ys = points.map(p => p.y)

  const segSpan = Math.max((feat.max - feat.min) * 0.1, feat.step * 4)
  const leftBound = Math.max(feat.min, feat.value - segSpan)
  const rightBound = Math.min(feat.max, feat.value + segSpan)
  const leftPred = await predict(buildInput({ [feat.key]: leftBound }), 30000)
  const rightPred = await predict(buildInput({ [feat.key]: rightBound }), 30000)
  const yLeft = Number(leftPred[selectedPdpTarget.value] ?? 0)
  const yRight = Number(rightPred[selectedPdpTarget.value] ?? 0)
  const dx = rightBound - leftBound
  const slope = dx > 0 ? (yRight - yLeft) / dx : 0
  const direction = slope > 1e-8 ? '上升' : slope < -1e-8 ? '下降' : '基本不变'
  const xFmt = (v) => Number(v).toFixed(feat.decimals)
  pdpSlopeExplain.value = `当前区间：初始${selectedPdpFeatureLabel.value} ∈ [${xFmt(leftBound)}, ${xFmt(rightBound)}]。在该区间内，初始${selectedPdpFeatureLabel.value} 每增加 1 单位，预测${selectedPdpTargetLabel.value}约${direction} ${Math.abs(slope).toFixed(4)}。`

  chart.setOption({
    animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: 45, right: 20, top: 24, bottom: 30 },
    xAxis: { type: 'category', data: xs, axisLabel: { fontSize: 10 } },
    yAxis: {
      type: 'value',
      scale: true, // 开启 y 轴自动缩放，放大微小波动
      axisLabel: { fontSize: 10, formatter: (v) => v.toFixed(2) }
    },
    series: [{
      type: 'line',
      data: ys,
      smooth: true,
      symbol: 'circle',
      symbolSize: 4,
      lineStyle: { width: 2, color: '#4a6cf7' },
      itemStyle: { color: '#4a6cf7' },
      markLine: {
        symbol: 'none',
        lineStyle: { color: '#f56c6c', type: 'dashed', width: 1 },
        data: [{ yAxis: Number((outputVars.value.find(o => o.key === selectedPdpTarget.value)?.predicted || 0).toFixed(4)) }]
      }
    }]
  })
}

const renderDistributionCharts = async () => {
  if (!distChartRef.value || !selectedDistFeatureData.value) return

  const item = selectedDistFeatureData.value
  const histChart = echarts.getInstanceByDom(distChartRef.value) || echarts.init(distChartRef.value)
  const edges = item.histogram?.edges || []
  const counts = item.histogram?.counts || []
  const labels = counts.map((_, idx) => {
    const left = edges[idx]
    const right = edges[idx + 1]
    return `${Number(left).toFixed(2)} ~ ${Number(right).toFixed(2)}`
  })

  histChart.setOption({
    animation: false,
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 28, bottom: 60 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { rotate: 35, fontSize: 10 }
    },
    yAxis: { type: 'value', name: '频数', axisLabel: { fontSize: 10 } },
    series: [{
      type: 'bar',
      data: counts,
      itemStyle: { color: '#4a6cf7', borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 28
    }]
  })
}

const loadTrainingDistribution = async () => {
  distributionLoading.value = true
  try {
    const resp = await axios.get('/api/training-data-distribution', { timeout: 10000 })
    const features = (resp.data?.features || [])
      .filter(item => !hiddenDistributionKeys.includes(item.feature))
    trainingDistribution.value = features
    if (features.length && !features.find(i => i.feature === selectedDistFeature.value)) {
      selectedDistFeature.value = features[0].feature
    }
    applyDistributionRanges()
    await nextTick()
    await renderDistributionCharts()
  } catch (err) {
    console.error('加载训练集分布失败：', err)
    trainingDistribution.value = []
  } finally {
    distributionLoading.value = false
  }
}

const resizeDistributionCharts = () => {
  if (distChartRef.value) {
    const c1 = echarts.getInstanceByDom(distChartRef.value)
    if (c1) c1.resize()
  }
}

const resizePdp = () => {
  if (!pdpChartRef.value) return
  const c = echarts.getInstanceByDom(pdpChartRef.value)
  if (c) c.resize()
}

let debounceTimer = null
let deepAnalysisTimer = null
let deepAnalysisVersion = 0

const scheduleDeepAnalysis = (delay = 650) => {
  clearTimeout(deepAnalysisTimer)
  deepAnalysisTimer = setTimeout(async () => {
    const version = ++deepAnalysisVersion
    await computeSensitivity()
    if (version !== deepAnalysisVersion) return
    await generateAnalysisReport()
  }, delay)
}

const onFeatureChange = () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(async () => {
    await runPrediction()
    await renderPdpChart()
    scheduleDeepAnalysis()
  }, 120)
}

watch(selectedDistFeature, async () => {
  await nextTick()
  await renderDistributionCharts()
})

watch(() => props.trainingKey, async () => {
  await reconnect()
  await loadTrainingDistribution()
})

const reconnect = async () => {
  await loadInspectorMeta()
  if (modelReady.value) {
    await runPrediction()
    outputVars.value.forEach(out => { out.baseline = out.predicted; out.delta = 0 })
    await nextTick(() => { renderPdpChart() })
    scheduleDeepAnalysis(120)
  }
}

onMounted(async () => {
  // 先尝试加载真实模型元信息
  const ok = await loadInspectorMeta()

  // 使用当前页面配置的默认值作为初始输入（不再覆盖为结果分析初始轨迹点）

  // 做预测初始化
  await runPrediction()
  outputVars.value.forEach(out => { out.baseline = out.predicted; out.delta = 0 })
  nextTick(async () => {
    await renderPdpChart()
    await loadTrainingDistribution()
    window.addEventListener('resize', resizePdp)
    window.addEventListener('resize', resizeDistributionCharts)
    if (modelReady.value) scheduleDeepAnalysis(80)
  })
  // 若首次连接失败，启动轮询
  if (!ok) startPolling()
})

onUnmounted(() => {
  clearTimeout(debounceTimer)
  clearTimeout(deepAnalysisTimer)
  window.removeEventListener('resize', resizePdp)
  window.removeEventListener('resize', resizeDistributionCharts)
})
</script>

<style scoped>
.inspector-wrap {
  min-height: 1360px;
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.model-strip {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f6f7f9;
  border: 1px solid #eceff4;
  border-radius: 8px;
  padding: 6px 10px;
  margin-bottom: 8px;
}
.strip-left { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.strip-brand { font-size: 11px; color: #808792; font-weight: 700; }
.strip-model { font-size: 12px; color: #303133; font-weight: 600; }
.strip-meta { font-size: 11px; color: #666; }
.strip-btn { border: 1px solid #d0d7e2; background: #fff; font-size: 11px; padding: 3px 9px; border-radius: 4px; }
.strip-btn.active { border-color: #4a6cf7; color: #4a6cf7; }
.reconnect-btn { border-color: #f59e0b; color: #f59e0b; font-weight: 600; cursor: pointer; }
.reconnect-btn:hover { background: #fffbf0; border-color: #d97706; color: #d97706; }

.risk-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.risk-title { font-size: 12px; font-weight: 700; color: #303133; }
.risk-current { font-size: 12px; color: #1f1f1f; font-weight: 700; }
.risk-bar-wrap { position: relative; margin-bottom: 8px; }
.risk-bar-bg { height: 12px; border-radius: 3px; background: linear-gradient(90deg, #6ec6ff 0%, #ffd166 50%, #ef476f 100%); opacity: .45; }
.risk-bar-now { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 3px; background: linear-gradient(90deg, #67c23a 0%, #f59e0b 55%, #f56c6c 100%); }
.risk-axis { display: flex; justify-content: space-between; font-size: 10px; color: #9aa1ad; margin-top: 2px; }

.inspector-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-shrink: 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 10px;
}

.insp-title { font-size: 14px; font-weight: 700; color: #1a1a2e; }
.insp-sub   { font-size: 11px; color: #aaa; }

.inspector-body {
  flex: 1;
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 14px;
  min-height: 0;
  overflow: visible;
}

/* ===== 左侧特征面板 ===== */
.feature-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: visible;
  padding-right: 4px;
}
.feature-panel::-webkit-scrollbar { width: 3px; }
.feature-panel::-webkit-scrollbar-thumb { background: #dde3f0; border-radius: 2px; }

.panel-label {
  font-size: 11px;
  font-weight: 700;
  color: #909399;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 2px;
}

.time-explain {
  margin: 2px 0 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f6f8ff;
  border: 1px solid #e3eaff;
  font-size: 12px;
  line-height: 1.5;
  color: #5b6475;
}

.feature-section { display: flex; flex-direction: column; gap: 5px; }

.fsec-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.3px;
  padding: 3px 0 2px 0;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 2px;
}

.feat-row { display: flex; flex-direction: column; gap: 2px; }

.feat-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.feat-name { font-size: 12px; color: #303133; font-weight: 500; }
.feat-val  { font-size: 12px; font-weight: 700; color: #4a6cf7; font-variant-numeric: tabular-nums; }

.feat-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 5px;
  border-radius: 3px;
  outline: none;
  cursor: pointer;
  transition: opacity 0.15s;
}

.state-slider   { background: linear-gradient(to right, #4a6cf7, #c8d4f8); }
.control-slider { background: linear-gradient(to right, #f59e0b, #fde8b0); }

.feat-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid #4a6cf7;
  box-shadow: 0 1px 4px rgba(0,0,0,0.15);
  cursor: pointer;
  transition: border-color 0.15s;
}

.control-slider::-webkit-slider-thumb { border-color: #f59e0b; }

.feat-range-labels {
  display: flex;
  justify-content: space-between;
  font-size: 9px;
  color: #c0c4cc;
  margin-top: -1px;
}

.reset-btn {
  margin-top: auto;
  padding: 6px 14px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  background: #fff;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}
.reset-btn:hover { background: #f0f4ff; border-color: #c6d8ff; color: #4a6cf7; }

/* ===== 右侧输出面板 ===== */
.output-panel {
  display: flex;
  flex-direction: column;
  overflow: visible;
  min-height: 0;
  gap: 6px;
}
.output-panel::-webkit-scrollbar { width: 3px; }
.output-panel::-webkit-scrollbar-thumb { background: #dde3f0; border-radius: 2px; }

.dist-card {
  background: #ffffff;
  border: 1px solid #e8edf7;
  border-radius: 12px;
  padding: 12px 14px;
}

.dist-sub {
  font-size: 11px;
  color: #8b93a6;
}

.dist-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dist-toolbar {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dist-select {
  width: 220px;
}

.dist-mini-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.dist-stat-chip {
  border: 1px solid #edf1f7;
  background: linear-gradient(180deg, #fafcff 0%, #f4f7fb 100%);
  border-radius: 10px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dist-stat-label {
  font-size: 10px;
  color: #8a91a1;
}

.dist-stat-value {
  font-size: 13px;
  font-weight: 700;
  color: #1f2937;
}

.dist-chart-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
}

.dist-chart-card {
  border: 1px solid #edf1f7;
  border-radius: 10px;
  background: #fbfcfe;
  padding: 10px;
}

.dist-chart-title {
  font-size: 12px;
  font-weight: 700;
  color: #4b5563;
  margin-bottom: 6px;
}

.dist-chart {
  height: 260px;
}

.pdp-card {
  border: 1px solid #eef1f5;
  background: #fff;
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 2px;
}

.pdp-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #303133;
  font-weight: 600;
  margin-bottom: 6px;
}
.pdp-selectors { display: flex; align-items: center; gap: 4px; }
.pdp-arrow { color: #909399; font-weight: 400; }

.pdp-select {
  border: 1px solid #d9dce3;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 11px;
  color: #303133;
  background: #fff;
}

.pdp-chart {
  height: 180px;
  width: 100%;
}


.output-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  flex-shrink: 0;
}

.out-card {
  background: #fafbfc;
  border: 1px solid #edf0fb;
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.out-card.flash-up { border-color: #4a6cf7; box-shadow: 0 0 0 2px rgba(74,108,247,0.12); }
.out-card.flash-dn { border-color: #f56c6c; box-shadow: 0 0 0 2px rgba(245,108,108,0.12); }

.out-name { font-size: 11px; font-weight: 700; color: #909399; }
.out-val  { font-size: 18px; font-weight: 800; color: #1a1a2e; font-variant-numeric: tabular-nums; line-height: 1.2; }

.out-delta { font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; }
.delta-up   { color: #4a6cf7; }
.delta-dn   { color: #f56c6c; }
.delta-zero { color: #c0c4cc; }

.out-bar-wrap { height: 4px; background: #f0f2f5; border-radius: 2px; overflow: hidden; margin-top: 2px; }
.out-bar-fill { height: 100%; border-radius: 2px; transition: width 0.3s ease, background 0.3s ease; }

/* ===== 敏感度矩阵 ===== */
.sens-section { flex-shrink: 0; }

.sens-table-wrap { overflow-x: auto; }

.sens-table {
  border-collapse: collapse;
  font-size: 11px;
  width: 100%;
}

.sens-corner {
  font-size: 10px;
  color: #aaa;
  font-weight: 600;
  padding: 4px 8px;
  text-align: left;
  white-space: nowrap;
}

.sens-table thead th {
  padding: 4px 6px;
  font-weight: 700;
  color: #4a6cf7;
  background: #f4f6ff;
  text-align: center;
  font-size: 11px;
  border: 1px solid #edf0fb;
}

.sens-feat {
  font-size: 11px;
  font-weight: 600;
  color: #303133;
  padding: 3px 8px;
  border: 1px solid #f0f0f0;
  white-space: nowrap;
  background: #fafbfc;
}

.sens-cell {
  padding: 2px 3px;
  border: 1px solid #f0f0f0;
  text-align: center;
}

.sens-block {
  width: 36px;
  height: 22px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  margin: 0 auto;
  transition: background 0.2s;
}

.sens-legend {
  display: flex;
  gap: 14px;
  margin-top: 6px;
  font-size: 11px;
  color: #909399;
}
.leg-item { display: flex; align-items: center; gap: 5px; }
.leg-box  { width: 12px; height: 12px; border-radius: 2px; flex-shrink: 0; }

/* ===== 提示卡 ===== */
.tip-card {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  background: #f4f6ff;
  border: 1px solid #c6d8ff;
  border-radius: 8px;
  padding: 8px 12px;
  flex-shrink: 0;
}
.tip-icon { font-size: 14px; flex-shrink: 0; }
.tip-text { font-size: 11px; color: #606266; line-height: 1.5; }

.report-card {
  border: 1px solid #e8ebf5;
  border-radius: 8px;
  background: #fff;
  padding: 10px 12px;
}
.report-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.report-title { font-size: 12px; font-weight: 700; color: #303133; }
.report-empty { font-size: 11px; color: #909399; padding: 6px 0; }
.report-meta { font-size: 11px; color: #909399; margin-bottom: 6px; }
.report-summary-box { border: 1px solid #e6ecff; background: #f7f9ff; border-radius: 6px; padding: 8px; margin-bottom: 8px; }
.report-summary-title { font-size: 11px; font-weight: 700; color: #4a6cf7; margin-bottom: 4px; }
.report-summary-text { font-size: 12px; color: #303133; line-height: 1.45; }
.report-metrics { display: flex; gap: 12px; flex-wrap: wrap; font-size: 11px; color: #606266; margin-bottom: 8px; }
.report-sec { margin-top: 6px; }
.report-sec-title { font-size: 11px; font-weight: 700; color: #4a6cf7; margin-bottom: 4px; }
.report-line { font-size: 11px; color: #303133; line-height: 1.45; }
</style>
  
