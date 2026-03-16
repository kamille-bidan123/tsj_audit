<template>
  <div class="results-view">
    <el-card shadow="hover" class="card">
      <template #header>
        <span class="card-title">审计结果</span>
      </template>
      <div class="filters-row">
        <el-select v-model="resultFilter.status" placeholder="筛选状态" class="filter-select">
          <el-option label="全部状态" value="all" />
          <el-option label="有漏洞" value="vulnerable" />
          <el-option label="安全" value="safe" />
        </el-select>
        <el-select v-model="resultFilter.type" placeholder="筛选类型" class="filter-select">
          <el-option label="全部类型" value="all" />
          <el-option label="命令注入" value="command_injection" />
          <el-option label="路径遍历" value="path_traversal" />
        </el-select>
        <el-input v-model="searchQuery" placeholder="搜索功能名称、文件路径..." class="search-input" clearable />
        <el-button @click="handleExport" icon="Download" class="export-btn">导出结果</el-button>
      </div>

      <!-- 结果统计 -->
      <el-row :gutter="20" class="stats-row">
        <el-col :span="8">
          <el-card shadow="never" class="stat-card-linear">
            <p class="stat-label-light">总共审计</p>
            <p class="stat-value-light">{{ filteredResults.length }}</p>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never" class="stat-card-linear vuln-card">
            <p class="stat-label-light">发现漏洞</p>
            <p class="stat-value-light">{{ vulnCount }}</p>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never" class="stat-card-linear safe-card">
            <p class="stat-label-light">安全函数</p>
            <p class="stat-value-light">{{ safeCount }}</p>
          </el-card>
        </el-col>
      </el-row>

      <!-- 结果列表 -->
      <el-card v-for="(result, index) in filteredResults" :key="index" shadow="hover" class="result-card">
        <template #header>
          <div class="result-header">
            <div class="result-info">
              <span class="result-name">{{ result.func_name }}</span>
              <el-tag :type="result.audit_results.length > 0 ? 'danger' : 'success'" size="small">
                {{ result.audit_results.length > 0 ? result.audit_results.length + ' 个漏洞' : '未发现漏洞' }}
              </el-tag>
              <el-tag type="info" size="small">{{ result.file_path }}</el-tag>
            </div>
            <el-button @click="toggleResultDetails(index)" icon="ArrowDown" text class="expand-btn">
              {{ expandedResults.includes(index) ? '收起' : '展开' }}
            </el-button>
          </div>
        </template>
        <div class="result-content">
          <div class="file-location">
            <span class="label">文件位置:</span>
            <code class="code">{{ result.file_path }}:{{ result.start_line }}-{{ result.end_line }}</code>
          </div>
          <el-card v-if="result.code_snippet" shadow="never" class="code-card">
            <pre class="code-snippet">{{ result.code_snippet }}</pre>
          </el-card>
          <div v-if="expandedResults.includes(index)">
            <el-card v-if="result.audit_results.length > 0" shadow="hover" class="audit-card" v-for="(audit, idx) in result.audit_results" :key="idx">
              <div class="audit-header">
                <el-tag :type="'danger'" size="small">{{ formatVulnType(audit.vulnerability_type) }}</el-tag>
                <el-tag :type="audit.confidence === 'high' ? 'danger' : (audit.confidence === 'medium' ? 'warning' : 'success')" size="small">
                  {{ audit.confidence === 'high' ? '高风险' : (audit.confidence === 'medium' ? '中风险' : '低风险') }}
                </el-tag>
              </div>
              <el-descriptions :column="1" size="small" class="audit-descriptions">
                <el-descriptions-item label="问题描述">
                  <p class="desc-text">{{ audit.description }}</p>
                </el-descriptions-item>
                <el-descriptions-item label="污点流向">
                  <code class="flow-code">{{ audit.taint_flow }}</code>
                </el-descriptions-item>
                <el-descriptions-item label="修复建议">
                  <p class="recommendation">{{ audit.recommendation }}</p>
                </el-descriptions-item>
              </el-descriptions>
            </el-card>
            <el-empty v-else description="未发现安全漏洞" class="empty-state" />
          </div>
        </div>
      </el-card>
      <el-empty v-if="filteredResults.length === 0" description="未找到匹配的审计结果" class="empty-state" />
    </el-card>
  </div>
</template>

<script>
import { Download, ArrowDown } from '@element-plus/icons-vue'

