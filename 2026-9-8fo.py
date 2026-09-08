# -*- coding: utf-8 -*-
"""
佛书网 (shu.fo) 文档爬虫 v2
改进：
  1. 列表阶段只保留 .docx 版本（同书多格式去重，省 41% 请求）
  2. 详情接口 with_all_content=true，取完整正文
  3. 内置正文截断检测：content 若恰好 4096 字符会发出警告
"""
import urllib.request
import urllib.parse
import json
import time
import random

# ==================== 配置区 ====================
BASE_URL = 'https://shu.fo'
LIST_API = BASE_URL + '/api/v1/document/list'
DETAIL_API = BASE_URL + '/api/v1/document'
OUTPUT_FILE = 'all_docs.json'

PAGE_SIZE = 20
TOTAL = 100                     # 目标文档数（按"书"计，去重后）
KEEP_EXT = '.docx'              # 只保留 docx 版本
RETRIES = 3
TIMEOUT = 20                    # with_all_content=true 响应更大，超时放宽

HEADERS = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0',
    'referer': BASE_URL + '/category',
}

COLLECTED = []
SEEN_BOOKS = set()              # 已收录的书名（爬虫端去重）


# ==================== 基础层 ====================
def get_content(url, retries=RETRIES):
    request = urllib.request.Request(url=url, headers=HEADERS)
    for i in range(retries):
        try:
            response = urllib.request.urlopen(request, timeout=TIMEOUT)
            return response.read().decode('utf-8')
        except Exception as e:
            print(f'    [警告] 请求失败({i + 1}/{retries}): {e}')
            time.sleep(2 ** i)
    return None


# ==================== 数据层 ====================
def fetch_uuids(page, size=PAGE_SIZE):
    """列表 API：只返回 .docx 版本的 (uuid, title) 列表和全站总数。"""
    params = {'order': 'id desc', 'status': '2', 'page': page, 'size': size}
    url = LIST_API + '?' + urllib.parse.urlencode(params)
    content = get_content(url)
    if not content:
        return [], 0
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        print(f'    [警告] 列表第 {page} 页不是 JSON: {content[:200]}')
        return [], 0

    results = []
    for item in data.get('document') or []:
        if item.get('ext') != KEEP_EXT:          # ← 关键：非 docx 直接跳过
            continue
        title_key = item['title'].replace(' ', '')
        if title_key in SEEN_BOOKS:              # 双保险：同名书只收一次
            continue
        results.append((item['uuid'], item['title']))
    return results, data.get('total', 0)


def fetch_detail(uuid):
    """详情 API：with_all_content=true 取完整正文。"""
    params = {
        'id': 0,
        'uuid': uuid,
        'with_author': 'true',
        'with_all_content': 'true',              # ← 关键：改这里
    }
    url = DETAIL_API + '?' + urllib.parse.urlencode(params)
    return get_content(url)


# ==================== 持久层 ====================
def collect(uuid, title, content):
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f'    [警告] {uuid} 不是 JSON: {e}')
        return False

    text = data.get('content', '')
    # 截断检测：恰好 4096 说明服务器仍然截断了
    if len(text) == 4096:
        print(f'    [警告] {title} 正文仍是 4096 字符，'
              f'with_all_content=true 未生效！')

    COLLECTED.append({
        'uuid': data['uuid'],
        'title': data['title'],
        'content': text,
        'keywords': data['keywords'],
        'ext': data['ext'],
        'pages': data['pages'],
        'size': data['size'],
    })
    return True


def dump_output():
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(COLLECTED, f, ensure_ascii=False, indent=2)
    print(f'\n已写入 {OUTPUT_FILE}（共 {len(COLLECTED)} 条）')


# ==================== 主流程 ====================
def main():
    pages_needed = (TOTAL * 2 + PAGE_SIZE - 1) // PAGE_SIZE  # docx 约占一半，页数×2 兜底
    stats = {'saved': 0, 'error': 0, 'failed': 0}
    page = 1

    print(f'目标: {TOTAL} 种(docx) | 全站约 {TOTAL * 2} 条记录(含pdf)\n')

    try:
        while stats['saved'] < TOTAL and page <= pages_needed:
            print(f'===== 列表第 {page} 页 =====')
            items, total = fetch_uuids(page)
            print(f'本页 docx: {len(items)} 个（全站共 {total} 条记录）')

            if not items and page > 1:
                break

            for uuid, title in items:
                if stats['saved'] >= TOTAL:
                    break
                content = fetch_detail(uuid)
                if content is None:
                    stats['failed'] += 1
                    print(f'    [失败] {title}')
                    continue
                if collect(uuid, title, content):
                    SEEN_BOOKS.add(title.replace(' ', ''))
                    stats['saved'] += 1
                    print(f'    [成功] {stats["saved"]}/{TOTAL}  {title}')
                else:
                    stats['error'] += 1
                time.sleep(random.uniform(1, 3))

            page += 1
            time.sleep(random.uniform(2, 4))

    except KeyboardInterrupt:
        print('\n[中断] 保存已抓取部分...')

    dump_output()
    print(f'统计：成功 {stats["saved"]} | 解析失败 {stats["error"]} | 请求失败 {stats["failed"]}')


if __name__ == '__main__':
    main()