import { createWebHistory, createRouter } from 'vue-router'
import LoginView from '../components/LoginView.vue'
import AdminLogin from '../components/AdminLogin.vue'
import DashboardView from '../views/DashboardView.vue'
import ScanView from '../views/ScanView.vue'
import AuditView from '../views/AuditView.vue'
import ResultsView from '../views/ResultsView.vue'
import UserManagementView from '../views/UserManagementView.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginView
  },
  {
    path: '/admin',
    name: 'AdminLogin',
    component: AdminLogin,
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    name: 'Main',
    component: () => import('../layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Dashboard',
        component: DashboardView
      },
      {
        path: 'scan',
        name: 'Scan',
        component: ScanView
      },
      {
        path: 'audit',
        name: 'Audit',
        component: AuditView
      },
      {
        path: 'results',
        name: 'Results',
        component: ResultsView
      },
      {
        path: 'users',
        name: 'UserManagement',
        component: UserManagementView,
        meta: { requiresAdmin: true }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫：检查是否需要登录
router.beforeEach((to, from, next) => {
  const userStr = localStorage.getItem('user')
  const user = userStr ? JSON.parse(userStr) : null

  // 管理员路由需要管理员权限
  if (to.meta.requiresAdmin) {
    if (!user) {
      next('/admin')
      return
    }
    if (user.role !== 'admin') {
      next('/')
      return
    }
  } else if (to.meta.requiresAuth === true && !user) {
    // 普通登录页面
    next('/admin')
    return
  }

  if (user && (to.path === '/login' || to.path === '/admin')) {
    next('/')
    return
  }

  next()
})

export default router
