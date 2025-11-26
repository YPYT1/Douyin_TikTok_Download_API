"""
目标4: 相关政策文献检索
功能：
1. 分析视频主题和发布时间
2. 生成搜索计划
3. 读取MCP搜索结果并生成报告

使用方式：
1. 运行 --plan 生成搜索计划
2. AI使用MCP搜索并保存结果到 search_results.json
3. 运行 --report 生成最终报告
"""

import os
import re
import json
import jieba
import pandas as pd
from pathlib import Path
from collections import Counter
from datetime import datetime
import argparse

# 主题分类映射
TOPIC_CATEGORIES = {
    '农业发展': ['农田', '种地', '粮食', '春耕', '农业', '种业', '机械化', '农作物', '荔枝', '石榴'],
    '绿色生态': ['植树', '造林', '绿色', '碳', '气候', '生态', '环保'],
    '能源建设': ['水电', '清洁能源', '新能源', '电力', '风电', '光伏', '绿电'],
    '科技创新': ['5G', '科技', '创新', '专利', '数字', '智造', '航天', 'AI'],
    '基础设施': ['南水北调', '大运河', '调水', '高铁', '交通'],
    '文化遗产': ['世界遗产', '文化', '运河', '申遗'],
    '区域发展': ['广西', '云南', '新疆', '河北', '江西'],
    '两会政策': ['两会', '政府工作报告', '热词'],
    '消费经济': ['消费', '旅游', '经济', '设备更新'],
}

# 政策搜索关键词模板
POLICY_KEYWORDS = {
    '农业发展': '中国农业政策 高标准农田 种业振兴 乡村振兴',
    '绿色生态': '中国生态文明 植树造林政策 双碳目标 绿色发展',
    '能源建设': '中国能源政策 清洁能源发展 新型电力系统',
    '科技创新': '中国科技创新政策 数字中国 知识产权战略',
    '基础设施': '中国基础设施建设 重大水利工程 交通强国',
    '文化遗产': '中国文化遗产保护 世界遗产 文化传承',
    '区域发展': '中国区域发展战略 西部大开发 乡村振兴',
    '两会政策': '两会政策要点 政府工作报告重点',
    '消费经济': '中国消费政策 扩大内需 设备更新以旧换新',
}


def classify_video_topic(title):
    """根据标题分类视频主题"""
    topics = []
    for category, keywords in TOPIC_CATEGORIES.items():
        for kw in keywords:
            if kw in title:
                topics.append(category)
                break
    return topics if topics else ['其他']


def analyze_videos(video_df):
    """分析视频主题和时间分布"""
    results = []
    
    for _, row in video_df.iterrows():
        title = str(row['视频标题'])
        pub_time = row['发布时间_格式化']
        topics = classify_video_topic(title)
        
        # 解析时间
        try:
            dt = datetime.strptime(str(pub_time), '%Y-%m-%d %H:%M:%S')
            year_month = dt.strftime('%Y-%m')
            year = dt.year
        except:
            year_month = '未知'
            year = None
        
        results.append({
            '目录编号': row['目录编号'],
            '视频标题': title[:50],
            '发布时间': pub_time,
            '年月': year_month,
            '年份': year,
            '主题分类': topics,
            '点赞数': row['点赞数'],
        })
    
    return pd.DataFrame(results)


def generate_search_plan(analysis_df):
    """生成搜索计划"""
    # 统计主题分布
    topic_counts = Counter()
    topic_times = {}
    
    for _, row in analysis_df.iterrows():
        for topic in row['主题分类']:
            topic_counts[topic] += 1
            if topic not in topic_times:
                topic_times[topic] = {'min': row['年月'], 'max': row['年月']}
            else:
                if row['年月'] < topic_times[topic]['min']:
                    topic_times[topic]['min'] = row['年月']
                if row['年月'] > topic_times[topic]['max']:
                    topic_times[topic]['max'] = row['年月']
    
    # 生成搜索计划
    search_plan = []
    for topic, count in topic_counts.most_common():
        if topic == '其他':
            continue
        time_range = topic_times.get(topic, {})
        search_plan.append({
            '主题': topic,
            '视频数量': count,
            '时间范围': f"{time_range.get('min', '未知')} ~ {time_range.get('max', '未知')}",
            '搜索关键词': POLICY_KEYWORDS.get(topic, topic + ' 政策'),
        })
    
    return search_plan


def generate_plan_output(base_dir):
    """生成搜索计划（第一阶段）"""
    video_file = base_dir / 'formatdata' / 'all_videos_info.csv'
    output_dir = base_dir / 'csvabstract'
    
    print('='*60)
    print('目标4: 相关政策文献检索 - 生成搜索计划')
    print('='*60)
    
    # 读取视频数据
    video_df = pd.read_csv(video_file, encoding='utf-8-sig')
    print(f'读取视频数量: {len(video_df)}')
    
    # 分析视频
    analysis_df = analyze_videos(video_df)
    
    # 保存分析结果
    analysis_path = output_dir / '视频主题时间分析.csv'
    analysis_df.to_csv(analysis_path, index=False, encoding='utf-8-sig')
    print(f'视频分析已保存: {analysis_path}')
    
    # 生成搜索计划
    search_plan = generate_search_plan(analysis_df)
    
    # 保存搜索计划
    plan_path = output_dir / '政策搜索计划.json'
    with open(plan_path, 'w', encoding='utf-8') as f:
        json.dump(search_plan, f, ensure_ascii=False, indent=2)
    print(f'搜索计划已保存: {plan_path}')
    
    # 打印搜索计划
    print('\n' + '='*60)
    print('搜索计划:')
    print('='*60)
    for i, plan in enumerate(search_plan, 1):
        print(f"\n{i}. 【{plan['主题']}】")
        print(f"   视频数量: {plan['视频数量']}")
        print(f"   时间范围: {plan['时间范围']}")
        print(f"   搜索关键词: {plan['搜索关键词']}")
    
    # 统计时间范围
    all_times = analysis_df['年月'].dropna().unique()
    all_times = sorted([t for t in all_times if t != '未知'])
    if all_times:
        print(f'\n整体时间范围: {all_times[0]} ~ {all_times[-1]}')
    
    print('\n' + '='*60)
    print('下一步: 请使用MCP工具搜索以上主题的相关政策')
    print('搜索结果请保存到: csvabstract/政策搜索结果.json')
    print('='*60)
    
    return search_plan


