def calculate_position_size(capital, price, stop_loss_price, risk_pct, max_leverage=None, max_trade_loss_pct_cap=None):
    stop_dist = abs(price - stop_loss_price)
    if stop_dist <= 0 or capital <= 0 or price <= 0:
        return 0

    risk_amt = capital * risk_pct
    quantity = risk_amt / stop_dist

    if max_leverage is not None and max_leverage > 0:
        max_notional = capital * max_leverage
        max_qty = max_notional / price
        quantity = min(quantity, max_qty)

    if max_trade_loss_pct_cap is not None and max_trade_loss_pct_cap > 0:
        cap_amt = capital * (max_trade_loss_pct_cap / 100)
        max_qty_by_cap = cap_amt / stop_dist
        quantity = min(quantity, max_qty_by_cap)

    return max(quantity, 0)
