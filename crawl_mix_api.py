"""
抖音合集爬虫 - 纯API版本

直接调用 crawlers/douyin/web/web_crawler.py 中的接口：
1. 合集视频列表 - fetch_user_mix_videos
2. 一级评论 - fetch_video_comments  
3. 二级评论 - fetch_video_comments_reply

数据格式符合 tt.md 规范
无需启动任何HTTP服务，直接运行即可。

日期: 2024年
"""

import argparse
import asyncio
import csv
import json
import datetime
from pathlib import Path
from typing import Dict, List, Optional

# 导入抖音API爬虫
from crawlers.douyin.web.web_crawler import DouyinWebCrawler


def log(msg: str, level: str = "INFO"):
    """统一日志输出"""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    icons = {
        "INFO": "ℹ️ ",
        "SUCCESS": "✅",
        "WARNING": "⚠️ ",
        "ERROR": "❌",
        "DEBUG": "🔍",
        "PROGRESS": "📊",
    }
    icon = icons.get(level, "")
    print(f"[{timestamp}] {icon} {msg}")


def sanitize_filename(name: str, max_length: int = 50) -> str:
    """清理文件名，移除非法字符"""
    invalid_chars = '<>:"/\\|?*\n\r\t'
    for char in invalid_chars:
        name = name.replace(char, '')
    name = name.strip()
    if len(name) > max_length:
        name = name[:max_length]
    return name or "untitled"


