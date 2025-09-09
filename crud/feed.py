# crud/feed.py
"""
CRUD para gestão de feed, postagens e comentários
"""

import logging
from typing import Optional, List, Dict
from firebase_admin import firestore
import schemas
from crud.utils import add_timestamps

logger = logging.getLogger(__name__)


def criar_postagem(db: firestore.client, postagem_data: schemas.PostagemCreate, profissional: Dict) -> Dict:
    """Cria uma nova postagem no feed."""
    try:
        postagem_dict = {
            'profissional_id': profissional['id'],
            'profissional_nome': profissional.get('nome', 'Profissional'),
            'negocio_id': postagem_data.negocio_id,
            'titulo': postagem_data.titulo,
            'conteudo': postagem_data.conteudo,
            'tipo': postagem_data.tipo or 'texto',
            'tags': postagem_data.tags or [],
            'anexos': postagem_data.anexos or [],
            'curtidas': 0,
            'comentarios': 0,
            'visibilidade': postagem_data.visibilidade or 'publica'
        }
        
        postagem_dict = add_timestamps(postagem_dict, is_update=False)
        
        doc_ref = db.collection('postagens').document()
        doc_ref.set(postagem_dict)
        postagem_dict['id'] = doc_ref.id
        
        logger.info(f"Postagem criada por profissional {profissional['id']}")
        return postagem_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar postagem: {e}")
        raise


def listar_postagens_por_profissional(db: firestore.client, profissional_id: str) -> List[Dict]:
    """Lista todas as postagens de um profissional."""
    postagens = []
    try:
        query = db.collection('postagens') \
                 .where('profissional_id', '==', profissional_id) \
                 .order_by('created_at', direction=firestore.Query.DESCENDING)
        
        for doc in query.stream():
            postagem_data = doc.to_dict()
            postagem_data['id'] = doc.id
            postagens.append(postagem_data)
        
        logger.info(f"Retornando {len(postagens)} postagens do profissional {profissional_id}")
        return postagens
        
    except Exception as e:
        logger.error(f"Erro ao listar postagens do profissional: {e}")
        return []


def listar_feed_por_negocio(db: firestore.client, negocio_id: str, user_id: Optional[str] = None) -> List[Dict]:
    """Lista o feed de postagens de um negócio."""
    postagens = []
    try:
        query = db.collection('postagens') \
                 .where('negocio_id', '==', negocio_id) \
                 .where('visibilidade', '==', 'publica') \
                 .order_by('created_at', direction=firestore.Query.DESCENDING) \
                 .limit(50)
        
        for doc in query.stream():
            postagem_data = doc.to_dict()
            postagem_data['id'] = doc.id
            
            # Verificar se o usuário curtiu esta postagem
            if user_id:
                curtida_query = db.collection('curtidas') \
                               .where('postagem_id', '==', doc.id) \
                               .where('user_id', '==', user_id) \
                               .limit(1)
                curtidas = list(curtida_query.stream())
                postagem_data['user_curtiu'] = len(curtidas) > 0
            else:
                postagem_data['user_curtiu'] = False
            
            postagens.append(postagem_data)
        
        logger.info(f"Retornando {len(postagens)} postagens do feed do negócio {negocio_id}")
        return postagens
        
    except Exception as e:
        logger.error(f"Erro ao listar feed do negócio: {e}")
        return []


def toggle_curtida(db: firestore.client, postagem_id: str, user_id: str) -> bool:
    """Adiciona ou remove uma curtida de uma postagem."""
    try:
        @firestore.transactional
        def update_in_transaction(transaction, post_reference, curtida_reference, curtida_existe):
            if curtida_existe:
                # Remover curtida
                transaction.delete(curtida_reference)
                transaction.update(post_reference, {"curtidas": firestore.Increment(-1)})
                return False
            else:
                # Adicionar curtida
                curtida_data = {
                    'postagem_id': postagem_id,
                    'user_id': user_id,
                    'created_at': firestore.SERVER_TIMESTAMP
                }
                transaction.set(curtida_reference, curtida_data)
                transaction.update(post_reference, {"curtidas": firestore.Increment(1)})
                return True
        
        # Verificar se a curtida já existe
        curtida_query = db.collection('curtidas') \
                         .where('postagem_id', '==', postagem_id) \
                         .where('user_id', '==', user_id) \
                         .limit(1)
        curtidas = list(curtida_query.stream())
        curtida_existe = len(curtidas) > 0
        
        post_ref = db.collection('postagens').document(postagem_id)
        curtida_ref = db.collection('curtidas').document() if not curtida_existe else curtidas[0].reference
        
        transaction = db.transaction()
        user_curtiu = update_in_transaction(transaction, post_ref, curtida_ref, curtida_existe)
        
        logger.info(f"Curtida {'adicionada' if user_curtiu else 'removida'} na postagem {postagem_id}")
        return user_curtiu
        
    except Exception as e:
        logger.error(f"Erro ao toggle curtida: {e}")
        return False


