# -*- coding: utf-8 -*-
import comtypes.client

# 生成 UI Automation 类型库
print("generating UI Automation type library...")
try:
    comtypes.client.GetModule('UIAutomationCore.dll')
    print("SUCCESS: UI Automation type library generated")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
