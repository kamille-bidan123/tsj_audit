#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化脚本
"""

from web.database import init_db, DB_PATH

if __name__ == "__main__":
    print(f"正在初始化数据库: {DB_PATH}")
    init_db()
    print("数据库初始化完成！")
