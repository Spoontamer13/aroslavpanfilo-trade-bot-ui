import numpy as np

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    ups = np.where(deltas>0, deltas, 0)
    downs = np.where(deltas<0, -deltas, 0)
    au = np.mean(ups[-period:])
    ad = np.mean(downs[-period:])
    rs = au / ad if ad!=0 else np.inf
    return 100 - 100/(1+rs)


def calculate_mrc_levels(prices):
    p = np.array(prices)
    mid = np.mean(p)
    std = np.std(p)
    
    levels = {
        '1': mid,
        '2': mid - std,
        '3': mid - 2*std,
        '4': mid - 3*std,
        '5': mid - 4*std,
        '2.1': mid + std,
        '3.1': mid + 2*std,
        '4.1': mid + 3*std,
        '5.1': mid + 4*std,
    }
    return levels