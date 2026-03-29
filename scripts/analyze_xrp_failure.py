import pandas as pd
import os

import glob
base_pattern = 'reports/XRP_USDT/2024_FULL/Risk_5/**/trades.csv'
files = glob.glob(base_pattern, recursive=True)
if not files:
    print(f"No files found for pattern: {base_pattern}")
    exit()
df = pd.read_csv(files[0])
closed = df[df['type']=='CLOSE']
wins = closed[closed['pnl_usdt'] > 0]
losses = closed[closed['pnl_usdt'] <= 0]

pf = abs(wins['pnl_usdt'].sum() / losses['pnl_usdt'].sum()) if len(losses) > 0 else 0

print(f'--- XRP 2024 Statistical Data ---')
print(f'Total Trades: {len(closed)}')
print(f'Win Rate: {len(wins)/len(closed)*100:.2f}%')
print(f'Avg Win: ${wins["pnl_usdt"].mean():.2f}')
print(f'Avg Loss: ${losses["pnl_usdt"].mean():.2f}')
print(f'Profit Factor: {pf:.2f}')

# Monthly Analysis
closed = closed.copy()
closed['time'] = pd.to_datetime(closed['time'])
monthly = closed.set_index('time')['pnl_usdt'].resample('ME').sum()
print('\n[ Monthly PnL Performance ]')
print(monthly)

# Trend duration
opens = df[df['type']=='OPEN'].copy()
opens['time'] = pd.to_datetime(opens['time'])
closes = df[df['type']=='CLOSE'].copy()
closes['time'] = pd.to_datetime(closes['time'])

durations = (closes['time'].values - opens['time'].values).astype('timedelta64[m]').astype(int)
print(f'\nAvg Trade Duration: {durations.mean():.1f} minutes')
print(f'Loss Trade Avg Duration: {durations[closed["pnl_usdt"] < 0].mean():.1f} minutes')
