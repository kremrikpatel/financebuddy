"""Backend message catalogs (alerts, emails, notifications)."""
from __future__ import annotations

CATALOGS: dict[str, dict[str, str]] = {
    "en": {
        "alert.unusual_charge.title": "Unusual charge detected",
        "alert.duplicate_charge.title": "Possible duplicate charge",
        "alert.velocity_burst.title": "Rapid spending burst",
        "alert.overspend.title": "Budget exceeded",
        "alert.duplicate_subscription.title": "Duplicate subscription suspected",
        "welcome.body": "Welcome to FinanceBuddy — your AI money coach.",
    },
    "es": {
        "alert.unusual_charge.title": "Cargo inusual detectado",
        "alert.duplicate_charge.title": "Posible cargo duplicado",
        "alert.velocity_burst.title": "Ráfaga de gastos rápida",
        "alert.overspend.title": "Presupuesto excedido",
        "alert.duplicate_subscription.title": "Posible suscripción duplicada",
        "welcome.body": "Bienvenido a FinanceBuddy, tu entrenador financiero con IA.",
    },
    "fr": {
        "alert.unusual_charge.title": "Dépense inhabituelle détectée",
        "alert.duplicate_charge.title": "Débit en double possible",
        "alert.velocity_burst.title": "Pic de dépenses rapide",
        "alert.overspend.title": "Budget dépassé",
        "alert.duplicate_subscription.title": "Abonnement en double suspecté",
        "welcome.body": "Bienvenue sur FinanceBuddy — votre coach financier IA.",
    },
    "de": {
        "alert.unusual_charge.title": "Ungewöhnliche Abbuchung erkannt",
        "alert.duplicate_charge.title": "Mögliche Doppelbuchung",
        "alert.velocity_burst.title": "Schnelle Ausgabenserie",
        "alert.overspend.title": "Budget überschritten",
        "alert.duplicate_subscription.title": "Mögliches doppeltes Abo",
        "welcome.body": "Willkommen bei FinanceBuddy – deinem KI-Finanzcoach.",
    },
    "hi": {
        "alert.unusual_charge.title": "असामान्य शुल्क का पता चला",
        "alert.duplicate_charge.title": "संभावित डुप्लिकेट चार्ज",
        "alert.velocity_burst.title": "तेज़ी से खर्च",
        "alert.overspend.title": "बजट पार हो गया",
        "alert.duplicate_subscription.title": "डुप्लिकेट सदस्यता की संभावना",
        "welcome.body": "FinanceBuddy में आपका स्वागत है — आपका AI मनी कोच।",
    },
    "ar": {
        "alert.unusual_charge.title": "تم اكتشاف رسوم غير معتادة",
        "alert.duplicate_charge.title": "رسوم مكررة محتملة",
        "alert.velocity_burst.title": "موجة إنفاق سريعة",
        "alert.overspend.title": "تجاوز الميزانية",
        "alert.duplicate_subscription.title": "اشتراك مكرر مشتبه به",
        "welcome.body": "مرحبًا بك في FinanceBuddy — مدربك المالي الذكي.",
    },
}
