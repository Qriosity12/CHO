<template>
  <div class="data-upload">
    <!-- 上传区域 -->
    <el-upload
      ref="uploadRef"
      class="upload-dragger"
      drag
      :auto-upload="false"
      :on-change="handleFileChange"
      :show-file-list="false"
      accept=".csv"
    >
      <div class="upload-inner">
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <p class="upload-text">拖拽或<em>点击</em>上传 CSV</p>
        <p class="upload-hint">需含 run_id 和 t_h 列，≤50MB</p>
      </div>
    </el-upload>

    <!-- 上传后信息 -->
    <div v-if="uploadedDataset" class="dataset-info">
      <div class="info-grid">
        <div class="info-cell">
          <span class="info-label">文件</span>
          <span class="info-val">{{ uploadedDataset.filename }}</span>
        </div>
        <div class="info-cell">
          <span class="info-label">行数</span>
          <span class="info-val">{{ uploadedDataset.rows }}</span>
        </div>
        <div class="info-cell">
          <span class="info-label">批次</span>
          <span class="info-val">{{ uploadedDataset.runs }}</span>
        </div>
        <div class="info-cell">
          <span class="info-label">列数</span>
          <span class="info-val">{{ uploadedDataset.columns?.length }}</span>
        </div>
      </div>
      <div class="columns-wrap">
        <el-tag v-for="col in uploadedDataset.columns" :key="col" size="small" type="info" class="col-tag">{{ col }}</el-tag>
      </div>
      <el-button type="primary" size="small" @click="confirmUpload" class="confirm-btn">
        确认使用
        <el-icon><Right /></el-icon>
      </el-button>
    </div>

    <!-- 历史数据集 -->
    <div v-if="datasets.length > 0" class="history-list">
      <div class="history-title">历史数据集</div>
      <div
        v-for="ds in datasets"
        :key="ds.name"
        class="history-item"
        @click="selectDataset(ds)"
      >
        <span class="ds-name">{{ ds.name }}</span>
        <span class="ds-meta">{{ ds.rows }}行 · {{ ds.runs }}批</span>
        <el-icon class="ds-arrow"><Right /></el-icon>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const emit = defineEmits(['uploaded'])

const uploadRef = ref()
const uploadedDataset = ref(null)
const datasets = ref([])

const handleFileChange = async (file) => {
  if (!file.name.endsWith('.csv')) { ElMessage.error('只能上传CSV文件！'); return }
  if (file.size / 1024 / 1024 >= 50) { ElMessage.error('文件大小不能超过50MB！'); return }
  const loadingMsg = ElMessage({ message: '正在上传...', type: 'info', duration: 0 })
  const formData = new FormData()
  formData.append('file', file.raw)
  try {
    const response = await axios.post('/api/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 30000
    })
    loadingMsg.close()
    if (response.data.success) {
      uploadedDataset.value = response.data
      ElMessage.success('上传成功！')
      loadDatasets()
    } else {
      ElMessage.error(response.data.detail || '上传失败')
    }
  } catch (error) {
    loadingMsg.close()
    ElMessage.error(error.response?.data?.detail || error.message || '上传失败')
  }
}

const confirmUpload = () => emit('uploaded', uploadedDataset.value)
const selectDataset = (dataset) => { uploadedDataset.value = dataset; emit('uploaded', dataset) }

const loadDatasets = async () => {
  try {
    const response = await axios.get('/api/datasets')
    if (response.data.success) datasets.value = response.data.datasets
  } catch (error) {
    console.warn('加载数据集列表失败:', error.message)
  }
}

onMounted(() => loadDatasets())
</script>

<style scoped>
.data-upload {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
}

.upload-dragger {
  width: 100%;
}

.upload-dragger :deep(.el-upload-dragger) {
  padding: 16px;
  height: auto;
}

.upload-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.upload-icon {
  font-size: 32px;
  color: #667eea;
}

.upload-text {
  font-size: 13px;
  color: #555;
  margin: 0;
}

.upload-text em {
  color: #667eea;
  font-style: normal;
  font-weight: 600;
}

.upload-hint {
  font-size: 11px;
  color: #aaa;
  margin: 0;
}

.dataset-info {
  background: #f8faff;
  border: 1px solid #e0e8ff;
  border-radius: 8px;
  padding: 10px 12px;
  animation: fadeIn 0.3s;
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 12px;
  margin-bottom: 8px;
}

.info-cell {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}

.info-label {
  color: #909399;
}

.info-val {
  font-weight: 600;
  color: #303133;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.columns-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
  max-height: 56px;
  overflow: hidden;
}

.col-tag {
  font-size: 11px;
}

.confirm-btn {
  width: 100%;
}

.history-list {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.history-title {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.2s;
  border-bottom: 1px solid #f0f0f0;
  font-size: 12px;
}

.history-item:hover {
  background: #f0f4ff;
}

.ds-name {
  flex: 1;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ds-meta {
  color: #909399;
  flex-shrink: 0;
}

.ds-arrow {
  color: #c0c4cc;
  flex-shrink: 0;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
