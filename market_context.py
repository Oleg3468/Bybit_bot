from dataclasses import dataclass


@dataclass
class MarketBias:
    direction: str = "NEUTRAL"
    strength: float = 0.0


class MarketAnalyzer:
    def analyze(self, symbol: str) -> MarketBias:
        """Межрыночный контекст (DXY/S&P500) — пока заглушка.
        Возвращает нейтральный bias, чтобы не блокировать сигналы."""
        return MarketBias()

    def format_summary(self, symbol: str) -> str:
        return f"Market context for {symbol}: neutral"

    def get_trade_filter(self, symbol: str, side: str):
        return True, "OK"


def get_analyzer() -> MarketAnalyzer:
    return MarketAnalyzer()
