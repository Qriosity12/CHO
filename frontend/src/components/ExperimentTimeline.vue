<template>
  <div class="timeline-wrap">
    <div class="toolbar">
      <span class="tl-title">实验操作时间轴</span>
      <button class="add-btn" @click="openAdd">+ 记录</button>
    </div>

    <div class="axis-scroll">
      <div class="axis-track">
        <div class="axis-line"></div>
        <div v-for="(item, idx) in sortedDays" :key="item.day" class="axis-node">

          <div v-if="idx % 2 === 0" class="node-card card-above">
            <div class="card-hd">
              <span class="day-badge">D{{ item.day }}</span>
              <span class="card-date">{{ item.date.slice(5) }}</span>
            </div>
            <div v-if="item.images && item.images.length" class="card-imgs">
              <img v-for="(img, ii) in item.images" :key="ii" :src="img" class="thumb" @click="openPreview(img)" />
            </div>
            <div v-for="section in item.sections" :key="section.type" class="card-section">
              <div class="section-label" :style="{ color: getSectionColor(section.type) }">
                <span class="section-dot" :style="{ background: getSectionColor(section.type) }"></span>
                {{ getSectionLabel(section.type) }}
              </div>
              <div class="card-chips">
                <div v-for="(val, key) in section.data" :key="key" class="chip">
                  <span class="chip-k">{{ key }}</span><span class="chip-v">{{ val }}</span>
                </div>
              </div>
              <div v-if="section.note" class="card-note">{{ section.note }}</div>
            </div>
          </div>
          <div v-else class="card-placeholder"></div>

          <div v-if="idx % 2 === 0" class="stem"></div>
          <div class="node-dot"></div>
          <div class="node-time">
            <div class="node-day">D{{ item.day }}</div>
            <div class="node-date">{{ item.date.slice(5) }}</div>
          </div>
          <div v-if="idx % 2 === 1" class="stem"></div>

          <div v-if="idx % 2 === 1" class="node-card card-below">
            <div class="card-hd">
              <span class="day-badge">D{{ item.day }}</span>
              <span class="card-date">{{ item.date.slice(5) }}</span>
            </div>
            <div v-if="item.images && item.images.length" class="card-imgs">
              <img v-for="(img, ii) in item.images" :key="ii" :src="img" class="thumb" @click="openPreview(img)" />
            </div>
            <div v-for="section in item.sections" :key="section.type" class="card-section">
              <div class="section-label" :style="{ color: getSectionColor(section.type) }">
                <span class="section-dot" :style="{ background: getSectionColor(section.type) }"></span>
                {{ getSectionLabel(section.type) }}
              </div>
              <div class="card-chips">
                <div v-for="(val, key) in section.data" :key="key" class="chip">
                  <span class="chip-k">{{ key }}</span><span class="chip-v">{{ val }}</span>
                </div>
              </div>
              <div v-if="section.note" class="card-note">{{ section.note }}</div>
            </div>
          </div>
          <div v-else class="card-placeholder"></div>
        </div>
      </div>
    </div>

    <!-- 图片预览弹层 -->
    <div v-if="previewImg" class="preview-mask" @click="previewImg = null">
      <img :src="previewImg" class="preview-img" />
      <button class="preview-close" @click.stop="previewImg = null">✕</button>
    </div>

    <!-- 添加记录弹窗 -->
    <div v-if="showDialog" class="dialog-mask" @click.self="showDialog = false">
      <div class="dialog">
        <div class="dialog-hd"><span>添加实验记录</span><button class="dlg-close" @click="showDialog = false">✕</button></div>
        <div class="dialog-bd">
          <div class="f-row"><label>日期</label><input v-model="neo.date" type="date" class="f-input" /></div>
          <div class="f-row"><label>培养天数 (D)</label><input v-model.number="neo.day" type="number" min="0" class="f-input" /></div>
          <div class="f-section">图像分析</div>
          <div class="f-grid">
            <div class="f-row"><label>颜色</label><input v-model="neo.image['颜色']" class="f-input" /></div>
            <div class="f-row"><label>汇合度</label><input v-model="neo.image['汇合度']" class="f-input" /></div>
            <div class="f-row"><label>圆度</label><input v-model="neo.image['圆度']" class="f-input" /></div>
            <div class="f-row"><label>光泽</label><input v-model="neo.image['光泽']" class="f-input" /></div>
            <div class="f-row"><label>大小</label><input v-model="neo.image['大小']" class="f-input" /></div>
            <div class="f-row"><label>形态</label><input v-model="neo.image['形态']" class="f-input" /></div>
          </div>
          <div class="f-row"><label>图像备注</label><input v-model="neo.imageNote" class="f-input" /></div>
          <div class="f-section">检测数据</div>
          <div class="f-grid">
            <div class="f-row"><label>密度（×10⁶/mL）</label><input v-model="neo.detection['密度']" class="f-input" /></div>
            <div class="f-row"><label>pH</label><input v-model="neo.detection['pH']" class="f-input" /></div>
            <div class="f-row"><label>葡萄糖（mM）</label><input v-model="neo.detection['葡萄糖']" class="f-input" /></div>
          </div>
          <div class="f-row"><label>检测备注</label><input v-model="neo.detectionNote" class="f-input" /></div>
          <div class="f-section">操作记录</div>
          <div class="f-grid">
            <div class="f-row"><label>操作类型</label>
              <select v-model="neo.operation['操作']" class="f-input">
                <option value="">--</option>
                <option value="补液">补液</option><option value="传代">传代</option>
                <option value="换液">换液</option><option value="取样">取样</option>
              </select>
            </div>
            <div class="f-row"><label>代次</label><input v-model="neo.operation['代次']" class="f-input" /></div>
            <div class="f-row"><label>培养基总量（mL）</label><input v-model="neo.operation['培养基总量']" class="f-input" /></div>
            <div class="f-row"><label>血清量（mL）</label><input v-model="neo.operation['血清量']" class="f-input" /></div>
          </div>
          <div class="f-row"><label>操作备注</label><input v-model="neo.operationNote" class="f-input" /></div>
          <div class="f-section">上传图片</div>
          <div class="img-upload-area" @click="triggerFileInput" @dragover.prevent @drop.prevent="handleDrop">
            <input ref="fileInputRef" type="file" accept="image/*" multiple style="display:none" @change="handleFileChange" />
            <span v-if="!neo.images || !neo.images.length" class="upload-hint">点击或拖拽图片到此</span>
            <div v-else class="upload-previews">
              <div v-for="(img, i) in neo.images" :key="i" class="upload-thumb-wrap">
                <img :src="img" class="upload-thumb" />
                <button class="remove-img" @click.stop="removeImg(i)">✕</button>
              </div>
            </div>
          </div>
        </div>
        <div class="dialog-ft">
          <button class="btn-cancel" @click="showDialog = false">取消</button>
          <button class="btn-ok" @click="addEvent">添加</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const showDialog = ref(false)
