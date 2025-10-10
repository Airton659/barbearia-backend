"""
Serviço de Apple Push Notifications (APNs) para Web Push
Envia notificações push para usuários Safari/iOS sem interferir no FCM existente.

Implementação usando HTTP/2 direto com a API do Apple APNs.

Configuração necessária:
1. Coloque o arquivo AuthKey_UD85TPJ89Y.p8 no Secret Manager do GCP
2. Configure as variáveis de ambiente:
   - APNS_KEY_PATH=/app/secrets/apns-auth-key.p8
   - APNS_KEY_ID=UD85TPJ89Y
   - APNS_TEAM_ID=M83XX73UUS
   - APNS_TOPIC=web.ygg.conciergeanalicegrubert
   - APNS_USE_SANDBOX=False  (True para desenvolvimento, False para produção)
"""

import os
import logging
import json
import time
from typing import Dict, List, Optional
import httpx
import jwt

logger = logging.getLogger(__name__)


class APNsService:
    """Serviço para enviar notificações via Apple Push Notification Service (Web Push)"""

    def __init__(self):
        """Inicializa o cliente APNs com as credenciais do arquivo .p8"""
        self.enabled = False
        self.auth_key = None
        self.key_id = None
        self.team_id = None
        self.topic = None
        self.use_sandbox = False
        self.apns_host = None

        try:
            # Carrega configurações do ambiente
            key_path = os.getenv('APNS_KEY_PATH')
            self.key_id = os.getenv('APNS_KEY_ID', 'UD85TPJ89Y')
            self.team_id = os.getenv('APNS_TEAM_ID', 'M83XX73UUS')
            self.topic = os.getenv('APNS_TOPIC', 'web.ygg.conciergeanalicegrubert')
            self.use_sandbox = os.getenv('APNS_USE_SANDBOX', 'False').lower() == 'true'

            # Define o host do APNs (sandbox ou produção)
            if self.use_sandbox:
                self.apns_host = 'https://api.sandbox.push.apple.com'
            else:
                self.apns_host = 'https://api.push.apple.com'

            if not key_path:
                logger.warning("APNS_KEY_PATH não configurado. APNs desabilitado. Configure para habilitar notificações Safari/iOS.")
                return

            if not os.path.exists(key_path):
                logger.error(f"Arquivo de chave APNs não encontrado: {key_path}")
                return

            # Lê o conteúdo do arquivo .p8
            with open(key_path, 'r') as f:
                self.auth_key = f.read()

            self.enabled = True
            logger.info(f"✅ APNs Service inicializado com sucesso (Topic: {self.topic}, Sandbox: {self.use_sandbox})")

        except Exception as e:
            logger.error(f"❌ Erro ao inicializar APNs Service: {e}")
            self.enabled = False

    def _generate_auth_token(self) -> str:
        """Gera um JWT token para autenticação com o APNs"""
        headers = {
            "alg": "ES256",
            "kid": self.key_id
        }

        payload = {
            "iss": self.team_id,
            "iat": int(time.time())
        }

        token = jwt.encode(
            payload,
            self.auth_key,
            algorithm="ES256",
            headers=headers
        )

        return token

    def send_notification(
        self,
        token: str,
        titulo: str,
        corpo: str,
        data_payload: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Envia uma notificação Web Push via APNs para um único token Safari.

        Args:
            token: Token de device APNs do Safari
            titulo: Título da notificação (ex: "Relatório Avaliado")
            corpo: Corpo da notificação (ex: "O Dr(a). House aprovou o relatório...")
            data_payload: Dados extras para a aplicação (ex: {"tipo": "RELATORIO_AVALIADO", "relatorio_id": "123"})

        Returns:
            True se enviado com sucesso, False caso contrário
        """
        if not self.enabled:
            logger.debug("APNs desabilitado. Ignorando envio.")
            return False

        try:
            # Gera o token de autenticação
            auth_token = self._generate_auth_token()

            # Constrói o payload da notificação
            payload = {
                "aps": {
                    "alert": {
                        "title": titulo,
                        "body": corpo
                    },
                    "sound": "default"
                }
            }

            # Adiciona dados customizados se fornecidos
            if data_payload:
                for key, value in data_payload.items():
                    payload[key] = value

            # Headers da requisição
            headers = {
                "authorization": f"bearer {auth_token}",
                "apns-topic": self.topic,
                "apns-push-type": "alert",
                "apns-priority": "10",
                "apns-expiration": "0"
            }

            # URL do endpoint APNs
            url = f"{self.apns_host}/3/device/{token}"

            # Envia a requisição HTTP/2
            with httpx.Client(http2=True) as client:
                response = client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=10.0
                )

            if response.status_code == 200:
                logger.info(f"✅ Notificação APNs enviada com sucesso para token {token[:15]}...")
                return True
            else:
                logger.error(f"❌ Erro ao enviar APNs. Status: {response.status_code}, Response: {response.text}")
                return False

        except Exception as e:
            logger.error(f"❌ Erro ao enviar notificação APNs para token {token[:15]}...: {e}")
            return False

    def send_notification_batch(
        self,
        tokens: List[str],
        titulo: str,
        corpo: str,
        data_payload: Optional[Dict[str, str]] = None
    ) -> Dict[str, int]:
        """
        Envia notificações para múltiplos tokens Safari (método em loop, seguindo padrão FCM).

        Args:
            tokens: Lista de tokens APNs
            titulo: Título da notificação
            corpo: Corpo da notificação
            data_payload: Dados extras para a aplicação

        Returns:
            Dicionário com contadores: {"sucessos": X, "falhas": Y}
        """
        if not self.enabled:
            logger.debug("APNs desabilitado. Ignorando envio em lote.")
            return {"sucessos": 0, "falhas": 0}

        sucessos = 0
        falhas = 0

        for token in tokens:
            if self.send_notification(token, titulo, corpo, data_payload):
                sucessos += 1
            else:
                falhas += 1

        logger.info(f"📊 Envio APNs em lote concluído. Sucessos: {sucessos}, Falhas: {falhas}")
        return {"sucessos": sucessos, "falhas": falhas}


# Instância global do serviço (singleton)
_apns_service_instance = None

def get_apns_service() -> APNsService:
    """Retorna a instância singleton do APNsService"""
    global _apns_service_instance
    if _apns_service_instance is None:
        _apns_service_instance = APNsService()
    return _apns_service_instance
