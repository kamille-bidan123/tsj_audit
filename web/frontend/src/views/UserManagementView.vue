<template>
  <div class="user-management-view">
    <el-card shadow="hover" class="card">
      <template #header>
        <div class="card-header">
          <span class="card-title">用户管理</span>
          <el-button type="primary" size="small" @click="showAddDialog = true">
            <el-icon><Plus /></el-icon>
            添加用户
          </el-button>
        </div>
      </template>

      <!-- 筛选条件 -->
      <div class="filters-row" style="margin-bottom: 20px">
        <el-input
          v-model="searchQuery"
          placeholder="搜索用户名或邮箱"
          class="search-input"
          clearable
        />
        <el-select v-model="roleFilter" placeholder="角色筛选" class="filter-select" style="width: 120px">
          <el-option label="全部角色" value="" />
          <el-option label="管理员" value="admin" />
          <el-option label="普通用户" value="user" />
        </el-select>
        <el-button type="primary" @click="loadUsers">查询</el-button>
      </div>

      <!-- 用户列表 -->
      <el-table :data="users" v-loading="loading" class="user-table">
        <el-table-column prop="username" label="用户名" width="150" />
        <el-table-column prop="email" label="邮箱" width="200" show-overflow-tooltip />
        <el-table-column prop="role" label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" size="small">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'warning'" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" :formatter="formatDateTime" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="showResetDialog(row)">重置密码</el-button>
            <el-button
              :type="row.is_active ? 'warning' : 'success'"
              link
              @click="toggleUserStatus(row)"
            >
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button type="danger" link @click="deleteUser(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <el-pagination
        v-if="total > 0"
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 20px"
        @size-change="loadUsers"
        @current-change="loadUsers"
      />
    </el-card>

    <!-- 添加用户对话框 -->
    <el-dialog v-model="showAddDialog" title="添加用户" width="500px">
      <el-form :model="addForm" :rules="addRules" label-width="100px" ref="addFormRef">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="addForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="addForm.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="addForm.email" placeholder="请输入邮箱（可选）" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-radio-group v-model="addForm.role">
            <el-radio value="user">普通用户</el-radio>
            <el-radio value="admin">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="handleAddUser">确定</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码对话框 -->
    <el-dialog v-model="showResetDialogVisible" title="重置密码" width="400px">
      <el-form :model="resetForm" :rules="resetRules" label-width="100px" ref="resetFormRef">
        <el-form-item label="新密码" prop="password">
          <el-input v-model="resetForm.password" type="password" placeholder="请输入新密码" show-password />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input v-model="resetForm.confirmPassword" type="password" placeholder="请再次输入密码" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showResetDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetLoading" @click="handleResetPassword">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { Plus } from '@element-plus/icons-vue'