const previewImg = ref(null)
const fileInputRef = ref(null)

const sectionTypes = [
  { key: 'image',     label: '图像', color: '#4a6cf7' },
  { key: 'detection', label: '检测', color: '#00b96b' },
  { key: 'operation', label: '操作', color: '#f59e0b' },
]
const getSectionColor = (key) => sectionTypes.find(s => s.key === key)?.color || '#909399'
const getSectionLabel = (key) => sectionTypes.find(s => s.key === key)?.label || key

const makeNeo = () => ({
  date: new Date().toISOString().slice(0, 10),
  day: 0,
  image: {},
  imageNote: '',
  detection: {},
  detectionNote: '',
  operation: {},
  operationNote: '',
  images: []
})
const neo = ref(makeNeo())
const openAdd = () => { neo.value = makeNeo(); showDialog.value = true }
const openPreview = (img) => { previewImg.value = img }
const triggerFileInput = () => { if (fileInputRef.value) fileInputRef.value.click() }
const readFile = (file) => new Promise(resolve => {
  const r = new FileReader()
  r.onload = e => resolve(e.target.result)
  r.readAsDataURL(file)
})
const handleFileChange = async (e) => {
  const files = Array.from(e.target.files)
  const imgs = await Promise.all(files.map(readFile))
  neo.value.images = [...(neo.value.images || []), ...imgs]
  e.target.value = ''
}
const handleDrop = async (e) => {
  const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'))
  const imgs = await Promise.all(files.map(readFile))
  neo.value.images = [...(neo.value.images || []), ...imgs]
}
const removeImg = (i) => { neo.value.images.splice(i, 1) }

