<template>
  <div class="result-analysis-layout">
    <!-- 中间面板：四宫格图表 -->
    <main class="center-panel">
      <div class="panel-header">
        <el-icon><TrendCharts /></el-icon>
        <span>可视化分析</span>
        <div class="header-actions">
          <el-button size="small" @click="refreshData">
            <el-icon><Refresh /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- 四宫格：始终渲染，图表格子在无数据时显示空占位 -->
      <div class="chart-grid">
        <!-- 左上：产物浓度 -->
        <div class="chart-cell">
          <div class="chart-cell-title">产物浓度 (Titer)</div>
          <div v-if="stateData.length === 0" class="cell-empty">请先完成模型训练</div>
          <div v-else ref="titerChartRef" class="cell-chart"></div>
        </div>
        <!-- 右上：细胞状态 -->
        <div class="chart-cell">
          <div class="chart-cell-title">细胞状态</div>
          <div v-if="stateData.length === 0" class="cell-empty">请先完成模型训练</div>
          <div v-else ref="stateChartRef" class="cell-chart"></div>
        </div>
        <!-- 左下：测试集性能 + 可信度评估 -->
        <div class="chart-cell perf-cell">
          <div class="chart-cell-title">测试集性能 &amp; 可信度评估</div>
          <div v-if="perfData.test.length === 0" class="cell-empty">请先完成模型训练</div>
          <div v-else class="perf-body">
            <div class="perf-table-wrap">
              <table class="perf-table">
                <thead>
                  <tr><th>变量</th><th>RMSE</th><th>σ 阈值</th><th>R²</th><th>可信度</th><th>补料触发</th><th>说明</th></tr>
                </thead>
                <tbody>
                  <tr v-for="row in perfData.test" :key="row.name">
                    <td class="var-name">{{ row.name }}</td>
                    <td>{{ row.rmse }}</td>
                    <td class="threshold-val">{{ rmseThreshold(row.name).label }}</td>
                    <td :class="r2Class(row.r2)">{{ row.r2 }}</td>
                    <td><span :class="['trust-badge', trustLevel(row.name, row.rmse, row.r2).cls]">{{ trustLevel(row.name, row.rmse, row.r2).text }}</span></td>
                    <td class="trigger-cell">{{ trustLevel(row.name, row.rmse, row.r2).canTrigger ? '可用' : '参考' }}</td>
                    <td class="reason-cell">{{ trustLevel(row.name, row.rmse, row.r2).reason }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <!-- 右下：补料-浓度机理速查 -->
        <div class="chart-cell perf-cell">
          <div class="chart-cell-title">补料-浓度机理速查</div>
          <div class="perf-body">
            <div class="ref-tabs">
              <div class="ref-tab-btns">
                <button :class="['ref-tab-btn', { active: refTab === 'mechanism' }]" @click="refTab = 'mechanism'">机理与触发</button>
                <button :class="['ref-tab-btn', { active: refTab === 'threshold' }]" @click="refTab = 'threshold'">标准差阈值</button>
              </div>
              <div v-show="refTab === 'mechanism'" class="perf-table-wrap">
                <table class="perf-table">
                  <thead><tr><th>变量</th><th>生物过程</th><th>补料关系</th><th>补料触发</th><th>可信度说明</th></tr></thead>
                  <tbody>
                    <tr v-for="row in mechData" :key="row.var">
                      <td class="var-name">{{ row.var }}</td>
                      <td class="mech-action-cell">{{ row.action }}</td>
                      <td class="mech-action-cell">{{ row.mechanism }}</td>
                      <td :class="['trigger-cell', row.trigger.includes('✔') ? 'trigger-yes' : 'trigger-no']">{{ row.trigger }}</td>
                      <td class="mech-action-cell">{{ row.credibility }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-show="refTab === 'threshold'" class="perf-table-wrap">
                <table class="perf-table">
                  <thead><tr><th>变量</th><th>实验标准差 σ</th><th>高可信 (R²≥0.85 &amp; RMSE≤1.5σ)</th><th>中可信 (R²≥0.70 &amp; RMSE≤2.0σ)</th><th>低可信 (R²&lt;0.70 或 RMSE&gt;2.5σ)</th></tr></thead>
                  <tbody>
                    <tr v-for="col in ['VCD', 'Glc', 'Gln', 'Amm', 'Lac', 'Titer', 'DCD', 'Lysed']" :key="col">
                      <td class="var-name">{{ col }}</td>
                      <td class="threshold-val">{{ experimentalStd[col]?.toFixed(2) || '—' }}</td>
                      <td class="r2-high">高</td>
                      <td class="r2-mid">中</td>
                      <td class="r2-low">低</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 可信度仪表板（在图表下方） -->
      <div v-if="credibilityData" class="credibility-section">
        <CredibilityDashboard :credibility-data="credibilityData" />
      </div>
    </main>

    <!-- 右侧面板：数据表格 -->
    <aside class="right-panel">
      <el-tabs v-model="activeTab" type="card" class="right-tabs">
        <el-tab-pane label="状态" name="state">
          <el-table :data="stateData.slice(0, 15)" size="small" class="compact-table">
            <el-table-column prop="time_step" label="T" width="36" />
            <el-table-column label="VCD">
              <template #default="{ row }">{{ formatValue(row.VCD) }}</template>
            </el-table-column>
            <el-table-column label="Glc">
              <template #default="{ row }">{{ formatValue(row.Glc) }}</template>
            </el-table-column>
            <el-table-column label="Gln">
              <template #default="{ row }">{{ formatValue(row.Gln) }}</template>
            </el-table-column>
            <el-table-column label="Titer">
              <template #default="{ row }">{{ formatValue(row.Titer) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="控制" name="control">
          <el-table :data="controlData.slice(0, 15)" size="small" class="compact-table">
            <el-table-column prop="time_step" label="T" width="36" />
            <el-table-column label="温度">
              <template #default="{ row }">{{ formatValue(row.temp) }}</template>
            </el-table-column>
            <el-table-column label="pH">
              <template #default="{ row }">{{ formatValue(row.pH) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="补料" name="feeding">
          <el-table :data="feedingRecommendations.slice(0, 15)" size="small" class="compact-table">
            <el-table-column prop="time_step" label="T" width="36" />
            <el-table-column label="Glc">
              <template #default="{ row }">
                <el-tag size="small" type="success">{{ formatValue(row.Feed_Glc) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="Gln">
              <template #default="{ row }">
                <el-tag size="small" type="warning">{{ formatValue(row.Feed_Gln) }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>

      <!-- Titer 统计（仅 titer 视图时有意义） -->
      <div class="titer-stats" v-if="stateData.length > 0">
        <div class="ts-cell">
          <div class="ts-label">初始 Titer</div>
          <div class="ts-val">{{ getTiterStats().initial }}</div>
        </div>
        <div class="ts-cell">
          <div class="ts-label">最终 Titer</div>
          <div class="ts-val">{{ getTiterStats().final }}</div>
        </div>
        <div class="ts-cell">
          <div class="ts-label">增长率</div>
          <div class="ts-val" :class="getTiterStats().growthClass">{{ getTiterStats().growth }}</div>
        </div>
      </div>

      <el-button type="primary" size="small" @click="downloadCSV" style="width:100%;margin-top:8px;flex-shrink:0">
        <el-icon><Download /></el-icon> 下载补料策略CSV
      </el-button>
    </aside>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import CredibilityDashboard from './CredibilityDashboard.vue'

const props = defineProps({
  results: Object
})

// 状态
const currentView = ref('titer')
const activeTab = ref('state')
const refTab = ref('r2')
const viewOptions = [
  { value: 'titer', label: '产物浓度' },
  { value: 'state', label: '细胞状态' },
  { value: 'control', label: '控制轨迹' },
  { value: 'feeding', label: '补料策略' }
]
const stateData = ref([])
const controlData = ref([])
const feedingRecommendations = ref([])
const feedingSummary = ref({
  total_steps: 0,
  avg_feed_glc: 'N/A',
  avg_feed_gln: 'N/A'
})

// 图表引用
const titerChartRef = ref()
const stateChartRef = ref()

// 模型性能数据（从后端训练结果动态解析）
const perfData = ref({ test: [] })
const credibilityData = ref(null)

const parsePerfData = (results) => {
  console.log('[parsePerfData] full results:', JSON.stringify(results))
  const root = results?.results || results
  const dynamics = root?.dynamics
  if (!dynamics?.test_metrics) {
    console.warn('[parsePerfData] test_metrics 不存在, dynamics:', JSON.stringify(dynamics))
    return
  }
  
  if (dynamics.experimental_std) {
    experimentalStd.value = dynamics.experimental_std
    console.log('[parsePerfData] ✓ 已更新实验标准差:', experimentalStd.value)
  } else {
    console.warn('[parsePerfData] ✗ experimental_std 为空，使用默认值')
  }
  
  const testM = dynamics.test_metrics
  perfData.value.test = Object.keys(testM).map(name => ({
    name,
    rmse: testM[name].rmse.toString(),
    r2: testM[name].r2.toString()
  }))
  console.log('[parsePerfData] 解析完成:', perfData.value.test)
  
  if (root?.credibility) {
    credibilityData.value = root.credibility
    console.log('[parsePerfData] ✓ 已加载可信度数据:', credibilityData.value)
  } else {
    console.warn('[parsePerfData] ✗ 可信度数据不存在')
  }
}

// 实验标准差（从后端动态获取，初始为空）
const experimentalStd = ref({
  VCD:   15.5876,
  Glc:   6.7217,
  Gln:   5.5279,
  Amm:   2.0325,
  Lac:   2.1342,
  Titer: 1146.2770,
  DCD:   6.3209,
  Lysed: 0.1566,
})

// 可信度评估（与后端 credibility.py 保持一致）
// 判定标准（新版本）：
//   高: R² ≥ 0.85 且 RMSE ≤ 1.5σ  → 权重 1.0  → 可作为补料触发依据
//   中: (R² ≥ 0.70 且 RMSE ≤ 2.0σ) 或 (R² ≥ 0.80 且 RMSE ≤ 2.5σ)  → 权重 0.6  → 仅供参考
//   低: R² < 0.70 或 RMSE > 2.5σ  → 权重 0.2  → 仅供参考
const rmseThreshold = (name) => {
  const std = experimentalStd.value[name]
  if (!std) return { label: '—' }
  return { label: `σ=${std.toFixed(2)}` }
}

const trustLevel = (name, rmseStr, r2Str) => {
  const rmse = parseFloat(rmseStr)
  const r2 = parseFloat(r2Str)
  const std = experimentalStd.value[name]
  
  if (!std) return { text: '—', cls: '' }
  
  // 新判定标准：基于 R² 和 RMSE 的组合判定
  
  // 高可信度：R² ≥ 0.85 且 RMSE ≤ 1.5σ
  if (r2 >= 0.85 && rmse <= 1.5 * std) {
    return { 
      text: '✓ 高', 
      cls: 'trust-high',
      canTrigger: true,
      reason: '可作为补料触发依据'
    }
  }
  
  // 中可信度：满足以下任一条件
  // 1. R² ≥ 0.70 且 RMSE ≤ 2.0σ
  // 2. R² ≥ 0.80 且 RMSE ≤ 2.5σ
  if ((r2 >= 0.70 && rmse <= 2.0 * std) || (r2 >= 0.80 && rmse <= 2.5 * std)) {
    return { 
      text: '△ 中', 
      cls: 'trust-mid',
      canTrigger: false,
      reason: '仅供参考'
    }
  }
  
  // 低可信度：R² < 0.70 或 RMSE > 2.5σ
  return { 
    text: '⚠ 低', 
    cls: 'trust-low',
    canTrigger: false,
    reason: '仅供参考'
  }
}

// 补料-浓度机理速查表（根据可信度和补料触发适用性）
// 可信度判断标准（与后端一致）：
//   高: R² ≥ 0.85 且 RMSE ≤ 1.5σ  → 可作为补料触发依据
//   中: (R² ≥ 0.70 且 RMSE ≤ 2.0σ) 或 (R² ≥ 0.80 且 RMSE ≤ 2.5σ)  → 仅供参考
//   低: R² < 0.70 或 RMSE > 2.5σ  → 仅供参考
const mechDataFull = [
  {
    var: 'Glc',
    range: '3–8 mM',
    action: 'Feed_Glc↑ → VCD/Titer↑（能量来源）；减少Feed_Glc可降低Lac积累',
    mechanism: '预测未来耗竭时间 + 不确定度',
    trigger: '最核心',
    credibility: '高可信度时触发补料',
    warn: '>15mM渗透压↑', 
    warnCls: 'trust-low'
  },
  {
    var: 'VCD',
    range: '目标最大化',
    action: 'Glc/Gln同时充足时增殖最旺；Amm/Lac积累或渗透压高时骤降',
    mechanism: '用增长速率趋势判断',
    trigger: '辅助',
    credibility: '中等可信度时参考增长趋势',
    warn: '平台期提前→缺营养', 
    warnCls: 'trust-mid'
  },
  {
    var: 'Lac',
    range: '< 15 mM',
    action: '减少Feed_Glc或降温(35°C)可减少乳酸；无直接补料操作',
    mechanism: '用于提示降低补料强度',
    trigger: '策略调整',
    credibility: '中等可信度时调整补料策略',
    warn: '>20mM直接毒性', 
    warnCls: 'trust-mid'
  },
  {
    var: 'Gln',
    range: '1.5–4 mM',
    action: 'Feed_Gln↑ → VCD/Titer↑（氮源）；同时促进Amm生成，需权衡',
    mechanism: '与 NH4 联合解释',
    trigger: '辅助触发',
    credibility: '高可信度时辅助触发，需与Amm联合判断',
    warn: '>6mM→Amm毒性', 
    warnCls: 'trust-low'
  },
  {
    var: 'Amm',
    range: '< 2 mM',
    action: '无直接补料；减少Feed_Gln或降温可降低生成速率',
    mechanism: '做红色风险提示',
    trigger: '主要用于风险控制',
    credibility: '低可信度时仍需监控，作为风险警报',
    warn: '>4mM强毒性', 
    warnCls: 'trust-low'
  },
  {
    var: 'Titer',
    range: '单调递增',
    action: 'Titer ∝ VCD × qP；适宜Glc+Gln+低温(35°C)提升比生产速率qP',
    mechanism: '展示预测曲线用于策略评估',
    trigger: '不适合即时触发',
    credibility: '仅供长期策略评估，不用于即时决策',
    warn: '下降→模型失效', 
    warnCls: 'trust-mid'
  },
  {
    var: 'DCD',
    range: '< 10 ×10⁶/mL',
    action: '死细胞比例升高→补料策略过激或环境恶化',
    mechanism: '用于提示调整策略',
    trigger: '主要用于风险控制',
    credibility: '低可信度时仍需监控，作为策略调整信号',
    warn: '>20%→严重问题', 
    warnCls: 'trust-low'
  },
  {
    var: 'Lysed',
    range: '< 0.3',
    action: '细胞裂解比例→环境渗透压或pH异常',
    mechanism: '用于提示调整策略',
    trigger: '主要用于风险控制',
    credibility: '低可信度时仍需监控，作为环境异常警报',
    warn: '>0.5→严重问题', 
    warnCls: 'trust-low'
  },
]

const mechData = mechDataFull

const r2Class = (val) => {
  const v = parseFloat(val)
  if (v >= 0.95) return 'r2-high'
  if (v >= 0.85) return 'r2-mid'
  return 'r2-low'
}

// 计算属性
const controlColumns = computed(() => {
  const inputs = props.results?.results?.dynamics?.input_columns || []
  const states = props.results?.results?.dynamics?.state_columns || []
  return inputs.filter(col => !states.includes(col))
})

const operationSteps = computed(() => {
  if (feedingRecommendations.value.length === 0) return []
  return feedingRecommendations.value.slice(0, 5).map((rec, index) => ({
    time: `第${rec.time_step}天`,
    description: generateRecommendation(rec)
  }))
})

// 方法
const getViewTitle = () => {
  const titles = {
    titer: '产物浓度轨迹 (Titer)',
    state: '细胞与营养物状态',
    control: 'MPC控制输入',
    feeding: '补料策略'
  }
  return titles[currentView.value] || '数据视图'
}

const getModelTypeName = (type) => {
  const names = { rf: '随机森林', nn: '神经网络', gp: '高斯过程' }
  return names[type] || type || 'N/A'
}

const formatValue = (value) => {
  if (value === undefined || value === null) return 'N/A'
  if (typeof value === 'number') return value.toFixed(3)
  return value
}

const getTiterStats = () => {
  if (!stateData.value || stateData.value.length === 0) {
    return { initial: 'N/A', final: 'N/A', growth: 'N/A', growthClass: '' }
  }
  const initial = stateData.value[0]?.Titer || 0
  const final = stateData.value[stateData.value.length - 1]?.Titer || 0
  const growth = initial > 0 ? (((final - initial) / initial) * 100).toFixed(1) + '%' : 'N/A'
  const growthClass = final > initial ? 'positive' : 'negative'
  return {
    initial: initial.toFixed(2),
    final: final.toFixed(2),
    growth,
    growthClass
  }
}

const generateRecommendation = (row) => {
  const parts = []
  if (row.Feed_Glc > 0) parts.push(`Glc ${formatValue(row.Feed_Glc)}mM`)
  if (row.Feed_Gln > 0) parts.push(`Gln ${formatValue(row.Feed_Gln)}mM`)
  if (row.temp) parts.push(`${formatValue(row.temp)}°C`)
  if (row.pH) parts.push(`pH ${formatValue(row.pH)}`)
  return parts.length > 0 ? parts.join(', ') : '无操作'
}

const refreshData = () => {
  loadTrajectories()
  loadFeedingStrategy()
  ElMessage.success('数据已刷新')
}

const loadTrajectories = async () => {
  try {
    const response = await axios.get('/api/trajectories')
    if (response.data.success) {
      stateData.value = response.data.state_trajectory
      controlData.value = response.data.control_trajectory
      renderAllCharts()
    }
  } catch (error) {
    console.error('加载轨迹数据失败:', error)
  }
}

const loadFeedingStrategy = async () => {
  try {
    const response = await axios.get('/api/feeding-strategy')
    if (response.data.success) {
      feedingRecommendations.value = response.data.recommendations
      feedingSummary.value = {
        total_steps: response.data.summary.total_steps,
        avg_feed_glc: formatValue(response.data.summary.avg_feed_glc),
        avg_feed_gln: formatValue(response.data.summary.avg_feed_gln)
      }
    }
  } catch (error) {
    console.error('加载补料策略失败:', error)
  }
}

const downloadCSV = async () => {
  try {
    const response = await axios.get('/api/download/feeding-strategy', {
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', 'feeding_recommendations.csv')
    document.body.appendChild(link)
    link.click()
    link.remove()
    ElMessage.success('下载成功')
  } catch (error) {
    ElMessage.error('下载失败')
  }
}

const renderAllCharts = () => {
  nextTick(() => {
    // 等待可信度面板渲染完成后再渲染图表，确保尺寸正确
    setTimeout(() => {
      renderTiterChart()
      renderStateChart()
    }, 600)
  })
}

const renderTiterChart = () => {
  if (!titerChartRef.value || !stateData.value.length) return
  const existing = echarts.getInstanceByDom(titerChartRef.value)
  const chart = existing || echarts.init(titerChartRef.value)
  const timeSteps = stateData.value.map(d => d.time_step)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 45, right: 15, bottom: 30, top: 20 },
    xAxis: { type: 'category', data: timeSteps, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', name: 'mg/L', nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 10 } },
    series: [{
      name: 'Titer', type: 'line', data: stateData.value.map(d => d.Titer?.toFixed(2)),
      smooth: true, lineStyle: { width: 2, color: '#e74c3c' },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(231,76,60,0.25)' }, { offset: 1, color: 'rgba(231,76,60,0.02)' }
      ])}
    }]
  })
  chart.resize()
}

const renderStateChart = () => {
  if (!stateChartRef.value || !stateData.value.length) return
  const existing = echarts.getInstanceByDom(stateChartRef.value)
  const chart = existing || echarts.init(stateChartRef.value)
  const timeSteps = stateData.value.map(d => d.time_step)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['VCD', 'Glc', 'Gln', 'Amm', 'Lac'], top: 2, textStyle: { fontSize: 10 }, itemWidth: 12, itemHeight: 8 },
    grid: { left: 45, right: 15, bottom: 30, top: 30 },
    xAxis: { type: 'category', data: timeSteps, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
    series: [
      { name: 'VCD', type: 'line', data: stateData.value.map(d => d.VCD?.toFixed(2)), smooth: true, lineStyle: { width: 1.5 } },
      { name: 'Glc', type: 'line', data: stateData.value.map(d => d.Glc?.toFixed(2)), smooth: true, lineStyle: { width: 1.5 } },
      { name: 'Gln', type: 'line', data: stateData.value.map(d => d.Gln?.toFixed(2)), smooth: true, lineStyle: { width: 1.5 } },
      { name: 'Amm', type: 'line', data: stateData.value.map(d => d.Amm?.toFixed(2)), smooth: true, lineStyle: { width: 1.5 } },
      { name: 'Lac', type: 'line', data: stateData.value.map(d => d.Lac?.toFixed(2)), smooth: true, lineStyle: { width: 1.5 } }
    ]
  })
  chart.resize()
}

