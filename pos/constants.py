"""POS payment method choices for Nepal."""

PAYMENT_METHOD_CHOICES = [
    ('cash', 'Cash'),
    ('card', 'Card'),
    ('esewa', 'eSewa'),
    ('khalti', 'Khalti'),
    ('fonepay', 'Fonepay'),
    ('credit', 'Credit'),
]

DIGITAL_WALLET_METHODS = frozenset({'esewa', 'khalti', 'fonepay'})