// 原始事件（每条一个 section）
const events = ref([
  // D0
  { id:1,  date:'2026-03-01', day:0, type:'image',     data:{'颜色':'淡黄','汇合度':'20%','圆度':'0.93','光泽':'亮','大小':'13μm','形态':'球形'}, note:'接种初期，细胞分散均匀' },
  { id:2,  date:'2026-03-01', day:0, type:'detection', data:{'密度':'0.5×10⁶/mL','pH':'7.35','葡萄糖':'8.1 mM'}, note:'' },
  { id:3,  date:'2026-03-01', day:0, type:'operation', data:{'操作':'接种','代次':'P3','培养基总量':'10 mL','血清量':'1 mL'}, note:'起始密度 0.5×10⁶/mL' },
  // D1
  { id:4,  date:'2026-03-02', day:1, type:'image',     data:{'颜色':'淡黄','汇合度':'35%','圆度':'0.91','光泽':'亮','大小':'14μm','形态':'球形'}, note:'细胞状态良好' },
  { id:5,  date:'2026-03-02', day:1, type:'detection', data:{'密度':'1.1×10⁶/mL','pH':'7.30','葡萄糖':'6.8 mM'}, note:'' },
  { id:6,  date:'2026-03-02', day:1, type:'operation', data:{'操作':'取样','培养基总量':'10 mL','血清量':'1 mL'}, note:'日常取样检测' },
  // D2
  { id:7,  date:'2026-03-03', day:2, type:'image',     data:{'颜色':'淡黄','汇合度':'55%','圆度':'0.90','光泽':'较亮','大小':'15μm','形态':'球形'}, note:'增殖旺盛' },
  { id:8,  date:'2026-03-03', day:2, type:'detection', data:{'密度':'1.8×10⁶/mL','pH':'7.25','葡萄糖':'5.2 mM'}, note:'' },
  { id:9,  date:'2026-03-03', day:2, type:'operation', data:{'操作':'取样','培养基总量':'10 mL','血清量':'1 mL'}, note:'' },
  // D3
  { id:10, date:'2026-03-04', day:3, type:'image',     data:{'颜色':'黄','汇合度':'75%','圆度':'0.89','光泽':'较亮','大小':'15μm','形态':'轻微聚集'}, note:'开始出现少量聚集' },
  { id:11, date:'2026-03-04', day:3, type:'detection', data:{'密度':'3.2×10⁶/mL','pH':'7.18','葡萄糖':'3.1 mM'}, note:'葡萄糖偏低' },
  { id:12, date:'2026-03-04', day:3, type:'operation', data:{'操作':'补液','培养基总量':'12 mL','血清量':'1.2 mL'}, note:'补充葡萄糖' },
  // D4
  { id:13, date:'2026-03-05', day:4, type:'image',     data:{'颜色':'橙黄','汇合度':'85%','圆度':'0.87','光泽':'暗淡','大小':'16μm','形态':'轻微聚集'}, note:'需关注聚集情况' },
  { id:14, date:'2026-03-05', day:4, type:'detection', data:{'密度':'4.5×10⁶/mL','pH':'7.10','葡萄糖':'2.3 mM'}, note:'密度接近上限' },
  { id:15, date:'2026-03-05', day:4, type:'operation', data:{'操作':'取样','培养基总量':'12 mL','血清量':'1.2 mL'}, note:'准备传代' },
  // D5
  { id:16, date:'2026-03-06', day:5, type:'image',     data:{'颜色':'黄','汇合度':'90%','圆度':'0.85','光泽':'暗','大小':'16μm','形态':'聚集明显'}, note:'传代后细胞重新分散' },
  { id:17, date:'2026-03-06', day:5, type:'detection', data:{'密度':'1.5×10⁶/mL','pH':'7.32','葡萄糖':'7.9 mM'}, note:'传代后密度恢复' },
  { id:18, date:'2026-03-06', day:5, type:'operation', data:{'操作':'传代','代次':'P4','培养基总量':'10 mL','血清量':'1 mL'}, note:'1:3 稀释传代' },
])

// 按天的图片（路径引用 public/images/）
const dayImages = ref({
  0: ['/images/day0.jpg'],
  1: ['/images/day1.jpg'],
  2: ['/images/day2.jpg'],
  3: ['/images/day3.jpg'],
  4: ['/images/day4.jpg'],
  5: ['/images/day5.jpg'],
})

