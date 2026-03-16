<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
        <div class="logo">
          <el-icon :size="40" color="#409eff"><Monitor /></el-icon>
        </div>
        <h1 class="title">代码安全审计系统</h1>
        <p class="subtitle">登录您的账户</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="login-form"
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
          <el-checkbox v-model="form.remember">记住我</el-checkbox>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            size="large"
            class="login-btn"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>

        <div class="form-footer">
          <span class="footer-text">没有账户?</span>
          <el-link type="primary" @click="showRegister = true">立即注册</el-link>
        </div>
      </el-form>

      <!-- 注册弹窗 -->
      <el-dialog
        v-model="showRegister"
        title="用户注册"
        width="500px"
        :close-on-click-modal="false"
      >
        <el-form
          ref="registerFormRef"
          :model="registerForm"
          :rules="registerRules"
          label-width="100px"
        >
          <el-form-item label="用户名" prop="username">
            <el-input v-model="registerForm.username" placeholder="请输入用户名" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="registerForm.password" type="password" placeholder="请输入密码" show-password />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirmPassword">
            <el-input v-model="registerForm.confirmPassword" type="password" placeholder="请再次输入密码" show-password />
          </el-form-item>
          <el-form-item label="邮箱" prop="email">
            <el-input v-model="registerForm.email" placeholder="请输入邮箱（可选）" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showRegister = false">取消</el-button>
          <el-button type="primary" :loading="registerLoading" @click="handleRegister">注册</el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<script>
export default {
  name: 'LoginView',
  data() {
    return {
      form: {
        username: '',
        password: '',
        remember: false,
      },
      rules: {
        username: [
          { required: true, message: '请输入用户名', trigger: 'blur' },
          { min: 3, max: 20, message: '用户名长度在 3 到 20 个字符', trigger: 'blur' }
        ],
        password: [
          { required: true, message: '请输入密码', trigger: 'blur' },
          { min: 6, max: 20, message: '密码长度在 6 到 20 个字符', trigger: 'blur' }
        ]
      },
      loading: false,
      showRegister: false,
      registerForm: {
        username: '',
        password: '',
        confirmPassword: '',
        email: ''
      },
      registerRules: {
        username: [
          { required: true, message: '请输入用户名', trigger: 'blur' },
          { min: 3, max: 20, message: '用户名长度在 3 到 20 个字符', trigger: 'blur' }
        ],
        password: [
          { required: true, message: '请输入密码', trigger: 'blur' },
          { min: 6, max: 20, message: '密码长度在 6 到 20 个字符', trigger: 'blur' }
        ],
        confirmPassword: [
          { required: true, message: '请再次输入密码', trigger: 'blur' },
          { validator: this.validatePasswordConfirm, trigger: 'blur' }
        ],
        email: [
          { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' }
        ]
      },
      registerLoading: false
    }
  },
  methods: {
    validatePasswordConfirm(rule, value, callback) {
      if (value !== this.registerForm.password) {
        callback(new Error('两次输入的密码不一致'))
      } else {
        callback()
      }
    },
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
            localStorage.setItem('user', JSON.stringify(result.data))
            localStorage.setItem('token', result.data.user_id.toString())
            if (this.form.remember) {
              localStorage.setItem('remember_user', 'true')
            } else {
              localStorage.removeItem('remember_user')
            }
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
    },
    async handleRegister() {
      this.$refs.registerFormRef.validate(async (valid) => {
        if (!valid) return

        if (this.registerForm.password !== this.registerForm.confirmPassword) {
          this.$message.error('两次输入的密码不一致')
          return
        }

        this.registerLoading = true
        try {
          const response = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              username: this.registerForm.username,
              password: this.registerForm.password,
              email: this.registerForm.email || undefined
            })
          })

          const result = await response.json()
          if (result.status === 'success') {
            this.$message.success('注册成功，请登录')
            this.showRegister = false
            this.form.username = this.registerForm.username
            this.form.password = this.registerForm.password
          } else {
            this.$message.error(result.data?.message || '注册失败')
          }
        } catch (error) {
          console.error('注册失败:', error)
          this.$message.error('注册失败: ' + error.message)
        } finally {
          this.registerLoading = false
        }
      })
    }
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.login-box {
  background: white;
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  padding: 48px 40px;
  width: 100%;
  max-width: 420px;
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  background: linear-gradient(to bottom right, #409eff, #3a8ee6);
  border-radius: 16px;
  margin-bottom: 16px;
}

.title {
  font-size: 24px;
  font-weight: bold;
  color: #1f2937;
  margin: 0 0 8px 0;
}

.subtitle {
  font-size: 14px;
  color: #6b7280;
  margin: 0;
}

.login-form {
  margin-top: 24px;
}

.login-btn {
  width: 100%;
  font-size: 16px;
}

.form-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 16px;
  font-size: 14px;
  color: #6b7280;
}

.footer-text {
  margin-right: 8px;
}

.el-checkbox {
  font-size: 14px;
}

.el-checkbox :deep(.el-checkbox__label) {
  font-size: 14px;
}
</style>
