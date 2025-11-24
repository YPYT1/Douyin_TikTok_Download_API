"""
完整爬取抖音合集（含视频详情与评论），结构化落盘。
输出结构：
output/
 ├─001/【视频标题】.csv   （含视频元信息 + 一级/二级评论）
 ├─002/...
"""

import argparse
import asyncio
import csv
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from crawlers.douyin.web.web_crawler import DouyinWebCrawler

# 让 stdout 行缓冲，避免“无响应”错觉
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """去除文件名非法字符，限制长度"""
    invalid = '\\/:*?"<>|'
    for ch in invalid:
        name = name.replace(ch, "_")
    name = name.strip().replace("\n", " ").replace("\r", " ")
    return (name[:max_len] or "untitled").strip()


class MixCrawler:
    """合集爬虫（逐个视频爬取并立即保存为CSV）"""

    def __init__(self, output_dir: Path, max_comments: int, sleep: float):
        self.crawler = DouyinWebCrawler()
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)
        self.max_comments = max_comments
        self.sleep = sleep

    async def verify_cookie(self) -> bool:
        """验证Cookie是否有效，通过请求用户信息接口测试"""
        print("\n【Cookie验证】正在检查Cookie有效性...")
        try:
            # 尝试获取热搜（无需登录的公开接口）
            resp = await self.crawler.fetch_hot_search_result()
            if resp and "data" in resp:
                print("✓ Cookie基础验证通过（能访问公开接口）")
                
                # 进一步验证评论接口（随机测试视频）
                print("✓ 正在测试评论接口...")
                test_aweme_id = "7320576816895348005"  # 测试视频ID
                comment_resp = await self.crawler.fetch_video_comments(
                    aweme_id=test_aweme_id, cursor=0, count=1
                )
                
                if comment_resp is not None:
                    # 检查是否有comments字段，或者是否有错误信息
                    if "comments" in comment_resp or comment_resp.get("status_code") == 0:
                        print("✓ Cookie完全验证通过！可以正常获取评论\n")
                        return True
                    elif "status_code" in comment_resp:
                        status_code = comment_resp.get("status_code")
                        status_msg = comment_resp.get("status_msg", "未知错误")
                        print(f"\n✗ 评论接口返回错误:")
                        print(f"  状态码: {status_code}")
                        print(f"  错误信息: {status_msg}")
                        if status_code == 2053:
                            print("  \n原因: Cookie已过期或需要重新登录")
                        elif status_code == 8:
                            print("  \n原因: 请求频率过快，被限流")
                        return False
                    else:
                        print("\n✗ 评论接口返回空内容，可能原因：")
                        print("  1. Cookie 已过期或不完整")
                        print("  2. 被风控系统拦截")
                        print("  3. msToken/verifyFp 等参数失效")
                        return False
                else:
                    print("\n✗ 评论接口返回 None")
                    return False
            else:
                print("\n✗ Cookie验证失败：无法访问基础接口")
                return False
                
        except Exception as e:
            print(f"\n✗ Cookie验证异常: {e}")
            return False

    async def crawl_mix_complete(self, mix_id: str, crawl_comments: bool = True):
        print(f"\n{'=' * 70}")
        print(f"开始爬取合集: {mix_id}")
        print(f"{'=' * 70}\n")

        # 先验证Cookie
        if not await self.verify_cookie():
            print("\n" + "=" * 70)
            print("⚠️  Cookie验证失败，请更新Cookie后重试！")
            print("=" * 70)
            print("\n更新Cookie步骤：")
            print("1. 打开浏览器访问 https://www.douyin.com 并登录")
            print("2. F12 打开开发者工具 → Network(网络)选项卡")
            print("3. 随便打开一个视频的评论区")
            print("4. 找到 'comment/list' 请求，点击查看 Request Headers")
            print("5. 复制完整的 Cookie 值")
            print("6. 替换到 crawlers/douyin/web/config.yaml 的 Cookie 字段")
            print("7. 保存文件并重新运行\n")
            return

        cursor = 0
        page = 1
        total_videos = 0

        while True:
            try:
                print(f"【获取第 {page} 页视频】")
                resp = await self.crawler.fetch_user_mix_videos(
                    mix_id=mix_id, cursor=cursor, count=20
                )
                if not resp:
                    print("✗ 未获取到视频，可能 Cookie 失效或接口变更")
                    break

                videos = resp.get("aweme_list") or []
                if not videos:
                    print("✓ 没有更多视频")
                    break

                print(f"  获取到 {len(videos)} 个视频\n")

                for video in videos:
                    total_videos += 1
                    await self.process_single_video(
                        video=video,
                        video_index=total_videos,
                        crawl_comments=crawl_comments,
                    )
                    await asyncio.sleep(self.sleep)

                has_more = resp.get("has_more", 0) == 1
                cursor = resp.get("cursor", 0)
                if not has_more:
                    break

                page += 1
                await asyncio.sleep(self.sleep)

            except Exception as e:
                print(f"  ✗ 获取第 {page} 页失败: {e}")
                break

        print(f"\n{'=' * 70}")
        print("爬取完成！")
        print(f"已处理视频总数: {total_videos}")
        print(f"输出目录: {self.output_dir.resolve()}")
        print(f"{'=' * 70}")

    async def process_single_video(self, video: Dict[str, Any], video_index: int, crawl_comments: bool):
        """处理单个视频：获取评论并立即保存为CSV"""
        folder = self.output_dir / f"{video_index:03d}"
        folder.mkdir(exist_ok=True)

        video_meta = self.extract_video_meta(video_index, video)
        file_name = sanitize_filename(f"{video_meta['视频标题']}_{video_meta['视频ID']}") + ".csv"
        file_path = folder / file_name

        if file_path.exists():
            print(f"  {video_index:03d} 已存在，跳过：{file_name}")
            return

        print(f"【处理视频 {video_index:03d}】{video_meta['视频标题'][:50]}...")

        comments: List[Dict[str, Any]] = []
        if crawl_comments and video_meta["评论总数"] > 0:
            try:
                comments = await self.get_all_comments(
                    aweme_id=video_meta["视频ID"],
                    video_title=video_meta["视频标题"],
                    expect_count=video_meta["评论总数"],
                )
            except Exception as e:
                print(f"    ✗ 拉取评论失败(已跳过): {e}")
                comments = []
            except BaseException as e:
                print(f"    ✗ 拉取评论被中断(已跳过): {e}")
                comments = []

        rows = self.merge_video_and_comments(video_meta, comments)
        self.save_csv(file_path, rows)

        try:
            rel_path = file_path.relative_to(self.output_dir)
        except Exception:
            rel_path = file_path.name
        print(f"  ✓ 已保存: {rel_path}\n")


    async def get_all_comments(self, aweme_id: str, video_title: str, expect_count: int):
        """完整拉取一级评论+部分二级（按 tt.md 要求），受 max_comments 限制"""
        collected: List[Dict[str, Any]] = []
        cursor = 0

        while len(collected) < self.max_comments:
            try:
                resp = await self.crawler.fetch_video_comments(
                    aweme_id=aweme_id, cursor=cursor, count=20
                )
                if not resp or "comments" not in resp:
                    break
                comments = resp.get("comments") or []
                if not comments:
                    break

                for c in comments:
                    collected.append(self.format_comment_row(c, level=1))
                    # 二级回复（只取必要数量，避免过多请求）
                    reply_total = c.get("reply_comment_total", 0)
                    if reply_total > 0 and len(collected) < self.max_comments:
                        replies = await self.get_comment_replies(
                            item_id=aweme_id,
                            comment_id=c.get("cid", ""),
                            max_needed=self.max_comments - len(collected),
                        )
                        collected.extend(replies)

                    if len(collected) >= self.max_comments:
                        break

                has_more = resp.get("has_more", 0) == 1
                cursor = resp.get("cursor", 0)
                if not has_more:
                    break
                await asyncio.sleep(0.25)

            except Exception as e:
                print(f"    ✗ 拉取评论失败: {e}")
                break

        print(f"    ✓ 获取 {len(collected)} 条评论（预期 {expect_count}）")
        return collected

    async def get_comment_replies(self, item_id: str, comment_id: str, max_needed: int):
        """获取二级回复，至多 max_needed"""
        replies: List[Dict[str, Any]] = []
        cursor = 0
        while len(replies) < max_needed:
            try:
                resp = await self.crawler.fetch_video_comments_reply(
                    item_id=item_id, comment_id=comment_id, cursor=cursor, count=20
                )
                if not resp or "comments" not in resp:
                    break
                data = resp.get("comments") or []
                if not data:
                    break

                for r in data:
                    replies.append(self.format_comment_row(r, level=2, parent_id=comment_id))
                    if len(replies) >= max_needed:
                        break

                has_more = resp.get("has_more", 0) == 1
                cursor = resp.get("cursor", 0)
                if not has_more:
                    break
                await asyncio.sleep(0.2)
            except Exception:
                break
        return replies

    def extract_video_meta(self, idx: int, video: Dict[str, Any]) -> Dict[str, Any]:
        """提取 tt.md 列表中的核心字段"""
        statistics = video.get("statistics") or {}
        author = video.get("author") or {}
        video_info = video.get("video") or {}
        text_extra = video.get("text_extra") or []
        topics = [t.get("hashtag_name") for t in text_extra if t.get("hashtag_name")]
        mentions = [t.get("user_id") for t in text_extra if t.get("user_id")]

        duration_ms = video_info.get("duration", 0)
        create_time = datetime.fromtimestamp(video.get("create_time", 0))

        return {
            "序号": idx,
            "视频ID": video.get("aweme_id", ""),
            "视频标题": video.get("desc", ""),
            "视频描述": video.get("desc", ""),
            "视频URL": f"https://www.douyin.com/video/{video.get('aweme_id', '')}",
            "发布时间": create_time.strftime("%Y-%m-%d %H:%M:%S"),
            "视频时长(s)": round(duration_ms / 1000, 2),
            "作者昵称": author.get("nickname", ""),
            "作者ID": author.get("unique_id") or author.get("short_id") or author.get("uid", ""),
            "话题标签": "|".join(topics) if topics else "",
            "@用户": "|".join(map(str, mentions)) if mentions else "",
            "点赞数": statistics.get("digg_count", 0),
            "收藏数": statistics.get("collect_count", 0),
            "分享数": statistics.get("share_count", 0),
            "播放数": statistics.get("play_count", 0),
            "评论总数": statistics.get("comment_count", 0),
            # 下面用于与评论合并的占位
            "层级": "video",
            "评论ID": "",
            "父评论ID": "",
            "评论内容": "",
            "评论用户": "",
            "评论点赞": "",
            "评论时间": "",
        }

    def format_comment_row(self, comment: Dict[str, Any], level: int, parent_id: str = "") -> Dict[str, Any]:
        user = comment.get("user") or {}
        ts = comment.get("create_time", 0)
        return {
            "序号": "",
            "视频ID": comment.get("aweme_id", ""),
            "视频标题": "",
            "视频描述": "",
            "视频URL": "",
            "发布时间": "",
            "视频时长(s)": "",
            "作者昵称": "",
            "作者ID": "",
            "话题标签": "",
            "@用户": "",
            "点赞数": "",
            "收藏数": "",
            "分享数": "",
            "播放数": "",
            "评论总数": "",
            "层级": f"comment{level}",
            "评论ID": comment.get("cid", ""),
            "父评论ID": parent_id,
            "评论内容": comment.get("text", ""),
            "评论用户": user.get("nickname", ""),
            "评论点赞": comment.get("digg_count", 0),
            "评论时间": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "",
        }

    def merge_video_and_comments(self, video_meta: Dict[str, Any], comments: List[Dict[str, Any]]):
        """单个视频的 CSV 行：首行是视频元信息，后面跟评论"""
        rows = [video_meta]
        for c in comments:
            # 填充视频ID，便于检索
            c = {**video_meta, **c} if c.get("层级", "").startswith("comment") else c
            rows.append(c)
        return rows

    def save_csv(self, filepath: Path, data: List[Dict[str, Any]]):
        """保存为 CSV 格式（固定列顺序，兼容 tt.md）"""
        if not data:
            print(f"  ✗ 无数据，跳过保存 {filepath.name}")
            return
        try:
            fieldnames = [
                "序号", "视频ID", "视频标题", "视频描述", "视频URL", "发布时间", "视频时长(s)",
                "作者昵称", "作者ID", "话题标签", "@用户",
                "点赞数", "收藏数", "分享数", "播放数", "评论总数",
                "层级", "评论ID", "父评论ID", "评论内容", "评论用户", "评论点赞", "评论时间"
            ]
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in data:
                    writer.writerow({k: row.get(k, "") for k in fieldnames})
            print(f"  ✓ 已保存: {filepath.name} ({len(data)} 条)")
        except Exception as e:
            print(f"  ✗ 保存失败 {filepath.name}: {e}")


async def main():
    parser = argparse.ArgumentParser(description="抖音合集完整爬虫")
    parser.add_argument("--mix-id", required=True, help="合集ID，例如 7326746646719498279")
    parser.add_argument("--no-comments", action="store_true", help="仅爬视频信息，不抓评论")
    parser.add_argument("--max-comments", type=int, default=1000, help="单视频最多抓取的评论条数")
    parser.add_argument("--sleep", type=float, default=0.4, help="请求间隔秒，适当放慢防封")
    parser.add_argument("--out", type=str, default="output", help="输出目录")
    args = parser.parse_args()

    print("=" * 70)
    print("抖音合集完整爬虫")
    print("=" * 70)
    print(f"合集ID: {args.mix_id}")
    print(f"输出目录: {args.out}")
    print(f"抓评论: {not args.no_comments}，单视频上限: {args.max_comments}")
    print(f"请求间隔: {args.sleep}s")

    crawler = MixCrawler(
        output_dir=Path(args.out),
        max_comments=args.max_comments,
        sleep=max(args.sleep, 0.2),
    )
    await crawler.crawl_mix_complete(args.mix_id, crawl_comments=not args.no_comments)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
