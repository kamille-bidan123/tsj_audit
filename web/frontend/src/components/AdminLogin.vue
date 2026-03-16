<template>
  <div class="admin-login-container">
    <div class="admin-login-box">
      <div class="admin-login-header">
        <div class="admin-logo">
          <el-icon :size="48" color="#409eff"><Monitor /></el-icon>
        </div>
        <h1 class="admin-title">代码安全审计系统</h1>
        <p class="admin-subtitle">后台管理登录</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="admin-login-form"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            prefix-icon="User"
            size="large"
            clearable
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            prefix-icon="Lock"
            size="large"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            size="large"
            class="admin-login-btn"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>

        <div class="admin-form-footer">
          <span class="admin-footer-text">使用管理员账户登录</span>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script>
export default {
  name: 'AdminLogin',
  data() {
    return {
      form: {
        username: '',
        password: '',
      },
      rules: {
        username: [
          { required: true, message: '请输入用户名', trigger: 'blur' }
        ],
        password: [
          { required: true, message: '请输入密码', trigger: 'blur' }
        ]
      },
      loading: false
    }
  },
  methods: {
    async handleLogin() {
      this.$refs.formRef.validate(async (valid) => {
        if (!valid) return

        this.loading = true
        try {
          const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.form)
          })

          const result = await response.json()
          if (result.status === 'success') {
            // 保存用户信息和 token
            localStorage.setItem('user', JSON.stringify(result.data))
            localStorage.setItem('token', result.data.user_id.toString())
            // 跳转到首页
            this.$router.push({ path: '/' })
            this.$message.success('登录成功')
          } else {
            this.$message.error(result.data?.message || '登录失败')
          }
        } catch (error) {
          console.error('登录失败:', error)
          this.$message.error('登录失败: ' + error.message)
        } finally {
          this.loading = false
        }
      })
    }
  }
}
</script>

<style scoped>
.admin-login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.admin-login-box {
  background: white;
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  padding: 48px 40px;
  width: 100%;
  max-width: 420px;
}

.admin-login-header {
  text-align: center;
  margin-bottom: 32px;
}

.admin-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  background: linear-gradient(to bottom right, #409eff, #3a8ee6);
  border-radius: 16px;
  margin-bottom: 16px;
}

.admin-title {
  font-size: 28px;
  font-weight: bold;
  color: #1f2937;
  margin: 0 0 8px 0;
}

.admin-subtitle {
  font-size: 14px;
  color: #6b7280;
  margin: 0;
}

.admin-login-form {
  margin-top: 24px;
}

.admin-login-btn {
  width: 100%;
  font-size: 16px;
}

.admin-form-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 16px;
  font-size: 14px;
  color: #6b7280;
}

.admin-footer-text {
  margin-right: 8px;
}

.admin-login-form :deep(.el-form-item__label) {
  font-size: 14px;
}

.admin-login-form :deep(.el-input__inner) {
  font-size: 14px;
}

.admin-login-form :deep(.el-button) {
  font-size: 16px;
}
</style>
