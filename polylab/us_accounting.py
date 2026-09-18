"""US simulation accounting. Decimal dollars; no account or order client.

Fee schedule effective 2026-09-17 00:00 America/New_York.
https://docs.polymarket.us/fees
Whole-contract simulation is a conservative experiment configuration, not a
claim that fractional public depth is invalid or executable.
"""
from decimal import Decimal, ROUND_HALF_EVEN

D=Decimal
CENT=D('.01')
TAKER=D('.0695')
MAKER=D('-.0125')

def number(value):
    x=D(str(value))
    if not x.is_finite():raise ValueError('Nonfinite amount')
    return x

def exact_fee(price,quantity,theta=TAKER):
    p,q=number(price),number(quantity)
    if not 0<p<1 or q<=0:raise ValueError('Invalid execution price or quantity')
    return number(theta)*q*p*(1-p)

def taker_fees(fills):
    """Per-fill rounding with the documented cumulative exact-fee cap.

    Fills are actual matching fills in sequence, not aggregated price levels.
    A depth snapshot does not reveal their fragmentation.
    """
    exact=paid=D(0);fees=[]
    for price,quantity in fills:
        fee=exact_fee(price,quantity);exact+=fee
        charge=max(D(0),min(fee.quantize(CENT,rounding=ROUND_HALF_EVEN),exact.quantize(CENT,rounding=ROUND_HALF_EVEN)-paid))
        fees.append(charge);paid+=charge
    return fees

def maker_fee(price,quantity):
    return exact_fee(price,quantity,MAKER).quantize(CENT,rounding=ROUND_HALF_EVEN)

def conservative_taker_fee(price,quantity):
    """Rounded total is a charge upper bound when matching fragments are unknown."""
    return exact_fee(price,quantity).quantize(CENT,rounding=ROUND_HALF_EVEN)

class Account:
    def __init__(self,capital='50',reserve='40'):
        self.initial=self.cash=number(capital);self.reserve=number(reserve)
        if not 0<=self.reserve<=self.cash:raise ValueError('Invalid reserve')
        self.positions={};self.realized=D(0);self.fees=D(0);self.ledger=[]

    def buy(self,slug,price,quantity,timestamp):
        p,q=number(price),number(quantity)
        if q!=q.to_integral_value():raise ValueError('Experiment uses whole contracts')
        if slug in self.positions:raise ValueError('Duplicate open position')
        fee=conservative_taker_fee(p,q);basis=p*q+fee
        if self.cash-basis<self.reserve:raise ValueError('Cash reserve breached')
        self.cash-=basis;self.fees+=fee
        self.positions[slug]=dict(quantity=q,basis=basis,entered_at=timestamp)
        self.ledger.append(dict(kind='buy',slug=slug,t=timestamp,price=str(p),quantity=str(q),fee=str(fee),cash=str(self.cash)))

    def close(self,slug,price,timestamp,settlement=False):
        p=number(price);pos=self.positions[slug];q=pos['quantity']
        if timestamp<pos['entered_at']:raise ValueError('Exit precedes entry')
        if not 0<=p<=1:raise ValueError('Invalid payout')
        fee=D(0) if settlement else conservative_taker_fee(p,q)
        proceeds=p*q-fee;pnl=proceeds-pos['basis']
        self.cash+=proceeds;self.fees+=fee;self.realized+=pnl;del self.positions[slug]
        self.ledger.append(dict(kind='settlement' if settlement else 'sell',slug=slug,t=timestamp,price=str(p),quantity=str(q),fee=str(fee),pnl=str(pnl),cash=str(self.cash)))
        return pnl

    def snapshot(self):
        basis=sum((p['basis'] for p in self.positions.values()),D(0))
        if self.cash+basis!=self.initial+self.realized:raise ValueError('Account does not reconcile')
        return dict(cash=str(self.cash),open_basis=str(basis),realized_pnl=str(self.realized),fees=str(self.fees),initial_capital=str(self.initial),reserve=str(self.reserve),positions=len(self.positions),fee_assumption='Upper bound from aggregate exact fee rounded half-even to cents; matching fragmentation unknown',live_execution=False)
