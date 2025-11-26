"""
目标1: 高赞评论关键词分析
功能：
1. 读取格式化后的评论数据
2. 筛选高赞评论
3. 使用jieba进行中文分词
4. 统计词频和TF-IDF关键词
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


# 停用词列表
STOPWORDS = set([
    '的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
    '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
    '自己', '这', '那', '里', '为', '什么', '吗', '啊', '呢', '吧', '么', '呀',
    '这个', '那个', '怎么', '没', '能', '可以', '就是', '还', '但是', '如果',
    '因为', '所以', '而且', '或者', '虽然', '但', '只', '把', '被', '让', '给',
    '用', '从', '对', '与', '及', '等', '以', '之', '而', '且', '或', '则',
    '来', '去', '过', '做', '想', '知道', '觉得', '感觉', '应该', '可能',
    '真的', '真是', '确实', '已经', '还是', '不是', '这样', '那样', '这么', '那么',
    '多', '少', '大', '小', '高', '低', '长', '短', '新', '老', '好', '坏',
    '比心', '赞', '玫瑰', '鼓掌', '感谢', '捂脸', '流泪', '呲牙', '大金牙',
    '666', '哈哈', '嘿嘿', '哦', '嗯', '啦', '喔', '哇', '唉', '嘛', '哎',
    '一下', '一点', '一些', '一样', '一起', '一直', '不要', '不会', '不能',
    '最', '太', '更', '非常', '特别', '十分', '比较', '相当', '尤其',
    '他', '她', '它', '他们', '她们', '它们', '我们', '你们', '咱们', '大家',
    '这里', '那里', '哪里', '什么时候', '为什么', '怎么样', '多少',
])


def clean_text(text):
    if pd.isna(text):
        return ''
    text = str(text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)
    return text


def segment_words(text):
    words = jieba.cut(text)
    return [w for w in words if len(w) >= 2 and w not in STOPWORDS]


def analyze_comments(df, min_likes=10):
    high_like_comments = df[pd.to_numeric(df['评论点赞数'], errors='coerce') >= min_likes].copy()
    print(f'高赞评论数量 (点赞>={min_likes}): {len(high_like_comments)}')
    
    all_words = []
    for content in high_like_comments['评论内容'].dropna():
        cleaned = clean_text(content)
        words = segment_words(cleaned)
        all_words.extend(words)
    
    word_freq = Counter(all_words)
    print(f'不重复词汇数量: {len(word_freq)}')
    
    all_text = ' '.join(high_like_comments['评论内容'].dropna().apply(clean_text))
    tfidf_keywords = jieba.analyse.extract_tags(all_text, topK=100, withWeight=True)
    
    return high_like_comments, word_freq, tfidf_keywords


def main():
    base_dir = Path(__file__).parent.parent
    input_file = base_dir / 'formatdata' / 'all_comments.csv'
    output_dir = base_dir / 'csvabstract'
    report_dir = base_dir / 'dock'
    
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    
    print('='*60)
    print('目标1: 高赞评论关键词分析')
    print('='*60)
    
    df = pd.read_csv(input_file, encoding='utf-8-sig')
    print(f'总评论数: {len(df)}')
    
    high_comments, word_freq, tfidf_kw = analyze_comments(df, min_likes=10)
    
    freq_df = pd.DataFrame(word_freq.most_common(200), columns=['关键词', '词频'])
    freq_df['排名'] = range(1, len(freq_df) + 1)
    freq_df = freq_df[['排名', '关键词', '词频']]
    freq_path = output_dir / '高赞评论关键词统计.csv'
    freq_df.to_csv(freq_path, index=False, encoding='utf-8-sig')
    print(f'词频统计已保存: {freq_path}')
    
    tfidf_df = pd.DataFrame(tfidf_kw, columns=['关键词', 'TF-IDF权重'])
    tfidf_df['排名'] = range(1, len(tfidf_df) + 1)
    tfidf_df = tfidf_df[['排名', '关键词', 'TF-IDF权重']]
    tfidf_path = output_dir / '高赞评论TF-IDF关键词.csv'
    tfidf_df.to_csv(tfidf_path, index=False, encoding='utf-8-sig')
    print(f'TF-IDF关键词已保存: {tfidf_path}')
    
    top20_freq = freq_df.head(20)
    top20_tfidf = tfidf_df.head(20)
    
    report = f'''# 目标1: 高赞评论关键词分析报告

## 分析概览

| 指标 | 数值 |
|------|------|
| 分析时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |
| 总评论数 | {len(df):,} |
| 高赞评论数(点赞>=10) | {len(high_comments):,} |
| 不重复词汇数 | {len(word_freq):,} |

---

## TOP20 高频关键词

| 排名 | 关键词 | 词频 |
|------|--------|------|
'''
    for _, row in top20_freq.iterrows():
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

## 关键词分析结论

### 主要发现

1. **核心主题词**: 从词频和TF-IDF分析中可以看出评论的核心关注点
2. **情感倾向**: 高赞评论体现了公众对相关话题的态度和情感
3. **关注焦点**: 反映了观众对"绘说现代化"系列视频内容的反馈重点

### 输出文件

- csvabstract/高赞评论关键词统计.csv - TOP200词频统计
- csvabstract/高赞评论TF-IDF关键词.csv - TOP100 TF-IDF关键词

---

*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
'''
    
    report_path = report_dir / '目标1_高赞评论关键词分析报告.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'分析报告已保存: {report_path}')
    
    print('='*60)
    print('目标1完成!')
    print('='*60)


if __name__ == '__main__':
    main()
