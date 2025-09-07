# apps/accounts/services/profile.py
import logging
logger = logging.getLogger(__name__)


def update_user_profile(user, cleaned_data):
    changed = {}
    for f in ("first_name", "last_name", "email"):
        if f in cleaned_data and getattr(user, f) != cleaned_data[f]:
            changed[f] = (getattr(user, f), cleaned_data[f])
            setattr(user, f, cleaned_data[f])

    if changed:
        user.save(update_fields=list(changed.keys()))
        logger.info("Perfil actualizado", extra={
                    "user_id": user.pk, "changed_fields": list(changed.keys())})
    return user
