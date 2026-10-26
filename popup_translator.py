# -*- coding: utf-8 -*-
"""
划词翻译弹窗 —— 在任意 Windows 软件中选中英文句子，
按下快捷键（默认双击 Ctrl+C）即弹出中文翻译 + 重点词汇。

翻译引擎：自动跟随 ~/.claude/api-profiles/profiles.json 中的当前档案。
"""

import ctypes
import ctypes.wintypes
import json
import os
import re
import sys
import threading
import time
import traceback

# 日志输出
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'translator.log')

class Logger:
    def __init__(self):
        try:
            self.terminal = sys.stdout
            self.log = open(LOG_FILE, 'a', encoding='utf-8')
            self.log.write(f"\n{'='*50}\n程序启动: {time.strftime('%Y-%m-%d %H:%M:%S')}\n{'='*50}\n")
            self.log.flush()
        except:
            self.terminal = sys.stdout
            self.log = None

    def write(self, message):
        try:
            self.terminal.write(message)
        except:
            pass
        if self.log:
            try:
                self.log.write(message)
                self.log.flush()
            except:
                pass

    def flush(self):
        try:
            self.terminal.flush()
        except:
            pass
        if self.log:
            try:
                self.log.flush()
            except:
                pass

# 检测是否有控制台（python.exe 有，pythonw.exe 没有）
_has_console = False
try:
    import msvcrt
    # 如果有控制台，getwche 会立即返回（不阻塞）
    # 如果没有控制台，会抛出异常
    if msvcrt.kbhit():
        _has_console = True
except:
    _has_console = False

# 如果没有控制台（pythonw.exe），重定向输出到日志文件
if not _has_console:
    sys.stdout = Logger()
    sys.stderr = Logger()

import keyboard
import mouse
import requests
import tkinter as tk
from tkinter import ttk

# UI Automation 用于获取选中文本（不依赖剪贴板）
try:
    import comtypes.client
    comtypes.client.GetModule('UIAutomationCore.dll')
    from comtypes.gen.UIAutomationClient import *
    _uia_available = True
    print("UI Automation 初始化成功")
except Exception as e:
    print(f"UI Automation 初始化失败: {e}")
    _uia_available = False

def get_selected_text_via_UIA(mouse_x=None, mouse_y=None):
    """使用 Windows UI Automation 获取选中文本（不依赖剪贴板）"""
    if not _uia_available:
        print("  [UIA] UI Automation 不可用")
        return ""

    try:
        # 必须先 CoInitialize 再调用任何 COM 对象
        print("  [UIA] 初始化 COM...")
        import comtypes
        comtypes.CoInitialize()

        # 给应用程序一点时间更新选区（快捷键可能干扰选区状态）
        import time
        time.sleep(0.15)

        print("  [UIA] 初始化 UI Automation...")
        # 创建 UI Automation 实例
        uia = comtypes.client.CreateObject('{ff48dba4-60ef-4201-aa87-54103eef594e}')  # CUIAutomation
        uia = uia.QueryInterface(IUIAutomation)

        # 优先使用鼠标位置的元素
        target_elem = None
        if mouse_x is not None and mouse_y is not None:
            print(f"  [UIA] 从鼠标位置 ({mouse_x}, {mouse_y}) 获取元素...")
            try:
                from ctypes.wintypes import POINT
                pt = POINT(mouse_x, mouse_y)
                target_elem = uia.ElementFromPoint(pt)
                if target_elem:
                    target_elem = target_elem.QueryInterface(IUIAutomationElement)
                    print(f"  [UIA] 鼠标位置元素: {target_elem.CurrentName}")
            except Exception as e:
                print(f"  [UIA] ElementFromPoint 失败: {e}")

        # 回退到焦点元素
        if not target_elem:
            print("  [UIA] 获取焦点元素...")
            focused = uia.GetFocusedElement()
            if focused:
                target_elem = focused.QueryInterface(IUIAutomationElement)
                print(f"  [UIA] 焦点元素: {target_elem.CurrentName}")

        if not target_elem:
            print("  [UIA] 无目标元素")
            comtypes.CoUninitialize()
            return ""

        # 尝试获取 TextPattern
        print("  [UIA] 尝试获取 TextPattern...")
        try:
            text_pattern = target_elem.GetCurrentPattern(UIA_TextPatternId)
            if text_pattern:
                text_pattern = text_pattern.QueryInterface(IUIAutomationTextPattern)
                selection = text_pattern.GetSelection()
                if selection and selection.Length > 0:
                    text_range = selection.GetElement(0)
                    text_range = text_range.QueryInterface(IUIAutomationTextRange)
                    selected_text = text_range.GetText(-1)
                    print(f"  [UIA] 选中文本长度: {len(selected_text)}")
                    comtypes.CoUninitialize()
                    return selected_text
        except Exception as e:
            print(f"  [UIA] 直接 TextPattern 失败: {e}")

        # 尝试从子元素中查找 TextPattern
        print("  [UIA] 搜索子元素中的 TextPattern...")
        try:
            # 创建 PropertyCondition 查找 Text 控件
            cond = uia.CreatePropertyCondition(UIA_ControlTypePropertyId, UIA_TextControlTypeId)
            found = target_elem.FindFirst(4, cond)  # TreeScope_Descendants = 4
            if found:
                found_elem = found.QueryInterface(IUIAutomationElement)
                print(f"  [UIA] 找到文本子元素: {found_elem.CurrentName}")
                text_pattern = found_elem.GetCurrentPattern(UIA_TextPatternId)
                if text_pattern:
                    text_pattern = text_pattern.QueryInterface(IUIAutomationTextPattern)
                    selection = text_pattern.GetSelection()
                    if selection and selection.Length > 0:
                        text_range = selection.GetElement(0)
                        text_range = text_range.QueryInterface(IUIAutomationTextRange)
                        selected_text = text_range.GetText(-1)
                        print(f"  [UIA] 子元素选中文本长度: {len(selected_text)}")
                        comtypes.CoUninitialize()
                        return selected_text
        except Exception as e:
            print(f"  [UIA] 子元素搜索失败: {e}")

        print("  [UIA] 未获取到选中文本（TextPattern 无选中）")
        comtypes.CoUninitialize()
        return ""

    except Exception as e:
        print(f"  [UIA] 错误: {e}")
        traceback.print_exc()
        try:
            comtypes.CoUninitialize()
        except:
            pass
        return ""

# ---------------------------------------------------------------------------
# 常量与配置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if __name__ == '__main__' else __file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')

DEFAULT_CONFIG = {
    'hotkey': 'ctrl+c, ctrl+c',
    'auto_close_seconds': 25,
    'max_vocabulary': 6,
    'timeout': 30,
    'profiles_path': 'C:/Users/qweli/.claude/api-profiles/profiles.json',
    'window_width': 440,
}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            user = json.load(f)
            if isinstance(user, dict):
                cfg.update(user)
    except Exception:
        pass
    return cfg

# ---------------------------------------------------------------------------
# DPI 感知（高 DPI 屏幕下正确定位）
# ---------------------------------------------------------------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Win32 辅助
# ---------------------------------------------------------------------------
class _POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

class _RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

class _MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', ctypes.c_ulong), ('rcMonitor', _RECT),
                ('rcWork', _RECT), ('dwFlags', ctypes.c_ulong)]

