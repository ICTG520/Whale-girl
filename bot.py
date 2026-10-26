import sys
from pathlib import Path

import nonebot
from nonebot.adapters.onebot.v11 import Adapter

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)
nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()
