import pandas as pd
import numpy as np
import os
import sys

sys.path.append(os.getcwd())
from src.indicators import calculate_chaos_index

df = pd.read_csv("data/TRUMP_USDT_1h.csv").tail(200)
chaos = calculate_chaos_index(df)
print(f"Chaos Index Stats:")
print(chaos.describe())
print(f"Latest 5 values: {chaos.tail(5).tolist()}")
