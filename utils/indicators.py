import numpy as np

def calculate_rsi(prices, period=14):
    prices = np.array(prices)
    if len(prices) < period + 1:
        return [np.nan]

    delta = np.diff(prices)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    avg_gain = np.convolve(gain, np.ones(period), 'valid') / period
    avg_loss = np.convolve(loss, np.ones(period), 'valid') / period

    rs = np.where(avg_loss == 0, np.inf, avg_gain / avg_loss)
    rsi = 100 - (100 / (1 + rs))
    return np.concatenate((np.full(period, np.nan), rsi))