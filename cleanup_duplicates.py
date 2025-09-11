#!/usr/bin/env python3
"""
Script para detectar e remover usuários duplicados no Firestore.

Este script procura por usuários que têm o mesmo firebase_uid e mantém
apenas o mais recente, removendo os duplicados.

IMPORTANTE: Execute este script apenas uma vez e faça backup antes!
"""

import firebase_admin
from firebase_admin import firestore, credentials
import json
from collections import defaultdict
from datetime import datetime
import os
import sys

# Adicionar o diretório atual ao path para importar decrypt_data
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from encryption_utils import decrypt_data
except ImportError:
    print("ERRO: Não foi possível importar encryption_utils. Certificar que o arquivo existe.")
    sys.exit(1)

def initialize_firebase():
    """Inicializa o Firebase Admin SDK"""
    try:
        # Tentar usar as credenciais padrão do ambiente
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        return firestore.client()
    except Exception as e:
        print(f"Erro ao inicializar Firebase: {e}")
        sys.exit(1)

def find_duplicate_users(db):
    """
    Encontra usuários duplicados baseado no firebase_uid
    Retorna um dicionário com firebase_uid como chave e lista de usuários como valor
    """
    print("🔍 Procurando usuários duplicados...")
    
    users_by_firebase_uid = defaultdict(list)
    
    # Buscar todos os usuários
    users_collection = db.collection('usuarios')
    
    for doc in users_collection.stream():
        user_data = doc.to_dict()
        firebase_uid = user_data.get('firebase_uid')
        
        if firebase_uid:
            users_by_firebase_uid[firebase_uid].append({
                'id': doc.id,
                'data': user_data,
                'doc_ref': users_collection.document(doc.id)
            })
    
    # Filtrar apenas os que têm duplicatas
    duplicates = {uid: users for uid, users in users_by_firebase_uid.items() if len(users) > 1}
    
    return duplicates

def display_duplicates(duplicates):
    """Exibe informações sobre os usuários duplicados"""
    if not duplicates:
        print("✅ Nenhum usuário duplicado encontrado!")
        return False
    
    print(f"\n🚨 Encontrados {len(duplicates)} firebase_uids com usuários duplicados:\n")
    
    for firebase_uid, users in duplicates.items():
        print(f"Firebase UID: {firebase_uid}")
        print(f"Quantidade de duplicatas: {len(users)}")
        
        for i, user in enumerate(users):
            try:
                # Descriptografar nome se possível
                nome = decrypt_data(user['data'].get('nome', 'Nome não disponível'))
            except:
                nome = '[Erro na descriptografia]'
            
            email = user['data'].get('email', 'Email não disponível')
            roles = user['data'].get('roles', {})
            created = user['data'].get('created_at', 'Data não disponível')
            
            print(f"  [{i+1}] ID: {user['id']}")
            print(f"      Nome: {nome}")
            print(f"      Email: {email}")
            print(f"      Roles: {roles}")
            print(f"      Criado: {created}")
        print("-" * 80)
    
    return True

def cleanup_duplicates(db, duplicates, dry_run=True):
    """
    Remove usuários duplicados, mantendo apenas o mais recente
    
    Args:
        db: Cliente do Firestore
        duplicates: Dicionário de usuários duplicados
        dry_run: Se True, apenas simula a remoção sem executar
    """
    
    if dry_run:
        print("\n🧪 MODO SIMULAÇÃO - Nenhuma alteração será feita no banco")
    else:
        print("\n⚠️ MODO REAL - Usuários serão removidos permanentemente!")
    
    total_to_remove = 0
    
    for firebase_uid, users in duplicates.items():
        print(f"\nProcessando Firebase UID: {firebase_uid}")
        
        # Ordenar usuários por data de criação (mais recente primeiro)
        # Se não houver created_at, usar o ID como critério
        def sort_key(user):
            created_at = user['data'].get('created_at')
            if created_at and hasattr(created_at, 'timestamp'):
                return created_at.timestamp()
            # Fallback: usar o ID do documento (mais recente = ID mais "alto")
            return user['id']
        
        users_sorted = sorted(users, key=sort_key, reverse=True)
        
        # Manter o primeiro (mais recente), remover o resto
        user_to_keep = users_sorted[0]
        users_to_remove = users_sorted[1:]
        
        try:
            nome_keep = decrypt_data(user_to_keep['data'].get('nome', 'Nome não disponível'))
        except:
            nome_keep = '[Erro na descriptografia]'
        
        print(f"✅ MANTER: {user_to_keep['id']} ({nome_keep})")
        
        for user in users_to_remove:
            try:
                nome_remove = decrypt_data(user['data'].get('nome', 'Nome não disponível'))
            except:
                nome_remove = '[Erro na descriptografia]'
            
            print(f"❌ REMOVER: {user['id']} ({nome_remove})")
            total_to_remove += 1
            
            if not dry_run:
                try:
                    user['doc_ref'].delete()
                    print(f"   ✅ Usuário {user['id']} removido com sucesso")
                except Exception as e:
                    print(f"   ❌ Erro ao remover usuário {user['id']}: {e}")
    
    print(f"\n📊 RESUMO:")
    print(f"Total de usuários duplicados encontrados: {sum(len(users) for users in duplicates.values())}")
    print(f"Total de usuários únicos (firebase_uid): {len(duplicates)}")
    print(f"Total de usuários a serem removidos: {total_to_remove}")
    
    if dry_run:
        print("\n💡 Para executar a limpeza real, execute: python cleanup_duplicates.py --execute")

def main():
    """Função principal"""
    
    # Verificar argumentos
    dry_run = '--execute' not in sys.argv
    
    if dry_run:
        print("🧪 Executando em MODO SIMULAÇÃO")
    else:
        print("⚠️ Executando em MODO REAL - CUIDADO!")
        response = input("Tem certeza que deseja remover usuários duplicados? Digite 'SIM' para confirmar: ")
        if response != 'SIM':
            print("Operação cancelada.")
            return
    
    # Inicializar Firebase
    db = initialize_firebase()
    print("✅ Firebase inicializado com sucesso")
    
    # Encontrar duplicatas
    duplicates = find_duplicate_users(db)
    
    # Exibir duplicatas
    has_duplicates = display_duplicates(duplicates)
    
    if has_duplicates:
        # Limpar duplicatas
        cleanup_duplicates(db, duplicates, dry_run)
    
    print("\n✅ Script concluído!")

if __name__ == "__main__":
    main()