class DouyinAPICrawler:
    """抖音合集爬虫 - 直接调用Python API"""
    
    def __init__(self, 
                 output_dir: str = "output_api",
                 max_comments: int = 2000,
                 fetch_replies: bool = True):
        """
        初始化爬虫
        
        Args:
            output_dir: 输出目录
            max_comments: 每个视频最大评论数
            fetch_replies: 是否获取二级评论
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.max_comments = max_comments
        self.fetch_replies = fetch_replies
        
        # API爬虫实例
        self.api = DouyinWebCrawler()
        
        # 统计
        self.stats = {
            'total_videos': 0,
            'processed_videos': 0,
            'total_comments': 0,
            'total_replies': 0,
            'failed_videos': 0,
        }
        
        # 配置
        self.retry_times = 3
        self.retry_delay = 1
    
    async def fetch_mix_videos(self, mix_id: str) -> List[Dict]:
        """获取合集视频列表"""
        log(f"获取合集视频列表 (mix_id: {mix_id})...", "INFO")
        
        videos = []
        cursor = 0
        page = 0
        
        while True:
            page += 1
            log(f"  获取第 {page} 页...", "DEBUG")
            
            try:
                resp = await self.api.fetch_user_mix_videos(
                    mix_id=mix_id, cursor=cursor, count=20
                )
                
                if not resp:
                    log(f"  第 {page} 页响应为空", "WARNING")
                    break
                
                aweme_list = resp.get('aweme_list', [])
                if not aweme_list:
                    log(f"  第 {page} 页无视频数据", "DEBUG")
                    break
                
                for item in aweme_list:
                    aweme_id = item.get('aweme_id', '')
                    if not aweme_id:
                        continue
                    
                    video = {
                        'index': len(videos) + 1,
                        'aweme_id': aweme_id,
                        'title': item.get('desc', ''),
                        'author': item.get('author', {}).get('nickname', ''),
                        'author_id': item.get('author', {}).get('sec_uid', ''),
                        'create_time': item.get('create_time', 0),
                        'duration': item.get('video', {}).get('duration', 0) // 1000,
                        'digg_count': item.get('statistics', {}).get('digg_count', 0),
                        'comment_count': item.get('statistics', {}).get('comment_count', 0),
                        'share_count': item.get('statistics', {}).get('share_count', 0),
                        'collect_count': item.get('statistics', {}).get('collect_count', 0),
                        'play_count': item.get('statistics', {}).get('play_count', 0),
                    }
                    videos.append(video)
                
                log(f"  已获取 {len(videos)} 个视频", "PROGRESS")
                
                # 检查是否还有更多
                has_more = resp.get('has_more', False)
                if not has_more:
                    break
                
                new_cursor = resp.get('cursor', 0)
                if new_cursor == cursor:
                    break
                cursor = new_cursor
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                log(f"  获取第 {page} 页失败: {e}", "ERROR")
                break
        
        log(f"共获取 {len(videos)} 个视频", "SUCCESS")
        self.stats['total_videos'] = len(videos)
        return videos
    
    async def fetch_video_comments(self, aweme_id: str, expected_count: int = 0) -> List[Dict]:
        """获取视频评论（一级 + 二级）"""
        log(f"  获取评论 (预期: {expected_count})...", "DEBUG")
        
        comments = []
        comment_ids = set()
        cursor = 0
        
        while len(comments) < self.max_comments:
            try:
                resp = await self.api.fetch_video_comments(
                    aweme_id=aweme_id, cursor=cursor, count=50
                )
                
                if not resp:
                    break
                
                comment_list = resp.get('comments', [])
                if not comment_list:
                    break
                
                for comment in comment_list:
                    cid = comment.get('cid', '')
                    if not cid or cid in comment_ids:
                        continue
                    
                    comment_ids.add(cid)
                    
                    # 解析一级评论
                    parsed = self._parse_comment(comment, level=1)
                    comments.append(parsed)
                    
                    # 获取二级评论
                    reply_count = comment.get('reply_comment_total', 0)
                    if self.fetch_replies and reply_count > 0:
                        replies = await self.fetch_comment_replies(
                            aweme_id, cid, reply_count
                        )
                        for reply in replies:
                            if reply['comment_id'] not in comment_ids:
                                comment_ids.add(reply['comment_id'])
                                comments.append(reply)
                    
                    if len(comments) >= self.max_comments:
                        break
                
                # 检查是否还有更多
                has_more = resp.get('has_more', 0)
                new_cursor = resp.get('cursor', 0)
                
                if not has_more or new_cursor == cursor:
                    break
                
                cursor = new_cursor
                await asyncio.sleep(0.3)
                
            except Exception as e:
                log(f"  获取评论失败: {e}", "WARNING")
                break
        
        return comments
    
    async def fetch_comment_replies(self, aweme_id: str, comment_id: str, 
                                     expected_count: int = 0) -> List[Dict]:
        """获取评论的二级回复"""
        replies = []
        reply_ids = set()
        cursor = 0
        max_replies = min(expected_count, 100)  # 每条评论最多获取100条回复
        
        while len(replies) < max_replies:
            try:
                resp = await self.api.fetch_video_comments_reply(
                    item_id=aweme_id,
                    comment_id=comment_id,
                    cursor=cursor,
                    count=20
                )
                
                if not resp:
                    break
                
                comment_list = resp.get('comments', [])
                if not comment_list:
                    break
                
                for reply in comment_list:
                    reply_id = reply.get('cid', '')
                    if not reply_id or reply_id in reply_ids:
                        continue
                    
                    reply_ids.add(reply_id)
                    parsed = self._parse_comment(reply, level=2)
                    replies.append(parsed)
                    
                    if len(replies) >= max_replies:
                        break
                
                has_more = resp.get('has_more', 0)
                new_cursor = resp.get('cursor', 0)
                
                if not has_more or new_cursor == cursor:
                    break
                
                cursor = new_cursor
                await asyncio.sleep(0.2)
                
            except Exception as e:
                log(f"  获取回复失败: {e}", "WARNING")
                break
        
        self.stats['total_replies'] += len(replies)
        return replies
    
    def _parse_comment(self, comment: Dict, level: int = 1) -> Dict:
        """解析评论数据"""
        try:
            comment_id = comment.get('cid', '')
            text = comment.get('text', '').strip()
            create_time = comment.get('create_time', 0)
            
            # 时间处理
            if create_time > 10000000000:
                create_time = create_time // 1000
            
            try:
                time_str = datetime.datetime.fromtimestamp(create_time).strftime('%Y-%m-%d %H:%M:%S')
            except:
                time_str = ''
            
            # 用户信息
            user = comment.get('user', {})
            nickname = user.get('nickname', '')
            user_id = user.get('uid', '') or user.get('sec_uid', '')
            
            # IP属地
            ip_label = comment.get('ip_label', '')
            
            # 回复目标
            reply_to = ''
            if comment.get('reply_to_userid'):
                reply_to = comment.get('reply_to_username', '') or str(comment.get('reply_to_userid', ''))
            
            return {
                'comment_id': comment_id,
                'text': text,
                'user': nickname,
                'user_id': user_id,
                'digg_count': comment.get('digg_count', 0),
                'reply_count': comment.get('reply_comment_total', 0),
                'create_time': time_str,
                'ip_label': ip_label,
                'level': level,
                'reply_to': reply_to,
            }
        except Exception as e:
            return {
                'comment_id': comment.get('cid', ''),
                'text': comment.get('text', ''),
                'user': '',
                'user_id': '',
                'digg_count': 0,
                'reply_count': 0,
                'create_time': '',
                'ip_label': '',
                'level': level,
                'reply_to': '',
            }
    
    async def process_video(self, video: Dict, crawl_comments: bool = True):
        """处理单个视频"""
        idx = video['index']
        aweme_id = video['aweme_id']
        total = self.stats['total_videos']
        
        # 创建输出目录
        folder = self.output_dir / f"{idx:03d}"
        folder.mkdir(exist_ok=True)
        
        title_short = (video['title'][:35] + '...') if len(video['title']) > 35 else video['title']
        
        print()
        log("=" * 60, "INFO")
        log(f"处理视频 [{idx}/{total}]", "PROGRESS")
        log(f"  标题: {title_short}", "INFO")
        log(f"  ID: {aweme_id}", "INFO")
        log(f"  作者: {video.get('author', '未知')}", "INFO")
        log(f"  时长: {video.get('duration', 0)} 秒", "INFO")
        log(f"  点赞: {video.get('digg_count', 0):,} | 评论: {video.get('comment_count', 0):,} | 分享: {video.get('share_count', 0):,}", "INFO")
        log("=" * 60, "INFO")
        
        # 视频详情
        detail = {
            'aweme_id': aweme_id,
            'title': video.get('title', ''),
            'author': video.get('author', ''),
            'author_id': video.get('author_id', ''),
            'create_time': video.get('create_time', 0),
            'duration': video.get('duration', 0),
            'digg_count': video.get('digg_count', 0),
            'comment_count': video.get('comment_count', 0),
            'share_count': video.get('share_count', 0),
            'collect_count': video.get('collect_count', 0),
            'play_count': video.get('play_count', 0),
        }
        
        # 获取评论
        comments = []
        total_expected = video.get('comment_count', 0)
        
        if crawl_comments and total_expected > 0:
            comments = await self.fetch_video_comments(aweme_id, total_expected)
            
            actual_count = len(comments)
            coverage = (actual_count / total_expected * 100) if total_expected > 0 else 0
            level1 = sum(1 for c in comments if c.get('level', 1) == 1)
            level2 = actual_count - level1
            
            self.stats['total_comments'] += actual_count
            
            if coverage >= 50:
                log(f"评论获取完成: {actual_count}/{total_expected} 条 (覆盖率 {coverage:.1f}%)", "SUCCESS")
            else:
                log(f"评论获取完成: {actual_count}/{total_expected} 条 (覆盖率 {coverage:.1f}%)", "WARNING")
            
            log(f"  一级评论: {level1} 条 | 二级评论: {level2} 条", "INFO")
        
        # 保存CSV
        file_name = sanitize_filename(f"{video['title']}_{aweme_id}") + ".csv"
        file_path = folder / file_name
        self._save_csv(file_path, detail, comments)
        log(f"已保存: {file_name}", "SUCCESS")
        
        # 保存JSON
        json_path = folder / f"{aweme_id}.json"
        self._save_json(json_path, detail, comments)
        
        self.stats['processed_videos'] += 1
    
    def _save_csv(self, filepath: Path, video: Dict, comments: List[Dict]):
        """保存为CSV - 符合tt.md格式"""
        fieldnames = [
            "序号", "视频ID", "视频标题", "视频URL", "发布时间", "视频时长(s)",
            "作者昵称", "作者ID", "点赞数", "收藏数", "分享数", "播放数", "评论总数",
            "层级", "评论ID", "评论内容", "评论用户", "评论用户ID",
            "评论点赞数", "回复数", "评论时间", "IP属地", "回复目标用户"
        ]
        
        rows = []
        
        # 视频信息行
        create_time = video.get('create_time', 0)
        if create_time > 10000000000:
            create_time = create_time // 1000
        
        video_row = {
            "序号": 1,
            "视频ID": video.get('aweme_id', ''),
            "视频标题": video.get('title', ''),
            "视频URL": f"https://www.douyin.com/video/{video.get('aweme_id', '')}",
            "发布时间": create_time,
            "视频时长(s)": video.get('duration', 0),
            "作者昵称": video.get('author', ''),
            "作者ID": video.get('author_id', ''),
            "点赞数": video.get('digg_count', 0),
            "收藏数": video.get('collect_count', 0),
            "分享数": video.get('share_count', 0),
            "播放数": video.get('play_count', 0),
            "评论总数": video.get('comment_count', 0),
            "层级": "video",
            "评论ID": "",
            "评论内容": "",
            "评论用户": "",
            "评论用户ID": "",
            "评论点赞数": "",
            "回复数": "",
            "评论时间": "",
            "IP属地": "",
            "回复目标用户": "",
        }
        rows.append(video_row)
        
        # 评论行
        for idx, comment in enumerate(comments, start=2):
            level = comment.get('level', 1)
            level_str = f"L{level}"
            
            comment_row = {
                "序号": idx,
                "视频ID": video.get('aweme_id', ''),
                "视频标题": "",
                "视频URL": "",
                "发布时间": "",
                "视频时长(s)": "",
                "作者昵称": "",
                "作者ID": "",
                "点赞数": "",
                "收藏数": "",
                "分享数": "",
                "播放数": "",
                "评论总数": "",
                "层级": level_str,
                "评论ID": comment.get('comment_id', ''),
                "评论内容": comment.get('text', ''),
                "评论用户": comment.get('user', ''),
                "评论用户ID": comment.get('user_id', ''),
                "评论点赞数": comment.get('digg_count', 0),
                "回复数": comment.get('reply_count', 0),
                "评论时间": comment.get('create_time', ''),
                "IP属地": comment.get('ip_label', ''),
                "回复目标用户": comment.get('reply_to', ''),
            }
            rows.append(comment_row)
        
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    
    def _save_json(self, filepath: Path, video: Dict, comments: List[Dict]):
        """保存为JSON"""
        data = {
            'video': video,
            'comments': comments,
            'stats': {
                'total_comments': len(comments),
                'level1_comments': sum(1 for c in comments if c.get('level', 1) == 1),
                'level2_comments': sum(1 for c in comments if c.get('level', 1) == 2),
            }
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    async def crawl_mix(self, mix_id: str, crawl_comments: bool = True, limit: int = 0):
        """爬取合集"""
        print()
        log("=" * 60, "INFO")
        log("抖音合集爬虫 - 纯API版本", "INFO")
        log("=" * 60, "INFO")
        log(f"合集ID: {mix_id}", "INFO")
        log(f"输出目录: {self.output_dir}", "INFO")
        log(f"最大评论数: {self.max_comments}", "INFO")
        log(f"抓取评论: {'是' if crawl_comments else '否'}", "INFO")
        log(f"抓取二级评论: {'是' if self.fetch_replies else '否'}", "INFO")
        if limit > 0:
            log(f"限制视频数: {limit}", "INFO")
        log("=" * 60, "INFO")
        
        # 获取视频列表
        videos = await self.fetch_mix_videos(mix_id)
        if not videos:
            log("未获取到视频列表", "ERROR")
            return
        
        # 限制视频数量
        if limit > 0:
            videos = videos[:limit]
            self.stats['total_videos'] = len(videos)
            log(f"限制处理前 {limit} 个视频", "INFO")
        
        # 处理每个视频
        for video in videos:
            try:
                await self.process_video(video, crawl_comments)
                await asyncio.sleep(1)  # 视频间隔
            except KeyboardInterrupt:
                log("用户中断", "WARNING")
                break
            except Exception as e:
                log(f"处理视频失败: {e}", "ERROR")
                self.stats['failed_videos'] += 1
                continue
        
        # 统计
        print()
        log("=" * 60, "INFO")
        log("爬取完成", "SUCCESS")
        log(f"  视频总数: {self.stats['total_videos']}", "INFO")
        log(f"  已处理: {self.stats['processed_videos']}", "INFO")
        log(f"  失败: {self.stats['failed_videos']}", "INFO")
        log(f"  评论总数: {self.stats['total_comments']}", "INFO")
        log(f"  二级评论: {self.stats['total_replies']}", "INFO")
        log(f"  输出目录: {self.output_dir}", "INFO")
        log("=" * 60, "INFO")


async def main_async():
    parser = argparse.ArgumentParser(description='抖音合集爬虫 - 纯API版本')
    parser.add_argument('--mix-id', type=str, required=True,
                        help='合集ID，例如: 7326746646719498279')
    parser.add_argument('--output', type=str, default='output_api',
                        help='输出目录，默认: output_api')
    parser.add_argument('--max-comments', type=int, default=2000,
                        help='每个视频最大评论数，默认: 2000')
    parser.add_argument('--limit', type=int, default=0,
                        help='限制处理的视频数量，0表示全部')
    parser.add_argument('--no-comments', action='store_true',
                        help='不抓取评论')
    parser.add_argument('--no-replies', action='store_true',
                        help='不抓取二级评论')
    
    args = parser.parse_args()
    
    crawler = DouyinAPICrawler(
        output_dir=args.output,
        max_comments=args.max_comments,
        fetch_replies=not args.no_replies,
    )
    
    await crawler.crawl_mix(args.mix_id, crawl_comments=not args.no_comments, limit=args.limit)


def main():
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
