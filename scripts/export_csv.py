#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
导出 GitHub Trending 数据为 CSV 文件

将 README.md 和 archived 目录中的所有项目条目导出为 CSV 格式。
每条记录有一个唯一的数字 ID，且 ID 在数据更新后保持稳定。
"""

import re
import csv
import json
import os
from pathlib import Path


def load_id_mapping(mapping_path):
    """加载 ID 映射文件"""
    if mapping_path.exists():
        with open(mapping_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'next_id': 1, 'mappings': {}}


def save_id_mapping(id_map, mapping_path):
    """保存 ID 映射文件"""
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mapping_path, 'w', encoding='utf-8') as f:
        json.dump(id_map, f, ensure_ascii=False, indent=2)


def get_or_create_id(link, id_map):
    """获取或创建项目 ID

    使用项目链接作为唯一标识，确保 ID 稳定。
    """
    if link in id_map['mappings']:
        return id_map['mappings'][link]

    # 分配新 ID
    new_id = id_map['next_id']
    id_map['mappings'][link] = new_id
    id_map['next_id'] = new_id + 1
    return new_id


def parse_entry(line, lang):
    """解析单行条目"""
    # 支持有描述和无描述两种格式
    pattern_with_desc = r'\* 【(\d{4}-\d{2}-\d{2})】\[([^\]]+)\]\(([^)]+)\)\s*-\s*(.+)'
    pattern_no_desc = r'\* 【(\d{4}-\d{2}-\d{2})】\[([^\]]+)\]\(([^)]+)\)\s*$'

    match = re.match(pattern_with_desc, line.strip())
    if match:
        return {
            '日期': match.group(1),
            '仓库名': match.group(2).replace(' / ', '/'),
            '链接': match.group(3),
            '介绍': match.group(4).strip(),
            '来自榜单': lang
        }

    match = re.match(pattern_no_desc, line.strip())
    if match:
        return {
            '日期': match.group(1),
            '仓库名': match.group(2).replace(' / ', '/'),
            '链接': match.group(3),
            '介绍': '',
            '来自榜单': lang
        }

    return None


def parse_markdown_file(filepath):
    """解析单个 markdown 文件，返回条目列表"""
    entries = []
    current_lang = ""

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            # 检测语言标题
            if line.startswith('## '):
                current_lang = line[3:].strip()
            # 检测项目条目
            elif line.startswith('* 【'):
                entry = parse_entry(line, current_lang)
                if entry:
                    entries.append(entry)
    return entries


def get_all_entries(project_root):
    """获取所有数据源的条目"""
    all_entries = []

    # 先读取 archived 目录下所有 md 文件（按文件名排序，最早的先处理）
    archived_dir = project_root / 'archived'
    if archived_dir.exists():
        for md_file in sorted(archived_dir.glob('*.md')):
            entries = parse_markdown_file(md_file)
            all_entries.extend(entries)

    # 再读取 README.md（最新的数据）
    readme_path = project_root / 'README.md'
    if readme_path.exists():
        entries = parse_markdown_file(readme_path)
        all_entries.extend(entries)

    return all_entries


def deduplicate_entries(entries):
    """去重，保留最早的记录"""
    seen = {}
    for entry in entries:
        link = entry['链接']
        if link not in seen:
            seen[link] = entry
        else:
            # 保留日期更早的记录
            if entry['日期'] < seen[link]['日期']:
                seen[link] = entry
    return list(seen.values())


def export_to_csv(entries, output_path):
    """导出为 CSV 文件"""
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ['id', '日期', '仓库名', '链接', '介绍', '来自榜单']

    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        # 按 ID 排序后写入
        sorted_entries = sorted(entries, key=lambda x: x['id'])
        writer.writerows(sorted_entries)


def main():
    # 获取项目根目录
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_path = project_root / 'data' / 'trending.csv'
    mapping_path = project_root / 'data' / 'id_mapping.json'

    # 加载 ID 映射
    id_map = load_id_mapping(mapping_path)
    initial_count = len(id_map['mappings'])

    # 获取所有条目
    print('正在读取数据...')
    all_entries = get_all_entries(project_root)
    print(f'共读取到 {len(all_entries)} 条记录')

    # 去重（保留最早的记录）
    print('正在去重...')
    unique_entries = deduplicate_entries(all_entries)
    print(f'去重后剩余 {len(unique_entries)} 条记录')

    # 按日期和仓库名排序，确保首次分配 ID 时的顺序一致
    unique_entries.sort(key=lambda x: (x['日期'], x['仓库名']))

    # 为每个条目分配 ID
    for entry in unique_entries:
        entry['id'] = get_or_create_id(entry['链接'], id_map)

    # 保存更新后的 ID 映射
    save_id_mapping(id_map, mapping_path)

    new_count = len(id_map['mappings']) - initial_count
    if new_count > 0:
        print(f'新分配了 {new_count} 个 ID')

    # 导出
    print(f'正在导出到 {output_path}...')
    export_to_csv(unique_entries, output_path)
    print('导出完成!')


if __name__ == '__main__':
    main()
