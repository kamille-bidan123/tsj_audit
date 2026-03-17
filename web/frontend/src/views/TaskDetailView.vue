<template>
  <div class="task-detail-view">
    <!-- 任务头信息 -->
    <el-card shadow="never" class="card">
      <div class="task-header">
        <div>
          <h1 class="card-title">审计任务详情</h1>
          <p class="card-desc">
            项目: <span class="project-path">{{ task?.project_path }}</span>
            <span v-if="task?.current_phase"> | 阶段: {{ phaseMap[task.current_phase] || task.current_phase }}</span>
          </p>
        </div>
        <div class="task-actions">
          <el-tag :type="taskStatusType" effect="plain">{{ taskStatusText }}</el-tag>
          <el-button v-if="task && task.status === 'running'" type="primary" size="small" @click="refreshStatus">
            刷新状态
          </el-button>
        </div>
      </div>

      <!-- 进度条 -->
      <div class="progress-section">
        <div class="progress-header">
          <el-space :size="20">
            <div v-for="(phase, key) in phaseList" :key="key" class="phase-item" :class="{ active: phase.active, completed: phase.completed }">
              <div class="phase-icon">
                <el-icon :size="16" v-if="phase.completed"><Check /></el-icon>
                <el-icon :size="16" v-else-if="phase.active"><Warning /></el-icon>
                <el-icon :size="16" v-else><Warning /></el-icon>
              </div>
              <span class="phase-name">{{ phase.name }}</span>
              <span class="phase-status" :style="{ color: phase.statusColor }">{{ phase.statusText }}</span>
            </div>
          </el-space>
        </div>
        <el-progress :percentage="task?.progress || 0" :status="taskStatus === 'failed' ? 'exception' : null" />
        <div class="progress-text">{{ task?.progress || 0 }}% - {{ task?.current_phase === 'scan' ? '正在扫描项目...' : (task?.current_phase === 'trace' ? '正在分析污点追踪...' : (task?.current_phase === 'report' ? '正在生成报告...' : '准备中')) }}</div>
      </div>
    </el-card>

    <!-- 详细信息 tabs -->
    <el-tabs v-model="activeTab" class="card" v-loading="loading">
      <!-- 汇总 -->
      <el-tab-pane label="汇总" name="overview">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务ID">{{ task?.task_id }}</el-descriptions-item>
          <el-descriptions-item label="项目路径">{{ task?.project_path }}</el-descriptions-item>
          <el-descriptions-item label="扫描脚本">{{ task?.scan_path }}</el-descriptions-item>
          <el-descriptions-item label="最大轮数">{{ task?.max_turns }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(task?.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">
            {{ task?.completed_at ? formatDateTime(task?.completed_at) : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="总函数数">{{ task?.total_functions }}</el-descriptions-item>
          <el-descriptions-item label="已完成">{{ task?.completed_functions }}</el-descriptions-item>
        </el-descriptions>
      </el-tab-pane>

      <!-- 对话过程 -->
      <el-tab-pane label="对话过程" name="conversation">
        <div class="conversation-container">
          <div v-for="log in logs" :key="log.id" class="conversation-item" :class="log.role">
            <div class="conversation-header">
              <el-icon :size="16" :color="roleColor(log.role)">
                <User v-if="log.role === 'user'" />
                <ChatLineRound v-if="log.role === 'assistant'" />
                <Tools v-if="log.role === 'tool'" />
                <Warning v-if="log.role === 'error'" />
                <InfoFilled v-if="log.role === 'system'" />
              </el-icon>
              <span class="role-badge">{{ roleText(log.role) }}</span>
              <span class="timestamp">{{ formatDateTime(log.timestamp) }}</span>
            </div>
            <div class="conversation-content">
              <el-text v-if="log.content" :truncated="false">{{ log.content }}</el-text>
              <el-text v-if="log.func_name" type="info" size="small" style="display: block; margin-top: 8px;">
                函数: {{ log.func_name }}
              </el-text>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 审计结果 -->
      <el-tab-pane label="审计结果" name="results">
        <el-empty v-if="!task || (traces && traces.length === 0)" description="暂无审计结果" class="empty-state" />
        <div v-else class="results-list">
          <el-card v-for="trace in traces" :key="trace.id" shadow="hover" class="result-item">
            <div class="result-header">
              <div class="result-title">
                <el-icon><Folder /></el-icon>
                <span class="func-name">{{ trace.func_name }}</span>
              </div>
              <el-tag size="small">{{ trace.file_path }}</el-tag>
            </div>
            <div class="result-meta">
              <span class="meta-item">行号: {{ trace.start_line }}-{{ trace.end_line }}</span>
              <span class="meta-item">漏洞数: {{ trace.total_vulnerabilities }}</span>
              <el-tag v-if="trace.total_vulnerabilities > 0" type="danger" size="small">发现漏洞</el-tag>
            </div>
            <div class="result-body" v-if="trace.audit_results && trace.audit_results.length">
              <div v-for="audit in trace.audit_results" :key="audit.id" class="audit-item" :class="audit.is_vulnerable ? 'vulnerable' : 'safe'">
                <div class="audit-header">
                  <span class="audit-type">{{ audit.vulnerability_type }}</span>
                  <el-tag size="small" :type="audit.is_vulnerable ? 'danger' : 'success'">
                    {{ audit.is_vulnerable ? '漏洞' : '安全' }}
                  </el-tag>
                  <span class="confidence">{{ audit.confidence }}</span>
                </div>
                <div class="audit-content">
                  <p class="description">{{ audit.description }}</p>
                  <el-collapse v-if="audit.recommendation">
                    <el-collapse-item name="recommendation" title="修复建议">
                      <p>{{ audit.recommendation }}</p>
                    </el-collapse-item>
                  </el-collapse>
                </div>
                <div v-if="audit.code_map && audit.code_map.length" class="code-map">
                  <el-text type="info" size="small">代码上下文:</el-text>
                  <div v-for="ctx in audit.code_map" :key="ctx.function_name" class="code-context">
                    <span class="ctx-func">{{ ctx.function_name }}</span>
                    <span class="ctx-file">{{ ctx.file_path }}</span>
                    <span class="ctx-lines">{{ ctx.line_start }}-{{ ctx.line_end }}</span>
                  </div>
                </div>
              </div>
            </div>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- PoC 结果 -->
      <el-tab-pane label="PoC 结果" name="exploit">
        <el-empty v-if="!exploits || exploits.length === 0" description="暂无 PoC 结果" class="empty-state" />
        <div v-else class="exploits-list">
          <el-card v-for="exploit in exploits" :key="exploit.id" shadow="hover" class="exploit-item">
            <div class="exploit-header">
              <span class="exploit-type">{{ exploit.vulnerability_type }}</span>
              <el-tag :type="exploit.success ? 'success' : 'info'" size="small">
                {{ exploit.success ? '成功' : '失败' }}
              </el-tag>
            </div>
            <div class="exploit-content">
              <div v-if="exploit.poc_command" class="poc-command">
                <el-text type="info" size="small">命令:</el-text>
                <code>{{ exploit.poc_command }}</code>
              </div>
              <div v-if="exploit.output" class="poc-output">
                <el-text type="info" size="small">输出:</el-text>
                <pre>{{ exploit.output }}</pre>
              </div>
              <div v-if="exploit.error" class="poc-error">
                <el-text type="danger" size="small">错误:</el-text>
                <pre>{{ exploit.error }}</pre>
              </div>
            </div>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
import { User, ChatLineRound, Tools, Warning, InfoFilled, Folder, Check } from '@element-plus/icons-vue'

export default {
  name: 'TaskDetailView',
  components: {
    User, ChatLineRound, Tools, Warning, InfoFilled, Folder, Check
  },
  data() {
    return {
      task: null,
      traces: [],
      exploits: [],
      logs: [],
      loading: false,
      activeTab: 'overview',
      eventSource: null,
      phaseMap: {
        scan: '扫描阶段',
        trace: '追踪阶段',
        audit: '审计阶段',
        exploit: '利用阶段',
        report: '报告阶段'
      },
      phaseList: []
    }
  },
  computed: {
    taskStatus() {
      return this.task?.status || 'pending'
    },
    taskStatusType() {
      if (this.taskStatus === 'completed') return 'success'
      if (this.taskStatus === 'failed') return 'danger'
      if (this.taskStatus === 'running') return 'warning'
      return ''
    },
    taskStatusText() {
      if (this.taskStatus === 'completed') return '已完成'
      if (this.taskStatus === 'failed') return '失败'
      if (this.taskStatus === 'running') return '进行中'
      return '等待中'
    }
  },
  watch: {
    '$route.params.id': {
      immediate: true,
      handler() {
        this.loadTask()
      }
    }
  },
  mounted() {
    this.loadTask()
  },
  beforeUnmount() {
    if (this.eventSource) {
      this.eventSource.close()
    }
  },
  methods: {
    async loadTask() {
      const taskId = this.$route.params.id
      this.loading = true
      try {
        const token = localStorage.getItem('token')
        const response = await fetch(`/api/tasks/${taskId}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        const result = await response.json()
        if (result.status === 'success') {
          this.task = result.task
          this.traces = []
          this.exploits = []
          this.logs = result.logs || []

          // 加载详细结果
          await this.loadResults(taskId)
          this.updatePhaseList()
        }
      } catch (error) {
        this.$message.error('加载任务失败: ' + error.message)
      } finally {
        this.loading = false
      }
    },
    async loadResults(taskId) {
      try {
        const token = localStorage.getItem('token')
        const response = await fetch(`/api/results/${taskId}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        const result = await response.json()
        if (result.status === 'success') {
          this.traces = result.data?.traces || []
          this.exploits = []
          // 提取所有 exploit 结果
          this.traces.forEach(trace => {
            if (trace.exploit_results) {
              this.exploits.push(...trace.exploit_results)
            }
          })
        }
      } catch (error) {
        console.error('加载结果失败:', error)
      }
    },
    updatePhaseList() {
      if (!this.task) return
      const phases = ['scan', 'trace', 'audit', 'exploit', 'report']
      const statusMap = {
        scan_status: 'scan',
        trace_status: 'trace',
        audit_status: 'audit',
        exploit_status: 'exploit',
        report_status: 'report'
      }
      const phaseNames = {
        scan: '扫描',
        trace: '追踪',
        audit: '审计',
        exploit: '利用',
        report: '报告'
      }
      this.phaseList = phases.map(phase => {
        const statusKey = statusMap[`${phase}_status`]
        const status = this.task[statusKey] || (phase === 'scan' && this.task.current_phase === 'scan' && this.task.status === 'running' ? 'running' : null)
        const currentPhase = this.task.current_phase === phase
        const completedPhase = status === 'completed'
        return {
          name: phaseNames[phase],
          active: currentPhase && this.task.status === 'running',
          completed: completedPhase,
          statusText: status === 'completed' ? '完成' : (status === 'running' ? '进行中' : '等待'),
          statusColor: status === 'completed' ? '#67c23a' : (status === 'running' ? '#e6a23c' : '#909399')
        }
      })
    },
    async refreshStatus() {
      await this.loadTask()
      this.startStreaming()
    },
    startStreaming() {
      if (this.eventSource) this.eventSource.close()
      const taskId = this.$route.params.id
      const token = localStorage.getItem('token')
      this.eventSource = new EventSource(`/api/tasks/${taskId}/stream`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      this.eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'final') {
            this.task = data.task
            this.logs = data.logs || []
            this.updatePhaseList()
            this.eventSource.close()
          } else if (data.type === 'message' && data.log) {
            this.logs.push(data.log)
          } else if (data.type === 'progress' && data.phase) {
            this.updatePhaseList()
          }
        } catch (e) {
          console.error('解析 SSE 消息失败:', e)
        }
      }
      this.eventSource.onerror = (error) => {
        console.error('SSE 连接错误:', error)
        this.eventSource.close()
      }
    },
    formatDateTime(isoString) {
      if (!isoString) return '-'
      const date = new Date(isoString)
      return date.toLocaleString('zh-CN')
    },
    roleColor(role) {
      const colors = {
        user: '#409eff',
        assistant: '#67c23a',
        tool: '#e6a23c',
        error: '#f56c6c',
        system: '#909399'
      }
      return colors[role] || '#909399'
    },
    roleText(role) {
      const texts = {
        user: '用户',
        assistant: 'AI',
        tool: '工具',
        error: '错误',
        system: '系统'
      }
      return texts[role] || role
    }
  }
}
</script>

<style scoped>
.task-detail-view {
  animation: fadeIn 0.3s;
}

.card {
  margin-bottom: 24px;
  border: 1px solid #e5e7eb;
}

.task-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.project-path {
  font-family: 'Courier New', monospace;
  color: #409eff;
  font-weight: 500;
}

.task-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.progress-section {
  padding: 16px;
  background: #f9fafb;
  border-radius: 8px;
}

.progress-header {
  display: flex;
  gap: 20px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.phase-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: white;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  transition: all 0.3s;
}

.phase-item.active {
  border-color: #409eff;
  background: #ecf5ff;
}

.phase-item.completed {
  border-color: #67c23a;
  background: #f0f9ff;
}

.phase-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.phase-name {
  font-weight: 500;
  font-size: 13px;
}

.phase-status {
  font-size: 12px;
}

.progress-text {
  margin-top: 8px;
  font-size: 13px;
  color: #6b7280;
  text-align: center;
}

.conversation-container {
  max-height: 600px;
  overflow-y: auto;
}

.conversation-item {
  padding: 16px;
  margin-bottom: 12px;
  border-radius: 12px;
  border-left: 4px solid;
}

.conversation-item.user {
  background: #f9fafb;
  border-left-color: #409eff;
}

.conversation-item.assistant {
  background: #f0f9ff;
  border-left-color: #67c23a;
}

.conversation-item.tool {
  background: #fefce8;
  border-left-color: #e6a23c;
}

.conversation-item.error {
  background: #fef2f2;
  border-left-color: #f56c6c;
}

.conversation-item.system {
  background: #f3f4f6;
  border-left-color: #909399;
}

.conversation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.role-badge {
  padding: 2px 8px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
  font-size: 12px;
}

.timestamp {
  font-size: 12px;
  color: #9ca3af;
}

.conversation-content {
  font-size: 14px;
  line-height: 1.6;
  color: #374151;
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-item {
  transition: all 0.3s;
}

.result-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.result-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 16px;
  color: #1f2937;
}

.func-name {
  color: #409eff;
}

.result-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #6b7280;
}

.audit-item {
  padding: 12px;
  margin-top: 12px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  background: white;
}

.audit-item.vulnerable {
  border-color: #fca5a5;
  background: #fef2f2;
}

.audit-item.safe {
  border-color: #86efac;
  background: #f0fdf4;
}

.audit-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.audit-type {
  font-weight: 600;
  font-size: 14px;
  color: #1f2937;
}

.confidence {
  font-size: 12px;
  color: #6b7280;
}

.audit-content .description {
  color: #4b5563;
  line-height: 1.6;
  margin-bottom: 8px;
}

.code-map {
  margin-top: 8px;
  padding: 8px;
  background: #f9fafb;
  border-radius: 6px;
}

.code-context {
  display: flex;
  gap: 8px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}

.ctx-func {
  color: #409eff;
  font-weight: 500;
}

.ctx-file {
  flex: 1;
}

exploits-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.exploit-item {
  transition: all 0.3s;
}

.exploit-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.exploit-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.exploit-type {
  font-weight: 600;
  font-size: 14px;
  color: #1f2937;
}

.poc-command code {
  display: block;
  padding: 8px;
  background: #1e293b;
  color: #e5e7eb;
  border-radius: 6px;
  font-size: 13px;
  margin: 8px 0;
}

.poc-output, .poc-error {
  margin-top: 8px;
}

.poc-output pre, .poc-error pre {
  padding: 8px;
  background: #f3f4f6;
  border-radius: 6px;
  font-size: 12px;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}

.empty-state {
  padding: 60px 24px;
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

:deep(.el-descriptions__label) {
  width: 120px;
}
:deep(.el-collapse-item__header) {
  background: #f9fafb;
}
</style>