export default {
  name: 'UserManagementView',
  components: {
    Plus
  },
  data() {
    return {
      users: [],
      loading: false,
      total: 0,
      currentPage: 1,
      pageSize: 10,
      searchQuery: '',
      roleFilter: '',
      showAddDialog: false,
      showResetDialogVisible: false,
      currentUserId: null,
      addForm: {
        username: '',
        password: '',
        email: '',
        role: 'user'
      },
      addRules: {
        username: [
          { required: true, message: '请输入用户名', trigger: 'blur' },
          { min: 3, max: 20, message: '用户名长度在 3 到 20 个字符', trigger: 'blur' }
        ],
        password: [
          { required: true, message: '请输入密码', trigger: 'blur' },
          { min: 6, max: 20, message: '密码长度在 6 到 20 个字符', trigger: 'blur' }
        ],
        email: [
          { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' }
        ]
      },
      addLoading: false,
      resetForm: {
        password: '',
        confirmPassword: ''
      },
      resetRules: {
        password: [
          { required: true, message: '请输入新密码', trigger: 'blur' },
          { min: 6, max: 20, message: '密码长度在 6 到 20 个字符', trigger: 'blur' }
        ],
        confirmPassword: [
          { required: true, message: '请再次输入密码', trigger: 'blur' },
          { validator: this.validateConfirmPassword, trigger: 'blur' }
        ]
      },
      resetLoading: false
    }
  },
  mounted() {
    this.loadUsers()
  },
  methods: {
    async loadUsers() {
      this.loading = true
      try {
        const token = localStorage.getItem('token')
        const response = await fetch(`/api/users`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })
        const result = await response.json()
        if (result.status === 'success') {
          this.users = result.data.users
          this.total = result.data.total
        } else {
          this.$message.error(result.data?.message || '获取用户列表失败')
        }
      } catch (error) {
        console.error('获取用户列表失败:', error)
        this.$message.error('获取用户列表失败: ' + error.message)
      } finally {
        this.loading = false
      }
    },
    formatDateTime(isoString) {
      if (!isoString) return '-'
      const date = new Date(isoString)
      return date.toLocaleString('zh-CN')
    },
    validateConfirmPassword(rule, value, callback) {
      if (value !== this.resetForm.password) {
        callback(new Error('两次输入的密码不一致'))
      } else {
        callback()
      }
    },
    showResetDialog(user) {
      this.currentUserId = user.id
      this.showResetDialogVisible = true
    },
    handleAddUser() {
      this.$refs.addFormRef.validate(async (valid) => {
        if (!valid) return

        this.addLoading = true
        try {
          const token = localStorage.getItem('token')
          const response = await fetch(`/api/users`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(this.addForm)
          })

          const result = await response.json()
          if (result.status === 'success') {
            this.$message.success('用户创建成功')
            this.showAddDialog = false
            this.addForm = { username: '', password: '', email: '', role: 'user' }
            this.loadUsers()
          } else {
            this.$message.error(result.data?.message || '创建用户失败')
          }
        } catch (error) {
          console.error('创建用户失败:', error)
          this.$message.error('创建用户失败: ' + error.message)
        } finally {
          this.addLoading = false
        }
      })
    },
    async handleResetPassword() {
      this.$refs.resetFormRef.validate(async (valid) => {
        if (!valid) return

        this.resetLoading = true
        try {
          const token = localStorage.getItem('token')
          const response = await fetch(`/api/users/${this.currentUserId}`, {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ password: this.resetForm.password })
          })

          const result = await response.json()
          if (result.status === 'success') {
            this.$message.success('密码重置成功')
            this.showResetDialogVisible = false
            this.resetForm = { password: '', confirmPassword: '' }
          } else {
            this.$message.error(result.data?.message || '密码重置失败')
          }
        } catch (error) {
          console.error('密码重置失败:', error)
          this.$message.error('密码重置失败: ' + error.message)
        } finally {
          this.resetLoading = false
        }
      })
    },
    async toggleUserStatus(user) {
      const newStatus = !user.is_active
      try {
        const token = localStorage.getItem('token')
        const response = await fetch(`/api/users/${user.id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ is_active: newStatus })
        })

        const result = await response.json()
        if (result.status === 'success') {
          this.$message.success(`${newStatus ? '启用' : '禁用'}成功`)
          user.is_active = newStatus
        } else {
          this.$message.error(result.data?.message || '操作失败')
        }
      } catch (error) {
        console.error('操作失败:', error)
        this.$message.error('操作失败: ' + error.message)
      }
    },
    async deleteUser(userId) {
      this.$confirm('确定要删除该用户吗？', '提示', {
        type: 'warning'
      }).then(async () => {
        try {
          const token = localStorage.getItem('token')
          const response = await fetch(`/api/users/${userId}`, {
            method: 'DELETE',
            headers: {
              'Authorization': `Bearer ${token}`
            }
          })

          const result = await response.json()
          if (result.status === 'success') {
            this.$message.success('删除成功')
            this.loadUsers()
          } else {
            this.$message.error(result.data?.message || '删除失败')
          }
        } catch (error) {
          console.error('删除失败:', error)
          this.$message.error('删除失败: ' + error.message)
        }
      }).catch(() => {})
    }
  }
}
</script>

<style scoped>
.user-management-view {
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

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.filters-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.search-input {
  width: 250px;
}

.filter-select {
  width: 120px;
}

.user-table :deep(th) {
  background: #f9fafb;
}

.el-checkbox {
  font-size: 14px;
}

.el-checkbox :deep(.el-checkbox__label) {
  font-size: 14px;
}
</style>