def get_cursor_pos():
    pt = _POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def get_workarea(x, y):
    """获取光标所在显示器的工作区（排除任务栏）"""
    try:
        pt = _POINT(x, y)
        mon = ctypes.windll.user32.MonitorFromPoint(pt, 2)  # MONITOR_DEFAULTTONEAREST
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            r = mi.rcWork
            return (r.left, r.top, r.right, r.bottom)
    except Exception:
        pass
    sw = ctypes.windll.user32.GetSystemMetrics(0)
    sh = ctypes.windll.user32.GetSystemMetrics(1)
    return (0, 0, sw, sh)

def get_clipboard_text():
    CF_UNICODETEXT = 13
    CF_TEXT = 1
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    # 确保返回值和参数类型正确（64 位系统上句柄是 64 位的）
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    if not user32.OpenClipboard(None):
        print("  [clipboard] OpenClipboard 失败")
        return None
    try:
        # 优先尝试 Unicode
        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            h = user32.GetClipboardData(CF_UNICODETEXT)
            if not h:
                print("  [clipboard] GetClipboardData 返回 0")
                return None
            ptr = kernel32.GlobalLock(h)
            if not ptr:
                print("  [clipboard] GlobalLock 返回 0")
                return None
            try:
                size = kernel32.GlobalSize(h)
                print(f"  [clipboard] UNICODE size={size}, ptr={ptr}")
                if not size or size < 2:
                    print(f"  [clipboard] size 太小: {size}")
                    return None
                result = ctypes.wstring_at(ptr, size // 2 - 1)
                print(f"  [clipboard] 读取成功: {repr(result[:50])}")
                return result
            except (OSError, ValueError) as e:
                print(f"  [clipboard] wstring_at 异常: {e}")
                return None
            finally:
                kernel32.GlobalUnlock(h)
        # 回退到 ANSI
        elif user32.IsClipboardFormatAvailable(CF_TEXT):
            h = user32.GetClipboardData(CF_TEXT)
            if not h:
                return None
            ptr = kernel32.GlobalLock(h)
            if not ptr:
                return None
            try:
                size = kernel32.GlobalSize(h)
                print(f"  [clipboard] ANSI size={size}, ptr={ptr}")
                if not size or size < 1:
                    return None
                result = ctypes.string_at(ptr, size - 1)
                # 尝试 GBK 解码（Windows 中文环境）
                try:
                    return result.decode('gbk')
                except UnicodeDecodeError:
                    return result.decode('utf-8', errors='replace')
            finally:
                kernel32.GlobalUnlock(h)
        else:
            print("  [clipboard] 没有文本格式 (UNICODE/ANSI)")
            return None
    finally:
        user32.CloseClipboard()

def set_clipboard_text(text):
    """设置剪贴板文本，返回 True/False 表示是否成功"""
    try:
        # 使用 tkinter 自带的剪贴板功能（更可靠）
        import tkinter as tk
        # 创建一个临时的 root 窗口（如果还没有）
        try:
            root = tk._default_root
            if root is None:
                root = tk.Tk()
                root.withdraw()
        except:
            root = tk.Tk()
            root.withdraw()

        # 清空并设置剪贴板
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        print("[CLIPBOARD] 使用 tkinter 剪贴板成功")
        return True
    except Exception as e:
        print(f"[CLIPBOARD] tkinter 剪贴板失败: {e}")

        # 回退到 Win32 API
        try:
            CF_UNICODETEXT = 13
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            data = (text + '\0').encode('utf-16-le')

            if not user32.OpenClipboard(None):
                print("[CLIPBOARD] OpenClipboard 失败")
                return False

            try:
                user32.EmptyClipboard()
                h = kernel32.GlobalAlloc(0x0042, len(data))
                if not h:
                    print("[CLIPBOARD] GlobalAlloc 失败")
                    return False

                p = kernel32.GlobalLock(h)
                if not p:
                    print("[CLIPBOARD] GlobalLock 失败")
                    kernel32.GlobalFree(h)
                    return False

                ctypes.memmove(p, data, len(data))
                kernel32.GlobalUnlock(h)

                result = user32.SetClipboardData(CF_UNICODETEXT, h)
                if not result:
                    print("[CLIPBOARD] SetClipboardData 失败")
                    kernel32.GlobalFree(h)
                    return False

                return True
            finally:
                user32.CloseClipboard()
        except Exception as e2:
            print(f"[CLIPBOARD] Win32 API 也失败: {e2}")
            return False

# ---------------------------------------------------------------------------
# 文本清洗与语言检测
# ---------------------------------------------------------------------------
def clean_text(t):
    if not t:
        return ''
    # ---- 第一步：Unicode 标准化（PDF 常见的连字、特殊字符） ----
    ligature_map = {
        'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl',
        'ﬃ': 'ffi', 'ﬄ': 'ffl',
        '‐': '-', '‑': '-', '‒': '-', '–': '-', '—': '-',
        '‘': "'", '’': "'", '“': '"', '”': '"',
        ' ': ' ',    # non-breaking space
        '​': '',     # zero-width space
        '‌': '',     # zero-width non-joiner
        '‍': '',     # zero-width joiner
        '﻿': '',     # BOM
    }
    for old, new in ligature_map.items():
        t = t.replace(old, new)

    t = t.strip()
    if not t:
        return ''

    # ---- 第二步：处理 PDF 连字符断词（必须在换行替换之前） ----
    # "method-\nology" → "methodology"
    t = re.sub(r'([A-Za-z]{2,})-\s*\n\s*([a-z])', r'\1\2', t)
    # "method- ology"（已经变成单行的情况）
    t = re.sub(r'([A-Za-z]{2,})-\s+([a-z])\b', r'\1\2', t)

    # ---- 第三步：处理换行 ----
    # 先标记段落分隔（2个及以上换行）
    t = re.sub(r'\n{2,}', '\x00', t)
    # PDF 常见：换行处两个字母直接拼接 → 加空格
    t = re.sub(r'([a-zA-Z])\n([a-zA-Z])', r'\1 \2', t)
    # 剩余的换行 → 空格
    t = re.sub(r'[ \t]*\n[ \t]*', ' ', t)
    # 恢复段落分隔
    t = t.replace('\x00', '\n')

    # ---- 第四步：清理多余空格 ----
    t = re.sub(r'[ \t]{2,}', ' ', t)
    # 去掉标点前的多余空格
    t = re.sub(r' ([,.;:!?])', r'\1', t)
    # 标点（非中文）后缺空格 → 加空格
    t = re.sub(r'([,.;:!?])([A-Za-z])', r'\1 \2', t)
    t = t.strip()
    return t

def detect_lang(t):
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return 'none'
    cjk = sum(1 for c in letters if '\u4e00' <= c <= '\u9fff')
    if cjk / len(letters) > 0.3:
        return 'zh'
    return 'en'

# ---------------------------------------------------------------------------
# LLM 调用
# ---------------------------------------------------------------------------
SYSTEM_EN = (
    '你是一位学术翻译助手。用户会给你一段英文文本（通常来自学术论文或专业书籍）。'
    '你只能输出一个合法的 JSON 对象，禁止输出任何 markdown 标记或其他文字，格式如下：\n'
    '{{"translation": "...", "vocabulary": [{{"word": "...", "phonetic": "...", "pos": "...", "meaning": "..."}}]}}\n'
    '要求：\n'
    '1. translation：把整段文本翻译成流畅准确的中文，保持学术语体，保留原意，不要遗漏。\n'
    '2. vocabulary：挑出对理解这段文本较重要的进阶词汇、学术词汇或专业术语，最多 {n} 个；'
    '给出国际音标（如 /ˈɛk.səm.pəl/）、词性（中文：名词/动词/形容词/副词等）、在该语境下的中文含义。'
    '若没有值得讲解的词汇则返回空数组。\n'
    '3. 严格输出合法 JSON，不要使用代码块包裹。'
)
SYSTEM_ZH = (
    '你是一位翻译助手。把用户给的中文翻译成流畅准确的英文，保持学术或正式语体。'
    '只输出一个合法 JSON 对象：{{"translation": "...", "vocabulary": []}}，禁止输出其他内容。'
)

def load_active_api(cfg):
    # 优先使用独立的 API 配置文件
    api_cfg_path = os.path.join(BASE_DIR, 'api_config.json')
    if os.path.isfile(api_cfg_path):
        try:
            with open(api_cfg_path, encoding='utf-8') as f:
                api_cfg = json.load(f)
            base = api_cfg.get('base_url', '').rstrip('/')
            token = api_cfg.get('api_key')
            model = api_cfg.get('model', 'deepseek-chat')
            if base and token:
                print(f"[API] 使用 api_config.json: {base} / {model}")
                return base, token, model, 'api_config'
        except Exception as e:
            print(f"[API] 读取 api_config.json 失败: {e}")

    # 回退到 profiles.json
    path = cfg['profiles_path']
    if not os.path.isfile(path):
        raise RuntimeError(f'找不到 API 配置文件：\n{path}\n请先配置 api_config.json 或 /switch-api')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    profiles = data.get('profiles', {})
    if not profiles:
        raise RuntimeError('profiles.json 中没有任何 API 档案')
    active = data.get('active')
    prof = profiles.get(active) if active else None
    if not prof:
        prof = next(iter(profiles.values()))
    env = prof.get('env', {})
    base = (env.get('ANTHROPIC_BASE_URL') or '').rstrip('/')
    token = env.get('ANTHROPIC_AUTH_TOKEN') or env.get('ANTHROPIC_API_KEY')
    model = env.get('ANTHROPIC_MODEL') or 'claude-3-5-sonnet-latest'
    if not base or not token:
        raise RuntimeError(f'档案 "{active}" 缺少 ANTHROPIC_BASE_URL 或 ANTHROPIC_AUTH_TOKEN')
    return base, token, model, active

def parse_llm_response(raw):
    raw = raw.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r'\{.*\}', raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {'translation': raw, 'vocabulary': []}

def _validate_response(result):
    """验证 LLM 返回格式：翻译必须是字符串，词汇必须是字典列表"""
    if not isinstance(result, dict):
        return False
    translation = result.get('translation')
    if not isinstance(translation, str) or not translation.strip():
        return False
    vocab = result.get('vocabulary')
    if vocab is not None:
        if not isinstance(vocab, list):
            return False
        for v in vocab:
            if not isinstance(v, dict):
                return False
            if 'word' not in v:
                return False
    return True

def _extract_translation_from_partial(raw):
    """从不完整的 JSON 流中提取已接收的翻译文本，用于渐进显示"""
    raw = raw.strip()
    # 尝试提取 "translation": "..." 的值（即使 JSON 不完整）
    m = re.search(r'"translation"\s*:\s*"((?:[^"\\]|\\.)*)', raw, re.S)
    if m:
        text = m.group(1)
        # 反转义 JSON 字符串
        text = text.replace('\\"', '"').replace('\\\\', '\\').replace('\\n', '\n').replace('\\/', '/')
        return text
    return None

def translate_streaming_with_llm(text, cfg, on_progress=None):
    """流式调用 LLM，通过 on_progress 回调逐步返回已接收的翻译文本。
    on_progress(partial_result) 会被多次调用，partial_result 格式：
    {'translation': '...', 'vocabulary': [], '_complete': False/True}
    最终返回 (result, lang)。
    """
    base, token, model, name = load_active_api(cfg)
    lang = detect_lang(text)
    if lang == 'zh':
        system = SYSTEM_ZH
    else:
        system = SYSTEM_EN.format(n=cfg['max_vocabulary'])
    payload = {
        'model': model,
        'max_tokens': 1024,
        'system': system,
        'stream': True,
        'messages': [{'role': 'user', 'content': text}],
        # 禁用思考模式（DeepSeek 等模型默认可能开启，会生成大量隐藏推理 token 拖慢速度）
        'thinking': {'type': 'disabled'},
    }
    headers = {
        'Content-Type': 'application/json',
        'anthropic-version': '2023-06-01',
        'Authorization': f'Bearer {token}',
        'x-api-key': token,
    }
    print(f"  [API-S1] 流式请求到 {base}/v1/messages")
    print(f"  [API-S2] 模型: {model}")
    print(f"  [API-S3] 文本长度: {len(text)}")
    import time
    start_time = time.time()
    try:
        resp = requests.post(
            base + '/v1/messages', headers=headers, json=payload,
            timeout=cfg['timeout'], stream=True,
        )
        # 如果 API 不支持 thinking 参数，回退重试
        if resp.status_code == 400 and 'thinking' in resp.text.lower():
            print(f"  [API-S3b] API 不支持 thinking 参数，回退重试")
            payload.pop('thinking', None)
            resp = requests.post(
                base + '/v1/messages', headers=headers, json=payload,
                timeout=cfg['timeout'], stream=True,
            )
        if resp.status_code != 200:
            elapsed = time.time() - start_time
            print(f"  [API-S4] API 错误: {resp.text[:200]}，耗时: {elapsed:.2f}s")
            raise RuntimeError(f'API 错误（HTTP {resp.status_code}，档案 {name}）：\n{resp.text[:300]}')

        raw_parts = []
        thinking_chars = 0  # 检测思考 token（会拖慢速度但不显示）
        last_progress_len = 0
        first_chunk_logged = False
        for line in resp.iter_lines():
            if not line:
                continue
            line_str = line.decode('utf-8', errors='replace')
            if not line_str.startswith('data: '):
                continue
            data_str = line_str[6:]
            if data_str.strip() == '[DONE]':
                break
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            evt_type = event.get('type', '')
            if evt_type == 'content_block_delta':
                delta = event.get('delta', {})
                delta_type = delta.get('type', '')
                if delta_type == 'text_delta':
                    chunk = delta.get('text', '')
                    if chunk:
                        raw_parts.append(chunk)
                        if not first_chunk_logged:
                            first_chunk_logged = True
                            elapsed = time.time() - start_time
                            print(f"  [API-S5] 首字节到达，耗时: {elapsed:.2f}s")
                elif delta_type == 'thinking_delta':
                    # 思考 token —— 不显示但占用时间
                    thinking_chars += len(delta.get('thinking', ''))
            elif evt_type == 'message_stop':
                break

            # 每累积 30 个字符通知一次 UI 更新，避免过于频繁
            current_raw = ''.join(raw_parts)
            if on_progress and len(current_raw) - last_progress_len >= 30:
                last_progress_len = len(current_raw)
                partial_text = _extract_translation_from_partial(current_raw)
                if partial_text:
                    on_progress({'translation': partial_text, 'vocabulary': [], '_complete': False})

        elapsed = time.time() - start_time
        raw = ''.join(raw_parts)
        thinking_note = f'，thinking: {thinking_chars}字符' if thinking_chars > 0 else ''
        print(f"  [API-S6] 流式完成，总耗时: {elapsed:.2f}s，长度: {len(raw)}{thinking_note}")
        result = parse_llm_response(raw)

        # 验证返回格式——词汇必须是字典列表
        if not _validate_response(result):
            raise ValueError(f'LLM 返回格式错误: vocabulary 不是字典列表')

        result['_complete'] = True
        if on_progress:
            on_progress(result)
        return result, lang

    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"  [API-S9] 请求超时，耗时: {elapsed:.2f}s")
        raise RuntimeError(f'API 请求超时（{cfg["timeout"]}秒）')
    except requests.exceptions.RequestException as e:
        elapsed = time.time() - start_time
        print(f"  [API-S9] 请求异常: {e}，耗时: {elapsed:.2f}s")
        raise

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
# 配色方案 — 柔和蓝灰调，干净高级
BG = '#EFF3F8'               # 窗口背景：柔和蓝灰
CARD_BG = '#FFFFFF'          # 卡片：纯白
BORDER = '#B8C9DC'           # 外边框：淡蓝灰
BORDER_LIGHT = '#DAE3EE'     # 分隔线：极淡蓝灰
FG = '#1E293B'               # 主文字：深蓝灰
FG_LIGHT = '#475569'         # 次文字
FG_MUTED = '#94A3B8'         # 弱化文字
GRAY = '#CBD5E1'
ACCENT = '#3B82F6'           # 主题蓝：明亮清爽
ACCENT_LIGHT = '#EFF6FF'     # 淡蓝背景
ACCENT_HOVER = '#2563EB'
ERROR_BG = '#FEF2F2'
ERROR_FG = '#EF4444'
SECTION_COLOR = '#1E293B'
SOURCE_BG = '#F8FAFC'        # 原文区域：极浅蓝灰
SOURCE_FG = '#334155'
SOURCE_BORDER = '#93C5FD'    # 原文左侧装饰线：淡蓝
TITLE_BG = '#FFFFFF'
TITLE_FG = '#0F172A'
SHADOW = '#00000008'
COPY_BG = '#E8EFF7'          # 复制按钮：淡蓝灰
COPY_FG = '#475569'
COPY_HOVER = '#D4E0EE'
VOCAB_BG = '#F8FAFC'
VOCAB_DOT = '#3B82F6'

