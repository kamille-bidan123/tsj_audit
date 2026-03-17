<template>
  <div class="skills-view">
    <!-- 头部 -->
    <el-card shadow="never" class="card">
      <div class="skills-header">
        <div>
          <h1 class="card-title">Skills 管理</h1>
          <p class="card-desc">创建和管理 Agent Skills，可以公开让其他用户使用</p>
        </div>
        <el-button type="primary" size="small" @click="showAddDialog = true">
          <el-icon><Plus /></el-icon>
          上传 Skill
        </el-button>
      </div>
    </el-card>

    <!-- 过滤和排序 -->
    <el-card shadow="hover" class="card">
      <el-tabs v-model="tabType" type="border-card" class="skills-tabs">
        <el-tab-pane label="我的 Skills" name="my">
          <div class="filter-row">
            <el-input
              v-model="searchQuery"
              placeholder="搜索 Skill 名称或描述"
              class="search-input"
              clearable
            />
            <el-button type="primary" @click="loadSkills">查询</el-button>
          </div>
          <!-- Skills 卡片网格 -->
          <el-empty v-if="mySkills.length === 0" description="暂无 Skills，点击上传按钮添加" class="empty-state">
            <el-button type="primary" @click="showAddDialog = true">上传 Skill</el-button>
          </el-empty>
          <el-row v-else :gutter="20">
            <el-col v-for="skill in mySkills" :key="skill.id" :span="8">
              <div class="skill-card">
                <div class="skill-card-header">
                  <div class="skill-name">{{ skill.skill_name }}</div>
                  <el-switch v-model="skill.is_public" @change="togglePublic(skill)" active-text="公开" inactive-text="私有" size="small" />
                </div>
                <div class="skill-description">{{ skill.description || '暂无描述' }}</div>
                <div class="skill-meta">
                  <span class="meta-item">上传于 {{ formatDateTime(skill.created_at) }}</span>
                  <span class="meta-item">{{ skill.is_public ? '公开' : '私有' }}</span>
                </div>
                <div class="skill-actions">
                  <el-button type="primary" link size="small" @click="viewSkill(skill)">查看</el-button>
                  <el-button type="warning" link size="small" @click="editSkill(skill)">编辑</el-button>
                  <el-button type="danger" link size="small" @click="deleteSkill(skill.id)">删除</el-button>
                </div>
              </div>
            </el-col>
          </el-row>
        </el-tab-pane>
        <el-tab-pane label="公开 Skills" name="public">
          <div class="filter-row">
            <el-input
              v-model="publicSearchQuery"
              placeholder="搜索公开 Skill"
              class="search-input"
              clearable
            />
            <el-button type="primary" @click="loadPublicSkills">查询</el-button>
          </div>
          <el-empty v-if="publicSkills.length === 0" description="暂无公开 Skills" class="empty-state">
            <el-button type="primary" @click="showAddDialog = true">上传我的第一个 Skill</el-button>
          </el-empty>
          <el-row v-else :gutter="20">
            <el-col v-for="skill in publicSkills" :key="skill.id" :span="8">
              <div class="skill-card">
                <div class="skill-card-header">
                  <div class="skill-name">{{ skill.skill_name }}</div>
                  <el-tag v-if="skill.is_public" type="success" size="small">公开</el-tag>
                </div>
                <div class="skill-description">{{ skill.description || '暂无描述' }}</div>
                <div class="skill-meta">
                  <span class="meta-item">by {{ skill.username }}</span>
                  <span class="meta-item">{{ formatDateTime(skill.created_at) }}</span>
                </div>
                <div class="skill-actions">
                  <el-button type="primary" link size="small" @click="viewSkill(skill)">查看</el-button>
                </div>
              </div>
            </el-col>
          </el-row>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 上传 Skill 对话框 -->
    <el-dialog v-model="showAddDialog" title="上传 Skill" width="600px" :close-on-click-modal="false">
      <el-form :model="addForm" :rules="addRules" label-width="100px" ref="addFormRef">
        <el-form-item label="Skill 名称" prop="skill_name">
          <el-input v-model="addForm.skill_name" placeholder="例如：pdf-processing" clearable>
            <template #tip>
              <div class="el-upload__tip">只能包含小写字母、数字和连字符，最多 64 个字符</div>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item label="Skill 文件" prop="skill_file">
          <el-upload
            ref="uploadRef"
            action="/api/skills/upload"
            :auto-upload="false"
            :show-file-list="true"
            :on-change="handleFileChange"
            :limit="1"
            accept=".zip,.md"
            drag
          >
            <el-icon class="el-icon--upload"><Upload /></el-icon>
            <div class="el-upload__drag">
              <p>点击或拖拽文件到此区域</p>
              <p class="el-upload__tip">支持 .zip 或 .md 文件</p>
            </div>
          </el-upload>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="addForm.description"
            type="textarea"
            placeholder="简要描述这个 Skill 的功能和用途，最多 1024 个字符"
            :rows="3"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="是否公开">
          <el-switch v-model="addForm.is_public" active-text="是" inactive-text="否" />
          <div class="form-tips">公开后其他用户可以看到您的 Skill</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="handleCreateSkill">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑 Skill 对话框 -->
    <el-dialog v-model="showEditDialog" title="编辑 Skill" width="500px" :close-on-click-modal="false">
      <el-form :model="editForm" :rules="editRules" label-width="100px" ref="editFormRef">
        <el-form-item label="Skill 名称">
          <el-input v-model="editForm.skill_name" disabled />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="editForm.description"
            type="textarea"
            placeholder="描述"
            :rows="3"
          />
        </el-form-item>
        <el-form-item label="是否公开">
          <el-switch v-model="editForm.is_public" active-text="是" inactive-text="否" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="editLoading" @click="handleUpdateSkill">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { Plus, Upload } from '@element-plus/icons-vue'