// 监听
watch(() => props.results, (newVal) => {
  if (newVal) {
    parsePerfData(newVal)
    setTimeout(() => {
      loadTrajectories()
      loadFeedingStrategy()
    }, 500)
  }
}, { immediate: true })

// 窗口resize时重绘图表
window.addEventListener('resize', () => {
  ;[titerChartRef, stateChartRef].forEach(r => {
    if (r.value) {
      const c = echarts.getInstanceByDom(r.value)
      if (c) c.resize()
    }
  })
})
</script>

<style scoped>
.result-analysis-layout {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 10px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

/* ===== 左侧面板 ===== */
.left-panel {
  background: white;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.07);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  gap: 0;
}

.left-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: #f0f0f0;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.lm-item {
  background: white;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.lm-label {
  font-size: 12px;
  color: #aaa;
}

.lm-val {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.lm-val.highlight {
  color: #4a6cf7;
}

.left-section {
  padding: 8px 10px;
  border-bottom: 1px solid #f5f5f5;
  flex-shrink: 0;
}

.section-title {
  font-size: 12px;
  font-weight: 700;
  color: #909399;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.summary-row {
  display: flex;
  gap: 4px;
}

.summary-cell {
  flex: 1;
  background: #f8faff;
  border-radius: 5px;
  padding: 5px 6px;
  text-align: center;
}

.sc-label {
  font-size: 11px;
  color: #aaa;
}

.sc-val {
  font-size: 15px;
  font-weight: 600;
  color: #4a6cf7;
}

.tag-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}

