#!/usr/bin/env node
// -*- coding: utf-8 -*-
/**
 * 使用 Playwright 检查前端页面渲染效果
 */

const { chromium } = require('playwright');

async function checkUI() {
  const browser = await chromium.launch({
    headless: false,
    slowMo: 50
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 }
  });

  const page = await context.newPage();

  // 访问页面
  console.log('正在加载页面...');
  await page.goto('http://localhost:8080/', {
    waitUntil: 'networkidle',
    timeout: 60000
  });

  // 等待 Vue 应用挂载
  await page.waitForSelector('#app', { timeout: 10000 });
  await new Promise(r => setTimeout(r, 2000));

  // 截图
  await page.screenshot({
    path: 'viewport_1920x1080.png',
    fullPage: true
  });
  console.log('已截图: viewport_1920x1080.png');

  // 获取页面状态
  const pageState = await page.evaluate(() => {
    const app = document.querySelector('#app');
    return {
      appExists: !!app,
      appChildCount: app?.children?.length || 0,
      bodyClass: document.body.className,
      documentTitle: document.title,
      linkCount: document.querySelectorAll('link').length,
      scriptCount: document.querySelectorAll('script').length,
    };
  });

  console.log('\n页面状态:');
  console.log('  App 元素存在:', pageState.appExists);
  console.log('  App 子元素数量:', pageState.appChildCount);
  console.log('  Body 类名:', pageState.bodyClass);
  console.log('  文档标题:', pageState.documentTitle);
  console.log('  Link 标签数量:', pageState.linkCount);
  console.log('  Script 标签数量:', pageState.scriptCount);

  // 检查 CSS 是否加载
  const cssStatus = await page.evaluate(() => {
    const links = Array.from(document.querySelectorAll('link[rel="stylesheet"]'));
    return links.map(link => ({
      href: link.href,
      success: link.href.indexOf('404') === -1
    }));
  });

  console.log('\nCSS 状态:');
  cssStatus.forEach(css => {
    console.log(`  ${css.href}: ${css.success ? '已加载' : '未找到'}`);
  });

  // 等待用户查看
  console.log('\n等待 10 秒供手动查看...');
  await new Promise(r => setTimeout(r, 10000));

  await browser.close();
}

checkUI().catch(console.error);
