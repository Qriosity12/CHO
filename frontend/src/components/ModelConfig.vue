<template>
  <div class="model-config">
    <el-form :model="config" label-position="top" size="small">

      <!-- 第一行：模型类型 + 控制输入 -->
      <div class="form-row">
        <div class="form-group">
          <div class="group-label">
            <el-icon><TrendCharts /></el-icon>
            动态模型类型
          </div>
          <el-radio-group v-model="config.dynamics_model_type" size="small">
            <el-radio-button value="rf">随机森林</el-radio-button>
            <el-radio-button value="nn">神经网络</el-radio-button>
            <el-radio-button value="gp">高斯过程</el-radio-button>
          </el-radio-group>
        </div>
        <div class="form-group">
          <div class="group-label">
            <el-icon><Operation /></el-icon>
            包含控制输入
          </div>
          <div class="switch-row">
            <el-switch v-model="config.include_controls" active-text="是" inactive-text="否" />
            <span class="hint">温度、pH等</span>
          </div>
        </div>
      </div>

      <div class="divider">MPC 优化参数</div>

      <!-- 第二行：三个数值参数横排 -->
      <div class="form-row three-col">
        <div class="form-group">
          <div class="group-label">预测时域</div>
          <el-input-number
            v-model="config.prediction_horizon"
            :min="5" :max="30" :step="1"
            style="width:100%"
          />
        </div>
        <div class="form-group">
          <div class="group-label">控制时域</div>
          <el-input-number
            v-model="config.control_horizon"
            :min="1" :max="config.prediction_horizon" :step="1"
            style="width:100%"
          />
        </div>
        <div class="form-group">
          <div class="group-label">仿真步数</div>
          <el-input-number
            v-model="config.simulation_steps"
            :min="10" :max="50" :step="1"
            style="width:100%"
          />
        </div>
      </div>

      <div class="divider">目标权重</div>

      <!-- 权重滑块：两列网格排列 -->
      <div class="weights-grid">
        <div class="weight-item">
          <div class="weight-label">
            <span>VCD</span>
            <span class="weight-val">{{ config.weight_vcd.toFixed(1) }}</span>
          </div>
          <el-slider v-model="config.weight_vcd" :min="0" :max="10" :step="0.1" />
        </div>
        <div class="weight-item">
          <div class="weight-label">
            <span>Titer</span>
            <span class="weight-val">{{ config.weight_titer.toFixed(1) }}</span>
          </div>
          <el-slider v-model="config.weight_titer" :min="0" :max="20" :step="0.1" />
        </div>
        <div class="weight-item weight-item--full">
          <div class="weight-label">
            <span>控制代价</span>
            <span class="weight-val">{{ config.weight_control.toFixed(2) }}</span>
          </div>
          <el-slider v-model="config.weight_control" :min="0" :max="1" :step="0.01" />
        </div>
      </div>

      <!-- 底部：按钮 -->
      <el-button type="primary" @click="confirmConfig" class="confirm-btn" :loading="props.isTraining" :disabled="props.isTraining">
        {{ props.isTraining ? '训练提交中...' : '确认配置，开始训练' }}
        <el-icon><Right /></el-icon>
      </el-button>

    </el-form>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({ dataset: Object, isTraining: Boolean })
const emit = defineEmits(['configured', 'startTraining'])

const config = ref({
  dynamics_model_type: 'rf',
  history_steps: 0,
  include_controls: true,
  prediction_horizon: 10,
  control_horizon: 5,
  simulation_steps: 10,
  weight_vcd: 1.0,
  weight_titer: 10.0,
  weight_control: 0.1
})

const modelTypeName = computed(() => ({
  rf: '随机森林', nn: '神经网络', gp: '高斯过程'
})[config.value.dynamics_model_type] || config.value.dynamics_model_type)

const confirmConfig = () => {
  ElMessage.success('配置已保存，开始训练...')
  emit('configured', config.value)
  emit('startTraining', config.value)
}
</script>

<style scoped>
.model-config {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.el-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  overflow-y: auto;
  padding: 0 4px 0 0;
}

.el-form::-webkit-scrollbar {
  width: 6px;
}

.el-form::-webkit-scrollbar-track {
  background: transparent;
}

.el-form::-webkit-scrollbar-thumb {
  background: #d9d9d9;
  border-radius: 3px;
}

.el-form::-webkit-scrollbar-thumb:hover {
  background: #bfbfbf;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.form-row.three-col {
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.group-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  line-height: 1.3;
}

.group-label .el-icon {
  color: #667eea;
  font-size: 14px;
  flex-shrink: 0;
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.hint {
  font-size: 11px;
  color: #aaa;
  white-space: nowrap;
}

.divider {
  font-size: 12px;
  font-weight: 700;
  color: #606266;
  border-bottom: 1px solid #e4e7ed;
  padding-bottom: 6px;
  margin: 4px 0 0 0;
}

.weights-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 16px;
}

.weight-item--full {
  grid-column: 1 / -1;
}

.weight-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.weight-label {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: #303133;
  font-weight: 500;
  line-height: 1.3;
}

.weight-val {
  font-weight: 700;
  color: #667eea;
  font-size: 13px;
}

.confirm-btn {
  height: 36px;
  font-size: 14px;
  font-weight: 600;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  flex-shrink: 0;
  white-space: nowrap;
  margin-top: auto;
}
</style>


