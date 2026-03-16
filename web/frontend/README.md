# 前端项目说明

这是一个使用 Vue 3 + Vite 构建的前端项目。

## 开发

```bash
npm install
npm run dev
```

## 构建

```bash
npm run build
```

构建后的文件会 output 到 `../static` 目录。

## 技术栈

- Vue 3
- Vite
- Tailwind CSS (通过 CDN)

## 构建为静态文件

项目配置为构建为纯静态文件（HTML + JS + CSS），可以直接部署到任何静态服务器，无需 Node.js 运行时。

构建命令：
```bash
npm run build
```

构建输出目录：`web/static/`
