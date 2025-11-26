"""
抖音合集爬虫 - DrissionPage版 v2（网络监听方式获取评论）

修复问题：
1. 监听器状态管理优化
2. 配置文件路径健壮处理
3. 时间戳单位兼容（秒/毫秒）
4. 登录超时逻辑修正
5. API响应包丢失风险处理
6. 验证码检测与暂停
7. 详细运行日志

日期: 2024年
"""

import argparse
import csv
import json
import os
import re
import time
import datetime
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from DrissionPage import ChromiumPage, ChromiumOptions


def log(msg: str, level: str = "INFO"):
    """统一日志输出"""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "ℹ️ ", "SUCCESS": "✅", "WARNING": "⚠️ ", "ERROR": "❌", "DEBUG": "🔍", "PROGRESS": "📊"}.get(level, "  ")
    print(f"[{timestamp}] {prefix} {msg}")


def sanitize_filename(name: str, max_len: int = 60) -> str:
    """清理文件名中的非法字符，并限制长度避免Windows路径过长"""
    # 【优化4】缩短文件名长度，Windows路径总长度限制260字符
    clean_name = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', name)
    return clean_name[:max_len]


def parse_timestamp(ts) -> str:
    """解析时间戳，兼容秒和毫秒"""
    try:
        if ts is None or ts == 0:
            return ""
        ts = int(ts)
        if ts > 10000000000:  # 大于10位是毫秒
            ts = ts // 1000
        return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return str(ts)


