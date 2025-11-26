"""
目标2: 视频标题高频词分析
功能：
1. 读取视频信息汇总
2. 提取所有视频标题
3. 使用jieba进行中文分词
4. 统计高频词汇
5. 输出结果和总结报告
"""

import os
import re
import jieba
import jieba.analyse
import pandas as pd
from pathlib import Path
from collections import Counter
from datetime import datetime


# 停用词列表（针对标题优化）
STOPWORDS = set([
    '的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
    '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
    '这', '那', '里', '为', '什么', '吗', '啊', '呢', '吧', '么', '呀', '多',
    '这个', '那个', '怎么', '没', '能', '可以', '就是', '还', '但是', '如果',
    '让', '给', '用', '从', '对', '与', '及', '等', '以', '之', '而', '且', '或',
    '来', '去', '过', '做', '想', '一起', '带你', '感受',
    '绘说现代化', '现代化', '磅礴', '力量', '分钟', '视频',
])


def clean_title(text):
    if pd.isna(text):
        return ''
    text = str(text)
    # 移除#标签
    text = re.sub(r'#\S+', '', text)
    # 移除表情符号
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', '', text)
    return text.strip()


def segment_words(text):
    words = jieba.cut(text)
    return [w for w in words if len(w) >= 2 and w not in STOPWORDS]


def extract_themes(titles):
    """提取主题分类"""
    themes = {
        '农业/粮食': ['种地', '粮食', '农业', '农田', '春耕', '种子', '耕地', '农民'],
        '科技/创新': ['科技', '5G', '数字', '创新', '专利', 'AI', '技术'],
        '工业/制造': ['汽车', '新能源', '造船', '制造', '工业', '航天'],
        '生态/环境': ['种树', '绿色', '生态', '环保', '能源', '清洁'],
        '文化/遗产': ['文化', '遗产', '大运河', '非遗', '传承', '历史'],
        '民生/社会': ['医保', '健康', '教育', '读书', '妇女', '儿童'],
        '交通/基建': ['高铁', '铁路', '公路', '桥梁', '基建'],
        '地方发展': ['辽宁', '广西', '云南', '新疆', '北京', '东北'],
    }
    
    theme_counts = {k: 0 for k in themes}
    for title in titles:
        for theme, keywords in themes.items():
            for kw in keywords:
                if kw in title:
                    theme_counts[theme] += 1
                    break
    
    return theme_counts


def main():
    base_dir = Path(__file__).parent.parent
    input_file = base_dir / 'formatdata' / 'all_videos_info.csv'
    output_dir = base_dir / 'csvabstract'
    report_dir = base_dir / 'dock'
    
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    
    print('='*60)
    print('目标2: 视频标题高频词分析')
    print('='*60)
    
    df = pd.read_csv(input_file, encoding='utf-8-sig')
    print(f'总视频数: {len(df)}')
    
    # 提取标题
    titles = df['视频标题'].dropna().tolist()
    
    # 保存视频标题列表
    title_df = df[['目录编号', '视频ID', '视频标题', '发布时间_格式化', '点赞数', '分享数', '播放数']].copy()
    title_path = output_dir / '视频标题列表.csv'
    title_df.to_csv(title_path, index=False, encoding='utf-8-sig')
    print(f'视频标题列表已保存: {title_path}')
    
    # 分词统计
    all_words = []
    for title in titles:
        cleaned = clean_title(title)
        words = segment_words(cleaned)
        all_words.extend(words)
    
    word_freq = Counter(all_words)
    print(f'不重复词汇数量: {len(word_freq)}')
    
    # 保存高频词统计
    freq_df = pd.DataFrame(word_freq.most_common(100), columns=['关键词', '词频'])
    freq_df['排名'] = range(1, len(freq_df) + 1)
    freq_df = freq_df[['排名', '关键词', '词频']]
    freq_path = output_dir / '视频标题高频词统计.csv'
    freq_df.to_csv(freq_path, index=False, encoding='utf-8-sig')
    print(f'高频词统计已保存: {freq_path}')
    
    # 提取TF-IDF关键词
    all_text = ' '.join([clean_title(t) for t in titles])
    tfidf_keywords = jieba.analyse.extract_tags(all_text, topK=50, withWeight=True)
    
    tfidf_df = pd.DataFrame(tfidf_keywords, columns=['关键词', 'TF-IDF权重'])
    tfidf_df['排名'] = range(1, len(tfidf_df) + 1)
    tfidf_df = tfidf_df[['排名', '关键词', 'TF-IDF权重']]
    tfidf_path = output_dir / '视频标题TF-IDF关键词.csv'
    tfidf_df.to_csv(tfidf_path, index=False, encoding='utf-8-sig')
    print(f'TF-IDF关键词已保存: {tfidf_path}')
    
    # 主题分类统计
    theme_counts = extract_themes(titles)
    theme_df = pd.DataFrame(list(theme_counts.items()), columns=['主题分类', '视频数量'])
    theme_df = theme_df.sort_values('视频数量', ascending=False)
    theme_path = output_dir / '视频主题分类统计.csv'
    theme_df.to_csv(theme_path, index=False, encoding='utf-8-sig')
    print(f'主题分类统计已保存: {theme_path}')
    
    # 生成报告
    top30_freq = freq_df.head(30)
    top20_tfidf = tfidf_df.head(20)
    
    report = f'''# 目标2: 视频标题高频词分析报告

## 分析概览

| 指标 | 数值 |
|------|------|
| 分析时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |
| 总视频数 | {len(df)} |
| 不重复词汇数 | {len(word_freq)} |

---

## TOP30 标题高频词

| 排名 | 关键词 | 词频 |
|------|--------|------|
'''
    for _, row in top30_freq.iterrows():
        report += f"| {row['排名']} | {row['关键词']} | {row['词频']} |\n"
    
    report += f'''
---

## TOP20 TF-IDF关键词

| 排名 | 关键词 | TF-IDF权重 |
|------|--------|------------|
'''
    for _, row in top20_tfidf.iterrows():
        report += f"| {row['排名']} | {row['关键词']} | {row['TF-IDF权重']:.4f} |\n"
    
    report += f'''
---

## 视频主题分类统计

| 主题分类 | 视频数量 |
|----------|----------|
'''
    for _, row in theme_df.iterrows():
        report += f"| {row['主题分类']} | {row['视频数量']} |\n"
    
    report += f'''
---

## 标题分析结论

### 主要发现

1. **核心主题**: 视频标题涵盖农业、科技、生态、文化等多个现代化建设领域
2. **内容特点**: 标题多使用"中国有多牛"、"震撼"等表达民族自豪感的词汇
3. **传播策略**: 标题注重数据呈现和情感共鸣，增强传播效果

### 主题分布

从主题分类可以看出，"绘说现代化"系列视频涵盖：
- 农业现代化（粮食安全、科技种田）
- 工业制造（汽车、造船、航天）
- 生态文明（植树造林、清洁能源）
- 文化传承（大运河、世界遗产）
- 民生改善（医保、教育）

### 输出文件

- csvabstract/视频标题列表.csv - 完整视频标题信息
- csvabstract/视频标题高频词统计.csv - TOP100高频词
- csvabstract/视频标题TF-IDF关键词.csv - TOP50 TF-IDF关键词
- csvabstract/视频主题分类统计.csv - 主题分类统计

---

*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
'''
    
    report_path = report_dir / '目标2_视频标题高频词分析报告.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'分析报告已保存: {report_path}')
    
    print('='*60)
    print('目标2完成!')
    print('='*60)


if __name__ == '__main__':
    main()
