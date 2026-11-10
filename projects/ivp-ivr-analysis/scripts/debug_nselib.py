import nselib
from nselib import capital_market
from datetime import datetime

print("=== nselib attributes ===")
for attr in dir(nselib):
    if not attr.startswith('_'):
        print(f"  {attr}")

print("\n=== Checking for 'fno' module ===")
if hasattr(nselib, 'fno'):
    print("  nselib.fno exists!")
    print(f"  fno attributes: {[x for x in dir(nselib.fno) if not x.startswith('_')]}")
else:
    print("  nselib.fno does NOT exist")

print("\n=== Searching for 'bhav' in all modules ===")
import pkgutil
import importlib

for module_name in ['nselib', 'nselib.capital_market', 'nselib.fno']:
    try:
        module = importlib.import_module(module_name)
        for attr in dir(module):
            if 'bhav' in attr.lower():
                print(f"  {module_name}.{attr}")
    except:
        pass

print("\n=== Searching for 'fno' in all modules ===")
for module_name in ['nselib', 'nselib.capital_market']:
    try:
        module = importlib.import_module(module_name)
        for attr in dir(module):
            if attr.lower().startswith('fno'):
                print(f"  {module_name}.{attr}")
    except:
        pass
