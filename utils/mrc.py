import pandas as pd

def calculate_mrc_levels(prices: list[float]) -> dict:
    df = pd.DataFrame(prices, columns=["close"])
    df["ma"] = df["close"].rolling(window=20).mean()
    df["std"] = df["close"].rolling(window=20).std()

    latest = df.iloc[-1]
    ma = latest["ma"]
    std = latest["std"]

    if pd.isna(ma) or pd.isna(std):
        return {}

    levels = {
        "1": ma,
        "2": ma - std * 1,
        "3": ma - std * 2,
        "4": ma - std * 3,
        "5": ma - std * 4,
        "2.1": ma + std * 1,
        "3.1": ma + std * 2,
        "4.1": ma + std * 3,
        "5.1": ma + std * 4,
    }

    return levels