export default {
  name: 'ResultsView',
  components: {
    Download,
    ArrowDown
  },
  data() {
    return {
      allResults: [],
      resultFilter: {
        status: 'all',
        type: 'all'
      },
      searchQuery: '',
      expandedResults: []
    }
  },
  computed: {
    filteredResults() {
      return this.allResults.filter(r => {
        if (this.resultFilter.status === 'vulnerable' && r.audit_results.length === 0) return false
        if (this.resultFilter.status === 'safe' && r.audit_results.length > 0) return false
        if (this.resultFilter.type !== 'all') {
          const hasType = r.audit_results.some(a => a.vulnerability_type === this.resultFilter.type)
          if (this.resultFilter.status === 'all' && !hasType) return false
          if (this.resultFilter.status === 'vulnerable' && !hasType) return false
        }
        if (this.searchQuery) {
          const query = this.searchQuery.toLowerCase()
          const matches = r.func_name.toLowerCase().includes(query) || (r.file_path && r.file_path.toLowerCase().includes(query))
          if (!matches) return false
        }
        return true
      })
    },
    vulnCount() {
      return this.filteredResults.filter(r => r.audit_results.length > 0).length
    },
    safeCount() {
      return this.filteredResults.filter(r => r.audit_results.length === 0).length
    }
  },
  mounted() {
    this.loadResults()
    // 从路由查询参数获取搜索词
    const search = this.$route.query.search
    if (search) {
      this.searchQuery = decodeURIComponent(search)
    }
  },
  watch: {
    searchQuery() {
      this.applyFilters()
    },
    resultFilter() {
      this.applyFilters()
    }
  },
  methods: {
    loadResults() {
      const results = localStorage.getItem('audit_results')
      if (results) {
        try {
          this.allResults = JSON.parse(results) || []
        } catch (e) {
          console.error('Failed to parse results:', e)
          this.allResults = []
        }
      } else {
        this.allResults = []
      }
    },
    applyFilters() {
      // 触发 filteredResults 计算
    },
    toggleResultDetails(index) {
      const idx = this.expandedResults.indexOf(index)
      if (idx > -1) {
        this.expandedResults.splice(idx, 1)
      } else {
        this.expandedResults.push(index)
      }
    },
    handleExport() {
      const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(this.filteredResults, null, 2))
      const downloadAnchorNode = document.createElement('a')
      downloadAnchorNode.setAttribute("href", dataStr)
      downloadAnchorNode.setAttribute("download", "audit_results.json")
      document.body.appendChild(downloadAnchorNode)
      downloadAnchorNode.click()
      downloadAnchorNode.remove()
      this.$message.success('导出成功')
    },
    formatVulnType(type) {
      const types = {
        'command_injection': '命令注入',
        'path_traversal': '路径遍历',
        'sql_injection': 'SQL注入',
        'xss': 'XSS攻击'
      }
      return types[type] || type
    }
  }
}
</script>

<style scoped>
.results-view {
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

.filters-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 24px;
}

.filter-select {
  width: 150px;
}

.search-input {
  width: 250px;
}

.stats-row {
  margin-bottom: 24px;
}

.stat-card-linear {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.stat-card-linear.vuln-card {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.stat-card-linear.safe-card {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.stat-label-light {
  color: rgba(255, 255, 255, 0.8);
  font-size: 14px;
  margin-bottom: 4px;
}

.stat-value-light {
  font-size: 32px;
  font-weight: bold;
}

.result-card {
  margin-bottom: 16px;
  border: 1px solid #e5e7eb;
}

.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.result-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.result-name {
  font-weight: 600;
}

.expand-btn {
  padding: 8px;
}

.result-content {
  padding-top: 20px;
}

.file-location {
  margin-bottom: 16px;
}

.file-location .label {
  font-size: 12px;
  color: #6b7280;
  margin-right: 8px;
}

.code {
  background: #f3f4f6;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 12px;
  margin-left: 8px;
}

.code-card {
  background: #1f2937;
  color: #d1d5db;
  margin-bottom: 16px;
}

.code-snippet {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-wrap: break-word;
  line-height: 1.5;
}

.audit-card {
  margin-bottom: 16px;
}

.audit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.audit-descriptions :deep(.el-descriptions__label) {
  width: 100px;
}

.desc-text {
  color: #374151;
  line-height: 1.6;
}

.flow-code {
  background: #f3f4f6;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 12px;
}

.recommendation {
  color: #374151;
  line-height: 1.6;
}

.empty-state {
  padding: 48px 24px;
}
</style>
