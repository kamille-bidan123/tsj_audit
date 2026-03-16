#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 Playwright 检查前端页面渲染效果
"""

import asyncio
from playwright.async_api import async_playwright

async def check_ui():
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()

        # 访问页面
        print("正在加载页面...")
        await page.goto('http://localhost:8080/')

        # 等待页面加载完成
        await page.wait_for_load_state('networkidle')

        # 等待 Vue 应用挂载
        await asyncio.sleep(3)

        # 截图
        await page.screenshot(path='viewport_1920x1080.png')
        print("已截图: viewport_1920x1080.png")

        # 检查是否有错误
        errors = await page.evaluate('''() => {
            return {
                hasVue: typeof window.Vue !== 'undefined',
                appMounted: document.querySelector('#app') !== null,
                appContent: document.querySelector('#app')?.innerText?.substring(0, 100) || '',
                cssLoaded: document.querySelector('link[rel="stylesheet"]') !== null,
                bodyStyles: window.getComputedStyle(document.body).fontFamily,
                scrollToExist: window.scrollBy !== undefined
            };
        }''')

        print("\n页面状态检查:")
        print(f"  Vue 是否加载: {errors['hasVue']}")
        print(f"  App 是否挂载: {errors['appMounted']}")
        print(f"  App 内容: {errors['appContent']}")
        print(f"  CSS 是否加载: {errors['cssLoaded']}")
        print(f"  Body 字体: {errors['bodyStyles']}")

        # 检查 CSS 文件是否成功加载
        css_status = await page.evaluate('''() => {
            const links = document.querySelectorAll('link[rel="stylesheet"]');
            const styles = [];
            links.forEach(link => {
                styles.push({
                    href: link.href,
                    buster: link.buster
                });
            });
            return styles;
        }''')

        print(f"\nCSS 链接: {css_status}")

        # 等待用户查看
        print("\n等待 5 秒供手动查看...")
        await asyncio.sleep(5)

        await browser.close()

if __name__ == '__main__':
    asyncio.run(check_ui())
