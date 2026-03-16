<template>
  <div class="dashboard-view">
    <el-card class="card" shadow="never">
      <div class="dashboard-header">
        <div>
          <h1 class="card-title">仪表盘</h1>
          <p class="card-desc">欢迎使用代码安全审计系统，开始您的安全审计之旅</p>
        </div>
        <el-tag type="success" effect="plain">系统运行中</el-tag>
      </div>
    </el-card>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-card-content">
            <div>
              <p class="stat-label">扫描项目</p>
              <p class="stat-value">{{ projects.length }}</p>
            </div>
            <el-icon :size="40" color="#409eff"><Folder /></el-icon>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-card-content">
            <div>
              <p class="stat-label">已完成审计</p>
              <p class="stat-value">{{ completedAudits }}</p>
            </div>
            <el-icon :size="40" color="#67c23a"><Check /></el-icon>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-card-content">
            <div>
              <p class="stat-label">发现漏洞</p>
              <p class="stat-value">{{ totalVulnerabilities }}</p>
            </div>
            <el-icon :size="40" color="#e6a23c"><WarningFilled /></el-icon>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-card-content">
            <div>
              <p class="stat-label">高危漏洞</p>
              <p class="stat-value high-risk">{{ highRiskVulnerabilities }}</p>
            </div>
            <el-icon :size="40" color="#f56c6c"><WarningFilled /></el-icon>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近任务 -->
    <el-card shadow="hover" class="card recent-card">
      <template #header>
        <div class="card-header">
          <span class="card-header-text">最近审计任务</span>
          <el-link type="primary" @click="$router.push('/results')">查看全部</el-link>
        </div>
      </template>

      <el-empty v-if="recentTasks.length === 0" description="暂无审计任务记录" class="empty-state">
        <el-button type="primary" @click="$router.push('/scan')">开始新审计</el-button>
      </el-empty>

      <el-table v-else :data="recentTasks" class="task-table">
        <el-table-column prop="projectPath" label="项目路径" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'completed' ? 'success' : (row.status === 'failed' ? 'danger' : 'warning')" size="small">
              {{ row.status === 'completed' ? '已完成' : (row.status === 'failed' ? '失败' : '进行中') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="timestamp" label="时间" width="180" :formatter="formatDateTime" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="auditTask(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script>
import { Folder, Check, WarningFilled } from '@element-plus/icons-vue'

export default {
  name: 'DashboardView',
  components: {
    Folder,
    Check,
    WarningFilled
  },
  data() {
    return {
      projects: [],
      completedAudits: 0,
      totalVulnerabilities: 0,
      highRiskVulnerabilities: 0,
      auditTasks: [],
      recentTasks: []
    }
  },
  mounted() {
    this.loadResults()
    this.invalidateRecentTasks()
  },
  methods: {
    formatDateTime(isoString) {
      const date = new Date(isoString)
      return date.toLocaleString('zh-CN')
    },
    invalidateRecentTasks() {
      this.recentTasks = this.auditTasks.slice(0, 5)
    },
    loadResults() {
      const results = localStorage.getItem('audit_results')
      if (results) {
        try {
          this.auditTasks = JSON.parse(results) || []
          this.updateDashboardStats()
          this.invalidateRecentTasks()
        } catch (e) {
          console.error('Failed to parse results:', e)
          this.auditTasks = []
        }
      } else {
        this.auditTasks = []
        this.recentTasks = []
      }
    },
    updateDashboardStats() {
      const results = this.auditTasks || []
      this.completedAudits = results.length

      let totalVulns = 0
      let highRisk = 0
      results.forEach(r => {
        const auditResults = r.audit_results || []
        auditResults.forEach(a => {
          totalVulns++
          if (a.confidence === 'high') highRisk++
        })
      })
      this.totalVulnerabilities = totalVulns
      this.highRiskVulnerabilities = highRisk
    },
    auditTask(task) {
      this.$router.push({ path: '/results', query: { search: task.projectPath } })
    }
  }
}
</script>

<style scoped>
.dashboard-view {
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

.card-desc {
  color: #6b7280;
  margin-top: 8px;
}

.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stats-row {
  margin-bottom: 24px;
}

.stat-card {
  height: 144px;
}

.stat-card-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stat-label {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
}

.high-risk {
  color: #dc2626;
}

.recent-card {
  margin-top: 32px;
}

.task-table :deep(th) {
  background: #f9fafb;
}

.empty-state {
  padding: 48px 24px;
}
</style>
