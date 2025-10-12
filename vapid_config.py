# vapid_config.py
import os

# Chaves VAPID para Web Push (Lembretes de Exames)
# Formato: DER base64url (sem padding)
VAPID_PRIVATE_KEY = "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgR0iDC2jbwq7O7nGDtLzt-yU20_G--2ivJ2d64JdAiCWhRANCAASKrsrKZJ6WIVJlDyjy96QiGvrs8_NwYTQWuj90WoBNolNGAl8ehhGaJSziEoAHZqcEojXHZPVIZXRaweUJ4q20"

VAPID_PUBLIC_KEY = "BIquyspknpYhUmUPKPL3pCIa-uzz83BhNBa6P3RagE2iU0YCXx6GEZolLOISgAdmpwSiNcdk9UhldFrB5QnirbQ"

VAPID_CLAIMS_EMAIL = "mailto:suporte@seusistema.com.br"