def generate_report(base_dir):
    """生成最终报告（第三阶段）"""
    output_dir = base_dir / 'csvabstract'
    report_dir = base_dir / 'dock'
    
    print('='*60)
    print('目标4: 相关政策文献检索 - 生成报告')
    print('='*60)
    
    # 读取搜索计划
    plan_path = output_dir / '政策搜索计划.json'
    with open(plan_path, 'r', encoding='utf-8') as f:
        search_plan = json.load(f)
    
    # 读取搜索结果
    results_path = output_dir / '政策搜索结果.json'
    if not results_path.exists():
        print(f'错误: 搜索结果文件不存在: {results_path}')
        print('请先使用MCP工具搜索并保存结果')
        return
    
    with open(results_path, 'r', encoding='utf-8') as f:
        search_results = json.load(f)
    
    # 读取视频分析
    analysis_path = output_dir / '视频主题时间分析.csv'
    analysis_df = pd.read_csv(analysis_path, encoding='utf-8-sig')
    
    # 生成报告
    report = f'''# 目标4: 相关政策文献检索报告

## 分析概览

| 指标 | 数值 |
|------|------|
| 分析时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |
| 视频总数 | {len(analysis_df)} |
| 主题分类数 | {len(search_plan)} |
| 搜索结果数 | {sum(len(r.get('results', [])) for r in search_results)} |

---

## 视频主题分布

| 主题 | 视频数量 | 时间范围 |
|------|----------|----------|
'''
    for plan in search_plan:
        report += f"| {plan['主题']} | {plan['视频数量']} | {plan['时间范围']} |\n"
    
    report += '\n---\n\n## 相关政策文献\n\n'
    
    # 按主题输出搜索结果
    for result in search_results:
        topic = result.get('topic', '未知主题')
        time_range = result.get('time_range', '')
        items = result.get('results', [])
        
        report += f'### {topic}\n\n'
        report += f'**搜索时间范围**: {time_range}\n\n'
        
        if items:
            report += '| 序号 | 标题 | 来源 | 链接 |\n'
            report += '|------|------|------|------|\n'
            for i, item in enumerate(items[:10], 1):  # 每个主题最多10条
                title = item.get('title', '')[:40]
                source = item.get('source', '')[:15]
                url = item.get('url', '')
                report += f'| {i} | {title} | {source} | [链接]({url}) |\n'
        else:
            report += '*暂无相关搜索结果*\n'
        
        report += '\n'
    
    report += f'''---

## 政策要点总结

### 农业现代化政策

- **高标准农田建设**: 国务院《全国高标准农田建设规划(2021—2030年)》
- **种业振兴**: 农业农村部种业振兴行动方案
- **农业机械化**: 《"十四五"全国农业机械化发展规划》

### 绿色发展政策

- **双碳目标**: 《2030年前碳达峰行动方案》
- **生态文明**: 《关于全面推进美丽中国建设的意见》
- **植树造林**: 全国绿化委员会国土绿化规划

### 科技创新政策

- **数字中国**: 《数字中国建设整体布局规划》
- **知识产权**: 《"十四五"国家知识产权保护和运用规划》
- **5G发展**: 工信部5G应用"扬帆"行动计划

### 基础设施政策

- **水利工程**: 国务院《"十四五"水安全保障规划》
- **交通强国**: 《国家综合立体交通网规划纲要》

---

## 输出文件

- csvabstract/视频主题时间分析.csv - 视频主题分类结果
- csvabstract/政策搜索计划.json - 搜索计划
- csvabstract/政策搜索结果.json - MCP搜索原始结果
- dock/目标4_政策文献检索报告.md - 本报告

---

*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
'''
    
    # 保存报告
    report_path = report_dir / '目标4_政策文献检索报告.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'报告已保存: {report_path}')
    
    print('='*60)
    print('目标4完成!')
    print('='*60)


def main():
    parser = argparse.ArgumentParser(description='目标4: 相关政策文献检索')
    parser.add_argument('--plan', action='store_true', help='生成搜索计划')
    parser.add_argument('--report', action='store_true', help='生成最终报告')
    args = parser.parse_args()
    
    base_dir = Path(__file__).parent.parent
    
    if args.plan:
        generate_plan_output(base_dir)
    elif args.report:
        generate_report(base_dir)
    else:
        # 默认执行计划生成
        print('使用方法:')
        print('  python task4_policy_search.py --plan    # 生成搜索计划')
        print('  python task4_policy_search.py --report  # 生成最终报告')
        print('\n默认执行: 生成搜索计划')
        generate_plan_output(base_dir)


if __name__ == '__main__':
    main()
