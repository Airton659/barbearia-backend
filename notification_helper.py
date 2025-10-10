"""
Helper de Notificações Híbridas (FCM + APNs)
Envia notificações para ambos os tipos de tokens sem duplicar código.

USO:
    from notification_helper import enviar_notificacao_hibrida

    enviar_notificacao_hibrida(
        fcm_tokens=['token1', 'token2'],
        apns_tokens=['token3', 'token4'],
        titulo="Relatório Avaliado",
        corpo="O Dr(a). House aprovou o relatório do paciente Rocky.",
        data_payload={"tipo": "RELATORIO_AVALIADO", "relatorio_id": "123"}
    )
"""

import logging
from typing import List, Optional, Dict
from firebase_admin import messaging
from apns_service import get_apns_service

logger = logging.getLogger(__name__)


def enviar_notificacao_hibrida(
    fcm_tokens: List[str],
    apns_tokens: List[str],
    titulo: str,
    corpo: str,
    data_payload: Optional[Dict[str, str]] = None,
    webpush_tag: Optional[str] = None
) -> Dict[str, int]:
    """
    Envia notificação para AMBOS FCM (Android/Chrome) e APNs (Safari/iOS).
    Segue o PADRÃO DE ENVIO EM LOOP que já está funcionando no sistema.

    Args:
        fcm_tokens: Lista de tokens FCM (Android/Chrome/Edge)
        apns_tokens: Lista de tokens APNs (Safari/iOS)
        titulo: Título da notificação (ex: "Relatório Avaliado")
        corpo: Corpo da notificação (ex: "O Dr(a). House aprovou...")
        data_payload: Dados extras (ex: {"tipo": "RELATORIO_AVALIADO", "relatorio_id": "123"})
        webpush_tag: Tag para substituir notificações antigas (opcional)

    Returns:
        Dicionário com contadores: {"fcm_sucessos": X, "fcm_falhas": Y, "apns_sucessos": Z, "apns_falhas": W}
    """
    resultado = {
        "fcm_sucessos": 0,
        "fcm_falhas": 0,
        "apns_sucessos": 0,
        "apns_falhas": 0
    }

    # ==============================
    # PARTE 1: ENVIAR PARA FCM (Android/Chrome)
    # ==============================
    if fcm_tokens:
        for token in fcm_tokens:
            try:
                # Monta o objeto Message do FCM
                message_kwargs = {
                    "notification": messaging.Notification(title=titulo, body=corpo),
                    "token": token
                }

                # Adiciona dados customizados se fornecidos
                if data_payload:
                    message_kwargs["data"] = data_payload

                # Adiciona configuração WebPush se tag foi fornecida
                if webpush_tag:
                    message_kwargs["webpush"] = messaging.WebpushConfig(
                        notification=messaging.WebpushNotification(tag=webpush_tag)
                    )

                # Envia a mensagem
                messaging.send(messaging.Message(**message_kwargs))
                resultado["fcm_sucessos"] += 1

            except Exception as e:
                logger.error(f"❌ Erro ao enviar FCM para token {token[:10]}...: {e}")
                resultado["fcm_falhas"] += 1

    # ==============================
    # PARTE 2: ENVIAR PARA APNs (Safari/iOS)
    # ==============================
    if apns_tokens:
        apns_service = get_apns_service()

        if apns_service.enabled:
            for token in apns_tokens:
                try:
                    sucesso = apns_service.send_notification(
                        token=token,
                        titulo=titulo,
                        corpo=corpo,
                        data_payload=data_payload
                    )

                    if sucesso:
                        resultado["apns_sucessos"] += 1
                    else:
                        resultado["apns_falhas"] += 1

                except Exception as e:
                    logger.error(f"❌ Erro ao enviar APNs para token {token[:10]}...: {e}")
                    resultado["apns_falhas"] += 1
        else:
            logger.debug("APNs desabilitado. Tokens Safari ignorados.")

    # Log do resultado
    total_fcm = resultado["fcm_sucessos"] + resultado["fcm_falhas"]
    total_apns = resultado["apns_sucessos"] + resultado["apns_falhas"]

    logger.info(
        f"📊 Notificação híbrida enviada: "
        f"FCM ({resultado['fcm_sucessos']}/{total_fcm}), "
        f"APNs ({resultado['apns_sucessos']}/{total_apns})"
    )

    return resultado


def enviar_notificacao_para_usuario(
    usuario_data: Dict,
    titulo: str,
    corpo: str,
    data_payload: Optional[Dict[str, str]] = None,
    webpush_tag: Optional[str] = None
) -> Dict[str, int]:
    """
    Versão simplificada: recebe o dicionário do usuário e envia para todos os tokens dele.

    Args:
        usuario_data: Dicionário do documento do usuário do Firestore
        titulo: Título da notificação
        corpo: Corpo da notificação
        data_payload: Dados extras
        webpush_tag: Tag WebPush (opcional)

    Returns:
        Dicionário com contadores de envio
    """
    fcm_tokens = usuario_data.get('fcm_tokens', [])
    apns_tokens = usuario_data.get('apns_tokens', [])

    return enviar_notificacao_hibrida(
        fcm_tokens=fcm_tokens,
        apns_tokens=apns_tokens,
        titulo=titulo,
        corpo=corpo,
        data_payload=data_payload,
        webpush_tag=webpush_tag
    )