class DrissionMixCrawler:
    """抖音合集爬虫 - DrissionPage版 v2"""
    
    def __init__(
        self,
        output_dir: Path = Path("output_drission"),
        max_comments: int = 2000,
        sleep: float = 3.0,
        headless: bool = False,
        login_wait: int = 60,
    ):
        self.output_dir = output_dir
        self.max_comments = max_comments
        self.sleep = sleep
        self.headless = headless
        self.login_wait = login_wait
        self.driver: Optional[ChromiumPage] = None
        
        # 统计信息
        self.stats = {
            'total_videos': 0,
            'processed_videos': 0,
            'total_comments': 0,
            'success_videos': 0,
            'failed_videos': 0,
        }
        
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def init_browser(self):
        """初始化浏览器"""
        log("初始化浏览器...", "INFO")
        
        try:
            co = ChromiumOptions()
            if self.headless:
                co.headless(True)
                log("  使用无头模式", "DEBUG")
            
            self.driver = ChromiumPage(co)
            log("浏览器启动成功", "SUCCESS")
            return True
        except Exception as e:
            log(f"浏览器初始化失败: {e}", "ERROR")
            return False
    
    def _check_captcha(self) -> bool:
        """检查是否出现验证码弹窗 - 优化版，减少误报"""
        try:
            # 只检测特定的验证码弹窗元素，不搜索整个页面文本（避免误报）
            # 抖音验证码通常是一个模态弹窗
            captcha_selectors = [
                'xpath://div[contains(@class, "captcha-verify")]',
                'xpath://div[contains(@class, "secsdk-captcha")]',
                'xpath://div[contains(@class, "verify-wrap")]',
                'xpath://iframe[contains(@src, "captcha")]',
                'xpath://div[@id="captcha_container"]',
                'xpath://div[contains(@class, "slidetounlock")]',
            ]
            
            for selector in captcha_selectors:
                ele = self.driver.ele(selector, timeout=0.3)
                if ele:
                    return True
            
            # 检查标题是否包含验证码关键词（这个比较可靠）
            title = self.driver.title or ""
            if '验证' in title and ('码' in title or '滑块' in title):
                return True
            
            return False
        except:
            return False
    
    def _handle_captcha(self):
        """处理验证码"""
        print()
        log("=" * 50, "WARNING")
        log("检测到验证码/风控！程序暂停", "WARNING")
        log("请在浏览器中手动完成验证", "WARNING")
        log("完成后按回车键继续...", "WARNING")
        log("=" * 50, "WARNING")
        input()
        log("继续执行...", "INFO")
    
    def _check_video_exists(self) -> bool:
        """检查视频是否存在，返回 True 表示视频有效"""
        try:
            # 检查页面标题
            title = self.driver.title or ""
            
            # 首先检查是否是正常的视频页面（抖音视频页标题通常包含作者名或视频标题）
            # 如果标题包含明确的错误信息，则视频不存在
            if '不存在' in title or '已删除' in title or '404' in title or '错误' in title:
                return False
            
            # 检查 URL 是否被重定向到错误页面
            current_url = self.driver.url or ""
            if '/error' in current_url or '/404' in current_url:
                return False
            
            # 检查页面可见文本中是否有明确的"不存在"提示
            # 注意：只检查特定的错误提示元素，避免误判
            error_texts = [
                '作品不存在',
                '视频不存在', 
                '内容不存在',
                '该视频已删除',
                '该作品已删除',
                '页面不存在',
                '抱歉，页面未找到',
            ]
            
            # 使用元素选择器检查错误提示（更精确）
            error_selectors = [
                'xpath://div[contains(@class, "error")]//span',
                'xpath://div[contains(@class, "empty")]//p',
                'xpath://div[contains(@class, "videoNotFound")]',
                'xpath://div[contains(@class, "notFound")]',
            ]
            
            for selector in error_selectors:
                try:
                    ele = self.driver.ele(selector, timeout=0.5)
                    if ele:
                        ele_text = ele.text or ""
                        for error_text in error_texts:
                            if error_text in ele_text:
                                return False
                except:
                    pass
            
            # 检查是否有视频播放器元素（视频存在的正面证据）
            video_selectors = [
                'xpath://video',
                'xpath://div[contains(@class, "xgplayer")]',
                'xpath://div[contains(@class, "video-player")]',
            ]
            
            for selector in video_selectors:
                try:
                    ele = self.driver.ele(selector, timeout=0.5)
                    if ele:
                        return True  # 找到视频播放器，视频存在
                except:
                    pass
            
            # 如果没有明确的错误提示，也没有找到视频播放器，可能还在加载中
            # 默认返回 True，让后续逻辑继续处理
            return True
            
        except Exception as e:
            # 检测出错时默认视频存在，继续尝试
            return True
    
    def load_cookies(self) -> Optional[List[Tuple[str, str]]]:
        """从 config.yaml 加载 Cookie - 支持多路径查找"""
        log("加载 Cookie...", "INFO")
        
        # 尝试多个可能的配置文件路径
        possible_paths = [
            Path("crawlers/douyin/web/config.yaml"),
            Path("config.yaml"),
            Path(__file__).parent / "crawlers/douyin/web/config.yaml",
        ]
        
        config_path = None
        for p in possible_paths:
            if p.exists():
                config_path = p
                log(f"  找到配置文件: {p}", "DEBUG")
                break
        
        if not config_path:
            log("未找到配置文件，将使用扫码登录", "WARNING")
            return None
        
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            cookie_str = config.get("TokenManager", {}).get("douyin", {}).get("headers", {}).get("Cookie", "")
            if not cookie_str:
                log("配置文件中没有 Cookie", "WARNING")
                return None
            
            cookies = []
            for item in cookie_str.split(';'):
                item = item.strip()
                if '=' in item:
                    name, value = item.split('=', 1)
                    cookies.append((name.strip(), value.strip()))
            
            log(f"解析到 {len(cookies)} 个 Cookie", "SUCCESS")
            return cookies
            
        except ImportError:
            log("未安装 PyYAML，请运行: pip install pyyaml", "ERROR")
            return None
        except Exception as e:
            log(f"加载 Cookie 失败: {e}", "ERROR")
            return None
    
    def check_login(self, cookies=None) -> bool:
        """检查登录状态，支持扫码登录"""
        log("访问抖音首页...", "INFO")
        
        try:
            self.driver.get("https://www.douyin.com/")
            time.sleep(2)
            log("页面加载完成", "SUCCESS")
            
            # 检查验证码
            if self._check_captcha():
                self._handle_captcha()
            
            # 设置Cookie
            if cookies:
                log(f"设置 {len(cookies)} 个 Cookie...", "DEBUG")
                success_count = 0
                for name, value in cookies:
                    try:
                        # 【优化5】先尝试不指定domain，让浏览器自动处理
                        self.driver.set.cookies.set(name, value)
                        success_count += 1
                    except:
                        try:
                            # 备用：指定domain
                            self.driver.set.cookies.set(name, value, domain='.douyin.com')
                            success_count += 1
                        except:
                            pass
                
                log(f"成功设置 {success_count}/{len(cookies)} 个 Cookie", "DEBUG")
                self.driver.refresh()
                time.sleep(3)
            
            # 检查是否已登录
            if self._is_logged_in():
                log("Cookie 有效，已登录状态", "SUCCESS")
                return True
            
            log("未检测到登录状态", "WARNING")
            
            if self.headless:
                log("无头模式无法扫码登录，请先配置有效的 Cookie", "ERROR")
                return False
            
            return self._wait_for_qr_login()
            
        except Exception as e:
            log(f"检查登录失败: {e}", "ERROR")
            return False
    
    def _is_logged_in(self) -> bool:
        """检查是否已登录"""
        try:
            page_text = self.driver.html
            # 检查登录标识
            if '退出登录' in page_text or '消息' in page_text:
                return True
            # 检查是否有头像元素
            avatar = self.driver.ele('xpath://img[contains(@class, "avatar")]', timeout=2)
            if avatar:
                return True
            return False
        except:
            return False
    
    def _wait_for_qr_login(self) -> bool:
        """等待用户扫码登录 - 使用while循环避免递归栈溢出"""
        
        while True:  # 【优化3】使用while循环替代递归
            print()
            log("=" * 50, "INFO")
            log("📱 请在浏览器中扫码登录抖音", "INFO")
            log("   1. 打开抖音APP", "INFO")
            log("   2. 扫描浏览器中的二维码", "INFO")
            log("   3. 确认登录", "INFO")
            log("=" * 50, "INFO")
            log(f"等待登录中... (最多等待 {self.login_wait} 秒)", "INFO")
            
            # 尝试点击登录按钮显示二维码
            try:
                login_btn = self.driver.ele('xpath://button[contains(text(), "登录")]', timeout=3)
                if login_btn:
                    login_btn.click()
                    time.sleep(1)
            except:
                pass
            
            start_time = time.time()
            
            while time.time() - start_time < self.login_wait:
                if self._is_logged_in():
                    log("登录成功！", "SUCCESS")
                    self._save_cookies()
                    return True
                
                remaining = int(self.login_wait - (time.time() - start_time))
                print(f"\r   等待登录... 剩余 {remaining} 秒   ", end='', flush=True)
                time.sleep(2)
            
            print()
            log("登录超时", "WARNING")
            
            # 超时后询问用户是否继续
            response = input("是否继续等待？(y/n): ").strip().lower()
            if response != 'y':
                return False  # 用户选择不继续，返回False
            # 否则继续外层while循环，重新等待
    
    def _save_cookies(self):
        """保存Cookie到文件"""
        try:
            cookies = self.driver.cookies()
            if cookies:
                cookie_file = self.output_dir / "cookies_saved.json"
                with open(cookie_file, 'w', encoding='utf-8') as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
                print(f"  💾 Cookie已保存到: {cookie_file}")
        except Exception as e:
            print(f"  保存Cookie失败: {e}")
    
    def get_mix_videos(self, mix_id: str) -> List[Dict]:
        """获取合集视频列表 - 优先使用API，备用页面滚动"""
        log(f"获取合集视频列表...", "INFO")
        
        videos = []
        actual_mix_id = mix_id
        
        try:
            # 如果是链接，先提取mix_id
            if 'douyin.com' in mix_id or 'http' in mix_id:
                log(f"  检测到链接，提取合集ID...", "DEBUG")
                self.driver.get(mix_id)
                time.sleep(4)
                current_url = self.driver.url
                log(f"  当前URL: {current_url}", "DEBUG")
                
                # 从URL中提取mix_id
                match = re.search(r'modal_id=(\d+)|collection/(\d+)|mix_id=(\d+)', current_url)
                if match:
                    actual_mix_id = match.group(1) or match.group(2) or match.group(3)
                    log(f"  从URL提取到合集ID: {actual_mix_id}", "SUCCESS")
                else:
                    # 如果重定向到视频页面，尝试从页面HTML中提取合集ID
                    log(f"  URL中未找到合集ID，尝试从页面提取...", "DEBUG")
                    page_html = self.driver.html or ""
                    
                    # 尝试多种模式匹配
                    patterns = [
                        r'"mixId"\s*:\s*"(\d+)"',
                        r'"mix_id"\s*:\s*"(\d+)"',
                        r'collection/(\d+)',
                        r'modal_id=(\d+)',
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, page_html)
                        if match:
                            actual_mix_id = match.group(1)
                            log(f"  从页面提取到合集ID: {actual_mix_id}", "SUCCESS")
                            break
                    
                    # 如果还是没找到，检查页面上是否有合集入口
                    if actual_mix_id == mix_id:
                        log(f"  尝试点击合集入口...", "DEBUG")
                        try:
                            # 查找合集相关的链接或按钮
                            mix_link = self.driver.ele('xpath://a[contains(@href, "collection") or contains(text(), "合集")]', timeout=3)
                            if mix_link:
                                mix_link.click()
                                time.sleep(3)
                                current_url = self.driver.url
                                match = re.search(r'collection/(\d+)|modal_id=(\d+)', current_url)
                                if match:
                                    actual_mix_id = match.group(1) or match.group(2)
                                    log(f"  点击后提取到合集ID: {actual_mix_id}", "SUCCESS")
                        except:
                            pass
            
            # 确保actual_mix_id是纯数字
            if not actual_mix_id.isdigit():
                log(f"  无法提取有效的合集ID，请直接使用数字ID", "ERROR")
                log(f"  提示：运行 python crawl_mix_drission.py --mix-id 7326746646719498279", "INFO")
                return []
            
            # 方法1: 使用现有API接口获取（更稳定）
            log(f"  使用合集ID: {actual_mix_id}", "INFO")
            log(f"  尝试使用API获取视频列表...", "DEBUG")
            videos = self._fetch_mix_videos_api(actual_mix_id)
            
            if videos:
                log(f"  API获取成功！", "SUCCESS")
            else:
                # 方法2: 备用 - 使用页面滚动方式
                log(f"  API获取失败，切换到页面滚动方式...", "WARNING")
                videos = self._fetch_mix_videos_scroll(actual_mix_id)
            
        except Exception as e:
            log(f"获取视频列表失败: {e}", "ERROR")
            import traceback
            traceback.print_exc()
        
        # 重新编号
        for idx, v in enumerate(videos):
            v['index'] = idx + 1
        
        self.stats['total_videos'] = len(videos)
        log(f"共获取 {len(videos)} 个视频", "SUCCESS")
        return videos
    
    def _fetch_mix_videos_api(self, mix_id: str) -> List[Dict]:
        """使用现有API获取合集视频"""
        import asyncio
        from crawlers.douyin.web.web_crawler import DouyinWebCrawler
        
        videos = []
        
        async def fetch():
            nonlocal videos
            api_crawler = DouyinWebCrawler()
            cursor = 0
            page = 0
            
            while True:
                page += 1
                log(f"    API获取第 {page} 页...", "DEBUG")
                
                try:
                    resp = await api_crawler.fetch_user_mix_videos(
                        mix_id=mix_id, cursor=cursor, count=20
                    )
                    
                    if not resp:
                        break
                    
                    aweme_list = resp.get("aweme_list") or []
                    if not aweme_list:
                        break
                    
                    for item in aweme_list:
                        video = {
                            'index': len(videos) + 1,
                            'aweme_id': item.get('aweme_id', ''),
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
                    
                    log(f"    已获取 {len(videos)} 个视频", "PROGRESS")
                    
                    if not resp.get("has_more", False):
                        break
                    
                    cursor = resp.get("cursor", cursor + 20)
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    log(f"    API请求失败: {e}", "ERROR")
                    break
        
        try:
            asyncio.run(fetch())
        except Exception as e:
            log(f"  API调用异常: {e}", "ERROR")
        
        return videos
    
    def _fetch_mix_videos_scroll(self, mix_id: str) -> List[Dict]:
        """备用方法：使用页面滚动获取合集视频"""
        videos = []
        
        try:
            # 先启动监听，再访问页面
            self.driver.listen.start(['mix/aweme', 'mix/detail', 'aweme/v1/web/mix'])
            self.driver.listen.clear()
            
            mix_url = f"https://www.douyin.com/collection/{mix_id}"
            log(f"  访问: {mix_url}", "DEBUG")
            self.driver.get(mix_url)
            time.sleep(4)
            
            if self._check_captcha():
                self._handle_captcha()
            
            last_count = 0
            no_new_count = 0
            scroll_round = 0
            
            log("  开始滚动加载视频列表...", "DEBUG")
            
            while no_new_count < 10:
                scroll_round += 1
                
                # 检查验证码
                if self._check_captcha():
                    self._handle_captcha()
                
                self.driver.scroll.down(500)
                time.sleep(1 + random.random())
                
                # 【修复5】处理多个数据包
                for _ in range(5):
                    resp = self.driver.listen.wait(timeout=0.5 if _ > 0 else 2)
                    if not resp:
                        break
                    
                    try:
                        json_data = resp.response.body
                        if json_data and 'aweme_list' in json_data:
                            aweme_list = json_data['aweme_list']
                            for item in aweme_list:
                                aweme_id = item.get('aweme_id', '')
                                if any(v['aweme_id'] == aweme_id for v in videos):
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
                            
                            if not json_data.get('has_more', True):
                                log(f"  已加载全部视频", "DEBUG")
                                no_new_count = 100
                                break
                    except Exception as e:
                        log(f"  解析响应失败: {e}", "DEBUG")
                
                if len(videos) > last_count:
                    no_new_count = 0
                    last_count = len(videos)
                    log(f"  第 {scroll_round} 轮滚动，已获取 {len(videos)} 个视频", "PROGRESS")
                else:
                    no_new_count += 1
            
            # 停止监听
            try:
                self.driver.listen.stop()
            except:
                pass
            
        except Exception as e:
            log(f"  滚动获取失败: {e}", "ERROR")
        
        return videos
    
    def get_video_comments(self, aweme_id: str, expected_count: int = 0) -> Optional[List[Dict]]:
        """获取视频评论 - 使用网络监听方式
        
        Returns:
            List[Dict]: 评论列表
            None: 视频不存在或已删除
        """
        comments = []
        comment_ids = set()
        
        log(f"  开始获取评论 (预期: {expected_count} 条)...", "DEBUG")
        
        try:
            # 【关键修复】停止之前的监听，重新启动，使用更通用的URL匹配
            try:
                self.driver.listen.stop()
            except:
                pass
            
            # 使用评论列表接口作为监听目标
            # 只监听一级评论接口，避免混入回复接口导致 has_more 提前结束
            # 一级评论: /aweme/v1/web/comment/list/
            self.driver.listen.start('comment/list')
            self.driver.listen.clear()
            
            url = f"https://www.douyin.com/video/{aweme_id}"
            log(f"  访问视频: {url}", "DEBUG")
            self.driver.get(url)
            time.sleep(4)  # 增加等待时间
            
            # 检查验证码
            if self._check_captcha():
                self._handle_captcha()
            
            # 检查视频是否存在（添加诊断信息）
            if not self._check_video_exists():
                log(f"  ⚠️ 页面显示视频不存在！", "WARNING")
                log(f"  当前URL: {self.driver.url}", "DEBUG")
                log(f"  页面标题: {self.driver.title}", "DEBUG")
                # 截图保存诊断
                try:
                    screenshot_path = self.output_dir / f"debug_video_not_exist_{aweme_id}.png"
                    self.driver.get_screenshot(path=str(screenshot_path))
                    log(f"  已保存截图: {screenshot_path}", "DEBUG")
                except:
                    pass
                # 尝试刷新页面重试一次
                log(f"  尝试刷新页面重试...", "WARNING")
                self.driver.refresh()
                time.sleep(5)
                if not self._check_video_exists():
                    log(f"  刷新后仍然显示不存在，可能是视频被删除或地域限制", "ERROR")
                    return None
                else:
                    log(f"  刷新后页面正常，继续处理", "SUCCESS")
            
            # 等待评论区加载
            log(f"  等待评论区加载...", "DEBUG")
            time.sleep(2)
            
            # 先处理页面加载时可能已经产生的评论数据包
            initial_count = 0
            for _ in range(15):
                resp = self.driver.listen.wait(timeout=0.5)
                if not resp:
                    break
                try:
                    json_data = resp.response.body
                    if json_data and 'comments' in json_data:
                        for comment in json_data['comments']:
                            comment_id = comment.get('cid', '') or str(comment.get('id', ''))
                            if comment_id and comment_id not in comment_ids:
                                comment_ids.add(comment_id)
                                parsed = self._parse_comment(comment)
                                comments.append(parsed)
                                initial_count += 1
                except:
                    pass
            
            if initial_count > 0:
                log(f"  初始加载获取 {initial_count} 条评论", "DEBUG")
            else:
                log(f"  初始加载未获取到评论，尝试触发加载...", "WARNING")
                
                # 方法1：尝试点击评论区
                try:
                    comment_btn = self.driver.ele('xpath://span[contains(text(), "评论") or contains(text(), "条")]', timeout=2)
                    if comment_btn:
                        comment_btn.click()
                        time.sleep(2)
                        # 再次尝试获取
                        for _ in range(10):
                            resp = self.driver.listen.wait(timeout=0.5)
                            if not resp:
                                break
                            try:
                                json_data = resp.response.body
                                if json_data and 'comments' in json_data:
                                    for comment in json_data['comments']:
                                        comment_id = comment.get('cid', '') or str(comment.get('id', ''))
                                        if comment_id and comment_id not in comment_ids:
                                            comment_ids.add(comment_id)
                                            parsed = self._parse_comment(comment)
                                            comments.append(parsed)
                            except:
                                pass
                        if comments:
                            log(f"  点击后获取 {len(comments)} 条评论", "DEBUG")
                except:
                    pass
                
                # 方法2：如果还是没有，尝试刷新页面
                if not comments:
                    log(f"  尝试刷新页面...", "WARNING")
                    self.driver.refresh()
                    time.sleep(4)
                    self.driver.listen.clear()
                    
                    for _ in range(10):
                        resp = self.driver.listen.wait(timeout=0.5)
                        if not resp:
                            break
                        try:
                            json_data = resp.response.body
                            if json_data and 'comments' in json_data:
                                for comment in json_data['comments']:
                                    comment_id = comment.get('cid', '') or str(comment.get('id', ''))
                                    if comment_id and comment_id not in comment_ids:
                                        comment_ids.add(comment_id)
                                        parsed = self._parse_comment(comment)
                                        comments.append(parsed)
                        except:
                            pass
                    if comments:
                        log(f"  刷新后获取 {len(comments)} 条评论", "DEBUG")
            
            # 【关键】先滚动到评论区域
            log(f"  滚动到评论区域...", "DEBUG")
            
            # 方法1：用 JS 滚动到页面中部（视频下方就是评论区）
            try:
                # 先滚动到视频下方
                self.driver.run_js('window.scrollTo(0, window.innerHeight * 0.8)')
                time.sleep(0.5)
                # 再往下滚动一点确保评论区可见
                self.driver.run_js('window.scrollBy(0, 300)')
                time.sleep(0.5)
            except Exception as e:
                log(f"  JS 滚动失败: {e}，尝试备用方法", "WARNING")
                try:
                    self.driver.scroll.to_half()
                    time.sleep(0.5)
                    self.driver.scroll.down(300)
                    time.sleep(0.5)
                except:
                    pass
            
            # 检查评论区是否可见（尝试找评论相关元素）
            try:
                comment_container = self.driver.ele('xpath://div[contains(@class, "comment")]', timeout=2)
                if comment_container:
                    log(f"  评论区域已定位", "DEBUG")
            except:
                log(f"  未找到评论区域元素，继续滚动...", "DEBUG")
                self.driver.run_js('window.scrollBy(0, 500)')
                time.sleep(0.5)
            
            no_new_count = 0
            scroll_round = 0
            
            # 根据预期评论数调整策略
            is_large_comment = expected_count > 500
            max_scroll_rounds = max(300, expected_count // 3)
            max_no_new_rounds = 50 if is_large_comment else 30
            
            last_count = 0
            stall_rounds = 0  # 评论数停滞的轮数
            
            # 滚动辅助函数
            def get_scroll_position():
                """获取当前滚动位置"""
                try:
                    return self.driver.run_js('return window.pageYOffset || document.documentElement.scrollTop') or 0
                except:
                    return 0
            
            scroll_method = 0  # 当前使用的滚动方法
            
            def js_scroll(distance):
                """单次滚动 - 尝试多种方法"""
                nonlocal scroll_method
                
                methods = [
                    # 方法0: window.scrollBy
                    lambda d: self.driver.run_js(f'window.scrollBy(0, {d})'),
                    # 方法1: document.documentElement.scrollTop
                    lambda d: self.driver.run_js(f'document.documentElement.scrollTop += {d}'),
                    # 方法2: document.body.scrollTop  
                    lambda d: self.driver.run_js(f'document.body.scrollTop += {d}'),
                    # 方法3: DrissionPage 原生滚动
                    lambda d: self.driver.scroll.down(d),
                    # 方法4: 按 PageDown 键
                    lambda d: self.driver.actions.key_down('PageDown').key_up('PageDown').perform(),
                ]
                
                # 先尝试当前方法
                try:
                    methods[scroll_method](distance)
                    return True
                except:
                    pass
                
                # 如果失败，尝试其他方法
                for i, method in enumerate(methods):
                    if i == scroll_method:
                        continue
                    try:
                        method(distance)
                        scroll_method = i  # 切换到有效的方法
                        log(f"    切换到滚动方法 {i}", "DEBUG")
                        return True
                    except:
                        continue
                
                return False
            
            # 记录初始滚动位置
            initial_scroll_pos = get_scroll_position()
            log(f"  当前滚动位置: {initial_scroll_pos}px", "DEBUG")
            
            # 使用 Python 循环滚动（更可靠）
            scroll_speed = 150 if is_large_comment else 100  # 每次滚动像素
            log(f"  启动持续滚动 (每次 {scroll_speed}px)", "DEBUG")
            
            # 实时日志变量
            last_log_time = time.time()
            last_log_count = 0
            start_time = time.time()
            
            last_scroll_pos = initial_scroll_pos
            scroll_failed_count = 0
            
            try:
                while scroll_round < max_scroll_rounds and len(comments) < self.max_comments:
                    scroll_round += 1
                    
                    # 【关键】每轮都执行滚动
                    js_scroll(scroll_speed)
                    time.sleep(0.15)  # 滚动后短暂等待
                    
                    # 每10轮检查滚动是否生效
                    if scroll_round % 10 == 0:
                        current_pos = get_scroll_position()
                        if current_pos <= last_scroll_pos + 10:  # 允许10px误差
                            scroll_failed_count += 1
                            if scroll_failed_count >= 2:
                                print()
                                log(f"    滚动未生效 (位置: {current_pos}px)，切换滚动方法...", "WARNING")
                                # 直接调用不同的滚动方法
                                try:
                                    self.driver.scroll.down(800)
                                except:
                                    try:
                                        self.driver.run_js('document.documentElement.scrollTop += 800')
                                    except:
                                        pass
                                # 尝试大幅滚动
                                js_scroll(800)
                                time.sleep(0.5)
                                scroll_failed_count = 0
                        else:
                            scroll_failed_count = 0
                        last_scroll_pos = current_pos
                    
                    # 快速处理数据包
                    found_new = False
                    new_in_round = 0
                    for _ in range(10):
                        resp = self.driver.listen.wait(timeout=0.3)
                        if not resp:
                            break
                        
                        try:
                            json_data = resp.response.body
                            
                            if json_data and 'comments' in json_data:
                                new_comments = json_data['comments']
                                
                                for comment in new_comments:
                                    comment_id = comment.get('cid', '') or str(comment.get('id', ''))
                                    
                                    if comment_id and comment_id not in comment_ids:
                                        comment_ids.add(comment_id)
                                        parsed = self._parse_comment(comment)
                                        comments.append(parsed)
                                        found_new = True
                                        new_in_round += 1
                        except:
                            pass
                    
                    if found_new:
                        no_new_count = 0
                    else:
                        no_new_count += 1
                        # 连续多次没数据时检查验证码
                        if no_new_count >= 10:
                            if self._check_captcha():
                                self._handle_captcha()
                                no_new_count = 0
                                continue
                    
                    # 【实时日志】每2秒或每获取20条新评论显示一次
                    current_time = time.time()
                    new_since_log = len(comments) - last_log_count
                    time_since_log = current_time - last_log_time
                    
                    if time_since_log >= 2 or new_since_log >= 20:
                        coverage = (len(comments) / expected_count * 100) if expected_count > 0 else 0
                        elapsed = current_time - start_time
                        speed = len(comments) / elapsed if elapsed > 0 else 0
                        level1 = sum(1 for c in comments if c.get('level', 1) == 1)
                        level2 = len(comments) - level1
                        
                        # 使用 \r 实现同行刷新效果
                        print(f"\r    📊 已获取 {len(comments):,} 条 (L1:{level1} L2:{level2}) | 覆盖率 {coverage:.1f}% | 速度 {speed:.1f}条/秒 | 用时 {elapsed:.0f}秒    ", end='', flush=True)
                        
                        last_log_time = current_time
                        last_log_count = len(comments)
                        
                        # 【优化】覆盖率达到100%时验证并提前结束
                        if coverage >= 100:
                            # 再滚动几次确认真的到底了
                            print()
                            log(f"    覆盖率达到 100%，验证中...", "DEBUG")
                            js_scroll(500)
                            time.sleep(0.5)
                            verify_found = False
                            for _ in range(5):
                                resp = self.driver.listen.wait(timeout=0.3)
                                if resp:
                                    try:
                                        json_data = resp.response.body
                                        if json_data and 'comments' in json_data:
                                            for comment in json_data['comments']:
                                                cid = comment.get('cid', '')
                                                if cid and cid not in comment_ids:
                                                    verify_found = True
                                                    comment_ids.add(cid)
                                                    comments.append(self._parse_comment(comment))
                                    except:
                                        pass
                            
                            if not verify_found:
                                log(f"    确认已获取全部评论，提前结束", "SUCCESS")
                                break
                            else:
                                log(f"    还有更多评论，继续滚动...", "DEBUG")
                    
                    # 每10轮检测停滞
                    if scroll_round % 10 == 0:
                        if len(comments) == last_count:
                            stall_rounds += 1
                            # 停滞时尝试大幅滚动
                            if stall_rounds >= 2:
                                print()  # 换行
                                log(f"    检测到停滞，尝试大幅滚动...", "DEBUG")
                                js_scroll(1000)
                                time.sleep(0.5)
                        else:
                            stall_rounds = 0
                        last_count = len(comments)
                    
                    # 每30轮尝试展开回复
                    if scroll_round % 30 == 0:
                        self._try_expand_replies()
                    
                    # 底部检测
                    if no_new_count >= max_no_new_rounds:
                        page_html = self.driver.html or ''
                        if '暂时没有更多评论' in page_html or '没有更多了' in page_html:
                            print()
                            log(f"    检测到评论底部标记", "DEBUG")
                            break
                        
                        # 尝试最后一次大幅滚动
                        js_scroll(2000)
                        time.sleep(0.8)
                        
                        # 再检查一次
                        final_found = False
                        for _ in range(5):
                            resp = self.driver.listen.wait(timeout=0.3)
                            if resp:
                                try:
                                    json_data = resp.response.body
                                    if json_data and 'comments' in json_data:
                                        for comment in json_data['comments']:
                                            comment_id = comment.get('cid', '') or str(comment.get('id', ''))
                                            if comment_id and comment_id not in comment_ids:
                                                comment_ids.add(comment_id)
                                                parsed = self._parse_comment(comment)
                                                comments.append(parsed)
                                                final_found = True
                                except:
                                    pass
                        
                        if not final_found:
                            print()
                            log(f"    连续 {no_new_count} 次无新评论，确认到底", "DEBUG")
                            break
                        else:
                            no_new_count = 0
                    
                    # 停滞太久退出
                    if stall_rounds >= 6:
                        log(f"    评论数长时间停滞，结束", "DEBUG")
                        break
                        
            except Exception as inner_e:
                print()
                log(f"    滚动循环异常: {inner_e}", "WARNING")
            
            # 最终统计
            print()  # 换行（因为之前用了 \r）
            elapsed_total = time.time() - start_time
            final_speed = len(comments) / elapsed_total if elapsed_total > 0 else 0
            level1_final = sum(1 for c in comments if c.get('level', 1) == 1)
            level2_final = len(comments) - level1_final
            print(f"    📜 滚动完成: {scroll_round} 轮 | {len(comments)} 条评论 (L1:{level1_final} L2:{level2_final}) | 平均 {final_speed:.1f}条/秒 | 耗时 {elapsed_total:.1f}秒")
            
        except Exception as e:
            print(f"    ✗ 获取评论异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 【修复】确保停止监听器，避免影响下一个视频
            try:
                self.driver.listen.stop()
            except:
                pass
        
        return comments
    
    def _parse_comment(self, comment: Dict) -> Dict:
        """解析评论数据（从API JSON）"""
        try:
            # 基本信息
            comment_id = comment.get('cid', '') or str(comment.get('id', ''))
            text = comment.get('text', '').strip()
            create_time = comment.get('create_time', 0)
            digg_count = comment.get('digg_count', 0)
            reply_count = comment.get('reply_comment_total', 0)
            
            # 用户信息
            user = comment.get('user', {})
            nickname = user.get('nickname', '未知用户')
            user_id = user.get('uid', '')
            sec_uid = user.get('sec_uid', '')
            
            # IP属地
            ip_label = comment.get('ip_label', '')
            
            # 回复信息
            reply_to_userid = comment.get('reply_to_userid', '') or ''
            reply_to_nickname = comment.get('reply_to_nickname', '') or ''
            
            # 【修复3】时间格式化，兼容秒和毫秒
            time_str = parse_timestamp(create_time)
            
            # 【修复】判断级别 - 更严格的判断
            # reply_id 为 "0" 或 0 或空都表示是一级评论
            reply_id = comment.get('reply_id', '')
            reply_id_str = str(reply_id) if reply_id else ''
            
            # 只有 reply_id 是非零非空的有效ID，或者有明确的 reply_to_userid 时才是二级评论
            is_reply = False
            if reply_id_str and reply_id_str != '0' and reply_id_str != '':
                is_reply = True
            if reply_to_userid and str(reply_to_userid) != '0' and str(reply_to_userid) != '':
                is_reply = True
            
            level = 2 if is_reply else 1
            
            return {
                'cid': comment_id,
                'text': text,
                'user': nickname,
                'user_id': user_id,
                'user_sec_id': sec_uid,
                'digg_count': digg_count,
                'reply_count': reply_count,
                'create_time': time_str,
                'ip_location': ip_label,
                'level': level,
                'reply_to_user': reply_to_nickname,
                'reply_to_user_id': reply_to_userid,
            }
        except Exception as e:
            print(f"      解析评论失败: {e}")
            return {
                'cid': str(comment.get('cid', '')),
                'text': comment.get('text', ''),
                'user': '未知',
                'level': 1,
            }
    
    def _try_expand_replies(self):
        """尝试展开更多回复"""
        try:
            # 查找展开按钮
            expand_btns = self.driver.eles('xpath://span[contains(text(), "展开") or contains(text(), "查看")]')
            for btn in expand_btns[:3]:
                try:
                    btn.click()
                    time.sleep(0.5)
                except:
                    pass
        except:
            pass
    
    def get_video_comments_api(self, aweme_id: str, expected_count: int = 0) -> List[Dict]:
        """使用 API 获取视频一级评论（适用于大量评论的视频，速度快，无需浏览器滚动）"""
        import asyncio
        
        comments = []
        comment_ids = set()
        
        log(f"  使用 API 模式获取一级评论（无需滚动）...", "INFO")
        
        try:
            # 导入 API 爬虫
            from crawlers.douyin.web.web_crawler import DouyinWebCrawler
            
            async def fetch_comments():
                crawler = DouyinWebCrawler()
                cursor = 0
                page = 0
                max_pages = 200  # 最多200页
                
                while page < max_pages and len(comments) < self.max_comments:
                    page += 1
                    
                    try:
                        result = await crawler.fetch_video_comments(
                            aweme_id=aweme_id,
                            cursor=cursor,
                            count=50  # 每页50条
                        )
                        
                        if not result:
                            log(f"    API 第 {page} 页返回空", "WARNING")
                            break
                        
                        comments_data = result.get('comments', [])
                        if not comments_data:
                            log(f"    API 第 {page} 页无评论数据", "DEBUG")
                            break
                        
                        for comment in comments_data:
                            comment_id = comment.get('cid', '')
                            if comment_id and comment_id not in comment_ids:
                                comment_ids.add(comment_id)
                                parsed = self._parse_comment(comment)
                                parsed['level'] = 1  # API 获取的都是一级评论
                                comments.append(parsed)
                        
                        # 检查是否还有更多
                        has_more = result.get('has_more', 0)
                        new_cursor = result.get('cursor', 0)
                        
                        # 实时显示进度
                        coverage = (len(comments) / expected_count * 100) if expected_count > 0 else 0
                        print(f"\r    📊 API 第 {page} 页 | 已获取 {len(comments):,} 条一级评论 | 覆盖率 {coverage:.1f}%    ", end='', flush=True)
                        
                        if not has_more or new_cursor == cursor:
                            print()  # 换行
                            log(f"    API 获取完成，共 {page} 页，{len(comments)} 条评论", "SUCCESS")
                            break
                        
                        cursor = new_cursor
                        await asyncio.sleep(0.3)  # API 间隔
                        
                    except Exception as e:
                        log(f"    API 第 {page} 页异常: {e}", "WARNING")
                        break
            
            # 运行异步任务
            asyncio.run(fetch_comments())
            
            if len(comments) > 0:
                log(f"  API 模式成功获取 {len(comments)} 条评论", "SUCCESS")
            else:
                log(f"  API 模式未获取到评论", "WARNING")
            
        except ImportError as e:
            log(f"  无法导入 API 模块: {e}，跳过该视频评论获取", "ERROR")
        except Exception as e:
            log(f"  API 获取异常: {e}，跳过该视频评论获取", "ERROR")
        
        return comments
    
    def _reset_browser_state(self):
        """重置浏览器状态，用于视频间切换"""
        try:
            # 停止所有监听器
            try:
                self.driver.listen.stop()
            except:
                pass
            
            # 清除监听器缓存
            try:
                self.driver.listen.clear()
            except:
                pass
            
            # 滚动到页面顶部
            try:
                self.driver.run_js('window.scrollTo(0, 0)')
            except:
                pass
                
        except Exception as e:
            pass  # 忽略重置过程中的错误
    
    def process_video(self, video: Dict, crawl_comments: bool = True):
        """处理单个视频"""
        # 【关键】在处理新视频前重置浏览器状态
        self._reset_browser_state()
        
        idx = video['index']
        aweme_id = video['aweme_id']
        # 【修复】显示原始合集总数，而不是当前批次总数
        total_original = self.stats.get('total_original', self.stats['total_videos'])
        
        folder = self.output_dir / f"{idx:03d}"
        folder.mkdir(exist_ok=True)
        
        title_short = (video['title'][:35] + '...') if len(video['title']) > 35 else video['title']
        
        print()
        log("=" * 60, "INFO")
        log(f"处理视频 [{idx}/{total_original}]", "PROGRESS")
        log(f"  标题: {title_short}", "INFO")
        log(f"  ID: {aweme_id}", "INFO")
        log(f"  作者: {video.get('author', '未知')}", "INFO")
        log(f"  时长: {video.get('duration', 0)} 秒", "INFO")
        log(f"  点赞: {video.get('digg_count', 0):,} | 评论: {video.get('comment_count', 0):,} | 分享: {video.get('share_count', 0):,}", "INFO")
        log("=" * 60, "INFO")
        
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
        
        comments = []
        total_expected = video.get('comment_count', 0)
        
        # 【优化】评论数 > 1500 时用 API 只抓一级评论（更快），否则用浏览器滚动抓全部
        LARGE_COMMENT_THRESHOLD = 1500
        
        video_not_exist = False
        
        if crawl_comments and total_expected > 0:
            if total_expected > LARGE_COMMENT_THRESHOLD:
                log(f"  评论数 {total_expected} > {LARGE_COMMENT_THRESHOLD}，使用 API 快速模式（只抓一级评论）", "INFO")
                comments = self.get_video_comments_api(aweme_id, total_expected)
            else:
                comments = self.get_video_comments(aweme_id, total_expected)
            
            # 检查视频是否存在 (get_video_comments 返回 None 表示视频不存在)
            if comments is None:
                video_not_exist = True
                comments = []
                log(f"视频不存在或已删除，跳过此视频", "WARNING")
            else:
                actual_count = len(comments)
                coverage = (actual_count / total_expected * 100) if total_expected > 0 else 0
                level1 = sum(1 for c in comments if c.get('level', 1) == 1)
                level2 = actual_count - level1
                
                self.stats['total_comments'] += actual_count
                
                if coverage >= 80:
                    log(f"评论获取完成: {actual_count}/{total_expected} 条 (覆盖率 {coverage:.1f}%)", "SUCCESS")
                else:
                    log(f"评论获取完成: {actual_count}/{total_expected} 条 (覆盖率 {coverage:.1f}%)", "WARNING")
                
                log(f"  一级评论: {level1} 条 | 二级评论: {level2} 条", "INFO")
        
        # 如果视频不存在，跳过保存
        if video_not_exist:
            self.stats['processed_videos'] += 1
            self.stats['failed_videos'] += 1
            return
        
        # 保存CSV
        file_name = sanitize_filename(f"{video['title']}_{aweme_id}") + ".csv"
        file_path = folder / file_name
        self._save_csv(file_path, detail, comments)
        log(f"已保存: {file_name}", "SUCCESS")
        
        self.stats['processed_videos'] += 1
        self.stats['success_videos'] += 1
    
    def _save_csv(self, filepath: Path, video: Dict, comments: List[Dict]):
        """保存为CSV"""
        fieldnames = [
            "序号", "视频ID", "视频标题", "视频URL", "发布时间", "视频时长(s)",
            "作者昵称", "作者ID", "点赞数", "收藏数", "分享数", "播放数", "评论总数",
            "层级", "评论ID", "评论内容", "评论用户", "评论用户ID",
            "评论点赞数", "回复数", "评论时间", "IP属地", "回复目标用户"
        ]
        
        rows = []
        
        # 视频信息行
        video_row = {
            "序号": 1,
            "视频ID": video.get('aweme_id', ''),
            "视频标题": video.get('title', ''),
            "视频URL": f"https://www.douyin.com/video/{video.get('aweme_id', '')}",
            "发布时间": video.get('create_time', ''),
            "视频时长(s)": video.get('duration', ''),
            "作者昵称": video.get('author', ''),
            "作者ID": video.get('author_id', ''),
            "点赞数": video.get('digg_count', 0),
            "收藏数": video.get('collect_count', 0),
            "分享数": video.get('share_count', 0),
            "播放数": video.get('play_count', 0),
            "评论总数": video.get('comment_count', 0),
            "层级": "video",
        }
        rows.append(video_row)
        
        # 评论行
        for idx, c in enumerate(comments):
            comment_row = {
                "序号": idx + 2,
                "视频ID": video.get('aweme_id', ''),
                "层级": f"L{c.get('level', 1)}",
                "评论ID": c.get('cid', ''),
                "评论内容": c.get('text', ''),
                "评论用户": c.get('user', ''),
                "评论用户ID": c.get('user_id', ''),
                "评论点赞数": c.get('digg_count', 0),
                "回复数": c.get('reply_count', 0),
                "评论时间": c.get('create_time', ''),
                "IP属地": c.get('ip_location', ''),
                "回复目标用户": c.get('reply_to_user', ''),
            }
            rows.append(comment_row)
        
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fieldnames})
    
    def close_browser(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
    
    def print_summary(self):
        """打印爬取总结"""
        print()
        log("=" * 60, "INFO")
        log("爬取任务完成", "SUCCESS")
        log("=" * 60, "INFO")
        log(f"  总视频数:   {self.stats['total_videos']}", "INFO")
        log(f"  已处理:     {self.stats['processed_videos']}", "INFO")
        log(f"  成功:       {self.stats['success_videos']}", "SUCCESS")
        log(f"  失败:       {self.stats['failed_videos']}", "WARNING" if self.stats['failed_videos'] > 0 else "INFO")
        log(f"  总评论数:   {self.stats['total_comments']:,}", "INFO")
        log(f"  输出目录:   {self.output_dir.resolve()}", "INFO")
        log("=" * 60, "INFO")
    
    def crawl_mix(self, mix_id: str, crawl_comments: bool = True, start: int = 0, end: int = 0):
        """爬取完整合集
        
        Args:
            mix_id: 合集ID或链接
            crawl_comments: 是否抓取评论
            start: 从第几个开始（1-based），0表示交互选择
            end: 到第几个结束（1-based），0表示到最后
        """
        print()
        log("=" * 60, "INFO")
        log("DrissionPage 抖音合集爬虫 v2 (网络监听版)", "INFO")
        log("=" * 60, "INFO")
        log(f"合集ID: {mix_id}", "INFO")
        log(f"输出目录: {self.output_dir}", "INFO")
        log(f"最大评论数: {self.max_comments}", "INFO")
        log(f"抓取评论: {'是' if crawl_comments else '否'}", "INFO")
        log("=" * 60, "INFO")
        
        try:
            if not self.init_browser():
                return
            
            cookies = self.load_cookies()
            
            if not self.check_login(cookies):
                return
            
            videos = self.get_mix_videos(mix_id)
            if not videos:
                log("未获取到视频列表", "ERROR")
                return
            
            total_count = len(videos)
            log(f"共发现 {total_count} 个视频", "SUCCESS")
            
            # 确定爬取区间
            start_idx = start if start > 0 else 1
            end_idx = end if end > 0 else total_count
            
            # 如果命令行指定了区间，直接使用
            if start > 0 or end > 0:
                start_idx = max(1, min(start_idx, total_count))
                end_idx = max(start_idx, min(end_idx, total_count))
                log(f"命令行指定: 爬取第 {start_idx} 到第 {end_idx} 个视频（共 {end_idx - start_idx + 1} 个）", "INFO")
            else:
                # 交互式询问区间（非无头模式下）
                if not self.headless:
                    print()
                    log("请选择爬取区间（直接回车表示全部爬取）", "INFO")
                    
                    try:
                        start_input = input(f"  从第几个视频开始? [1-{total_count}，默认1]: ").strip()
                        if start_input:
                            start_idx = max(1, min(int(start_input), total_count))
                        
                        end_input = input(f"  到第几个视频结束? [{start_idx}-{total_count}，默认{total_count}]: ").strip()
                        if end_input:
                            end_idx = max(start_idx, min(int(end_input), total_count))
                    except ValueError:
                        log("输入无效，使用默认值（全部爬取）", "WARNING")
                        start_idx = 1
                        end_idx = total_count
                    except KeyboardInterrupt:
                        log("用户取消", "WARNING")
                        return
                
                print()
                if start_idx == 1 and end_idx == total_count:
                    log(f"将爬取全部 {total_count} 个视频", "INFO")
                else:
                    log(f"将爬取第 {start_idx} 到第 {end_idx} 个视频（共 {end_idx - start_idx + 1} 个）", "INFO")
            
            # 根据区间筛选视频
            videos = videos[start_idx - 1:end_idx]
            
            # 更新视频索引（保持原始编号）
            for i, video in enumerate(videos):
                video['index'] = start_idx + i
            
            # 【修复】保存原始合集总数，用于显示正确的序号
            self.stats['total_original'] = total_count
            self.stats['total_videos'] = len(videos)
            
            for video in videos:
                try:
                    self.process_video(video, crawl_comments)
                except Exception as e:
                    log(f"视频处理异常: {e}", "ERROR")
                    self.stats['failed_videos'] += 1
                
                time.sleep(self.sleep)
            
            self.print_summary()
            
        finally:
            self.close_browser()


def main():
    parser = argparse.ArgumentParser(description="DrissionPage 抖音合集爬虫（网络监听版）")
    parser.add_argument("--mix-id", required=True, help="合集ID或合集链接(支持短链接)")
    parser.add_argument("--no-comments", action="store_true", help="不抓评论")
    parser.add_argument("--max-comments", type=int, default=2000, help="单视频最大评论数")
    parser.add_argument("--start", type=int, default=0, help="从第几个视频开始（1-based），0表示交互选择")
    parser.add_argument("--end", type=int, default=0, help="到第几个视频结束（1-based），0表示到最后")
    parser.add_argument("--sleep", type=float, default=3.0, help="视频间隔秒数")
    parser.add_argument("--out", type=str, default="output_drission", help="输出目录")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--login-wait", type=int, default=60, help="登录等待秒数")
    args = parser.parse_args()
    
    crawler = DrissionMixCrawler(
        output_dir=Path(args.out),
        max_comments=args.max_comments,
        sleep=args.sleep,
        headless=args.headless,
        login_wait=args.login_wait,
    )
    
    crawler.crawl_mix(
        args.mix_id, 
        crawl_comments=not args.no_comments, 
        start=args.start,
        end=args.end
    )


if __name__ == "__main__":
    main()
