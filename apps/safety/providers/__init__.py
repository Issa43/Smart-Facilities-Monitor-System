"""External hazard provider adapters.

Adapters only translate a provider response into validated
``NormalizedHazardEvent`` values. They never evaluate project impact, create
alerts, notify anyone, or recommend operational actions; that belongs to the
Safety domain services and policy.
"""
