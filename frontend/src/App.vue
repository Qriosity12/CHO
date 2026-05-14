<template>
  <div id="app" class="app-container">
    <!-- 顶部标题栏 -->
    <header class="app-header">
      <div class="header-left">
        <el-icon :size="28"><Operation /></el-icon>
        <h1>CHO细胞培养优化系统</h1>
      </div>
      <div class="header-status">
        <div class="status-dot" :class="{ active: !!currentDataset }">
          <el-icon><Upload /></el-icon> 数据
        </div>
        <div class="status-arrow">→</div>
        <div class="status-dot" :class="{ active: !!modelConfig }">
          <el-icon><Setting /></el-icon> 配置
        </div>
        <div class="status-arrow">→</div>
        <div class="status-dot" :class="{ active: !!trainingResults }">
          <el-icon><TrendCharts /></el-icon> 结果
        </div>
      </div>
      <div class="header-right">
        <el-button @click="resetWorkflow" type="danger" plain size="small">
          <el-icon><RefreshLeft /></el-icon>
          重置
        </el-button>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="main-layout">
      <!-- 上半区：左侧（数据上传 + 模型配置）+ 右侧空白 -->
      <div class="top-row">
        <!-- 左侧列：数据上传 + 模型配置垂直排列 -->
        <div class="left-col">
          <!-- 数据上传 -->
          <section class="grid-card upload-section">
            <div class="card-header">
              <div class="header-title">
                <el-icon><Upload /></el-icon>
                <span>数据上传</span>
              </div>
              <el-tag v-if="currentDataset" type="success" size="small">已完成</el-tag>
            </div>
            <div class="card-body">
              <DataUpload @uploaded="handleDataUploaded" :compact="true" />
            </div>
          </section>

          <!-- 模型配置 + 自动训练 -->
          <section class="grid-card config-train-section">
            <div class="card-header">
              <div class="header-title">
                <el-icon><Cpu /></el-icon>
                <span>模型配置 &amp; 训练</span>
              </div>
              <div class="header-tags">
                <el-tag v-if="modelConfig" type="success" size="small" style="margin-right:6px">配置完成</el-tag>
                <el-tag v-if="trainingResults" type="primary" size="small">训练完成</el-tag>
                <el-tag v-if="isTraining" type="warning" size="small">训练中...</el-tag>
              </div>
            </div>
            <div class="card-body">
              <ModelConfig
                :dataset="currentDataset"
                :is-training="isTraining"
                @configured="handleModelConfigured"
                @startTraining="handleStartTraining"
                :compact="true"
              />
            </div>
          </section>
        </div>

        <!-- 右侧：实验操作时间轴 -->
        <section class="grid-card timeline-section">
          <div class="card-header">
            <div class="header-title">
              <el-icon><Calendar /></el-icon>
              <span>实验操作时间轴</span>
            </div>
          </div>
          <div class="card-body">
            <ExperimentTimeline />
          </div>
        </section>
      </div>

      <!-- 下半区：结果分析 -->
      <div class="bottom-row">
        <section class="grid-card result-section">
          <div class="card-header">
            <div class="header-title">
              <el-icon><TrendCharts /></el-icon>
              <span>结果分析</span>
            </div>
            <div class="header-actions-right">
              <el-tag v-if="trainingResults" type="success" size="small">已完成</el-tag>
            </div>
          </div>
          <div class="card-body result-body">
            <ResultAnalysis :results="trainingResults" :task-id="activeTaskId" :compact="true" />
          </div>
        </section>
      </div>

      <div v-if="trainingResults" class="inspector-page-row">
        <section class="grid-card inspector-page-section">
          <div class="card-header">
            <div class="header-title">
              <el-icon><Operation /></el-icon>
              <span>模型行为探查</span>
            </div>
          </div>
          <div class="card-body inspector-page-body">
            <ModelInspector :training-key="inspectorKey" :task-id="activeTaskId" />
          </div>
        </section>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DataUpload from './components/DataUpload.vue'
import ModelConfig from './components/ModelConfig.vue'
import ResultAnalysis from './components/ResultAnalysis.vue'
import ExperimentTimeline from './components/ExperimentTimeline.vue'
import ModelInspector from './components/ModelInspector.vue'
import axios from 'axios'

const currentDataset = ref(null)
const modelConfig = ref(null)
const trainingResults = ref(null)
const activeTaskId = ref(null)
const isTraining = ref(false)
const inspectorKey = ref(0)
let trainingPollTimer = null

const handleDataUploaded = (dataset) => {
  currentDataset.value = dataset
  ElMessage.success('数据上传成功，请配置模型参数')
}

const handleModelConfigured = (config) => {
  modelConfig.value = config
}