def _make_font(name='Microsoft YaHei UI', size=11, weight='normal', slant='roman'):
    try:
        from tkinter import font as tkfont
        return tkfont.Font(family=name, size=size, weight=weight, slant=slant)
    except Exception:
        return (name, size)

class TranslatorPopup:
    def __init__(self, master, source_text, x, y, cfg):
        print(f"  [UI-1] TranslatorPopup.__init__ 开始")
        print(f"  [UI-2] source_text 长度: {len(source_text)}")
        self.master = master
        self.cfg = cfg
        self.source_text = source_text
        self.result = None
        self._closed = False
        self._has_result = False  # 标记：翻译结果已到达，停止动画
        self._mouse_hook = None
        self._timer = None
        self._anim_id = None

        print(f"  [UI-3] 创建 Toplevel 窗口")
        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.configure(bg=BORDER)
        self.win.title('Translation')

        # 外层边框（模拟彩色边框效果）
        outer = tk.Frame(self.win, bg=BORDER)
        outer.pack(fill='both', expand=True)

        # 内层卡片
        self.card = tk.Frame(outer, bg=CARD_BG)
        self.card.pack(fill='both', expand=True, padx=2, pady=2)

        # ===== 标题栏 =====
        title_frame = tk.Frame(self.card, bg=TITLE_BG, height=44)
        title_frame.pack(fill='x')
        title_frame.pack_propagate(False)  # 固定高度

        title_inner = tk.Frame(title_frame, bg=TITLE_BG)
        title_inner.pack(fill='both', expand=True, padx=18, pady=0)

        # 标题图标和文字
        title_content = tk.Frame(title_inner, bg=TITLE_BG)
        title_content.pack(side='left', fill='x', expand=True)

        icon_label = tk.Label(title_content, text='✦', bg=TITLE_BG, fg=ACCENT,
                              font=('Segoe UI', 13))
        icon_label.pack(side='left', padx=(0, 10))

        title_label = tk.Label(title_content, text='翻译', bg=TITLE_BG, fg=TITLE_FG,
                               font=('Microsoft YaHei UI', 11, 'bold'))
        title_label.pack(side='left')

        # 关闭按钮 — 更低调
        close_btn = tk.Label(title_inner, text='✕', bg=TITLE_BG, fg=GRAY,
                             font=('Segoe UI', 11), cursor='hand2')
        close_btn.pack(side='right', padx=(8, 0))
        close_btn.bind('<Button-1>', lambda e: self.close())
        close_btn.bind('<Enter>', lambda e: close_btn.configure(fg=ERROR_FG))
        close_btn.bind('<Leave>', lambda e: close_btn.configure(fg=GRAY))

        # 标题下分隔线 — 更淡
        sep1 = tk.Frame(self.card, bg=BORDER_LIGHT, height=1)
        sep1.pack(fill='x')

        # ===== 原文区域 — 带左侧装饰线 =====
        source_outer = tk.Frame(self.card, bg=SOURCE_BG)
        source_outer.pack(fill='x', padx=18, pady=(14, 0))

        # 左侧装饰线 + 内容
        source_container = tk.Frame(source_outer, bg=SOURCE_BG)
        source_container.pack(fill='x', side='left', expand=True)

        # 左边框用一个小 Frame 模拟
        source_accent = tk.Frame(source_container, bg=SOURCE_BORDER, width=3)
        source_accent.pack(side='left', fill='y', padx=(0, 12))
        source_accent.pack_propagate(False)

        source_inner = tk.Frame(source_container, bg=SOURCE_BG)
        source_inner.pack(side='left', fill='x', expand=True, pady=(0, 14))

        # 原文标签 — 更小巧
        src_header = tk.Frame(source_inner, bg=SOURCE_BG)
        src_header.pack(fill='x')

        src_label = tk.Label(src_header, text='原文', bg=SOURCE_BG, fg=FG_MUTED,
                             font=('Microsoft YaHei UI', 9))
        src_label.pack(side='left')

        # 原文内容 — 更大字号，更好阅读
        snippet = source_text.replace('\n', ' ')
        if len(snippet) > 200:
            snippet = snippet[:197] + '…'
        print(f"  [UI-10] 设置原文: {snippet[:50]}...")
        self.source_label = tk.Label(source_inner, text=snippet, bg=SOURCE_BG, fg=SOURCE_FG,
                                     anchor='w', justify='left', wraplength=340,
                                     font=('Microsoft YaHei UI', 10))
        self.source_label.pack(fill='x', pady=(6, 0))
        print(f"  [UI-11] 原文 Label 已创建")

        # ===== 操作栏 =====
        btn_frame = tk.Frame(source_inner, bg=SOURCE_BG)
        btn_frame.pack(fill='x', pady=(10, 0))

        # 复制按钮 — 低调灰色风格
        copy_frame = tk.Frame(btn_frame, bg=COPY_BG, cursor='hand2',
                              highlightbackground=BORDER, highlightthickness=1)
        copy_frame.pack(side='left')
        self.copy_btn = tk.Label(copy_frame, text='复制翻译', bg=COPY_BG, fg=COPY_FG,
                                 font=('Microsoft YaHei UI', 9), cursor='hand2',
                                 padx=10, pady=4)
        self.copy_btn.pack()
        # 阻止事件冒泡，防止触发拖动
        self.copy_btn.bind('<Button-1>', lambda e: (e.widget.winfo_toplevel().focus_force(), self._copy_with_effect()), add='+')
        self.copy_btn.bind('<Enter>', lambda e: copy_frame.configure(bg=COPY_HOVER))
        self.copy_btn.bind('<Leave>', lambda e: copy_frame.configure(bg=COPY_BG))
        copy_frame.bind('<Enter>', lambda e: copy_frame.configure(bg=COPY_HOVER))
        copy_frame.bind('<Leave>', lambda e: copy_frame.configure(bg=COPY_BG))

        # 正文 Text - 翻译结果
        text_frame = tk.Frame(self.card, bg=CARD_BG)
        text_frame.pack(fill='both', expand=True, padx=18, pady=(12, 16))
        self.scroll = ttk.Scrollbar(text_frame, orient='vertical')
        self.scroll.pack(side='right', fill='y')
        self.body = tk.Text(
            text_frame, bd=0, highlightthickness=0, bg=CARD_BG, fg=FG,
            wrap='word', padx=0, pady=0, spacing1=3, spacing3=3,
            font=('Microsoft YaHei UI', 11), state='disabled',
            cursor='arrow', yscrollcommand=self.scroll.set, width=48,
            height=8,  # 初始高度较小，后续 _relayout 会调整
        )
        self.body.pack(side='left', fill='both', expand=True)
        self.scroll.config(command=self.body.yview)

        # 配置 tags — 精致的排版
        from tkinter import font as tkfont
        self.body.tag_configure('loading', foreground=FG_MUTED, font=tkfont.Font(family='Microsoft YaHei UI', size=10, slant='italic'))
        self.body.tag_configure('section', foreground=ACCENT, font=tkfont.Font(family='Microsoft YaHei UI', size=9, weight='bold'), spacing1=12, spacing3=4)
        self.body.tag_configure('translation', foreground=FG, font=tkfont.Font(family='Microsoft YaHei UI', size=11), spacing3=8)
        self.body.tag_configure('word', foreground=FG, font=tkfont.Font(family='Segoe UI', size=11, weight='bold'))
        self.body.tag_configure('phonetic', foreground=FG_MUTED, font=('Segoe UI', 10))
        self.body.tag_configure('pos', foreground=ACCENT, font=tkfont.Font(family='Microsoft YaHei UI', size=9), lmargin1=4)
        self.body.tag_configure('meaning', foreground=FG_LIGHT, font=('Microsoft YaHei UI', 10), lmargin1=20, lmargin2=20, spacing1=2, spacing3=4)
        self.body.tag_configure('error', foreground=ERROR_FG, font=('Microsoft YaHei UI', 10))

        # 初始 loading 显示
        self._show_loading()

        # 先让 tkinter 计算自然尺寸，再定位窗口
        self.win.update_idletasks()
        natural_w = max(self.win.winfo_reqwidth(), self.cfg['window_width'])
        natural_h = self.win.winfo_reqheight()
        self._place(x, y, provisional=True, height=natural_h)
        # 确保宽度至少是配置值
        try:
            self.win.geometry(f'{natural_w}x{natural_h}+{self._anchor[0]}+{self._anchor[1]}')
        except Exception:
            pass

        # 绑定：Esc 关闭
        self.win.bind('<Escape>', lambda e: self.close())
        self.win.after(50, self.win.focus_force)

        # 拖动功能 - 在标题栏和原文区域拖动
        title_frame.bind('<Button-1>', self._start_drag)
        title_frame.bind('<B1-Motion>', self._on_drag)
        title_inner.bind('<Button-1>', self._start_drag)
        title_inner.bind('<B1-Motion>', self._on_drag)
        title_content.bind('<Button-1>', self._start_drag)
        title_content.bind('<B1-Motion>', self._on_drag)
        title_label.bind('<Button-1>', self._start_drag)
        title_label.bind('<B1-Motion>', self._on_drag)
        icon_label.bind('<Button-1>', self._start_drag)
        icon_label.bind('<B1-Motion>', self._on_drag)
        source_outer.bind('<Button-1>', self._start_drag)
        source_outer.bind('<B1-Motion>', self._on_drag)
        source_container.bind('<Button-1>', self._start_drag)
        source_container.bind('<B1-Motion>', self._on_drag)
        source_inner.bind('<Button-1>', self._start_drag)
        source_inner.bind('<B1-Motion>', self._on_drag)
        src_label.bind('<Button-1>', self._start_drag)
        src_label.bind('<B1-Motion>', self._on_drag)
        self.source_label.bind('<Button-1>', self._start_drag)
        self.source_label.bind('<B1-Motion>', self._on_drag)

        # 不自动关闭，不鼠标点击关闭 - 只能通过按钮或 Esc 关闭

        # 强制立即显示窗口和原文
        print(f"  [UI-20] 强制刷新窗口")
        self.win.update_idletasks()
        print(f"  [UI-21] update_idletasks 完成")
        self.win.update()
        print(f"  [UI-22] update 完成")
        self.win.lift()
        self.win.attributes('-topmost', True)
        self.win.deiconify()
        print(f"  [UI-23] 窗口已显示")

    # ---------- loading 动画 ----------
    def _show_loading(self):
        """在翻译结果区域显示 loading，原文保持不变"""
        self._has_result = False  # 重置标志，允许动画运行
        self._anim_step = 0
        self.body.configure(state='normal')
        self.body.delete('1.0', 'end')
        self.body.insert('1.0', '正在翻译.', 'loading')
        self.body.configure(state='disabled')
        self._animate()

    def _animate(self):
        if self._closed or self._has_result:
            return
        dots = '.' * ((self._anim_step % 3) + 1)
        self.body.configure(state='normal')
        self.body.delete('1.0', 'end')
        self.body.insert('1.0', '正在翻译' + dots, 'loading')
        self.body.configure(state='disabled')
        self._anim_step += 1
        try:
            self._anim_id = self.win.after(400, self._animate)
        except Exception:
            pass

    # ---------- 更新内容（不改变位置） ----------
    def _update_content(self, source_text):
        """更新窗口内容，保持位置不变"""
        print(f"  [UI-UPDATE-1] _update_content 被调用")
        print(f"  [UI-UPDATE-2] source_text: {source_text[:50]}")
        self.source_text = source_text
        self.result = None
        self._has_result = False  # 重置标志，允许动画继续
        # 更新原文显示
        snippet = source_text.replace('\n', ' ')
        if len(snippet) > 200:
            snippet = snippet[:197] + '…'
        self.source_label.configure(text=snippet)
        print(f"  [UI-UPDATE-3] 原文已更新")
        # 强制立即刷新，让原文立即显示
        self.win.update_idletasks()
        self.win.update()
        print(f"  [UI-UPDATE-3.5] 窗口已强制刷新")
        # 显示 loading
        self._show_loading()
        print(f"  [UI-UPDATE-4] loading 已显示")
        # 开始流式翻译
        import threading
        popup_ref = self
        def worker():
            print(f"  [UI-UPDATE-5] 翻译线程启动（流式）")
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    print(f"  [UI-UPDATE-6] 调用 translate_streaming_with_llm（第 {attempt+1} 次）...")
                    def progress_cb(partial):
                        popup_ref.on_progress(partial)
                    result, lang = translate_streaming_with_llm(source_text, self.cfg, on_progress=progress_cb)
                    print(f"  [UI-UPDATE-7] 翻译完成")
                    popup_ref.win.after(0, lambda: popup_ref.on_result(result))
                    print(f"  [UI-UPDATE-8] 已调度 on_result")
                    return  # 成功，退出
                except ValueError as e:
                    # 格式错误 → 重试
                    print(f"  [UI-UPDATE-6b] 格式错误，重试: {e}")
                    if attempt < max_retries:
                        popup_ref._has_result = False
                        popup_ref._show_loading()
                        continue
                    else:
                        popup_ref.win.after(0, lambda: popup_ref.on_error(f'LLM 返回格式错误（重试 {max_retries} 次后放弃）'))
                        return
                except Exception as e:
                    print(f"  [UI-UPDATE-9] 翻译异常: {e}")
                    import traceback
                    traceback.print_exc()
                    popup_ref.win.after(0, lambda: popup_ref.on_error(str(e)))
                    return
        print(f"  [UI-UPDATE-10] 启动翻译线程")
        threading.Thread(target=worker, daemon=True).start()
        print(f"  [UI-UPDATE-11] 翻译线程已启动")

    # ---------- 渐进显示（流式输出） ----------
    def on_progress(self, partial_result):
        """流式翻译过程中渐进显示已接收的翻译文本"""
        if self._closed:
            return
        try:
            translation = (partial_result.get('translation') or '').strip()
            if not translation:
                return
            is_complete = partial_result.get('_complete', False)
            # 在主线程更新 UI
            def _do_update():
                if self._closed:
                    return
                # 如果已有完整结果，忽略后续的不完整进度
                if self._has_result and not is_complete:
                    return
                # 首次收到内容时，停止 loading 动画
                if not self._has_result:
                    self._has_result = True  # 标记：已有内容，阻止 _animate 覆盖
                    try:
                        if self._anim_id:
                            self.win.after_cancel(self._anim_id)
                    except Exception:
                        pass
                    self._anim_id = None
                # 显示部分/完整翻译结果
                self.body.configure(state='normal')
                self.body.delete('1.0', 'end')
                if is_complete:
                    self.body.insert('end', '翻译\n', 'section')
                else:
                    self.body.insert('end', '翻译中\n', 'loading')
                self.body.insert('end', translation, 'translation')
                self.body.configure(state='disabled')
            self.win.after(0, _do_update)
        except Exception:
            pass

    # ---------- 显示结果 ----------
    def on_result(self, result):
        if self._closed:
            return
        # 立即设置标志，阻止后续的 _animate 覆盖结果
        self._has_result = True
        # 停止动画
        try:
            if self._anim_id:
                self.win.after_cancel(self._anim_id)
        except Exception:
            pass
        self._anim_id = None

        self.result = result
        translation = (result.get('translation') or '').strip()
        vocab = result.get('vocabulary') or []

        self.body.configure(state='normal')
        self.body.delete('1.0', 'end')

        # 翻译结果
        if translation:
            self.body.insert('end', '翻译\n', 'section')
            self.body.insert('end', translation, 'translation')

        # 词汇（已验证：每个 v 一定是 dict 且包含 'word' key）
        if vocab:
            self.body.insert('end', '\n\n词汇\n', 'section')
            for i, v in enumerate(vocab):
                word = (v.get('word') or '').strip()
                phonetic = (v.get('phonetic') or '').strip()
                pos = (v.get('pos') or v.get('type') or '').strip()
                meaning = (v.get('meaning') or v.get('definition') or v.get('translation') or '').strip()
                if not word:
                    continue
                # 每个词条前的分隔
                if i > 0:
                    self.body.insert('end', '\n', 'meaning')
                # 单词行：• word  /phonetic/  词性
                self.body.insert('end', '•  ', 'meaning')
                self.body.insert('end', word, 'word')
                if phonetic:
                    ph = phonetic if phonetic.startswith('/') else '/' + phonetic
                    self.body.insert('end', '  ' + ph, 'phonetic')
                if pos:
                    self.body.insert('end', '    ' + pos, 'pos')
                self.body.insert('end', '\n')
                # 释义
                if meaning:
                    self.body.insert('end', meaning + '\n', 'meaning')

        if not translation and not vocab:
            self.body.insert('end', '（未返回结果）', 'loading')
        self.body.configure(state='disabled')
        self._relayout()
        # 强制刷新显示
        self.win.update_idletasks()
        self.win.update()
        print(f"  [ON-RESULT] 翻译结果已显示")

    def on_error(self, msg):
        if self._closed:
            return
        self._has_result = True  # 阻止动画覆盖错误信息
        try:
            if self._anim_id:
                self.win.after_cancel(self._anim_id)
        except Exception:
            pass
        self._anim_id = None
        self.body.configure(state='normal')
        self.body.delete('1.0', 'end')
        self.body.insert('end', '翻译失败\n', 'error')
        self.body.insert('end', msg, 'error')
        self.body.configure(state='disabled')
        self._relayout()
        # 强制刷新显示
        self.win.update_idletasks()
        self.win.update()

    # ---------- 布局 ----------
    def _relayout(self):
        if self._closed:
            return
        self.body.update_idletasks()
        self.win.update_idletasks()
        # 固定高度，超出部分用滚动条
        body_height = 15
        self.body.configure(height=body_height)
        # 始终显示滚动条
        try:
            self.scroll.grid()
        except Exception:
            pass
        self.win.update_idletasks()
        # 计算所需高度，保持当前位置和宽度
        try:
            self.win.update_idletasks()
            needed_h = self.win.winfo_reqheight()
            w = self.win.winfo_width()
            x = self.win.winfo_x()
            y = self.win.winfo_y()
            if w < 100:  # 如果宽度异常小，使用配置值
                w = self.cfg['window_width']
            if needed_h < 50:
                needed_h = 300
            self.win.geometry(f'{w}x{needed_h}+{x}+{y}')
        except Exception:
            pass

    def _place(self, x, y, provisional=False, height=None):
        wa = get_workarea(x, y)
        w = self.cfg['window_width']
        if height is None:
            h = 100 if provisional else self.win.winfo_reqheight()
        else:
            h = height
        px = x + 16
        py = y + 20
        if px + w > wa[2] - 8:
            px = wa[2] - w - 8
        if py + h > wa[3] - 8:
            py = max(wa[1] + 8, wa[3] - h - 8)
        px = max(px, wa[0] + 8)
        try:
            if provisional:
                # 只设置位置，让窗口高度由内容决定（避免固定小高度裁剪内容）
                self.win.geometry(f'+{px}+{py}')
            else:
                self.win.geometry(f'{w}x{h}+{px}+{py}')
        except Exception:
            pass
        self._anchor = (px, py)

    # ---------- 拖动 ----------
    def _start_drag(self, event):
        """记录拖动起点"""
        self._drag_x = event.x_root - self.win.winfo_x()
        self._drag_y = event.y_root - self.win.winfo_y()

    def _on_drag(self, event):
        """拖动窗口"""
        try:
            x = event.x_root - self._drag_x
            y = event.y_root - self._drag_y
            self.win.geometry(f'+{x}+{y}')
            self._anchor = (x, y)
        except Exception:
            pass

    # ---------- 关闭 ----------
    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._timer:
                self.master.after_cancel(self._timer)
        except Exception:
            pass
        try:
            if self._anim_id:
                self.master.after_cancel(self._anim_id)
        except Exception:
            pass
        if self._mouse_hook is not None:
            try:
                mouse.unhook(self._mouse_hook)
            except Exception:
                pass
            self._mouse_hook = None
        try:
            self.win.destroy()
        except Exception:
            pass

    # ---------- 事件 ----------
    def _copy_with_effect(self):
        """复制并显示视觉特效"""
        print("[COPY] 复制按钮被点击（带特效）")
        if not self.result or not self.result.get('translation'):
            print("[COPY] 没有翻译结果可复制")
            return

        text = self.result['translation']
        print(f"[COPY] 准备复制: {text[:50]}...")

        # 复制
        success = set_clipboard_text(text)
        if success:
            print("[COPY] 复制成功")
            # 视觉特效：临时改变按钮文字和颜色
            original_text = self.copy_btn.cget('text')
            original_fg = self.copy_btn.cget('fg')
            # 显示成功状态 — 靛蓝色确认
            self.copy_btn.configure(text='已复制 ✓', fg=ACCENT)
            # 1.5秒后恢复
            self.master.after(1500, lambda: self._reset_copy_button(original_text, original_fg))
        else:
            print("[COPY] 复制失败")

    def _reset_copy_button(self, original_text, original_fg):
        """恢复复制按钮原始状态"""
        try:
            self.copy_btn.configure(text=original_text, fg=original_fg)
        except Exception:
            pass

    def _copy(self):
        print("[COPY] 复制按钮被点击")
        print(f"[COPY] result: {self.result}")
        if not self.result or not self.result.get('translation'):
            print("[COPY] 没有翻译结果可复制")
            return
        try:
            text = self.result['translation']
            print(f"[COPY] 准备复制: {text[:50]}...")
            result = set_clipboard_text(text)
            if result:
                print("[COPY] 复制成功")
                # 临时提示
                self.source_label.configure(text='✓ 已复制到剪贴板')
                self.master.after(1500, lambda: self.source_label.configure(
                    text=self.source_text.replace('\n', ' ')[:150] + ('…' if len(self.source_text) > 150 else '')
                ))
            else:
                print("[COPY] 复制失败")
        except Exception as e:
            print(f"[COPY] 复制异常: {e}")
            import traceback
            traceback.print_exc()

    def _on_click_outside(self):
        try:
            x, y = mouse.get_position()
            wx = self.win.winfo_rootx()
            wy = self.win.winfo_rooty()
            ww = self.win.winfo_width()
            wh = self.win.winfo_height()
            if not (wx <= x <= wx + ww and wy <= y <= wy + wh):
                self.master.after(0, self.close)
        except Exception:
            pass

    def _on_focus_out(self, event):
        # 焦点离开时若目标窗口不是本弹窗的子代，则关闭
        try:
            focus = self.win.focus_get()
            # 如果 focus 在本窗口内，忽略
            if focus is not None and str(focus).startswith(str(self.win)):
                return
        except Exception:
            pass

