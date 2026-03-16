<template>
  <div class="audit-view">
    <el-card shadow="hover" class="card">
      <template #header>
        <span class="card-title">审计任务</span>
      </template>
      <el-form :model="auditForm" label-width="100px" max-width="600px">
        <el-form-item label="项目路径">
          <el-input v-model="auditForm.projectPath" placeholder="/path/to/your/project" />
        </el-form-item>
        <el-form-item label="最大轮数">
          <el-input-number v-model="auditForm.maxTurns" :min="1" :max="100" :step="1" />
        </el-form-item>
        <el-form-item label="审计类型">
          <el-select v-model="auditForm.auditType" placeholder="请选择">
            <el-option label="全部类型" value="all" />
            <el-option label="命令注入" value="command_injection" />
            <el-option label="路径遍历" value="path_traversal" />
          </el-select>
        </el-form-item>
        <el-alert type="warning" closable class="warning-alert">
          审计过程可能需要一些时间，请根据项目复杂度调整最大轮数。
        </el-alert>
        <el-form-item>
          <el-button type="danger" :loading="auditLoading" @click="handleStartAudit" class="full-width-button">
            <el-icon v-show="auditLoading" class="is-loading"><Loading /></el-icon>
            {{ auditLoading ? '审计中...' : '开始审计' }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 审计进度 -->
    <el-card v-if="currentAuditTask" shadow="hover" class="card">
      <template #header>
        <span class="card-title">审计进度</span>
      </template>
      <el-descriptions :column="2" border class="progress-descriptions">
        <el-descriptions-item label="功能">{{ currentAuditTask.funcName }}</el-descriptions-item>
        <el-descriptions-item label="文件">{{ currentAuditTask.filePath }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag type="success">{{ currentAuditTask.status }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <el-divider />
      <div class="progress-section">
        <div class="progress-header">
          <span class="progress-label">审计进度</span>
          <span class="progress-value">{{ auditProgress }}%</span>
        </div>
        <el-progress :percentage="auditProgress" :status="auditProgress === 100 ? 'success' : 'exception'" />
      </div>
      <el-card shadow="never" class="log-card">
        <template #header>
          <span class="log-title">审计日志</span>
        </template>
        <div class="log-content">
          <div v-for="log in auditLogs" :key="log.id" :class="['log-item', log.type]">
            <span class="log-time">[{{ log.timestamp.split(' ')[1] || '' }}]</span>
            <span class="log-text">{{ log.message }}</span>
          </div>
        </div>
      </el-card>
    </el-card>
  </div>
</template>

<script>
import { Loading } from '@element-plus/icons-vue'

export default {
  name: 'AuditView',
  components: {
    Loading
  },
  data() {
    return {
      auditForm: {
        projectPath: '',
        maxTurns: 50,
        auditType: 'all'
      },
      currentAuditTask: null,
      auditLoading: false,
      auditProgress: 0,
      auditLogs: [],
      baseUrl: '/api'
    }
  },
  mounted() {
    // 从路由参数获取审计函数
    const func = this.$route.query.func
    const project = this.$route.query.project
    if (func && project) {
      this.auditForm.projectPath = decodeURIComponent(project)
      this.auditFunction(decodeURIComponent(func))
    }
  },
  methods: {
    async handleStartAudit() {
      if (!this.auditForm.projectPath) {
        this.$message.warning('请输入项目路径')
        return
      }

      this.auditLoading = true
      this.auditLogs = []
      this.auditProgress = 0
      this.currentAuditTask = null

      try {
        const response = await fetch(`${this.baseUrl}/audit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.auditForm),
        })

        const result = await response.json()

        this.auditLogs = []
        this.auditLogs.push({
          id: Date.now(),
          timestamp: this.formatDateTime(new Date().toISOString()),
          message: `开始审计 ${result.data.total} 个函数`,
          type: 'info'
        })

        if (result.data && result.data.results) {
          result.data.results.forEach((r, index) => {
            r.timestamp = new Date().toISOString()
            r.status = 'completed'
            r.projectPath = this.auditForm.projectPath
            r.funcName = r.func_name || '-'
            r.filePath = r.file_path || '-'

            this.auditLogs.push({
              id: Date.now() + index,
              timestamp: this.formatDateTime(new Date().toISOString()),
              message: `完成: ${r.funcName} (${r.file_path})`,
              type: 'success'
            })
          })

          this.auditLogs.push({
            id: Date.now() + 1000,
            timestamp: this.formatDateTime(new Date().toISOString()),
            message: `审计完成，共 ${result.data.total} 个函数`,
            type: 'success'
          })

          const allResults = JSON.parse(localStorage.getItem('audit_results') || '[]')
          allResults.unshift(...result.data.results)
          localStorage.setItem('audit_results', JSON.stringify(allResults))

          this.$message.success(`审计完成，共审计 ${result.data.total} 个函数`)
        }
      } catch (error) {
        console.error('审计失败:', error)
        this.$message.error('审计失败: ' + error.message)
      } finally {
        this.auditLoading = false
      }
    },
    async auditFunction(funcName) {
      this.auditLoading = true
      this.currentAuditTask = { funcName: funcName, filePath: '*', status: 'running' }
      try {
        const response = await fetch(`${this.baseUrl}/audit/${encodeURIComponent(funcName)}?project_path=${encodeURIComponent(this.auditForm.projectPath)}`)
        const result = await response.json()
        if (result.data && result.data.result) {
          this.currentAuditTask = {
            funcName: funcName,
            filePath: result.data.result.file_path || '*',
            status: result.data.status || 'completed'
          }
          this.auditLogs.push({
            id: Date.now(),
            timestamp: this.formatDateTime(new Date().toISOString()),
            message: `审计完成: ${funcName}`,
            type: 'info'
          })
        }
        this.$message.success('审计完成')
      } catch (error) {
        console.error('审计失败:', error)
        this.auditLogs.push({
          id: Date.now(),
          timestamp: this.formatDateTime(new Date().toISOString()),
          message: `审计失败: ${error.message}`,
          type: 'error'
        })
        this.currentAuditTask = null
        this.$message.error('审计失败: ' + error.message)
      } finally {
        this.auditLoading = false
      }
    },
    formatDateTime(isoString) {
      const date = new Date(isoString)
      return date.toLocaleString('zh-CN')
    }
  }
}
</script>

<style scoped>
.audit-view {
  animation: fadeIn 0.3s;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.card {
  margin-bottom: 24px;
  border: 1px solid #e5e7eb;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
}

.full-width-button {
  width: 100%;
}

.warning-alert {
  margin: 16px 0;
}

.progress-section {
  margin: 20px 0;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.progress-label {
  font-size: 14px;
  color: #4b5563;
}

.progress-value {
  font-size: 14px;
  color: #4f46e5;
}

.log-card :deep(.el-card__header) {
  padding: 12px 20px;
}

.log-title {
  font-size: 14px;
  font-weight: 600;
  color: #6b7280;
}

.log-content {
  max-height: 256px;
  overflow: auto;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 12px;
}

.log-item {
  padding: 4px 0;
  line-height: 1.5;
}

.log-item.info .log-text {
  color: #374151;
}

.log-item.success .log-text {
  color: #22c55e;
}

.log-item.warning .log-text {
  color: #eab308;
}

.log-item.error .log-text {
  color: #ef4444;
}

.log-time {
  opacity: 0.5;
  margin-right: 8px;
}
</style>
