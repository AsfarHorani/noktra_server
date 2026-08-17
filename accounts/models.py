import secrets

from django.conf import settings
from django.db import models


def generate_token_key():
    return secrets.token_hex(32)


# A hand-rolled token model rather than pulling in Django REST Framework's
# authtoken app — this project has stayed deliberately dependency-light
# throughout (requirements.txt is just Django + requests), and a single
# model + one auth decorator (see auth.py) covers everything actually
# needed here: one token per login, checked on every request via an
# Authorization: Token <key> header.
class AuthToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='auth_tokens')
    key = models.CharField(max_length=64, unique=True, db_index=True, default=generate_token_key)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'AuthToken(user={self.user_id})'
