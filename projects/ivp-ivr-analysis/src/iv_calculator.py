import numpy as np
from scipy.stats import norm
from datetime import datetime

def black_scholes_price(S, K, T, r, sigma, option_type='CE'):
    """
    Calculate Black-Scholes option price
    S: Spot price
    K: Strike price
    T: Time to expiry (in years)
    r: Risk-free rate
    sigma: Implied volatility
    option_type: 'CE' for Call, 'PE' for Put
    """
    if T <= 0:
        return max(0, S - K) if option_type == 'CE' else max(0, K - S)
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    if option_type == 'CE':
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    
    return price

def calculate_iv(option_price, S, K, T, r=0.05, option_type='CE', precision=0.0001):
    """
    Calculate Implied Volatility using Newton-Raphson method
    """
    if T <= 0:
        return 0.0
    
    # Initial guess
    sigma = 0.3
    max_iterations = 100
    
    for i in range(max_iterations):
        price = black_scholes_price(S, K, T, r, sigma, option_type)
        vega = calculate_vega(S, K, T, r, sigma)
        
        if vega == 0:
            break
            
        diff = price - option_price
        sigma -= diff / vega
        
        if abs(diff) < precision:
            break
            
        if sigma < 0.01:
            sigma = 0.01
        elif sigma > 3.0:
            sigma = 3.0
    
    return sigma * 100  # Return as percentage

def calculate_vega(S, K, T, r, sigma):
    """Calculate Vega for Black-Scholes"""
    if T <= 0:
        return 0
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    vega = S * norm.pdf(d1) * np.sqrt(T)
    return vega

def get_atm_strike(spot, strike_prices):
    """Find the ATM strike closest to spot price"""
    if not strike_prices:
        return None
    return min(strike_prices, key=lambda x: abs(x - spot))