# ---------------------------------------------------------------------------
# 启动 Toast
# ---------------------------------------------------------------------------
def show_toast(master, message, ms=2500):
    t = tk.Toplevel(master)
    t.overrideredirect(True)
    t.attributes('-topmost', True)
    try:
        t.attributes('-alpha', 0.95)
    except Exception:
        pass
    lbl = tk.Label(t, text=message, bg='#2F3640', fg='white',
                   padx=16, pady=10, font=('Microsoft YaHei UI', 10))
    lbl.pack()
    t.update_idletasks()
    wa = get_workarea(0, 0)
    tw = t.winfo_width()
    th = t.winfo_height()
    t.geometry(f'+{wa[2] - tw - 24}+{wa[3] - th - 24}')
    try:
        master.after(ms, t.destroy)
    except Exception:
        t.destroy()

# ---------------------------------------------------------------------------
# 主应用
# ---------------------------------------------------------------------------
class App:
    def __init__(self):
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title('PopupTranslator')
        self.popup = None
        self._last_text_hash = (None, 0.0)

        # 注册快捷键
        hotkey = self.cfg['hotkey']
        try:
            keyboard.add_hotkey(hotkey, self._on_hotkey, suppress=False)
            print(f"✅ 快捷键已注册: {hotkey}")
        except Exception as e:
            print(f"❌ 快捷键注册失败: {e}")
            self.root.after(300, lambda: show_toast(self.root, f'快捷键注册失败：{e}', 4000))
            traceback.print_exc()

        # 启动提示
        hk_display = hotkey.upper()
        print(f"划词翻译已启动，选中文字后按 {hk_display}")
        self.root.after(400, lambda: show_toast(
            self.root, f'划词翻译已启动\n选中文字后按 {hk_display}', 2800))

        # 启动时显示欢迎窗口
        self.root.after(800, self._show_welcome)

    def _show_welcome(self):
        """启动时显示欢迎窗口"""
        import ctypes.wintypes
        # 获取屏幕中心位置
        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        x = screen_w // 2 - 280
        y = screen_h // 2 - 150

        welcome_text = "欢迎使用划词翻译！\n\n选中任意英文文本，按快捷键即可翻译。\n窗口可拖动，点 ✕ 或按 Esc 关闭。"
        self.popup = TranslatorPopup(self.root, welcome_text, x, y, self.cfg)
        # 直接显示完成状态（不加载）
        self.popup.body.configure(state='normal')
        self.popup.body.delete('1.0', 'end')
        self.popup.body.insert('1.0', welcome_text, 'translation')
        self.popup.body.configure(state='disabled')
        # 更新原文显示
        self.popup.source_label.configure(text=welcome_text)

    def _on_hotkey(self):
        print(f"\n=== 快捷键触发: {self.cfg['hotkey']} ===")
        # 快捷键回调在 keyboard 库的线程里；把实际工作放到独立线程
        threading.Thread(target=self._capture_and_translate, daemon=True).start()

    def _capture_and_translate(self):
        try:
            print("  [1] 开始捕获和翻译...")
            pos = get_cursor_pos()
            hotkey = self.cfg['hotkey'].strip()

            # 如果快捷键最后一步是 ctrl+c，剪贴板已是最新，不需要再模拟
            ends_with_copy = hotkey.lower().endswith('ctrl+c')
            print(f"  [2] ends_with_copy={ends_with_copy}")

            if ends_with_copy:
                # 清空剪贴板，便于检测新复制
                try:
                    ctypes.windll.user32.OpenClipboard(None)
                    ctypes.windll.user32.EmptyClipboard()
                    ctypes.windll.user32.CloseClipboard()
                except Exception:
                    pass

                # 等待键盘事件传递给应用并处理
                time.sleep(0.2)

                # 轮询等待剪贴板有新内容（最多等 1 秒）
                text = None
                for _ in range(20):
                    time.sleep(0.05)
                    text = get_clipboard_text()
                    if text:
                        print(f"  [2.1] 剪贴板有内容（自然复制）")
                        break

                # 如果剪贴板还是空的，说明按键没传过去，手动补发 Ctrl+C
                if not text:
                    print(f"  [2.2] 自然复制失败，手动发送 Ctrl+C")
                    self._send_ctrl_c()
                    time.sleep(0.3)
                    text = get_clipboard_text()
                    if text:
                        print(f"  [2.3] 手动 Ctrl+C 成功")

                before = None
                if not text:
                    print(f"  [2.4] 最终无内容，退出")
                    return
                print(f"  [2.5] 剪贴板内容长度: {len(text)}")
            else:
                before = get_clipboard_text()
                print(f"  [3] 剪贴板原内容长度: {len(before) if before else 0}")

                # 找到鼠标下方的窗口
                mouse_x, mouse_y = pos
                pt = _POINT(mouse_x, mouse_y)
                user32 = ctypes.windll.user32
                hwnd = user32.WindowFromPoint(pt)

                if hwnd:
                    # 获取根窗口（处理子窗口情况）
                    root_hwnd = user32.GetAncestor(hwnd, 2)  # GA_ROOT = 2
                    target = root_hwnd or hwnd
                    print(f"  [3.1] 目标窗口句柄: {target}")

                    # 强制激活目标窗口（绕过 Windows 后台进程限制）
                    self._force_activate_window(target)
                    time.sleep(0.15)

                # 模拟 Ctrl+C
                self._send_ctrl_c()
                time.sleep(0.25)

                text = get_clipboard_text()
                # 如果剪贴板没变，再试一次
                if text == before or not text:
                    time.sleep(0.15)
                    self._send_ctrl_c()
                    time.sleep(0.25)
                    text = get_clipboard_text()

                print(f"  [4] 剪贴板新内容长度: {len(text) if text else 0}")

            if not text:
                return
            # 如果剪贴板内容和之前一样（没有新复制），跳过
            if before is not None and text == before:
                print(f"  [5] 剪贴板无变化，跳过")
                return
            text = clean_text(text)
            print(f"  [7] cleaned text length={len(text)}")
            if not text or len(text.strip()) < 2:
                print(f"  [8] 文本太短，退出")
                return

            # 2 秒内相同文本去重
            h = hash(text)
            prev_text, prev_ts = self._last_text_hash
            if h == prev_text and time.time() - prev_ts < 2.0:
                print(f"  [9] 重复触发，退出")
                return
            self._last_text_hash = (h, time.time())

            text = text[:4000]
            print(f"  [10] 准备显示弹窗...")
            print(f"  [10.1] 文本长度: {len(text)}")
            print(f"  [10.2] 文本前50字符: {text[:50]}")
            self.root.after(0, lambda: self._show_popup(text, pos))
            print(f"  [10.3] 已调度 _show_popup")
        except Exception:
            traceback.print_exc()

    def _force_activate_window(self, hwnd):
        """强制激活窗口——使用"闪现"技巧绕过 Windows 前台限制"""
        user32 = ctypes.windll.user32
        try:
            # 如果窗口最小化，先恢复
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE

            # 核心技巧：快速 Hide → Show 让 Windows 认为用户激活了这个窗口
            user32.ShowWindow(hwnd, 0)   # SW_HIDE
            user32.ShowWindow(hwnd, 5)   # SW_SHOW

            # 然后再尝试前台切换
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)

            # 模拟 Alt 按键释放前台锁定
            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            print(f"  [activate] 窗口已激活")
        except Exception as e:
            print(f"  [activate] 窗口激活失败: {e}")

    def _send_ctrl_c(self):
        """模拟 Ctrl+C —— 优先用 keyboard 库（权限更高），回退到 SendInput"""
        try:
            # keyboard 库使用低级钩子，模拟的输入更"真实"
            import keyboard as kb
            kb.send('ctrl+c')
            print(f"  [ctrl+c] 使用 keyboard 库发送")
        except Exception as e1:
            print(f"  [ctrl+c] keyboard 库失败: {e1}，回退到 SendInput")
            # 回退到 SendInput
            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [("wVk", ctypes.wintypes.WORD),
                            ("wScan", ctypes.wintypes.WORD),
                            ("dwFlags", ctypes.wintypes.DWORD),
                            ("time", ctypes.wintypes.DWORD),
                            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

            class INPUT(ctypes.Structure):
                class _INPUT(ctypes.Union):
                    _fields_ = [("ki", KEYBDINPUT)]
                _anonymous_ = ("_input",)
                _fields_ = [("type", ctypes.wintypes.DWORD),
                            ("_input", _INPUT)]

            INPUT_KEYBOARD = 1
            KEYEVENTF_KEYUP = 0x0002
            VK_CONTROL = 0x11
            VK_C = 0x43

            inputs = (INPUT * 4)()
            inputs[0].type = INPUT_KEYBOARD
            inputs[0].ki.wVk = VK_CONTROL
            inputs[0].ki.dwFlags = 0
            inputs[1].type = INPUT_KEYBOARD
            inputs[1].ki.wVk = VK_C
            inputs[1].ki.dwFlags = 0
            inputs[2].type = INPUT_KEYBOARD
            inputs[2].ki.wVk = VK_C
            inputs[2].ki.dwFlags = KEYEVENTF_KEYUP
            inputs[3].type = INPUT_KEYBOARD
            inputs[3].ki.wVk = VK_CONTROL
            inputs[3].ki.dwFlags = KEYEVENTF_KEYUP

            ctypes.windll.user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))

    def _show_popup(self, text, pos):
        print(f"  [11] _show_popup 被调用")
        print(f"  [11.1] 文本长度: {len(text)}")
        if self.popup and not self.popup._closed:
            try:
                print(f"  [11.2] 窗口已存在，更新内容")
                # 如果窗口已存在且未关闭，更新内容但不改变位置
                self.popup._update_content(text)
                return
            except Exception as e:
                print(f"  [11.2] 更新失败: {e}")
                self.popup = None
        elif self.popup and self.popup._closed:
            print(f"  [11.2b] 旧窗口已关闭，清理引用")
            self.popup = None
        print(f"  [11.3] 创建新窗口")
        # 首次创建时放在屏幕中央
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        center_x = screen_w // 2 - 280
        center_y = screen_h // 2 - 200
        print(f"  [11.4] 窗口位置: ({center_x}, {center_y})")
        self.popup = TranslatorPopup(self.root, text, center_x, center_y, self.cfg)
        print(f"  [11.5] TranslatorPopup 创建完成")

        # 直接捕获 popup 引用，避免 self.popup 被后续快捷键替换导致回调丢失
        popup = self.popup

        def worker():
            print(f"  [12] 翻译线程启动（流式）")
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    print(f"  [12.1] 调用 translate_streaming_with_llm（第 {attempt+1} 次）...")
                    def progress_cb(partial):
                        popup.on_progress(partial)
                    result, lang = translate_streaming_with_llm(text, self.cfg, on_progress=progress_cb)
                    print(f"  [12.2] 翻译完成: {len(str(result))} 字符")
                    popup.win.after(0, lambda: popup.on_result(result))
                    print(f"  [12.3] 已调度 on_result")
                    return  # 成功
                except ValueError as e:
                    print(f"  [12.1b] 格式错误，重试: {e}")
                    if attempt < max_retries:
                        popup._has_result = False
                        popup._show_loading()
                        continue
                    else:
                        popup.win.after(0, lambda: popup.on_error(f'LLM 返回格式错误（重试 {max_retries} 次后放弃）'))
                        return
                except Exception as e:
                    print(f"  [12.9] 翻译异常: {e}")
                    import traceback
                    traceback.print_exc()
                    popup.win.after(0, lambda: popup.on_error(str(e)))
                    return
        print(f"  [11.6] 启动翻译线程")
        threading.Thread(target=worker, daemon=True).start()
        print(f"  [11.7] 翻译线程已启动")

    def run(self):
        self.root.mainloop()

# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
_mutex_handle = None

def main():
    global _mutex_handle
    if sys.platform != 'win32':
        print('此工具目前仅支持 Windows')
        return
    # 单实例
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, 'PopupTranslator_SingleInstance_v1')
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        show_toast(None, '划词翻译已在运行')
        return
    App().run()

if __name__ == '__main__':
    main()
