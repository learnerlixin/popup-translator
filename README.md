# 划词翻译弹窗

在任意 Windows 软件中选中英文句子 → 按快捷键 → 鼠标旁弹出中文翻译 + 重点词汇卡片。

> 项目路径：`E:\vscode代码\AI_coding\popup-translator\`

## 特性

- **全局生效**：浏览器、PDF、Word、终端……任何能选文字的地方都能用
- **默认快捷键**：双击 `Ctrl+C`（习惯跟有道词典一致），支持自定义
- **翻译引擎自动跟随**：读取 `C:/Users/qweli/.claude/api-profiles/profiles.json` 中的当前档案，`/switch-api use xxx` 切换后无需重启本工具
- **卡片内容**：
  - 整句中文翻译（保持学术语体）
  - 重点词汇：音标 / 词性 / 语境含义
  - 复制按钮、Esc 关闭、点击外部关闭、自动关闭（默认 25 秒）
- **自动处理 PDF 软换行**：合并断行、去除行尾连字符

## 使用方法

### 1. 安装依赖

```powershell
E:\Python310\python.exe -m pip install -r E:\vscode代码\AI_coding\popup-translator\requirements.txt
```

（已安装：keyboard、mouse、requests）

### 2. 启动

**双击** `E:\vscode代码\AI_coding\popup-translator\启动划词翻译.vbs`

右下角会弹出 toast 提示 "划词翻译已启动 · 选中文字后按 CTRL+C, CTRL+C"。

### 3. 使用

1. 在任何软件中**选中一段英文**
2. 按下 **Ctrl+C 再按一次 Ctrl+C**（双击）
3. 鼠标旁会弹出翻译卡片
4. 卡片行为：
   - 点右上角 ✕ 或按 Esc 关闭
   - 点任意空白处自动关闭
   - 25 秒无操作自动关闭（可在 `config.json` 修改 `auto_close_seconds`）
   - 点 "复制" 把翻译复制到剪贴板

### 4. 设置开机自启

按 `Win + R` 输入 `shell:startup` 回车，把 `E:\vscode代码\AI_coding\popup-translator\启动划词翻译.vbs` 的快捷方式丢进去即可。

## 配置

编辑 `E:\vscode代码\AI_coding\popup-translator\config.json`：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `hotkey` | `"ctrl+c, ctrl+c"` | 快捷键，如 `"ctrl+alt+t"`（改完后需重启工具）|
| `auto_close_seconds` | `25` | 多久无操作自动关闭弹窗 |
| `max_vocabulary` | `6` | 每个弹窗最多显示几个重点词 |
| `timeout` | `30` | API 请求超时秒数 |
| `window_width` | `440` | 弹窗宽度（像素）|
| `profiles_path` | `C:/Users/qweli/.claude/api-profiles/profiles.json` | API 档案路径 |

## 故障排查

- **按快捷键没反应**
  - 检查 toast 是否出现，说明热键注册失败？看 config.json 的 hotkey 是否合法
  - 某些以管理员身份运行的程序（如某些 PDF 阅读器）无法被普通权限的 hook 拦截 → 以管理员身份运行 vbs
- **弹窗位置不对 / 很小**
  - 高 DPI 屏幕已做 DPI 感知；如仍有问题可尝试修改 `window_width`
- **翻译失败**
  - 错误信息会显示在弹窗里
  - 常见原因：API 档案切换后当前档案失效、网络问题、余额不足
- **想完全退出工具**
  - 任务管理器里找 `pythonw.exe`，结束进程
  - 或 `taskkill /f /im pythonw.exe`（小心这会结束所有 pythonw）

## 文件结构

```
popup-translator/
├── popup_translator.py     # 主程序
├── config.json             # 配置
├── requirements.txt        # 依赖
├── 启动划词翻译.vbs         # 启动脚本（无控制台窗口）
└── README.md               # 本文件
```
