import logging

logger = logging.getLogger("RiskManager")

class RiskManager:
    """
    Manager responsible for validation of risk parameters
    and exposure limitations.
    """
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.logger = logging.getLogger("RiskManager")

    async def check_exposure_safety(self, symbol, last_price, new_order_value_usdt, exchange_adapter, max_position_value_usdt):
        """
        Calculates total exposure (current position value + pending orders value)
        and asserts if it does not exceed the allowed threshold.
        """
        if self.dry_run:
            return True
        
        limit = float(max_position_value_usdt)
        try:
            positions = await exchange_adapter.fetch_positions()
            # Normalize symbol naming for comparison
            normalized_symbol = symbol.replace('/', '').split(':')[0]
            pos = next((p for p in positions if p['symbol'].replace('/', '').split(':')[0] == normalized_symbol), None)
            
            current_pos_value = abs(float(pos['notional'])) if pos and pos.get('notional') else 0
            
            open_orders = await exchange_adapter.get_all_open_orders()
            pending_value = 0
            for o in open_orders:
                price = float(o.get('stopPrice') or o.get('price') or last_price)
                qty = float(o.get('amount', 0))
                pending_value += (price * qty)
                
            total_exposure = current_pos_value + pending_value + new_order_value_usdt
            if total_exposure > limit:
                self.logger.warning(f"⚠️ SAFETY LIMIT REACHED: ${total_exposure:,.2f} > ${limit:,.2f}")
                return False
            return True
        except Exception as e:
            self.logger.error(f"Safety check error: {e}")
            # Err on the side of caution: if check fails, block order execution
            return False
