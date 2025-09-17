from __future__ import annotations
import dns.resolver


DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "guerrillamail.com",
    "10minutemail.com",
    "tempmail.com",
    "trashmail.com",
    "yopmail.com",
    "sharklasers.com",
    "getnada.com",
    "emailondeck.com",
}

def is_disposable_domain(domain: str) -> bool:
    """True si el dominio es de correo desechable (temporal)."""
    return domain.lower() in DISPOSABLE_DOMAINS

def has_mx_records(domain: str) -> bool:
    """
    True si el dominio tiene registros MX (indica que puede recibir correo).
    """
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return len(answers) > 0
    except Exception:
        return False
