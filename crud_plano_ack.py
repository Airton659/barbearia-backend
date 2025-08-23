# crud_plano_ack.py
from datetime import date, datetime
from typing import Optional, Dict, Any

from google.cloud.firestore import Client as FirestoreClient
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Utiliza o fuso do usuário/sistema para "ack_date" (America/Sao_Paulo).
# Evita depender de libs extras; ZoneInfo é stdlib (Python 3.9+).
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    TZ = None  # fallback: UTC/local sem conversão explícita

COLLECTION = "plano_ack"


def _today_local_str() -> str:
    """YYYY-MM-DD no fuso America/Sao_Paulo (se disponível)."""
    if TZ:
        return datetime.now(TZ).date().isoformat()
    return date.today().isoformat()


def _doc_id(paciente_id: int, tecnico_id: int, plano_version_id: str, ack_date: str) -> str:
    # ID determinístico para idempotência:
    # <paciente>_<tecnico>_<versao>_<YYYY-MM-DD>
    # Evita duplicidade por dia/versão.
    return f"{paciente_id}_{tecnico_id}_{plano_version_id}_{ack_date}"


def get_plano_ack(
    db: FirestoreClient,
    paciente_id: int,
    tecnico_id: int,
    plano_version_id: str,
    dia: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """
    Busca o ACK do técnico para o paciente e versão do plano no 'dia' (default: hoje).
    Retorna o dict do documento ou None.
    """
    ack_date = (dia or date.fromisoformat(_today_local_str())).isoformat()
    doc_ref = db.collection(COLLECTION).document(
        _doc_id(paciente_id, tecnico_id, plano_version_id, ack_date)
    )
    snap = doc_ref.get()
    return snap.to_dict() if snap.exists else None


def create_plano_ack(
    db: FirestoreClient,
    paciente_id: int,
    tecnico_id: int,
    plano_version_id: str,
    dia: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Cria (idempotente) a confirmação de leitura do plano.
    Se já existir, retorna a existente; caso contrário, grava e retorna.
    """
    ack_date = (dia or date.fromisoformat(_today_local_str())).isoformat()
    doc_id = _doc_id(paciente_id, tecnico_id, plano_version_id, ack_date)
    doc_ref = db.collection(COLLECTION).document(doc_id)

    snap = doc_ref.get()
    if snap.exists:
        return snap.to_dict()

    payload = {
        "id": doc_id,
        "paciente_id": paciente_id,
        "tecnico_id": tecnico_id,
        "plano_version_id": plano_version_id,
        "ack_date": ack_date,  # string YYYY-MM-DD
        "ack_at": SERVER_TIMESTAMP,  # carimbo de servidor
    }
    # merge=False: queremos criar o doc “do zero”; se colidir, falhará — mas já tratamos acima com exists.
    doc_ref.set(payload)
    # ler novamente para materializar o SERVER_TIMESTAMP
    return doc_ref.get().to_dict()
