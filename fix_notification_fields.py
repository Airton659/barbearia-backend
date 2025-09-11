#!/usr/bin/env python3
"""
Script para corrigir campos de notificações existentes no Firestore.

Este script:
1. Busca todas as notificações que têm campos 'titulo/corpo'
2. Adiciona os campos 'title/body' correspondentes
3. Mantém os campos antigos para compatibilidade
"""

import firebase_admin
from firebase_admin import firestore
import sys
import os

def initialize_firebase():
    """Inicializa o Firebase Admin SDK"""
    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        return firestore.client()
    except Exception as e:
        print(f"Erro ao inicializar Firebase: {e}")
        sys.exit(1)

def find_notifications_to_fix(db):
    """
    Encontra notificações que precisam ser corrigidas
    """
    print("🔍 Procurando notificações com campos titulo/corpo...")
    
    notifications_to_fix = []
    
    # Buscar todos os usuários
    users_collection = db.collection('usuarios')
    
    for user_doc in users_collection.stream():
        user_id = user_doc.id
        
        # Buscar notificações do usuário
        notifications_collection = user_doc.reference.collection('notificacoes')
        
        for notif_doc in notifications_collection.stream():
            notif_data = notif_doc.to_dict()
            notif_id = notif_doc.id
            
            # Verificar se tem 'titulo' mas não tem 'title'
            needs_fix = False
            fix_data = {}
            
            if 'titulo' in notif_data and 'title' not in notif_data:
                fix_data['title'] = notif_data['titulo']
                needs_fix = True
                
            if 'corpo' in notif_data and 'body' not in notif_data:
                fix_data['body'] = notif_data['corpo']
                needs_fix = True
            
            if needs_fix:
                notifications_to_fix.append({
                    'user_id': user_id,
                    'notif_id': notif_id,
                    'doc_ref': notif_doc.reference,
                    'fix_data': fix_data,
                    'original_data': notif_data
                })
                
                print(f"📝 Usuário {user_id}: Notificação {notif_id} precisa ser corrigida")
    
    return notifications_to_fix

def fix_notifications(db, notifications_to_fix, dry_run=True):
    """
    Corrige as notificações encontradas
    """
    if not notifications_to_fix:
        print("✅ Nenhuma notificação precisa ser corrigida!")
        return
    
    print(f"\n📊 Encontradas {len(notifications_to_fix)} notificações para corrigir")
    
    if dry_run:
        print("🧪 MODO SIMULAÇÃO - Nenhuma alteração será feita")
    else:
        print("⚠️ MODO REAL - Notificações serão corrigidas permanentemente!")
    
    success_count = 0
    
    for notification in notifications_to_fix:
        user_id = notification['user_id']
        notif_id = notification['notif_id']
        fix_data = notification['fix_data']
        
        print(f"\n🔄 Corrigindo: Usuário {user_id}, Notificação {notif_id}")
        print(f"  Adicionando campos: {list(fix_data.keys())}")
        
        if not dry_run:
            try:
                notification['doc_ref'].update(fix_data)
                print(f"  ✅ Notificação corrigida com sucesso")
                success_count += 1
            except Exception as e:
                print(f"  ❌ Erro ao corrigir notificação: {e}")
        else:
            print(f"  🧪 SIMULAÇÃO: Adicionaria campos {fix_data}")
            success_count += 1
    
    print(f"\n📊 RESUMO:")
    print(f"Total de notificações processadas: {len(notifications_to_fix)}")
    print(f"Correções bem-sucedidas: {success_count}")
    
    if dry_run:
        print("\n💡 Para executar a correção real, execute: python fix_notification_fields.py --execute")
    else:
        print("\n✅ Correção concluída! As notificações agora têm os campos corretos.")

def main():
    """Função principal"""
    
    # Verificar argumentos
    dry_run = '--execute' not in sys.argv
    
    if dry_run:
        print("🧪 Executando em MODO SIMULAÇÃO")
    else:
        print("⚠️ Executando em MODO REAL - CUIDADO!")
        response = input("Tem certeza que deseja corrigir as notificações? Digite 'SIM' para confirmar: ")
        if response != 'SIM':
            print("Operação cancelada.")
            return
    
    # Inicializar Firebase
    db = initialize_firebase()
    print("✅ Firebase inicializado com sucesso")
    
    # Encontrar notificações para corrigir
    notifications_to_fix = find_notifications_to_fix(db)
    
    # Corrigir notificações
    fix_notifications(db, notifications_to_fix, dry_run)
    
    print("\n✅ Script concluído!")

if __name__ == "__main__":
    main()