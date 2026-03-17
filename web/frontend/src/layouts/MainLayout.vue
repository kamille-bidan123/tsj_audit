<template>
  <div class="main-layout">
    <!-- 顶部导航 -->
    <div class="header">
      <div class="header-content">
        <div class="logo-section">
          <div class="logo">
            <el-icon :size="24" color="white"><Monitor /></el-icon>
          </div>
          <span class="title">代码安全审计系统</span>
        </div>
        <el-menu
          :default-active="currentPath"
          mode="horizontal"
          @select="handleMenuSelect"
          class="menu"
          :ellipsis="false"
        >
          <el-menu-item index="/">仪表盘</el-menu-item>
          <el-menu-item index="/scan">项目扫描</el-menu-item>
          <el-menu-item index="/audit">审计任务</el-menu-item>
          <el-menu-item index="/results">审计结果</el-menu-item>
          <el-menu-item index="/skills">Skills</el-menu-item>
          <el-menu-item v-if="currentUser?.role === 'admin'" index="/users">用户管理</el-menu-item>
        </el-menu>
        <div class="header-actions">
          <el-input
            v-model="config.projectPath"
            placeholder="项目路径"
            style="width: 200px"
            size="small"
          >
            <template #prefix>
              <el-icon><Folder /></el-icon>
            </template>
          </el-input>
          <el-button type="primary" size="small" @click="navigateTo('/scan')">
            开始审计
          </el-button>
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-icon><User /></el-icon>
              <span>{{ currentUser?.username }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人资料</el-dropdown-item>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </div>

    <div class="main-container">
      <!-- 主内容 -->
      <div class="main-content">
        <router-view />
      </div>
    </div>

    <!-- 底部 -->
    <footer class="footer">
      <div class="footer-content">
        <p class="footer-text">© 2026 代码安全审计系统. All rights reserved.</p>
        <span class="version">v1.0.0</span>
      </div>
    </footer>
  </div>
</template>

<script>
import { Monitor, Folder, User } from '@element-plus/icons-vue'

export default {
  name: 'MainLayout',
  components: {
    Monitor,
    Folder,
    User
  },
  data() {
    return {
      config: {
        projectPath: '',
        baseUrl: '/api',
      }
    }
  },
  computed: {
    currentUser() {
      const userStr = localStorage.getItem('user')
      return userStr ? JSON.parse(userStr) : null
    },
    currentPath() {
      return this.$route.path
    }
  },
  methods: {
    handleMenuSelect(index) {
      this.$router.push(index)
    },
    navigateTo(path) {
      this.$router.push(path)
    },
    handleCommand(command) {
      if (command === 'logout') {
        this.handleLogout()
      }
    },
    handleLogout() {
      localStorage.removeItem('user')
      this.$router.push('/login')
      this.$message.success('已退出登录')
    }
  }
}
</script>

<style scoped>
.main-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* Header */
.header {
  background: white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  padding: 0 24px;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
}

.logo-section {
  display: flex;
  align-items: center;
}

.logo {
  background: linear-gradient(to bottom right, #409eff, #3a8ee6);
  border-radius: 8px;
  padding: 8px;
  margin-right: 16px;
}

.title {
  font-size: 20px;
  font-weight: bold;
  background: linear-gradient(to right, #3a8ee6, #409eff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.menu {
  margin: 0 24px;
  border-bottom: none;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 8px 12px;
  border-radius: 4px;
  transition: background 0.3s;
}

.user-info:hover {
  background: #f3f4f6;
}

/* Main Container */
.main-container {
  flex: 1;
  display: flex;
}

.main-content {
  flex: 1;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

/* Footer */
.footer {
  background: white;
  border-top: 1px solid #e5e7eb;
  padding: 16px 24px;
  margin-top: auto;
}

.footer-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.footer-text {
  color: #6b7280;
  font-size: 14px;
}

.version {
  color: #9ca3af;
  font-size: 14px;
}
</style>