const handleStartTraining = async (config) => {
  if (!currentDataset.value) {
    ElMessage.warning('请先上传数据集')
    return
  }
  isTraining.value = true
  trainingResults.value = null
  activeTaskId.value = null
  if (trainingPollTimer) {
    clearInterval(trainingPollTimer)
    trainingPollTimer = null
  }
  try {
    const trainRequest = {
      dataset_name: currentDataset.value.dataset_name,
      model_settings: {
        dynamics_model_type: config.dynamics_model_type,
        history_steps: config.history_steps,
        include_controls: config.include_controls
      },
      mpc_settings: {
        prediction_horizon: config.prediction_horizon,
        control_horizon: config.control_horizon,
        simulation_steps: config.simulation_steps,
        weight_vcd: config.weight_vcd,
        weight_titer: config.weight_titer,
        weight_control: config.weight_control
      }
    }
    const response = await axios.post('/api/train/submit', trainRequest)
    if (!response.data.success || !response.data.job_id) {
      throw new Error(response.data.detail || '任务提交失败')
    }

    activeTaskId.value = response.data.job_id
    ElMessage.success(`训练任务已提交：${response.data.job_id}`)

    const pollTask = async () => {
      const statusResp = await axios.get(`/api/train/jobs/${activeTaskId.value}`)
      const statusData = statusResp.data
      if (!statusData.success) {
        throw new Error('任务状态获取失败')
      }

      if (statusData.status === 'completed') {
        trainingResults.value = statusData.result
        clearInterval(trainingPollTimer)
        trainingPollTimer = null
        isTraining.value = false
        await nextTick()
        inspectorKey.value += 1
        ElMessage.success('训练完成，模型行为探查已自动连接真实模型')
      } else if (statusData.status === 'failed') {
        clearInterval(trainingPollTimer)
        trainingPollTimer = null
        isTraining.value = false
        throw new Error(statusData.error || '训练失败')
      }
    }

    await pollTask()
    if (isTraining.value) {
      trainingPollTimer = setInterval(async () => {
        try {
          await pollTask()
        } catch (pollError) {
          clearInterval(trainingPollTimer)
          trainingPollTimer = null
          isTraining.value = false
          ElMessage.error(`训练失败: ${pollError.message || '未知错误'}`)
        }
      }, 2000)
    }
  } catch (error) {
    const msg = error.response?.data?.detail?.error || error.response?.data?.detail || error.message || '未知错误'
    ElMessage.error(`训练失败: ${msg}`)
    isTraining.value = false
  }
}

const resetWorkflow = async () => {
  try {
    await ElMessageBox.confirm('确定要重置整个流程吗？', '警告', { type: 'warning' })
    currentDataset.value = null
    modelConfig.value = null
    trainingResults.value = null
    activeTaskId.value = null
    if (trainingPollTimer) {
      clearInterval(trainingPollTimer)
      trainingPollTimer = null
    }
    inspectorKey.value = 0
    ElMessage.success('流程已重置')
  } catch {
    // 用户取消
  }
}
</script>

<style scoped>
* {
  box-sizing: border-box;
}

.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #e8ecf5;
  overflow-x: hidden;
  overflow-y: auto;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ===== 顶部标题栏 ===== */
.app-header {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 0 24px;
  height: 52px;
  background: #fff;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.1);
  flex-shrink: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #4a6cf7;
}

.header-left h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: #1a1a2e;
  white-space: nowrap;
}

.header-status {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 auto;
}

.status-dot {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
  background: #f0f2f5;
  color: #909399;
  transition: all 0.3s;
}

.status-dot.active {
  background: #ecf5ff;
  color: #4a6cf7;
  border: 1px solid #c6d8ff;
}

.status-arrow {
  color: #c0c4cc;
  font-size: 14px;
}

.header-right {
  margin-left: auto;
}

/* ===== 主布局 ===== */
.main-layout {
  display: flex;
  flex-direction: column;
  flex: 1;
  gap: 12px;
  padding: 12px;
  overflow: visible;
  min-height: 0;
}

/* 上半行：左侧列 + 右侧空白 */
.top-row {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 12px;
  min-height: 520px;
}

/* 左侧列：数据上传 + 模型配置垂直排列 */
.left-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}

.left-col .upload-section {
  flex: 0 0 180px;
  max-height: 180px;
  overflow: hidden;
}

.left-col .config-train-section {
  flex: 1 1 0;
  min-height: 0;
}

/* 右侧空白区域 */
.right-blank {
  background: transparent;
}

/* 时间轴卡片 */
.timeline-section {
  min-height: 0;
  overflow: hidden;
}

.timeline-section .card-body {
  padding: 12px 12px 8px 12px;
  overflow: hidden;
}

/* 下半区 */
.bottom-row {
  display: flex;
  min-height: 780px;
}

.inspector-page-row {
  display: flex;
  min-height: 1450px;
}

.inspector-page-section {
  width: 100%;
}

.inspector-page-body {
  padding: 10px;
  overflow: visible;
  min-height: 1380px;
}

.result-section {
  min-height: 0;
  overflow: hidden;
  width: 100%;
}

.header-actions-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.result-body {
  overflow: hidden;
  padding: 0;
}

.inspector-dialog-body {
  height: 76vh;
}

:deep(.inspector-dialog .el-dialog) {
  border-radius: 14px;
  overflow: hidden;
}

:deep(.inspector-dialog .el-dialog__header) {
  background: linear-gradient(90deg, #f6f8ff 0%, #fffaf2 100%);
  margin-right: 0;
  padding: 14px 20px;
  border-bottom: 1px solid #eef2ff;
}

:deep(.inspector-dialog .el-dialog__body) {
  padding: 12px 14px 14px;
}

/* ===== 卡片 ===== */
.grid-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 18px;
  border-bottom: 1px solid #f0f0f0;
  background: #fafbfc;
  flex-shrink: 0;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1a1a2e;
}

.header-title .el-icon {
  color: #4a6cf7;
}

.header-tags {
  display: flex;
  align-items: center;
}

.card-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  min-height: 0;
}

.card-body.no-pad {
  padding: 0;
  display: flex;
  flex-direction: column;
}
</style>
