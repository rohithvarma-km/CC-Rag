from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, get_current_user
from app.db import user_client
from app.schemas import ThreadCreate

router = APIRouter(prefix="/threads", tags=["threads"])


@router.get("")
def list_threads(user: CurrentUser = Depends(get_current_user)):
    r = user_client(user).table("threads").select("id,title,updated_at").order("updated_at", desc=True).execute()
    return r.data


@router.post("")
def create_thread(body: ThreadCreate, user: CurrentUser = Depends(get_current_user)):
    r = user_client(user).table("threads").insert({"title": body.title, "user_id": user.id}).execute()
    return r.data[0]


@router.get("/{thread_id}/messages")
def list_messages(thread_id: str, user: CurrentUser = Depends(get_current_user)):
    db = user_client(user)
    if not db.table("threads").select("id").eq("id", thread_id).execute().data:
        raise HTTPException(404, "Thread not found")
    r = db.table("messages").select("id,role,content,created_at").eq("thread_id", thread_id).order("created_at").execute()
    return r.data


@router.delete("/{thread_id}", status_code=204)
def delete_thread(thread_id: str, user: CurrentUser = Depends(get_current_user)):
    user_client(user).table("threads").delete().eq("id", thread_id).execute()
