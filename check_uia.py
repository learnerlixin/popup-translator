# -*- coding: utf-8 -*-
from comtypes.gen.UIAutomationClient import *
import comtypes.client

# 查看 IUIAutomationTextRangeArray 的方法
print("IUIAutomationTextRangeArray methods:")
for name in dir(IUIAutomationTextRangeArray):
    if not name.startswith('_'):
        print(f"  {name}")

print("\nIUIAutomationTextPattern methods:")
for name in dir(IUIAutomationTextPattern):
    if not name.startswith('_'):
        print(f"  {name}")