def criar_comentario(db: firestore.client, comentario_data: schemas.ComentarioCreate, usuario: schemas.UsuarioProfile) -> Dict:
    """Cria um novo comentário em uma postagem."""
    try:
        comentario_dict = {
            'postagem_id': comentario_data.postagem_id,
            'user_id': usuario.id,
            'user_nome': usuario.nome,
            'conteudo': comentario_data.conteudo,
            'tipo': comentario_data.tipo or 'texto'
        }
        
        comentario_dict = add_timestamps(comentario_dict, is_update=False)
        
        # Salvar comentário
        doc_ref = db.collection('comentarios').document()
        doc_ref.set(comentario_dict)
        comentario_dict['id'] = doc_ref.id
        
        # Incrementar contador de comentários na postagem
        post_ref = db.collection('postagens').document(comentario_data.postagem_id)
        post_ref.update({"comentarios": firestore.Increment(1)})
        
        logger.info(f"Comentário criado na postagem {comentario_data.postagem_id}")
        return comentario_dict
        
    except Exception as e:
        logger.error(f"Erro ao criar comentário: {e}")
        raise


def listar_comentarios(db: firestore.client, postagem_id: str) -> List[Dict]:
    """Lista todos os comentários de uma postagem."""
    comentarios = []
    try:
        query = db.collection('comentarios') \
                 .where('postagem_id', '==', postagem_id) \
                 .order_by('created_at', direction=firestore.Query.ASCENDING)
        
        for doc in query.stream():
            comentario_data = doc.to_dict()
            comentario_data['id'] = doc.id
            comentarios.append(comentario_data)
        
        logger.info(f"Retornando {len(comentarios)} comentários da postagem {postagem_id}")
        return comentarios
        
    except Exception as e:
        logger.error(f"Erro ao listar comentários: {e}")
        return []


def deletar_postagem(db: firestore.client, postagem_id: str, profissional_id: str) -> bool:
    """Remove uma postagem (apenas o autor pode deletar)."""
    try:
        post_ref = db.collection('postagens').document(postagem_id)
        post_doc = post_ref.get()
        
        if not post_doc.exists:
            return False
        
        post_data = post_doc.to_dict()
        
        # Verificar se o profissional é o autor
        if post_data.get('profissional_id') != profissional_id:
            logger.warning(f"Profissional {profissional_id} tentou deletar postagem que não é sua")
            return False
        
        # Deletar comentários associados
        comentarios_query = db.collection('comentarios').where('postagem_id', '==', postagem_id)
        batch = db.batch()
        
        for doc in comentarios_query.stream():
            batch.delete(doc.reference)
        
        # Deletar curtidas associadas
        curtidas_query = db.collection('curtidas').where('postagem_id', '==', postagem_id)
        for doc in curtidas_query.stream():
            batch.delete(doc.reference)
        
        # Deletar a postagem
        batch.delete(post_ref)
        batch.commit()
        
        logger.info(f"Postagem {postagem_id} deletada")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao deletar postagem: {e}")
        return False


def deletar_comentario(db: firestore.client, postagem_id: str, comentario_id: str, user_id: str) -> bool:
    """Remove um comentário (apenas o autor pode deletar)."""
    try:
        comentario_ref = db.collection('comentarios').document(comentario_id)
        comentario_doc = comentario_ref.get()
        
        if not comentario_doc.exists:
            return False
        
        comentario_data = comentario_doc.to_dict()
        
        # Verificar se o usuário é o autor
        if comentario_data.get('user_id') != user_id:
            logger.warning(f"Usuário {user_id} tentou deletar comentário que não é seu")
            return False
        
        # Verificar se o comentário pertence à postagem
        if comentario_data.get('postagem_id') != postagem_id:
            return False
        
        # Deletar comentário
        comentario_ref.delete()
        
        # Decrementar contador na postagem
        post_ref = db.collection('postagens').document(postagem_id)
        post_ref.update({"comentarios": firestore.Increment(-1)})
        
        logger.info(f"Comentário {comentario_id} deletado")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao deletar comentário: {e}")
        return False