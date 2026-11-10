import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from src.metrics import calculate_ivr, calculate_ivp

def test_ivr():
    """Test IV Rank calculation"""
    current_iv = 30
    historical = [20, 25, 28, 30, 35, 40, 45]
    
    ivr = calculate_ivr(current_iv, historical)
    
    # Expected: (30-20)/(45-20)*100 = 40
    assert abs(ivr - 40.0) < 0.01
    print("IVR test passed!")

def test_ivp():
    """Test IV Percentile calculation"""
    current_iv = 30
    historical = [20, 25, 28, 30, 35, 40, 45]
    
    ivp = calculate_ivp(current_iv, historical)
    
    # Expected: 3 days below 30 out of 7 = 42.86%
    assert abs(ivp - 42.86) < 0.01
    print("IVP test passed!")

if __name__ == "__main__":
    test_ivr()
    test_ivp()
    print("All tests passed!")