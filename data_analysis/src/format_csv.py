"""
CSV数据格式化脚本
功能：
1. 读取output目录下所有CSV文件
2. 分离视频信息和评论数据
3. 将视频信息填充到评论行
4. 转换时间戳为可读格式
5. 输出格式化后的数据到formatdata目录
"""

import os
import pandas as pd
from datetime import datetime
from pathlib import Path


def timestamp_to_datetime(ts):
    """将时间戳转换为可读日期格式"""
    try:
        if pd.isna(ts) or ts == '':
            return ''
        return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError, OSError):
        return str(ts)


def extract_video_info(df):
    """从DataFrame中提取视频信息（第一行数据）"""
    if len(df) == 0:
        return None
    
    video_row = df[df['层级'] == 'video']
    if len(video_row) == 0:
        # 如果没有video层级，取第一行
        video_row = df.iloc[[0]]
    
    return video_row.iloc[0].to_dict()


def format_single_csv(input_path, video_info_list, all_comments_list):
    """
    格式化单个CSV文件
    
    Args:
        input_path: 输入CSV文件路径
        video_info_list: 视频信息列表（用于收集所有视频信息）
        all_comments_list: 所有评论列表（用于收集所有评论）
    
    Returns:
        tuple: (视频信息dict, 评论DataFrame)
    """
    try:
        # 读取CSV文件
        df = pd.read_csv(input_path, encoding='utf-8', dtype=str)
        
        if len(df) == 0:
            print(f"  跳过空文件: {input_path}")
            return None, None
        
        # 提取视频信息
        video_info = extract_video_info(df)
        if video_info is None:
            print(f"  无法提取视频信息: {input_path}")
            return None, None
        
        # 转换视频发布时间
        if '发布时间' in video_info:
            video_info['发布时间_格式化'] = timestamp_to_datetime(video_info['发布时间'])
        
        # 从文件名提取目录编号
        parent_dir = Path(input_path).parent.name
        video_info['目录编号'] = parent_dir
        
        # 添加到视频信息列表
        video_info_list.append(video_info)
        
        # 提取评论数据（排除video层级行）
        comments_df = df[df['层级'] != 'video'].copy()
        
        if len(comments_df) == 0:
            print(f"  无评论数据: {input_path}")
            return video_info, None
        
        # 填充视频信息到评论行
        video_fields = ['视频ID', '视频标题', '视频URL', '发布时间', '视频时长(s)', 
                       '作者昵称', '作者ID', '点赞数', '收藏数', '分享数', '播放数', '评论总数']
        
        for field in video_fields:
            if field in video_info and video_info[field]:
                comments_df[field] = video_info[field]
        
        # 添加格式化后的发布时间
        comments_df['发布时间_格式化'] = video_info.get('发布时间_格式化', '')
        comments_df['目录编号'] = parent_dir
        
        # 清理评论内容中的换行符
        if '评论内容' in comments_df.columns:
            comments_df['评论内容'] = comments_df['评论内容'].fillna('').str.replace('\n', ' ').str.replace('\r', ' ')
        
        # 添加到全部评论列表
        all_comments_list.append(comments_df)
        
        return video_info, comments_df
        
    except Exception as e:
        print(f"  处理失败: {input_path}, 错误: {e}")
        return None, None


def main():
    # 路径配置
    base_dir = Path(__file__).parent.parent
    input_dir = base_dir / 'output'
    output_dir = base_dir / 'formatdata'
    
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    print("-" * 50)
    
    # 收集所有数据
    video_info_list = []
    all_comments_list = []
    
    # 遍历所有子目录
    subdirs = sorted([d for d in input_dir.iterdir() if d.is_dir()])
    total = len(subdirs)
    
    print(f"共发现 {total} 个视频目录")
    print("-" * 50)
    
    for i, subdir in enumerate(subdirs, 1):
        # 查找CSV文件
        csv_files = list(subdir.glob('*.csv'))
        if not csv_files:
            print(f"[{i:03d}/{total}] {subdir.name}: 无CSV文件")
            continue
        
        csv_path = csv_files[0]  # 每个目录只有一个CSV
        print(f"[{i:03d}/{total}] 处理: {subdir.name}")
        
        format_single_csv(csv_path, video_info_list, all_comments_list)
    
    print("-" * 50)
    
    # 保存视频信息汇总表
    if video_info_list:
        video_df = pd.DataFrame(video_info_list)
        
        # 重新排列列顺序
        video_columns = ['目录编号', '视频ID', '视频标题', '视频URL', '发布时间', '发布时间_格式化',
                        '视频时长(s)', '作者昵称', '作者ID', '点赞数', '收藏数', '分享数', 
                        '播放数', '评论总数']
        video_columns = [c for c in video_columns if c in video_df.columns]
        video_df = video_df[video_columns]
        
        # 按点赞数排序（降序）
        if '点赞数' in video_df.columns:
            video_df['点赞数_数值'] = pd.to_numeric(video_df['点赞数'], errors='coerce')
            video_df = video_df.sort_values('点赞数_数值', ascending=False)
            video_df = video_df.drop(columns=['点赞数_数值'])
        
        video_output_path = output_dir / 'all_videos_info.csv'
        video_df.to_csv(video_output_path, index=False, encoding='utf-8-sig')
        print(f"视频信息汇总已保存: {video_output_path}")
        print(f"  共 {len(video_df)} 个视频")
    
    # 保存所有评论汇总表
    if all_comments_list:
        comments_df = pd.concat(all_comments_list, ignore_index=True)
        
        # 重新排列列顺序
        comment_columns = ['目录编号', '视频ID', '视频标题', '发布时间_格式化', '点赞数', '分享数', '播放数',
                          '层级', '评论ID', '评论内容', '评论用户', '评论用户ID', 
                          '评论点赞数', '回复数', '评论时间', 'IP属地', '回复目标用户']
        comment_columns = [c for c in comment_columns if c in comments_df.columns]
        comments_df = comments_df[comment_columns]
        
        comments_output_path = output_dir / 'all_comments.csv'
        comments_df.to_csv(comments_output_path, index=False, encoding='utf-8-sig')
        print(f"评论数据汇总已保存: {comments_output_path}")
        print(f"  共 {len(comments_df)} 条评论")
        
        # 按评论点赞数排序，保存高赞评论
        if '评论点赞数' in comments_df.columns:
            comments_df['评论点赞数_数值'] = pd.to_numeric(comments_df['评论点赞数'], errors='coerce')
            top_comments = comments_df.nlargest(500, '评论点赞数_数值')
            top_comments = top_comments.drop(columns=['评论点赞数_数值'])
            
            top_comments_path = output_dir / 'top_comments.csv'
            top_comments.to_csv(top_comments_path, index=False, encoding='utf-8-sig')
            print(f"高赞评论TOP500已保存: {top_comments_path}")
    
    print("-" * 50)
    print("格式化完成！")


if __name__ == '__main__':
    main()
