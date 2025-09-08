# routers/interacoes.py
"""
Router para feed, comentários, avaliações e interações sociais
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
import schemas
import crud
from database import get_db
from auth import (
    get_current_user_firebase, get_current_profissional_user,
    get_optional_current_user_firebase, validate_negocio_id
)
from firebase_admin import firestore

router = APIRouter(tags=["Feed e Interações", "Avaliações"])

# =================================================================================
# ENDPOINTS DO FEED E POSTAGENS
# =================================================================================

@router.post("/postagens", response_model=schemas.PostagemResponse)
def criar_postagem(
    postagem_data: schemas.PostagemCreate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Cria uma nova postagem no feed."""
    # Buscar dados do profissional
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    return crud.criar_postagem(db, postagem_data, profissional)

@router.get("/feed", response_model=List[schemas.PostagemResponse])
def listar_feed(
    negocio_id: str = Depends(validate_negocio_id),
    current_user: Optional[schemas.UsuarioProfile] = Depends(get_optional_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Lista as postagens do feed de um negócio."""
    user_id = current_user.id if current_user else None
    return crud.listar_feed_por_negocio(db, negocio_id, user_id)

@router.post("/postagens/{postagem_id}/curtir")
def curtir_descurtir_postagem(
    postagem_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Curte ou descurte uma postagem."""
    # Implementar lógica de curtir/descurtir
    # Por enquanto, retornar resposta básica
    return {"message": "Ação de curtir/descurtir processada", "postagem_id": postagem_id}

@router.delete("/postagens/{postagem_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_postagem(
    postagem_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_profissional_user),
    db: firestore.client = Depends(get_db)
):
    """Remove uma postagem do feed."""
    # Buscar dados do profissional
    profissional = crud.buscar_profissional_por_uid(db, negocio_id, current_user.firebase_uid)
    if not profissional:
        raise HTTPException(status_code=404, detail="Perfil profissional não encontrado")
    
    success = crud.deletar_postagem(db, postagem_id, profissional['id'])
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Postagem não encontrada ou você não tem permissão para deletá-la"
        )

# =================================================================================
# ENDPOINTS DE COMENTÁRIOS
# =================================================================================

@router.post("/comentarios", response_model=schemas.ComentarioResponse)
def criar_comentario(
    comentario_data: schemas.ComentarioCreate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Cria um novo comentário em uma postagem."""
    return crud.criar_comentario(db, comentario_data, current_user)

@router.get("/comentarios/{postagem_id}", response_model=List[schemas.ComentarioResponse])
def listar_comentarios_postagem(
    postagem_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: Optional[schemas.UsuarioProfile] = Depends(get_optional_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Lista todos os comentários de uma postagem."""
    return crud.listar_comentarios(db, postagem_id)

@router.delete("/comentarios/{comentario_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_comentario(
    comentario_id: str,
    postagem_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Remove um comentário de uma postagem."""
    success = crud.deletar_comentario(db, postagem_id, comentario_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Comentário não encontrado ou você não tem permissão para deletá-lo"
        )

# =================================================================================
# ENDPOINTS DE AVALIAÇÕES
# =================================================================================

@router.post("/avaliacoes", response_model=schemas.AvaliacaoResponse, status_code=status.HTTP_201_CREATED)
def criar_avaliacao(
    avaliacao_data: schemas.AvaliacaoCreate,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: schemas.UsuarioProfile = Depends(get_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Cria uma nova avaliação para um profissional."""
    return crud.criar_avaliacao(db, avaliacao_data, current_user)

@router.get("/avaliacoes/{profissional_id}", response_model=List[schemas.AvaliacaoResponse])
def listar_avaliacoes_profissional(
    profissional_id: str,
    negocio_id: str = Depends(validate_negocio_id),
    current_user: Optional[schemas.UsuarioProfile] = Depends(get_optional_current_user_firebase),
    db: firestore.client = Depends(get_db)
):
    """Lista todas as avaliações de um profissional."""
    return crud.listar_avaliacoes_por_profissional(db, profissional_id)