// 按天合并所有 sections
const sortedDays = computed(() => {
  const dayMap = {}
  for (const ev of events.value) {
    if (!dayMap[ev.day]) {
      dayMap[ev.day] = { day: ev.day, date: ev.date, sections: [], images: dayImages.value[ev.day] || [] }
    }
    const data = Object.fromEntries(Object.entries(ev.data).filter(([, v]) => v !== '' && v !== undefined))
    if (Object.keys(data).length > 0 || ev.note) {
      dayMap[ev.day].sections.push({ type: ev.type, data, note: ev.note })
    }
  }
  return Object.values(dayMap).sort((a, b) => a.day - b.day)
})

const addEvent = () => {
  const n = neo.value
  if (!n.date) return
  const typeOrder = ['image', 'detection', 'operation']
  const dataMap = { image: n.image, detection: n.detection, operation: n.operation }
  const noteMap = { image: n.imageNote, detection: n.detectionNote, operation: n.operationNote }
  for (const type of typeOrder) {
    const data = Object.fromEntries(Object.entries(dataMap[type]).filter(([, v]) => v !== '' && v !== undefined))
    if (Object.keys(data).length > 0 || noteMap[type]) {
      events.value.push({ id: Date.now() + Math.random(), date: n.date, day: n.day, type, data, note: noteMap[type] })
    }
  }
  if (n.images && n.images.length) {
    dayImages.value[n.day] = [...(dayImages.value[n.day] || []), ...n.images]
  }
  showDialog.value = false
}
</script>

