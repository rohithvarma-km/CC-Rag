from supabase import Client, create_client

from app.auth import CurrentUser
from app.config import get_settings


def user_client(user: CurrentUser) -> Client:
    """Supabase client acting as the user, so Postgres RLS applies."""
    s = get_settings()
    client = create_client(s.supabase_url, s.supabase_anon_key)
    client.postgrest.auth(user.token)
    return client
