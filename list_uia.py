# -*- coding: utf-8 -*-
from comtypes.gen.UIAutomationClient import *
import sys

# 搜索 ControlType 相关常量
for name in sorted(dir()):
    if 'ControlType' in name and name.startswith('UIA'):
        print(f"{name} = {eval(name)}")

print("\n--- TextPattern related ---")
for name in sorted(dir()):
    if 'TextPattern' in name or 'Text' in name and name.startswith('UIA'):
        print(f"{name} = {eval(name)}")

print("\n--- PropertyId related ---")
for name in sorted(dir()):
    if 'PropertyId' in name and name.startswith('UIA'):
        print(f"{name} = {eval(name)}")
