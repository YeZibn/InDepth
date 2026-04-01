#!/usr/bin/env python3
"""
初始化知识库目录结构

用法:
    python init_knowledge.py [--path PATH]

示例:
    python init_knowledge.py
    python init_knowledge.py --path ./my_knowledge
"""

import argparse
from pathlib import Path


def init_knowledge(base_path: Path):
    """初始化知识库目录结构"""
    dirs = [
        base_path / "base" / "experience",
        base_path / "base" / "principles",
    ]
    
    for dir_path in dirs:
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"[创建目录] {dir_path}")
    
    # 创建索引文件
    exp_index = base_path / "base" / "experience" / "INDEX.md"
    if not exp_index.exists():
        exp_index.write_text("""# Experience 索引

> 自动生成，新增经验文档时更新此文件

| 文件 | 描述 | 标签 |
|------|------|------|
""", encoding='utf-8')
        print(f"[创建] {exp_index}")
    
    prin_index = base_path / "base" / "principles" / "INDEX.md"
    if not prin_index.exists():
        prin_index.write_text("""# Principles 索引

> 自动生成，新增原则文档时更新此文件

| 文件 | 描述 | 标签 |
|------|------|------|
""", encoding='utf-8')
        print(f"[创建] {prin_index}")
    
    print(f"\n[完成] 知识库初始化成功: {base_path.resolve()}")


def main():
    parser = argparse.ArgumentParser(description='初始化知识库目录结构')
    parser.add_argument('--path', '-p', default='memory_knowledge', help='知识库根路径')
    
    args = parser.parse_args()
    
    base_path = Path(args.path)
    init_knowledge(base_path)


if __name__ == '__main__':
    main()