<style scoped>
.timeline-wrap { height: 100%; display: flex; flex-direction: column; overflow: hidden; }
.toolbar { display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; margin-bottom: 8px; }
.tl-title { font-size: 13px; font-weight: 700; color: #1a1a2e; }
.add-btn { display: flex; align-items: center; gap: 4px; padding: 4px 12px; background: linear-gradient(135deg, #4a6cf7, #764ba2); color: #fff; border: none; border-radius: 20px; font-size: 12px; font-weight: 600; cursor: pointer; flex-shrink: 0; }
.add-btn:hover { opacity: 0.88; }
.axis-scroll { flex: 1; overflow-x: auto; overflow-y: hidden; min-height: 0; }
.axis-scroll::-webkit-scrollbar { height: 5px; }
.axis-scroll::-webkit-scrollbar-thumb { background: #dde3f0; border-radius: 3px; }
.axis-track { position: relative; display: flex; flex-direction: row; align-items: center; min-width: max-content; height: 100%; padding: 0 24px; }
.axis-line { position: absolute; left: 0; right: 0; top: 50%; height: 2px; background: linear-gradient(90deg, transparent 0%, #c8d4f8 5%, #c8d4f8 95%, transparent 100%); transform: translateY(-50%); pointer-events: none; z-index: 0; }
.axis-node { display: flex; flex-direction: column; align-items: center; width: 220px; flex-shrink: 0; height: 100%; justify-content: center; position: relative; z-index: 1; }
.node-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; background: #4a6cf7; box-shadow: 0 0 0 3px #fff, 0 0 0 5px rgba(74,108,247,0.25); z-index: 2; }
.node-time { display: flex; flex-direction: column; align-items: center; margin: 3px 0; }
.node-day { font-size: 13px; font-weight: 700; color: #4a6cf7; line-height: 1.2; }
.node-date { font-size: 12px; font-weight: 600; color: #606266; line-height: 1.2; }
.stem { width: 2px; height: 24px; background: #d0d9f5; flex-shrink: 0; }
.card-placeholder { flex: 1; min-height: 120px; width: 210px; }
.node-card { width: 210px; background: #fff; border: 1px solid #edf0fb; border-radius: 10px; padding: 10px 12px; box-shadow: 0 2px 8px rgba(74,108,247,0.07); flex-shrink: 0; flex: 1; max-height: 45%; overflow-y: auto; }
.node-card:hover { box-shadow: 0 4px 14px rgba(74,108,247,0.15); }
.node-card::-webkit-scrollbar { width: 3px; }
.node-card::-webkit-scrollbar-thumb { background: #dde3f0; border-radius: 2px; }
.card-hd { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.day-badge { font-size: 12px; font-weight: 800; color: #fff; background: linear-gradient(135deg, #4a6cf7, #764ba2); border-radius: 4px; padding: 2px 7px; }
.card-date { font-size: 11px; color: #c0c4cc; }
.card-imgs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.thumb { width: 52px; height: 52px; object-fit: cover; border-radius: 5px; border: 1px solid #e8ecf8; cursor: pointer; transition: transform 0.15s; }
.thumb:hover { transform: scale(1.08); border-color: #4a6cf7; }
.card-section { margin-bottom: 6px; }
.card-section:last-child { margin-bottom: 0; }
.section-label { display: flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 700; margin-bottom: 4px; }
.section-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.card-chips { display: flex; flex-wrap: wrap; gap: 3px; }
.chip { display: flex; align-items: center; gap: 2px; background: #f4f6ff; border-radius: 3px; padding: 2px 6px; }
.chip-k { font-size: 10px; color: #909399; }
.chip-v { font-size: 11px; font-weight: 600; color: #303133; }
.card-note { font-size: 11px; color: #aaa; margin-top: 3px; font-style: italic; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.preview-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.75); display: flex; align-items: center; justify-content: center; z-index: 2000; cursor: zoom-out; }
.preview-img { max-width: 90vw; max-height: 88vh; border-radius: 10px; box-shadow: 0 8px 40px rgba(0,0,0,0.5); object-fit: contain; }
.preview-close { position: absolute; top: 20px; right: 24px; background: rgba(255,255,255,0.15); border: none; color: #fff; font-size: 22px; width: 36px; height: 36px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.preview-close:hover { background: rgba(255,255,255,0.30); }
.dialog-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.35); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.dialog { background: #fff; border-radius: 12px; width: 440px; max-width: 94vw; max-height: 88vh; display: flex; flex-direction: column; box-shadow: 0 8px 32px rgba(0,0,0,0.18); }
.dialog-hd { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px 10px; border-bottom: 1px solid #f0f0f0; font-size: 15px; font-weight: 600; color: #1a1a2e; }
.dlg-close { background: none; border: none; font-size: 16px; color: #909399; cursor: pointer; }
.dialog-bd { flex: 1; overflow-y: auto; padding: 14px 18px; display: flex; flex-direction: column; gap: 8px; }
.f-section { font-size: 11px; font-weight: 700; color: #909399; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #f0f0f0; padding-bottom: 4px; margin-top: 4px; }
.f-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; }
.f-row { display: flex; flex-direction: column; gap: 3px; }
.f-row label { font-size: 12px; font-weight: 500; color: #606266; }
.f-input { border: 1px solid #e4e7ed; border-radius: 6px; padding: 5px 8px; font-size: 13px; color: #303133; outline: none; width: 100%; box-sizing: border-box; background: #fff; }
.f-input:focus { border-color: #4a6cf7; }
.img-upload-area { border: 2px dashed #d0d9f5; border-radius: 8px; min-height: 64px; display: flex; align-items: center; justify-content: center; cursor: pointer; padding: 8px; transition: border-color 0.15s; }
.img-upload-area:hover { border-color: #4a6cf7; }
.upload-hint { font-size: 12px; color: #c0c4cc; }
.upload-previews { display: flex; flex-wrap: wrap; gap: 6px; width: 100%; }
.upload-thumb-wrap { position: relative; width: 56px; height: 56px; }
.upload-thumb { width: 100%; height: 100%; object-fit: cover; border-radius: 6px; border: 1px solid #e8ecf8; }
.remove-img { position: absolute; top: -5px; right: -5px; width: 18px; height: 18px; border-radius: 50%; background: #f56c6c; color: #fff; border: none; font-size: 10px; cursor: pointer; display: flex; align-items: center; justify-content: center; line-height: 1; }
.dialog-ft { display: flex; justify-content: flex-end; gap: 8px; padding: 10px 18px 14px; border-top: 1px solid #f0f0f0; }
.btn-cancel { padding: 6px 16px; border: 1px solid #e4e7ed; border-radius: 6px; background: #fff; color: #606266; font-size: 13px; cursor: pointer; }
.btn-ok { padding: 6px 16px; border: none; border-radius: 6px; background: linear-gradient(135deg, #4a6cf7, #764ba2); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; }
</style> 