export default {
  name: 'SkillsView',
  components: {
    Plus,
    Upload
  },
  data() {
    return {
      tabType: 'my',
      searchQuery: '',
      publicSearchQuery: '',
      mySkills: [],
      publicSkills: [],
      loading: false,
      addForm: {
        skill_name: '',
        description: '',
        is_public: false
      },
      addRules: {
        skill_name: [
          { required: true, message: '请输入 Skill 名称', trigger: 'blur' },
          { pattern: /^[a-z0-9-]+$/, message: '只能包含小写字母、数字和连字符', trigger: 'blur' },
          { min: 2, max: 64, message: '长度在 2 到 64 个字符', trigger: 'blur' }
        ],
        description: [
          { max: 1024, message: '描述长度不能超过 1024 个字符', trigger: 'blur' }
        ]
      },
      editForm: {
        id: null,
        skill_name: '',
        description: '',
        is_public: false
      },
      editRules: {
        description: [
          { max: 1024, message: '描述长度不能超过 1024 个字符', trigger: 'blur' }
        ]
      },
      showAddDialog: false,
      showEditDialog: false,
      addLoading: false,
      editLoading: false,
      currentFile: null
    }
  },
  mounted() {
    this.loadSkills()
    this.loadPublicSkills()
  },
  methods: {
    async loadSkills() {
      this.loading = true
      try {
        const token = localStorage.getItem('token')
        const response = await fetch('/api/skills', {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })
        const result = await response.json()
        if (result.status === 'success') {
          this.mySkills = result.data.skills || []
        } else {
          this.$message.error(result.data?.message || '获取 Skills 失败')
        }
      } catch (error) {
        console.error('获取 Skills 失败:', error)
        this.$message.error('获取 Skills 失败: ' + error.message)
      } finally {
        this.loading = false
      }
    },
    async loadPublicSkills() {
      try {
        const token = localStorage.getItem('token')
        const response = await fetch('/api/skills?publicOnly=true', {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })
        const result = await response.json()
        if (result.status === 'success') {
          this.publicSkills = result.data.skills || []
        }
      } catch (error) {
        console.error('获取公开 Skills 失败:', error)
      }
    },
    formatDateTime(isoString) {
      if (!isoString) return '-'
      const date = new Date(isoString)
      return date.toLocaleString('zh-CN')
    },
    handleFileChange(file) {
      this.currentFile = file.raw
    },
    async handleCreateSkill() {
      this.$refs.addFormRef.validate(async (valid) => {
        if (!valid) return

        if (!this.currentFile) {
          this.$message.warning('请上传 Skill 文件（.zip 或 .md）')
          return
        }

        this.addLoading = true
        try {
          const token = localStorage.getItem('token')
          const formData = new FormData()
          formData.append('skill_file', this.currentFile)
          if (this.addForm.description) {
            formData.append('description', this.addForm.description)
          }
          formData.append('is_public', this.addForm.is_public)

          // 直接上传文件
          const response = await fetch('/api/skills/upload', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`
            },
            body: formData
          })

          const result = await response.json()
          if (result.status === 'success') {
            this.$message.success('Skill 上传成功')
            this.showAddDialog = false
            this.addForm = { skill_name: '', description: '', is_public: false }
            this.currentFile = null
            this.loadSkills()
          } else {
            this.$message.error(result.data?.message || '上传 Skill 失败')
          }
        } catch (error) {
          console.error('上传 Skill 失败:', error)
          this.$message.error('上传 Skill 失败: ' + error.message)
        } finally {
          this.addLoading = false
        }
      })
    },
    editSkill(skill) {
      this.editForm = {
        id: skill.id,
        skill_name: skill.skill_name,
        description: skill.description || '',
        is_public: skill.is_public === 1
      }
      this.showEditDialog = true
    },
    async handleUpdateSkill() {
      this.$refs.editFormRef.validate(async (valid) => {
        if (!valid) return

        this.editLoading = true
        try {
          const token = localStorage.getItem('token')
          const response = await fetch(`/api/skills/${this.editForm.id}`, {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
              description: this.editForm.description,
              is_public: this.editForm.is_public
            })
          })

          const result = await response.json()
          if (result.status === 'success') {
            this.$message.success('Skill 更新成功')
            this.showEditDialog = false
            this.loadSkills()
          } else {
            this.$message.error(result.data?.message || '更新失败')
          }
        } catch (error) {
          console.error('更新 Skill 失败:', error)
          this.$message.error('更新失败: ' + error.message)
        } finally {
          this.editLoading = false
        }
      })
    },
    async deleteSkill(skillId) {
      this.$confirm('确定要删除该 Skill 吗？', '提示', {
        type: 'warning'
      }).then(async () => {
        try {
          const token = localStorage.getItem('token')
          const response = await fetch(`/api/skills/${skillId}`, {
            method: 'DELETE',
            headers: {
              'Authorization': `Bearer ${token}`
            }
          })

          const result = await response.json()
          if (result.status === 'success') {
            this.$message.success('删除成功')
            this.loadSkills()
          } else {
            this.$message.error(result.data?.message || '删除失败')
          }
        } catch (error) {
          console.error('删除失败:', error)
          this.$message.error('删除失败: ' + error.message)
        }
      }).catch(() => {})
    },
    async togglePublic(skill) {
      try {
        const token = localStorage.getItem('token')
        const response = await fetch(`/api/skills/${skill.id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ is_public: !skill.is_public })
        })

        const result = await response.json()
        if (result.status === 'success') {
          skill.is_public = !skill.is_public
          this.$message.success(skill.is_public ? '已公开' : '已设为私有')
        } else {
          this.$message.error(result.data?.message || '操作失败')
          // 恢复开关状态
          skill.is_public = !skill.is_public
        }
      } catch (error) {
        console.error('操作失败:', error)
        this.$message.error('操作失败: ' + error.message)
        skill.is_public = !skill.is_public
      }
    },
    viewSkill(skill) {
      this.$message.info(`查看 Skill: ${skill.skill_name}`)
      // 可以添加查看 skill 详情的逻辑
    }
  }
}
</script>

<style scoped>
.skills-view {
  animation: fadeIn 0.3s;
}

.card {
  margin-bottom: 24px;
  border: 1px solid #e5e7eb;
}

.skills-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
}

.card-desc {
  color: #6b7280;
  margin-top: 8px;
}

.skills-tabs :deep(.el-tabs__header) {
  margin-bottom: 24px;
}

.filter-row {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
}

.search-input {
  width: 250px;
}

.empty-state {
  padding: 60px 24px;
}

/* Skill 卡片样式 */
.skill-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.3s;
  border: 1px solid #e5e7eb;
}

.skill-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
}

.skill-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f3f4f6;
}

.skill-name {
  font-weight: 600;
  font-size: 16px;
  color: #1f2937;
  flex: 1;
}

.skill-description {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 12px;
  line-height: 1.6;
}

.skill-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  font-size: 12px;
  color: #9ca3af;
}

.meta-item::before {
  content: '•';
  margin: 0 8px;
  color: #d1d5db;
}

.meta-item:first-child::before {
  content: '';
  margin: 0;
}

.skill-actions {
  display: flex;
  gap: 8px;
}

.skill-actions :deep(.el-button) {
  font-size: 12px;
}

.form-tips {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
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
