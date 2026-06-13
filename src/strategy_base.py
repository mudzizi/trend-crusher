from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    """
    Abstract Base Class for all trading strategies.
    Ensures consistent interface for live trading bots and backtest engines.
    """
    
    @abstractmethod
    def calculate_indicators(self, df_sig, df_trend, config, is_live=False):
        """
        Calculates indicators needed for the strategy.
        Returns a pandas DataFrame with indicator columns.
        """
        pass

    @abstractmethod
    def check_entry_signal(self, row, last_price, use_sniper=False, retest_maker=False, config=None, is_ambushing=False):
        """
        Checks if the current market state row satisfies entry conditions.
        Returns (signal_type, target_price, stop_loss_price).
        """
        pass

    @abstractmethod
    def check_exit_signal(self, row, last_price, state, config):
        """
        Checks if exit conditions are triggered.
        Returns True/False (whether to exit) and updates protected state['sl_price'].
        """
        pass
