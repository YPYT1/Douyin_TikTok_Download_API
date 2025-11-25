"""
使用 Playwright 模拟真实浏览器爬取抖音合集评论
绕过反爬检测，获取完整评论数据
"""

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.parse import urlencode

from playwright.async_api import async_playwright, Page, BrowserContext

# 导入原有的爬虫（用于获取视频列表）
from crawlers.douyin.web.web_crawler import DouyinWebCrawler

# 让 stdout 行缓冲
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


class PlaywrightMixCrawler:
    """使用 Playwright 的合集爬虫"""

    def __init__(self, output_dir: Path, max_comments: int, sleep: float, headless: bool = True, login_wait: int = 40):
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)
        self.max_comments = max_comments
        self.sleep = sleep
        self.headless = headless
        self.login_wait = login_wait  # 登录等待时间（秒）
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def init_browser(self):
        """初始化浏览器"""
        print("\n【初始化浏览器】...")
        playwright = await async_playwright().start()
        
        # 使用 Chromium，模拟真实浏览器
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        
        # 创建上下文，设置真实的浏览器指纹
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )
        
        # 注入脚本隐藏自动化特征
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            window.chrome = { runtime: {} };
        """)
        
        self.page = await self.context.new_page()
        print("✓ 浏览器初始化完成")

    async def load_cookies_from_config(self):
        """从 config.yaml 加载 Cookie"""
        try:
            import yaml
            config_path = Path("crawlers/douyin/web/config.yaml")
            if not config_path.exists():
                return False
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            cookie_str = config.get("TokenManager", {}).get("douyin", {}).get("headers", {}).get("Cookie", "")
            if not cookie_str:
                return False
            
            # 解析 Cookie 字符串
            cookies = []
            for item in cookie_str.split(';'):
                item = item.strip()
                if '=' in item:
                    name, value = item.split('=', 1)
                    cookies.append({
                        'name': name.strip(),
                        'value': value.strip(),
                        'domain': '.douyin.com',
                        'path': '/',
                    })
            
            if cookies:
                await self.context.add_cookies(cookies)
                print(f"✓ 已加载 {len(cookies)} 个 Cookie")
                return True
        except Exception as e:
            print(f"  加载 Cookie 失败: {e}")
        return False

    async def login_douyin(self):
        """打开抖音并等待用户登录（如果需要）"""
        print("\n【加载 Cookie】...")
        cookie_loaded = await self.load_cookies_from_config()
        
        print("\n【访问抖音】...")
        try:
            await self.page.goto('https://www.douyin.com', wait_until='domcontentloaded', timeout=30000)
        except Exception as e:
            print(f"  首页加载超时，继续尝试: {e}")
        
        await asyncio.sleep(3)
        print("✓ 页面已加载")
        
        # 如果已加载 Cookie，验证是否有效
        if cookie_loaded:
            # 检查是否有用户头像（表示已登录）
            try:
                avatar = await self.page.query_selector('[data-e2e="user-info"] img, .avatar, img[src*="avatar"]')
                if avatar:
                    print("✓ Cookie 有效，已登录状态")
                    return
            except:
                pass
            print("⚠️  Cookie 可能已失效")
        
        # 非无头模式下，等待用户登录
        if not self.headless:
            print("\n" + "=" * 50)
            print(f"⏳ 等待 {self.login_wait} 秒，请在浏览器中操作：")
            print("  1. 扫码登录（如有弹窗）")
            print("  2. 确保登录成功后等待倒计时结束")
            print("=" * 50)
            for i in range(self.login_wait, 0, -1):
                print(f"\r  倒计时: {i} 秒...", end="", flush=True)
                await asyncio.sleep(1)
            print("\n✓ 等待完成，开始爬取...")
            await asyncio.sleep(2)

    async def close_browser(self):
        """关闭浏览器"""
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass  # 忽略关闭时的连接错误

    async def get_mix_videos(self, mix_id: str) -> List[Dict]:
        """获取合集内所有视频 - 使用原有 API 接口"""
        print(f"\n【获取合集视频列表】mix_id={mix_id}")
        print("  使用 API 接口获取（更稳定）...")
        
        videos = []
        api_crawler = DouyinWebCrawler()
        cursor = 0
        page = 1
        
        while True:
            try:
                print(f"  获取第 {page} 页...")
                resp = await api_crawler.fetch_user_mix_videos(
                    mix_id=mix_id, cursor=cursor, count=20
                )
                
                if not resp:
                    print("  ✗ API 返回空")
                    break
                
                aweme_list = resp.get("aweme_list") or []
                if not aweme_list:
                    print("  ✓ 没有更多视频")
                    break
                
                for video in aweme_list:
                    idx = len(videos) + 1
                    aweme_id = video.get("aweme_id", "")
                    title = video.get("desc", f"视频{idx}")
                    
                    # 提取更多信息
                    statistics = video.get("statistics") or {}
                    author = video.get("author") or {}
                    
                    videos.append({
                        'index': idx,
                        'aweme_id': aweme_id,
                        'title': title,
                        'url': f"https://www.douyin.com/video/{aweme_id}",
                        # 额外信息（API 直接提供）
                        'digg_count': statistics.get("digg_count", 0),
                        'comment_count': statistics.get("comment_count", 0),
                        'share_count': statistics.get("share_count", 0),
                        'collect_count': statistics.get("collect_count", 0),
                        'play_count': statistics.get("play_count", 0),
                        'author': author.get("nickname", ""),
                        'author_id': author.get("unique_id") or author.get("short_id", ""),
                        'create_time': video.get("create_time", 0),
                        'duration': video.get("video", {}).get("duration", 0),
                        'raw_data': video,  # 保留原始数据
                    })
                
                has_more = resp.get("has_more", 0) == 1
                cursor = resp.get("cursor", 0)
                
                if not has_more:
                    break
                
                page += 1
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"  ✗ 获取失败: {e}")
                break
        
        print(f"✓ 共获取 {len(videos)} 个视频")
        return videos

    async def get_video_detail(self, aweme_id: str) -> Dict:
        """获取视频详情"""
        url = f"https://www.douyin.com/video/{aweme_id}"
        try:
            await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
        except Exception as e:
            print(f"    视频页加载超时，继续: {e}")
        await asyncio.sleep(3)
        
        detail = {
            'aweme_id': aweme_id,
            'title': '',
            'desc': '',
            'author': '',
            'author_id': '',
            'create_time': '',
            'duration': '',
            'digg_count': 0,
            'comment_count': 0,
            'share_count': 0,
            'collect_count': 0,
            'play_count': 0,
            'hashtags': [],      # 话题标签
            'mentions': [],      # @用户
        }
        
        # 解析数字的辅助函数
        def parse_count(text: str) -> int:
            text = text.strip()
            if not text:
                return 0
            text = text.replace(',', '')
            if '万' in text:
                return int(float(text.replace('万', '')) * 10000)
            if 'w' in text.lower():
                return int(float(text.lower().replace('w', '')) * 10000)
            try:
                return int(text)
            except:
                return 0
        
        try:
            # 获取标题/描述
            title_elem = await self.page.query_selector('h1, [data-e2e="video-desc"], .video-info-detail')
            if title_elem:
                detail['title'] = await title_elem.inner_text()
                detail['desc'] = detail['title']
            
            # 获取作者昵称
            author_elem = await self.page.query_selector('[data-e2e="video-author-title"], .author-card-user-name')
            if author_elem:
                detail['author'] = (await author_elem.inner_text()).strip()
            
            # 获取作者ID（从链接中提取）
            author_link = await self.page.query_selector('[data-e2e="video-author-avatar"] a, a[href*="/user/"]')
            if author_link:
                href = await author_link.get_attribute('href')
                if href:
                    # 提取 sec_user_id 或 unique_id
                    match = re.search(r'/user/([^/?]+)', href)
                    if match:
                        detail['author_id'] = match.group(1)
            
            # 获取发布时间
            time_elem = await self.page.query_selector('[data-e2e="video-time"], .video-publish-time, span:has-text("发布")')
            if time_elem:
                detail['create_time'] = (await time_elem.inner_text()).strip()
            
            # 获取视频时长（从进度条或视频元素）
            duration_elem = await self.page.query_selector('.xgplayer-time-current + .xgplayer-time-separator + span, .video-duration')
            if duration_elem:
                detail['duration'] = (await duration_elem.inner_text()).strip()
            
            # 获取话题标签 (#xxx)
            hashtag_elems = await self.page.query_selector_all('a[href*="/hashtag/"], span.hashtag, a:has-text("#")')
            for elem in hashtag_elems:
                text = await elem.inner_text()
                if text.startswith('#'):
                    detail['hashtags'].append(text.replace('#', '').strip())
            
            # 获取@用户
            mention_elems = await self.page.query_selector_all('a[href*="/user/"]:has-text("@")')
            for elem in mention_elems:
                text = await elem.inner_text()
                if text.startswith('@'):
                    detail['mentions'].append(text.replace('@', '').strip())
            
            # 获取统计数据（点赞、评论、收藏、分享）
            # 方式1: 从底部按钮获取
            stat_buttons = await self.page.query_selector_all('[data-e2e="video-tab"]')
            for btn in stat_buttons:
                text = await btn.inner_text()
                # 点赞
                if '赞' in text or 'digg' in text.lower():
                    nums = re.findall(r'[\d.]+[万w]?', text)
                    if nums:
                        detail['digg_count'] = parse_count(nums[0])
                # 评论
                elif '评论' in text or 'comment' in text.lower():
                    nums = re.findall(r'[\d.]+[万w]?', text)
                    if nums:
                        detail['comment_count'] = parse_count(nums[0])
                # 收藏
                elif '收藏' in text or 'collect' in text.lower():
                    nums = re.findall(r'[\d.]+[万w]?', text)
                    if nums:
                        detail['collect_count'] = parse_count(nums[0])
                # 分享
                elif '分享' in text or 'share' in text.lower():
                    nums = re.findall(r'[\d.]+[万w]?', text)
                    if nums:
                        detail['share_count'] = parse_count(nums[0])
            
            # 方式2: 备选 - 从 span 获取
            if detail['digg_count'] == 0:
                stats = await self.page.query_selector_all('[data-e2e="video-tab"] span, .video-info-item span')
                stat_values = []
                for stat in stats:
                    text = await stat.inner_text()
                    if text.strip():
                        stat_values.append(text)
                
                if len(stat_values) >= 1:
                    detail['digg_count'] = parse_count(stat_values[0])
                if len(stat_values) >= 2:
                    detail['comment_count'] = parse_count(stat_values[1])
                if len(stat_values) >= 3:
                    detail['collect_count'] = parse_count(stat_values[2])
                if len(stat_values) >= 4:
                    detail['share_count'] = parse_count(stat_values[3])
                
        except Exception as e:
            print(f"    获取视频详情部分失败: {e}")
        
        return detail

    async def _expand_replies(self) -> int:
        """展开所有二级评论入口（展开x条回复），返回点击的按钮数量"""
        expanded = 0
        try:
            # 方法1：通过精确类名查找展开按钮
            buttons = await self.page.query_selector_all('button.comment-reply-expand-btn, .comment-reply-expand-btn')
            for btn in buttons:
                try:
                    if await btn.is_visible():
                        await btn.click(timeout=1000)
                        expanded += 1
                        await asyncio.sleep(0.4)
                except:
                    pass
            
            # 方法2：通过文本匹配查找 "展开x条回复"
            buttons = await self.page.query_selector_all('button, span')
            for btn in buttons:
                try:
                    text = await btn.inner_text()
                    if '展开' in text and '回复' in text and '更多' not in text:
                        if await btn.is_visible():
                            await btn.click(timeout=1000)
                            expanded += 1
                            await asyncio.sleep(0.4)
                except:
                    pass
        except Exception as e:
            pass
        
        await asyncio.sleep(0.3)
        return expanded

    async def _expand_more_replies(self) -> int:
        """展开更多回复（点击"展开更多"直到变成"收起"），返回点击次数"""
        expanded = 0
        try:
            # 查找所有 "展开更多" 按钮 (class="FgYRerj2" 且包含"展开更多"文本)
            buttons = await self.page.query_selector_all('button.FgYRerj2')
            for btn in buttons:
                try:
                    text = await btn.inner_text()
                    # 只点击包含"展开更多"的按钮，跳过"收起"按钮
                    if '展开更多' in text and '收起' not in text:
                        if await btn.is_visible():
                            await btn.click(timeout=1000)
                            expanded += 1
                            await asyncio.sleep(0.5)
                except:
                    pass
            
            # 备用方法：通过文本直接查找
            if expanded == 0:
                buttons = await self.page.query_selector_all('button')
                for btn in buttons:
                    try:
                        text = await btn.inner_text()
                        if '展开更多' in text and '收起' not in text:
                            if await btn.is_visible():
                                await btn.click(timeout=1000)
                                expanded += 1
                                await asyncio.sleep(0.5)
                    except:
                        pass
        except Exception as e:
            pass
        
        return expanded

    async def _check_comments_end(self) -> bool:
        """检查是否已到评论底部（显示'暂时没有更多评论'）- 更严格的检测"""
        try:
            # 精确检测：必须在评论列表容器内找到底部标记
            result = await self.page.evaluate('''() => {
                // 在评论列表内查找底部标记
                const container = document.querySelector('[data-e2e="comment-list"]');
                if (!container) return false;
                
                // 查找底部提示文字
                const endMarker = container.querySelector('.cnqD49jq');
                if (endMarker) {
                    const text = endMarker.innerText || '';
                    if (text.includes('暂时没有更多评论') || text.includes('没有更多')) {
                        return true;
                    }
                }
                
                // 备用：直接查找文本
                const allText = container.innerText || '';
                if (allText.includes('暂时没有更多评论')) {
                    return true;
                }
                
                return false;
            }''')
            return result
        except:
            return False

    async def _full_expand_visible_replies(self) -> int:
        """完全展开当前可见的所有回复（包括展开更多），返回总点击次数"""
        total_expanded = 0
        
        # 先展开"展开x条回复"
        expanded1 = await self._expand_replies()
        total_expanded += expanded1
        
        # 然后循环点击"展开更多"直到没有更多
        max_more_rounds = 50  # 防止无限循环
        for _ in range(max_more_rounds):
            expanded2 = await self._expand_more_replies()
            if expanded2 == 0:
                break
            total_expanded += expanded2
            await asyncio.sleep(0.3)
        
        return total_expanded

    async def _is_page_valid(self) -> bool:
        """检查页面是否仍然有效"""
        try:
            if self.page is None or self.page.is_closed():
                return False
            # 尝试执行简单操作验证页面有效
            await self.page.evaluate('() => true')
            return True
        except Exception:
            return False

    async def _take_debug_screenshot(self, name: str = "debug") -> str:
        """截取调试截图并返回路径"""
        try:
            if not await self._is_page_valid():
                return ""
            screenshot_dir = self.output_dir / "screenshots"
            screenshot_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = screenshot_dir / f"{name}_{timestamp}.png"
            await self.page.screenshot(path=str(path), full_page=False)
            return str(path)
        except Exception as e:
            print(f"      截图失败: {e}")
            return ""

    async def _get_page_source_sample(self) -> str:
        """获取页面源码样本用于调试"""
        try:
            if not await self._is_page_valid():
                return ""
            # 获取评论区域的HTML
            html = await self.page.evaluate('''() => {
                const container = document.querySelector('[data-e2e="comment-list"]');
                if (container) {
                    // 只返回前5000字符避免过长
                    return container.outerHTML.substring(0, 5000);
                }
                return '';
            }''')
            return html
        except:
            return ""

    async def get_video_comments(self, aweme_id: str, expected_count: int = 0) -> List[Dict]:
        """获取视频评论 - 完整加载所有评论和回复（边滚动边展开策略）"""
        comments = []
        
        try:
            # 检查页面有效性
            if not await self._is_page_valid():
                print(f"    ⚠️ 页面已关闭，跳过评论获取")
                return comments
            
            # 等待页面加载
            await asyncio.sleep(3)
            
            # === 预处理：等待评论区加载并激活 ===
            print(f"    ⏳ 等待评论区加载...")
            
            # 等待评论区出现
            try:
                await self.page.wait_for_selector('[data-e2e="comment-list"]', timeout=10000)
            except:
                print(f"    ⚠️ 评论区未找到，尝试继续...")
            
            # 检查评论区滚动状态
            scroll_info = await self.page.evaluate('''() => {
                const container = document.querySelector('[data-e2e="comment-list"].comment-mainContent') ||
                                 document.querySelector('[data-e2e="comment-list"]') ||
                                 document.querySelector('.comment-mainContent');
                if (container) {
                    return {
                        found: true,
                        scrollable: container.scrollHeight > container.clientHeight,
                        height: container.scrollHeight,
                        clientHeight: container.clientHeight,
                        commentCount: document.querySelectorAll('[data-e2e="comment-item"]').length
                    };
                }
                return { found: false };
            }''')
            
            if scroll_info.get('found'):
                print(f"    ✓ 评论区已加载 (可滚动: {scroll_info.get('scrollable')}, 初始评论: {scroll_info.get('commentCount')}条)")
            else:
                print(f"    ⚠️ 评论区容器未找到")
            
            # 尝试点击评论区域以激活滚动
            try:
                comment_container = await self.page.query_selector('[data-e2e="comment-list"]')
                if comment_container:
                    await comment_container.click()
                    await asyncio.sleep(0.5)
            except:
                pass
            
            # === 主循环：边滚动边展开，直到到达底部 ===
            print(f"    📜 边滚动边展开评论...")
            last_comment_count = 0
            scroll_round = 0
            total_expanded = 0
            max_scroll_rounds = max(1000, expected_count * 2)  # 大幅增加上限
            reached_end = False
            no_progress_count = 0
            end_detected_count = 0  # 连续检测到底部的次数
            
            while scroll_round < max_scroll_rounds and not reached_end:
                scroll_round += 1
                
                try:
                    # 检查页面有效性（每20轮检查一次）
                    if scroll_round % 20 == 0 and not await self._is_page_valid():
                        print(f"      ⚠️ 页面已关闭，停止滚动")
                        break
                    
                    # 1. 先展开当前可见的所有回复（包括"展开更多"）
                    if scroll_round % 3 == 0:  # 每3次滚动完整展开一次
                        expanded = await self._full_expand_visible_replies()
                        total_expanded += expanded
                        if expanded > 0:
                            no_progress_count = 0
                            end_detected_count = 0  # 有新展开，重置底部计数
                    
                    # 2. 滚动评论容器
                    scrolled = await self.page.evaluate('''() => {
                        const container = document.querySelector('[data-e2e="comment-list"].comment-mainContent') ||
                                         document.querySelector('[data-e2e="comment-list"]') ||
                                         document.querySelector('.comment-mainContent');
                        if (container && container.scrollHeight > container.clientHeight) {
                            const oldTop = container.scrollTop;
                            container.scrollTop += 800;
                            return container.scrollTop > oldTop;
                        } else {
                            const oldY = window.scrollY;
                            window.scrollBy(0, 800);
                            return window.scrollY > oldY;
                        }
                    }''')
                    
                    await asyncio.sleep(0.6)
                    
                    # 3. 统计当前评论数
                    current_count = await self.page.evaluate('''() => {
                        return document.querySelectorAll('[data-e2e="comment-item"]').length;
                    }''')
                    
                    if current_count > last_comment_count:
                        no_progress_count = 0
                        end_detected_count = 0  # 有新评论，重置底部计数
                        last_comment_count = current_count
                    else:
                        no_progress_count += 1
                    
                    # 4. 检查是否到达底部（需要连续检测5次才认为真的到底）
                    if await self._check_comments_end():
                        end_detected_count += 1
                        if end_detected_count >= 5:
                            print(f"      ✓ 连续 {end_detected_count} 次检测到评论底部标记")
                            reached_end = True
                    else:
                        end_detected_count = 0
                    
                    # 5. 每10次滚动显示进度
                    if scroll_round % 10 == 0:
                        print(f"      已滚动 {scroll_round} 次，发现 {current_count} 条评论，展开 {total_expanded} 处")
                    
                    # 6. 如果滚动30轮但评论数很少，尝试备用滚动方式
                    if scroll_round == 30 and current_count < 50:
                        print(f"      📢 评论数较少，尝试备用滚动方式...")
                        # 尝试使用键盘滚动
                        try:
                            for _ in range(10):
                                await self.page.keyboard.press('PageDown')
                                await asyncio.sleep(0.3)
                        except:
                            pass
                    
                    # 7. 长时间无进展则认为到底（但要同时检测到底部标记）
                    if no_progress_count >= 50 and end_detected_count >= 3:
                        print(f"      连续 {no_progress_count} 次无新评论且检测到底部，认为已到底部")
                        reached_end = True
                    elif no_progress_count >= 150:
                        print(f"      连续 {no_progress_count} 次无新评论，强制认为已到底部")
                        reached_end = True
                        
                except Exception as e:
                    if 'closed' in str(e).lower() or 'target' in str(e).lower():
                        print(f"      ⚠️ 页面异常关闭，停止滚动")
                        break
                    # 其他异常继续尝试
                    continue
            
            print(f"    📜 第一轮滚动完成，共 {scroll_round} 轮，发现 {last_comment_count} 条评论")
            
            # === 验证阶段：再扫描2遍确保完全展开 ===
            if await self._is_page_valid():
                print(f"    🔄 验证阶段：再扫描2遍确保完全展开...")
                for verify_round in range(2):
                    try:
                        print(f"      验证第 {verify_round + 1} 遍...")
                        
                        # 滚动回顶部
                        await self.page.evaluate('''() => {
                            const container = document.querySelector('[data-e2e="comment-list"].comment-mainContent') ||
                                             document.querySelector('[data-e2e="comment-list"]') ||
                                             document.querySelector('.comment-mainContent');
                            if (container) {
                                container.scrollTop = 0;
                            } else {
                                window.scrollTo(0, 0);
                            }
                        }''')
                        await asyncio.sleep(1)
                        
                        # 从头到尾再滚动一遍，边滚动边展开
                        verify_scroll = 0
                        verify_expanded = 0
                        while verify_scroll < 500:
                            verify_scroll += 1
                            
                            # 展开所有可见的回复
                            expanded = await self._full_expand_visible_replies()
                            verify_expanded += expanded
                            
                            # 滚动
                            await self.page.evaluate('''() => {
                                const container = document.querySelector('[data-e2e="comment-list"].comment-mainContent') ||
                                                 document.querySelector('[data-e2e="comment-list"]') ||
                                                 document.querySelector('.comment-mainContent');
                                if (container && container.scrollHeight > container.clientHeight) {
                                    container.scrollTop += 500;
                                } else {
                                    window.scrollBy(0, 500);
                                }
                            }''')
                            await asyncio.sleep(0.3)
                            
                            # 检查是否到底
                            if await self._check_comments_end():
                                break
                        
                        # 统计验证后的评论数
                        final_count = await self.page.evaluate('''() => {
                            return document.querySelectorAll('[data-e2e="comment-item"]').length;
                        }''')
                        print(f"      验证第 {verify_round + 1} 遍完成：{final_count} 条评论，新展开 {verify_expanded} 处")
                        
                        # 如果这一遍没有新展开，可以提前结束
                        if verify_expanded == 0:
                            print(f"      无新展开，验证完成")
                            break
                    except Exception as e:
                        if 'closed' in str(e).lower() or 'target' in str(e).lower():
                            print(f"      ⚠️ 页面异常关闭，跳过验证")
                            break
                        continue
            
            # 最终等待
            await asyncio.sleep(2)
            
            # 截图保存当前状态用于调试
            screenshot_path = await self._take_debug_screenshot(f"comments_{aweme_id}")
            if screenshot_path:
                print(f"    📸 已保存截图: {screenshot_path}")
            
            # 使用精确选择器提取评论
            print(f"    提取评论数据...")
            raw_comments = await self.page.evaluate('''() => {
                const results = [];
                const seen = new Set();
                
                // 获取所有评论项 (使用 data-e2e="comment-item")
                const commentItems = document.querySelectorAll('[data-e2e="comment-item"]');
                
                commentItems.forEach((item, index) => {
                    try {
                        // 判断是否是二级评论（在 replyContainer 内或包含reply类）
                        const isReply = item.closest('.replyContainer') !== null || 
                                       item.closest('[class*="reply"]') !== null ||
                                       item.closest('[class*="Reply"]') !== null;
                        const level = isReply ? 2 : 1;
                        
                        // ========== 获取用户信息 ==========
                        let username = '';
                        let userId = '';
                        let userUrl = '';
                        
                        // 用户链接 a[href*="/user/"]
                        const userLink = item.querySelector('a[href*="/user/"]');
                        if (userLink) {
                            userUrl = userLink.href || '';
                            // 从URL提取用户ID
                            const userMatch = userUrl.match(/user\\/([^?]+)/);
                            if (userMatch) {
                                userId = userMatch[1];
                            }
                            
                            // 用户名在 .arnSiSbK.xtTwhlGw 或 .arnSiSbK 内的最深层span
                            const nameSpan = userLink.querySelector('.arnSiSbK.xtTwhlGw') || 
                                           userLink.querySelector('.arnSiSbK');
                            if (nameSpan) {
                                // 获取最深层的文本
                                const deepSpans = nameSpan.querySelectorAll('span');
                                if (deepSpans.length > 0) {
                                    // 取最后一个span的文本
                                    for (let i = deepSpans.length - 1; i >= 0; i--) {
                                        const text = deepSpans[i].innerText?.trim();
                                        if (text && text.length > 0) {
                                            username = text;
                                            break;
                                        }
                                    }
                                }
                                if (!username) {
                                    username = nameSpan.innerText?.trim() || '';
                                }
                            }
                            
                            // 备用方式
                            if (!username) {
                                username = userLink.innerText?.trim().split('\\n')[0] || '';
                            }
                        }
                        
                        // ========== 获取评论内容 ==========
                        let content = '';
                        let contentWithEmoji = '';
                        
                        // 评论内容在 .C7LroK_h 下的 .arnSiSbK 内
                        const contentDiv = item.querySelector('.C7LroK_h');
                        if (contentDiv) {
                            const contentSpan = contentDiv.querySelector('.arnSiSbK');
                            if (contentSpan) {
                                // 获取纯文本
                                content = contentSpan.innerText?.trim() || '';
                                
                                // 获取包含表情的完整内容
                                let fullContent = '';
                                contentSpan.childNodes.forEach(node => {
                                    if (node.nodeType === Node.TEXT_NODE) {
                                        fullContent += node.textContent;
                                    } else if (node.tagName === 'IMG') {
                                        fullContent += node.alt || '[表情]';
                                    } else if (node.tagName === 'SPAN') {
                                        fullContent += node.innerText || '';
                                    }
                                });
                                contentWithEmoji = fullContent.trim() || content;
                            }
                        }
                        
                        // ========== 获取点赞数 ==========
                        let likeCount = 0;
                        let likeText = '';
                        
                        // 点赞数在 p.xZhLomAs 下的 span 内
                        const likeP = item.querySelector('p.xZhLomAs');
                        if (likeP) {
                            const likeSpan = likeP.querySelector('span');
                            if (likeSpan) {
                                likeText = likeSpan.innerText?.trim() || '0';
                                if (likeText.includes('万')) {
                                    likeCount = Math.round(parseFloat(likeText) * 10000);
                                } else if (likeText.includes('w')) {
                                    likeCount = Math.round(parseFloat(likeText) * 10000);
                                } else {
                                    likeCount = parseInt(likeText) || 0;
                                }
                            }
                        }
                        
                        // ========== 获取时间和IP属地 ==========
                        let timeText = '';
                        let publishTime = '';
                        let ipLocation = '';
                        
                        // 时间地点在 .fJhvAqos 下的 span 内
                        const timeDiv = item.querySelector('.fJhvAqos');
                        if (timeDiv) {
                            const timeSpan = timeDiv.querySelector('span');
                            if (timeSpan) {
                                timeText = timeSpan.innerText?.trim() || '';
                                // 分离时间和IP属地 (格式: "3周前·四川")
                                if (timeText.includes('·')) {
                                    const parts = timeText.split('·');
                                    publishTime = parts[0].trim();
                                    ipLocation = parts[1]?.trim() || '';
                                } else {
                                    publishTime = timeText;
                                }
                            }
                        }
                        
                        // ========== 获取回复目标（二级评论） ==========
                        let replyToUser = '';
                        if (level === 2) {
                            // 查找 @用户 的链接
                            const replyLinks = item.querySelectorAll('a[href*="/user/"]');
                            if (replyLinks.length > 1) {
                                // 第二个链接通常是被回复的用户
                                const replyLink = replyLinks[1];
                                const replySpan = replyLink.querySelector('.arnSiSbK');
                                if (replySpan) {
                                    replyToUser = replySpan.innerText?.trim() || '';
                                }
                            }
                        }
                        
                        // 生成唯一标识
                        const key = `${username}_${content}_${timeText}_${index}`;
                        
                        // 只添加有效评论（有内容或有用户名）
                        if ((content && content.length > 0) && !seen.has(key)) {
                            seen.add(key);
                            results.push({
                                username: username || '匿名用户',
                                userId: userId,
                                userUrl: userUrl,
                                content: content,
                                contentWithEmoji: contentWithEmoji,
                                likeCount: likeCount,
                                likeText: likeText,
                                timeText: timeText,
                                publishTime: publishTime,
                                ipLocation: ipLocation,
                                level: level,
                                replyToUser: replyToUser,
                                index: index
                            });
                        }
                    } catch (e) {
                        console.error('解析评论失败:', e);
                    }
                });
                
                return results;
            }''')
            
            print(f"    提取到 {len(raw_comments)} 条评论")
            
            # 转换为标准格式，区分一级和二级评论
            level1_comments = []
            level2_comments = []
            
            for c in raw_comments:
                if c['level'] == 1:
                    level1_comments.append(c)
                else:
                    level2_comments.append(c)
            
            print(f"    一级评论: {len(level1_comments)} 条, 二级评论: {len(level2_comments)} 条")
            
            # 先添加一级评论，再添加二级评论
            parent_cid = ''
            parent_username = ''
            for idx, c in enumerate(raw_comments[:self.max_comments]):
                cid = str(abs(hash(f"{c.get('userId', '')}_{c['content']}_{c['timeText']}_{idx}")))
                
                # 如果是一级评论，记录其 cid 和用户名作为后续二级评论的 parent
                if c['level'] == 1:
                    parent_cid = cid
                    parent_username = c['username']
                
                comments.append({
                    'cid': cid,
                    'text': c['content'],
                    'text_with_emoji': c.get('contentWithEmoji', c['content']),
                    'user': c['username'],
                    'user_id': c.get('userId', ''),
                    'user_url': c.get('userUrl', ''),
                    'digg_count': c['likeCount'],
                    'digg_count_text': c.get('likeText', ''),
                    'create_time': c.get('publishTime', c['timeText']),
                    'time_text': c['timeText'],
                    'ip_location': c.get('ipLocation', ''),
                    'level': c['level'],
                    'parent_cid': parent_cid if c['level'] == 2 else '',
                    'parent_user': parent_username if c['level'] == 2 else '',
                    'reply_to_user': c.get('replyToUser', ''),
                })
                
        except Exception as e:
            print(f"    获取评论异常: {e}")
            import traceback
            traceback.print_exc()
        
        return comments

    async def process_video(self, video: Dict, crawl_comments: bool = True):
        """处理单个视频"""
        idx = video['index']
        aweme_id = video['aweme_id']
        
        folder = self.output_dir / f"{idx:03d}"
        folder.mkdir(exist_ok=True)
        
        title_short = video['title'][:40] if video['title'] else f"视频{idx}"
        print(f"\n【处理视频 {idx:03d}】{title_short}...")
        
        # 使用 API 已经获取的视频信息（不需要再访问页面获取详情）
        detail = {
            'aweme_id': aweme_id,
            'title': video.get('title', ''),
            'desc': video.get('title', ''),
            'author': video.get('author', ''),
            'author_id': video.get('author_id', ''),
            'create_time': video.get('create_time', 0),
            'duration': video.get('duration', 0),
            'digg_count': video.get('digg_count', 0),
            'comment_count': video.get('comment_count', 0),
            'share_count': video.get('share_count', 0),
            'collect_count': video.get('collect_count', 0),
            'play_count': video.get('play_count', 0),
            'hashtags': [],
            'mentions': [],
        }
        
        # 从原始数据提取话题标签和@用户
        raw_data = video.get('raw_data', {})
        text_extra = raw_data.get("text_extra") or []
        detail['hashtags'] = [t.get("hashtag_name") for t in text_extra if t.get("hashtag_name")]
        detail['mentions'] = [t.get("user_id") for t in text_extra if t.get("user_id")]
        
        # 格式化时间
        if detail['create_time'] and isinstance(detail['create_time'], int):
            detail['create_time'] = datetime.fromtimestamp(detail['create_time']).strftime("%Y-%m-%d %H:%M:%S")
        
        # 格式化时长
        if detail['duration'] and isinstance(detail['duration'], int):
            detail['duration'] = round(detail['duration'] / 1000, 2)  # 毫秒转秒
        
        # 获取评论（使用 Playwright）
        comments = []
        expected_count = detail.get('comment_count', 0)
        if crawl_comments and expected_count > 0:
            print(f"    📊 预期评论数: {expected_count}")
            print(f"    🔍 使用 Playwright 获取评论...")
            
            # 打开视频页面
            url = f"https://www.douyin.com/video/{aweme_id}"
            try:
                await self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(5)  # 增加等待时间确保页面加载
                
                # 传入预期评论数以便自动调整滚动次数
                comments = await self.get_video_comments(aweme_id, expected_count)
                
                # 验证并报告
                actual_count = len(comments)
                coverage = (actual_count / expected_count * 100) if expected_count > 0 else 0
                
                if coverage >= 80:
                    print(f"    ✅ 获取 {actual_count} 条评论 (覆盖率 {coverage:.1f}%)")
                elif coverage >= 50:
                    print(f"    ⚠️  获取 {actual_count} 条评论 (覆盖率 {coverage:.1f}%，部分评论可能被折叠)")
                else:
                    print(f"    ⚠️  获取 {actual_count} 条评论 (覆盖率 {coverage:.1f}%)")
                    print(f"        说明：抖音页面可能限制了评论加载数量")
            
            except asyncio.CancelledError:
                print(f"    ⚠️  评论获取被取消，跳过此视频")
                raise  # 重新抛出以便上层处理
            except Exception as e:
                print(f"    ✗ 获取评论失败: {e}")
        
        # 保存CSV
        file_name = sanitize_filename(f"{video['title']}_{aweme_id}") + ".csv"
        file_path = folder / file_name
        self._save_csv(file_path, detail, comments)
        print(f"    ✓ 已保存: {file_path.name}")
        
        # === 视频爬取总结 ===
        actual_count = len(comments)
        level1_count = sum(1 for c in comments if c.get('level') == 1)
        level2_count = sum(1 for c in comments if c.get('level') == 2)
        total_expected = detail.get('comment_count', 0)
        coverage = (actual_count / total_expected * 100) if total_expected > 0 else 0
        
        print(f"\n    {'─' * 50}")
        print(f"    📋 视频 {idx:03d} 爬取总结")
        print(f"    {'─' * 50}")
        print(f"    │ 视频标题: {title_short}")
        print(f"    │ 视频ID:   {aweme_id}")
        print(f"    │ 预期评论: {total_expected} 条")
        print(f"    │ 实际爬取: {actual_count} 条 (覆盖率 {coverage:.1f}%)")
        print(f"    │   ├─ 一级评论: {level1_count} 条")
        print(f"    │   └─ 二级评论: {level2_count} 条")
        if coverage < 50 and total_expected > 0:
            print(f"    │ ⚠️ 覆盖率较低，可能原因：评论被折叠/页面限制/需要更多滚动")
        print(f"    {'─' * 50}\n")

    def _save_csv(self, filepath: Path, video: Dict, comments: List[Dict]):
        """保存为CSV - 完整详细版"""
        fieldnames = [
            # 视频信息
            "序号", "视频ID", "视频标题", "视频描述", "视频URL", "发布时间", "视频时长(s)",
            "作者昵称", "作者ID", "话题标签", "@用户",
            "点赞数", "收藏数", "分享数", "播放数", "评论总数",
            # 评论信息
            "层级", "评论ID", "父评论ID", "父评论用户",
            "评论内容", "评论内容(含表情)", 
            "评论用户", "评论用户ID", "评论用户主页",
            "评论点赞数", "评论点赞数(原始)",
            "评论时间", "评论时间(原始)", "IP属地",
            "回复目标用户"
        ]
        
        rows = []
        
        # 处理话题标签和@用户
        hashtags = video.get('hashtags', [])
        mentions = video.get('mentions', [])
        hashtags_str = '|'.join(hashtags) if isinstance(hashtags, list) else str(hashtags)
        mentions_str = '|'.join(mentions) if isinstance(mentions, list) else str(mentions)
        
        # 视频信息行
        video_row = {
            "序号": 1,
            "视频ID": video.get('aweme_id', ''),
            "视频标题": video.get('title', ''),
            "视频描述": video.get('desc', '') or video.get('title', ''),
            "视频URL": f"https://www.douyin.com/video/{video.get('aweme_id', '')}",
            "发布时间": video.get('create_time', ''),
            "视频时长(s)": video.get('duration', ''),
            "作者昵称": video.get('author', ''),
            "作者ID": video.get('author_id', ''),
            "话题标签": hashtags_str,
            "@用户": mentions_str,
            "点赞数": video.get('digg_count', 0),
            "收藏数": video.get('collect_count', 0),
            "分享数": video.get('share_count', 0),
            "播放数": video.get('play_count', 0),
            "评论总数": video.get('comment_count', 0),
            "层级": "video",
            "评论ID": "",
            "父评论ID": "",
            "父评论用户": "",
            "评论内容": "",
            "评论内容(含表情)": "",
            "评论用户": "",
            "评论用户ID": "",
            "评论用户主页": "",
            "评论点赞数": "",
            "评论点赞数(原始)": "",
            "评论时间": "",
            "评论时间(原始)": "",
            "IP属地": "",
            "回复目标用户": "",
        }
        rows.append(video_row)
        
        # 评论行
        for idx, c in enumerate(comments):
            comment_row = {
                "序号": idx + 2,  # 从2开始，因为1是视频行
                "视频ID": video.get('aweme_id', ''),
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
                "层级": f"L{c.get('level', 1)}",
                "评论ID": c.get('cid', ''),
                "父评论ID": c.get('parent_cid', ''),
                "父评论用户": c.get('parent_user', ''),
                "评论内容": c.get('text', ''),
                "评论内容(含表情)": c.get('text_with_emoji', c.get('text', '')),
                "评论用户": c.get('user', ''),
                "评论用户ID": c.get('user_id', ''),
                "评论用户主页": c.get('user_url', ''),
                "评论点赞数": c.get('digg_count', 0),
                "评论点赞数(原始)": c.get('digg_count_text', ''),
                "评论时间": c.get('create_time', ''),
                "评论时间(原始)": c.get('time_text', ''),
                "IP属地": c.get('ip_location', ''),
                "回复目标用户": c.get('reply_to_user', ''),
            }
            rows.append(comment_row)
        
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fieldnames})

    async def crawl_mix(self, mix_id: str, crawl_comments: bool = True):
        """爬取完整合集"""
        print(f"\n{'=' * 70}")
        print(f"Playwright 抖音合集爬虫")
        print(f"{'=' * 70}")
        print(f"合集ID: {mix_id}")
        print(f"输出目录: {self.output_dir}")
        print(f"最大评论数: {self.max_comments}")
        print(f"{'=' * 70}")
        
        try:
            await self.init_browser()
            await self.login_douyin()
            
            # 获取合集视频列表
            videos = await self.get_mix_videos(mix_id)
            
            if not videos:
                print("✗ 未获取到视频")
                return
            
            # 处理每个视频
            success_count = 0
            error_count = 0
            for video in videos:
                try:
                    await self.process_video(video, crawl_comments)
                    success_count += 1
                except asyncio.CancelledError:
                    print(f"    ⚠️  视频处理被取消，继续下一个...")
                    error_count += 1
                except Exception as e:
                    print(f"    ✗ 视频处理异常: {e}，继续下一个...")
                    error_count += 1
                await asyncio.sleep(self.sleep)
            
            print(f"\n{'=' * 70}")
            print("爬取完成！")
            print(f"共处理 {len(videos)} 个视频 (成功: {success_count}, 失败: {error_count})")
            print(f"输出目录: {self.output_dir.resolve()}")
            print(f"{'=' * 70}")
            
        finally:
            await self.close_browser()


async def main():
    parser = argparse.ArgumentParser(description="Playwright 抖音合集爬虫")
    parser.add_argument("--mix-id", required=True, help="合集ID")
    parser.add_argument("--no-comments", action="store_true", help="不抓评论")
    parser.add_argument("--max-comments", type=int, default=2000, help="单视频最大评论数（默认2000）")
    parser.add_argument("--sleep", type=float, default=3.0, help="视频间隔秒数（默认3秒）")
    parser.add_argument("--out", type=str, default="output_playwright", help="输出目录")
    parser.add_argument("--no-headless", action="store_true", help="显示浏览器（默认无头模式）")
    parser.add_argument("--login-wait", type=int, default=10, help="登录等待秒数（无头模式默认10秒）")
    args = parser.parse_args()
    
    # 默认使用无头模式，除非指定 --no-headless
    use_headless = not args.no_headless
    # 无头模式登录等待5秒，有头模式使用用户指定的等待时间
    actual_login_wait = 5 if use_headless else args.login_wait
    
    crawler = PlaywrightMixCrawler(
        output_dir=Path(args.out),
        max_comments=args.max_comments,
        sleep=args.sleep,
        headless=use_headless,
        login_wait=actual_login_wait,
    )
    
    await crawler.crawl_mix(args.mix_id, crawl_comments=not args.no_comments)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
