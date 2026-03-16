<template>
  <div class="scan-view">
    <!-- 项目卡片列表 -->
    <el-card shadow="hover" class="card">
      <template #header>
        <div class="card-header">
          <span class="card-header-text">项目列表</span>
          <el-button type="primary" size="small" @click="showAddDialog = true">
            <el-icon><Plus /></el-icon>
            新建项目
          </el-button>
        </div>
      </template>

      <!-- 空状态 -->
      <el-empty v-if="projects.length === 0" description="暂无项目，点击新建项目按钮添加" class="empty-state">
        <el-button type="primary" @click="showAddDialog = true">新建项目</el-button>
      </el-empty>

      <!-- 项目卡片网格 -->
      <el-row v-else :gutter="20">
        <el-col v-for="project in projects" :key="project.id" :span="8">
          <div class="project-card">
            <div class="project-card-header">
              <div class="project-name">{{ project.project_name }}</div>
              <div class="project-type">{{ project.project_type }}</div>
            </div>
            <div class="project-path">{{ project.project_path }}</div>
            <div class="project-time">最后更新: {{ formatDateTime(project.updated_at) }}</div>
            <div class="project-actions">
              <el-button type="primary" link size="small" @click="scanProject(project)">
                <el-icon><Folder /></el-icon>
                扫描
              </el-button>
              <el-button type="warning" link size="small" @click="auditProject(project)">
                <el-icon><Tickets /></el-icon>
                审计
              </el-button>
              <el-button type="danger" link size="small" @click="deleteProject(project.id)">
                <el-icon><Delete /></el-icon>
                删除
              </el-button>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 新建项目对话框 -->
    <el-dialog v-model="showAddDialog" title="新建项目" width="500px" :close-on-click-modal="false">
      <el-form :model="addForm" :rules="addRules" label-width="100px" ref="addFormRef">
        <el-form-item label="项目名称" prop="project_name">
          <el-input v-model="addForm.project_name" placeholder="请输入项目名称" />
        </el-form-item>
        <el-form-item label="代码文件" prop="uploaded_file">
          <el-upload
            ref="uploadRef"
            action="/api/upload"
            :auto-upload="false"
            :show-file-list="true"
            :on-change="handleFileChange"
            :limit="1"
            accept=".zip,.tar,.tar.gz,.tgz"
          >
            <template #trigger>
              <el-button type="primary">
                <el-icon><Upload /></el-icon>
                选择压缩包
              </el-button>
            </template>
            <template #tip>
              <div class="el-upload__tip">支持 .zip, .tar, .tar.gz 等压缩格式</div>
            </template>
          </el-upload>
          <div v-if="addForm.project_name" class="file-info">
            已选择: {{ addForm.project_name }}
          </div>
        </el-form-item>
        <el-form-item label="项目路径" prop="project_path">
          <el-input v-model="addForm.project_path" placeholder="例如: /path/to/your/project">
            <template #prefix>
              <el-icon><Folder /></el-icon>
            </template>
          </el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="handleCreateProject">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { Plus, Folder, Delete, Upload, Tickets } from '@element-plus/icons-vue'

export default {
  name: 'ScanView',
  components: {
    Plus,
    Folder,
    Delete,
    Upload,
    Tickets
  },
  data() {
    return {
      projects: [],
      loading: false,
      showAddDialog: false,
      addForm: {
        project_name: '',
        project_path: '',
        uploaded_file: null
      },
      addRules: {
        project_name: [
          { required: true, message: '请输入项目名称', trigger: 'blur' },
          { min: 2, max: 50, message: '项目名称长度在 2 到 50 个字符', trigger: 'blur' }
        ],
        project_path: [
          { required: true, message: '请输入项目路径', trigger: 'blur' }
        ]
      },
      selectedFile: null,
      addLoading: false
    }
  },
  mounted() {
    this.loadProjects()
  },
  methods: {
    async loadProjects() {
      this.loading = true
      try {
        const token = localStorage.getItem('token')
        const response = await fetch('/api/projects', {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })
        const result = await response.json()
        if (result.status === 'success') {
          this.projects = result.data.projects || []
        } else {
          this.$message.error(result.data?.message || '获取项目列表失败')
        }
      } catch (error) {
        console.error('获取项目列表失败:', error)
        this.$message.error('获取项目列表失败: ' + error.message)
      } finally {
        this.loading = false
      }
    },
    formatDateTime(isoString) {
      if (!isoString) return '-'
      const date = new Date(isoString)
      return date.toLocaleString('zh-CN')
    },
    handleFileChange(file) {
      // 保存文件信息用于后续上传
      this.selectedFile = file
    },
    async handleCreateProject() {
      this.$refs.addFormRef.validate(async (valid) => {
        if (!valid) return

        this.addLoading = true
        try {
          // 先创建项目记录
          const token = localStorage.getItem('token')
          const response = await fetch('/api/projects', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
              project_name: this.addForm.project_name,
              project_path: this.addForm.project_path,
              project_type: 'c'
            })
          })

          const result = await response.json()
          if (result.status === 'success') {
            this.$message.success('项目创建成功')
            this.showAddDialog = false
            this.addForm = { project_name: '', project_path: '', uploaded_file: null }
            this.selectedFile = null
            this.loadProjects()
          } else {
            this.$message.error(result.data?.message || '创建项目失败')
          }
        } catch (error) {
          console.error('创建项目失败:', error)
          this.$message.error('创建项目失败: ' + error.message)
        } finally {
          this.addLoading = false
        }
      })
    },
    async deleteProject(projectId) {
      this.$confirm('确定要删除该项目吗？', '提示', {
        type: 'warning'
      }).then(async () => {
        try {
          const token = localStorage.getItem('token')
          const response = await fetch(`/api/projects/${projectId}`, {
            method: 'DELETE',
            headers: {
              'Authorization': `Bearer ${token}`
            }
          })

          const result = await response.json()
          if (result.status === 'success') {
            this.$message.success('删除成功')
            this.loadProjects()
          } else {
            this.$message.error(result.data?.message || '删除失败')
          }
        } catch (error) {
          console.error('删除失败:', error)
          this.$message.error('删除失败: ' + error.message)
        }
      }).catch(() => {})
    },
    scanProject(project) {
      this.$router.push({
        path: '/scan',
        query: { project_path: project.project_path, project_name: project.project_name }
      })
    },
    auditProject(project) {
      this.$router.push({
        path: '/audit',
        query: { project_path: project.project_path }
      })
    }
  }
}
</script>

<style scoped>
.scan-view {
  animation: fadeIn 0.3s;
}

.card {
  margin-bottom: 24px;
  border: 1px solid #e5e7eb;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-header-text {
  font-weight: 600;
}

.empty-state {
  padding: 60px 24px;
}

/* 项目卡片样式 */
.project-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.3s;
  border: 1px solid #e5e7eb;
}

.project-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
}

.project-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f3f4f6;
}

.project-name {
  font-weight: 600;
  font-size: 16px;
  color: #1f2937;
  flex: 1;
}

.project-type {
  background: #f3f4f6;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  color: #6b7280;
  text-transform: uppercase;
}

.project-path {
  font-size: 13px;
  color: #6b7280;
  word-break: break-all;
  font-family: 'Courier New', monospace;
  background: #f9fafb;
  padding: 8px;
  border-radius: 4px;
  margin: 12px 0;
}

.project-time {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 12px;
}

.project-actions {
  display: flex;
  gap: 8px;
}

.project-actions :deep(.el-button) {
  font-size: 12px;
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
</style>