.vtag {
  font-size: 10px;
}

/* ===== 中间面板 ===== */
.center-panel {
  background: white;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.07);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.credibility-section {
  flex-shrink: 0;
  border-bottom: 1px solid #f0f0f0;
}

.header-actions {
  margin-left: auto;
}

/* 四宫格图表区 */
.chart-grid {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 320px 320px;
  gap: 6px;
  padding: 8px;
}

.chart-cell {
  background: #fafbfc;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.chart-cell-title {
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  padding: 5px 10px;
  border-bottom: 1px solid #f0f0f0;
  background: white;
  flex-shrink: 0;
}

.cell-chart {
  flex: 1;
  min-height: 0;
  height: 100%;
}

.cell-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #c0c4cc;
}

/* ===== 右侧面板 ===== */
.right-panel {
  background: white;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.07);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 8px;
  gap: 8px;
}

.right-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.right-tabs :deep(.el-tabs__header) {
  margin: 0 0 4px 0;
  flex-shrink: 0;
}

.right-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.right-tabs :deep(.el-tab-pane) {
  height: 100%;
  overflow-y: auto;
}

.compact-table :deep(.el-table__cell) {
  padding: 5px 6px !important;
  font-size: 12px;
}

.titer-stats {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.ts-cell {
  flex: 1;
  background: #f8faff;
  border-radius: 5px;
  padding: 5px;
  text-align: center;
}

.ts-label {
  font-size: 11px;
  color: #aaa;
}

.ts-val {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.ts-val.positive { color: #67c23a; }
.ts-val.negative { color: #f56c6c; }

/* ===== 性能指标面板 ===== */
.perf-cell {
  overflow: hidden;
}

.perf-body {
  flex: 1;
  overflow: hidden;
  padding: 6px 8px;
  min-height: 0;
}

.perf-table-wrap {
  height: 100%;
  overflow-y: auto;
}

.perf-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}

.perf-table thead tr:first-child th {
  background: #f0f4ff;
  color: #4a6cf7;
  font-weight: 700;
  text-align: center;
  padding: 4px 6px;
  border-bottom: 1px solid #dce6ff;
}

.perf-table thead tr:last-child th {
  background: #f7f9ff;
  color: #909399;
  font-weight: 600;
  text-align: center;
  padding: 3px 6px;
  border-bottom: 2px solid #e4e7ed;
  font-size: 11px;
}

.perf-table tbody tr {
  border-bottom: 1px solid #f5f5f5;
  transition: background 0.1s;
}

.perf-table tbody tr:hover {
  background: #f8faff;
}

.perf-table tbody td {
  padding: 4px 6px;
  text-align: center;
  color: #606266;
}

.perf-table .var-name {
  font-weight: 600;
  color: #303133;
  text-align: left;
  font-size: 12px;
}

.r2-high { color: #67c23a; font-weight: 700; }
.r2-mid  { color: #e6a23c; font-weight: 700; }
.r2-low  { color: #f56c6c; font-weight: 700; }

.mech-range-cell {
  font-size: 11px;
  font-weight: 600;
  color: #67c23a;
  white-space: nowrap;
}

.mech-action-cell {
  font-size: 10.5px;
  color: #606266;
  line-height: 1.4;
}

/* 参考阈值 tab 切换 */
.ref-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.ref-tab-btns {
  display: flex;
  gap: 4px;
  padding: 4px 0 6px 0;
  flex-shrink: 0;
}

.ref-tab-btn {
  padding: 3px 12px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  background: white;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
  transition: all 0.15s;
}

.ref-tab-btn:hover {
  background: #f0f4ff;
  border-color: #c6d8ff;
  color: #4a6cf7;
}

.ref-tab-btn.active {
  background: #4a6cf7;
  border-color: #4a6cf7;
  color: white;
  font-weight: 600;
}

.threshold-val {
  font-size: 10px;
  color: #b0b8c9;
}

/* 可信度徽章 */
.trust-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: 700;
  white-space: nowrap;
}
.trust-high { background: #f0faf0; color: #67c23a; border: 1px solid #b7eb8f; }
.trust-mid  { background: #fff8ec; color: #e6a23c; border: 1px solid #ffe58f; }
.trust-low  { background: #fff2f0; color: #f56c6c; border: 1px solid #ffccc7; }

/* 补料触发和说明列 */
.trigger-cell {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.trigger-yes {
  color: #67c23a;
}

.trigger-no {
  color: #f56c6c;
}

.reason-cell {
  font-size: 10px;
  color: #909399;
  max-width: 120px;
  word-break: break-word;
  line-height: 1.3;
}

/* 补料触发状态 */
.trigger-cell {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.trigger-yes { color: #67c23a; }
.trigger-no  { color: #f56c6c; }

/* 可信度说明 */
.reason-cell {
  font-size: 10px;
  color: #909399;
  white-space: nowrap;
}

/* 机理速查卡 */
.mech-cards {
  flex-shrink: 0;
  border-top: 1px solid #f0f0f0;
  padding-top: 5px;
}

.mech-title {
  font-size: 11px;
  font-weight: 700;
  color: #909399;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.mech-grid {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.mech-item {
  display: grid;
  grid-template-columns: 42px 80px 1fr;
  align-items: center;
  gap: 4px;
  padding: 3px 4px;
  background: #f8faff;
  border-radius: 4px;
  font-size: 10.5px;
}

.mech-var {
  font-weight: 700;
  color: #4a6cf7;
}

.mech-range {
  color: #67c23a;
  font-weight: 600;
  font-size: 10px;
}

.mech-action {
  color: #606266;
  line-height: 1.3;
}
</style>

