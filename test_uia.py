# -*- coding: utf-8 -*-
"""测试 UI Automation 获取选中文本"""
import comtypes.client
import time

print("=" * 50)
print("UI Automation 测试")
print("=" * 50)
print("请在 3 秒内选中一段文本...")
time.sleep(3)

try:
    # 创建 UI Automation 实例
    print("\n[1] 创建 UI Automation 实例...")
    uia = comtypes.client.CreateObject('{ff48dba4-60ef-4201-aa87-54103eef594e}')
    print(f"    成功: {type(uia)}")

    # 获取当前焦点元素
    print("\n[2] 获取焦点元素...")
    from comtypes.gen.UIAutomationClient import IUIAutomation
    uia = uia.QueryInterface(IUIAutomation)
    focused = uia.GetFocusedElement()
    print(f"    焦点元素: {focused}")

    if focused:
        from comtypes.gen.UIAutomationClient import IUIAutomationElement, UIA_TextPatternId
        elem = focused.QueryInterface(IUIAutomationElement)
        print(f"    元素名称: {elem.CurrentName}")
        print(f"    元素类名: {elem.CurrentClassName}")
        print(f"    控件类型: {elem.CurrentControlType}")

        # 尝试获取 TextPattern
        print("\n[3] 尝试获取 TextPattern...")
        try:
            text_pattern = elem.GetCurrentPattern(UIA_TextPatternId)
            print(f"    TextPattern: {text_pattern}")

            if text_pattern:
                from comtypes.gen.UIAutomationClient import IUIAutomationTextPattern
                text_pattern = text_pattern.QueryInterface(IUIAutomationTextPattern)

                # 获取选中的文本
                print("\n[4] 获取选中文本...")
                selection = text_pattern.GetSelection()
                print(f"    选择数量: {selection.length if selection else 0}")

                if selection and selection.length > 0:
                    text_range = selection.GetAt(0)
                    from comtypes.gen.UIAutomationClient import IUIAutomationTextRange
                    text_range = text_range.QueryInterface(IUIAutomationTextRange)
                    text = text_range.GetText(-1)
                    print(f"\n✓ 选中文本 ({len(text)} 字符):")
                    print("-" * 50)
                    print(text[:500])
                else:
                    print("\n✗ 无选中文本")
        except Exception as e:
            print(f"    TextPattern 失败: {e}")

except Exception as e:
    print(f"\n✗ 错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 50)
input("按回车退出...")
