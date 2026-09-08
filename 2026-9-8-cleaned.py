# -*- coding: utf-8 -*-
"""
脏数据清洗脚本
输入: all_docs.json（爬虫原始输出）
输出: all_docs_cleaned.json

字段处理策略:
  uuid    → 不动（已验证：16位hex、唯一）
  title   → 去空格、统一"筆記"编号格式
  content → ① NFKC 归一化(清康熙部首乱码) ② 目录点线清除(保留条目文字和页码)
            注意: 羂/哳/𧙃 等佛经用字是合法字符，绝不过滤
  keywords → 不动（已验证：格式规范）
  ext     → 不动
  pages/size → 不动（数值字段）
"""
import json
import re
import unicodedata

INPUT_FILE = 'all_docs.json'
OUTPUT_FILE = 'all_docs_cleaned.json'


# ========== title 清洗 ==========
def clean_title(title: str) -> str:
    # 去掉所有空格（"筆記 016" → "筆記016"）
    title = re.sub(r'\s+', '', title)
    # 下划线统一（"筆記_010" → "筆記010"）
    title = title.replace('筆記_', '筆記')
    return title


# ========== content 清洗 ==========
def clean_content(text: str) -> str:
    # ---- 第 1 步: NFKC 归一化 ----
    # 把康熙部首区的错误字符转回正常汉字:
    #   ⽣(U+2F66) → 生(U+751F)   ⼀(U+2F00) → 一(U+4E00)  ...
    # 这是源站 docx 字体映射错误，26852 处，必须清，否则检索/分词失效
    # 只影响兼容区字符，不会动正常汉字和佛经稀有字
    text = unicodedata.normalize('NFKC', text)

    lines = text.split('\n')
    out = []
    for ln in lines:
        # ---- 第 2 步: 目录点线 ----
        # "瑜伽師地論略纂卷第十五(...)..............1603" → "...（論本…) 1603"
        # 规则: 行尾的点线(3个及以上) + 页码 → 换成 " 页码"
        # 保留条目文字和页码, 只删点线
        ln = re.sub(r'[.．·•‥⋯]{3,}\s*(\d+)\s*$', r' \1', ln)
        # 行内残留的点线(不跟页码的) → 单个空格
        ln = re.sub(r'[.．·•‥⋯]{3,}', ' ', ln)

        # ---- 第 3 步: 空白符统一 ----
        ln = ln.replace('　', ' ').replace('\u00a0', ' ').replace('\t', ' ')

        # ---- 第 4 步: 行首尾去空白 ----
        ln = ln.strip()

        # ---- 第 5 步: 连续空行压缩 ----
        # 清完点线后可能产生空行, 跳过与上一行重复的空行
        if not ln and out and out[-1] == '':
            continue
        out.append(ln)

    text = '\n'.join(out)

    # ---- 第 6 步: 去掉文首空行, 3个以上连续换行压成1个空行 ----
    text = text.strip('\n')
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text


# ========== 主流程 ==========
def main():
    with open(INPUT_FILE, encoding='utf-8') as f:
        records = json.load(f)

    for r in records:
        r['title'] = clean_title(r['title'])
        r['content'] = clean_content(r['content'])
        # uuid / keywords / ext / pages / size 原样保留, 不做任何操作

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f'清洗完成: {len(records)} 条 → {OUTPUT_FILE}')


if __name__ == '__main__':
    main()