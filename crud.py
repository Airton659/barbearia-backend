from sqlalchemy.orm import Session
import models, schemas
from passlib.hash import bcrypt
import uuid

# --------- USUÁRIOS ---------
def criar_usuario(db: Session, usuario: schemas.UsuarioCreate):
    senha_hash = bcrypt.hash(usuario.senha)
    novo_usuario = models.Usuario(
        id=uuid.uuid4(),
        nome=usuario.nome,
        email=usuario.email,
        senha_hash=senha_hash
    )
    db.add(novo_usuario)
    db.commit()
    db.refresh(novo_usuario)
    return novo_usuario

def buscar_usuario_por_email(db: Session, email: str):
    return db.query(models.Usuario).filter(models.Usuario.email == email).first()


# --------- BARBEIROS ---------
def listar_barbeiros(db: Session):
    return db.query(models.Barbeiro).filter(models.Barbeiro.ativo == True).all()


# --------- AGENDAMENTOS ---------
def criar_agendamento(db: Session, agendamento: schemas.AgendamentoCreate):
    novo_agendamento = models.Agendamento(
        id=uuid.uuid4(),
        usuario_id=agendamento.usuario_id,
        barbeiro_id=agendamento.barbeiro_id,
        data_hora=agendamento.data_hora
    )
    db.add(novo_agendamento)
    db.commit()
    db.refresh(novo_agendamento)
    return novo_agendamento
