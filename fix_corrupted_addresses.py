#!/usr/bin/env python3
"""
Script para detectar e limpar endereços corrompidos no Firestore.

Este script encontra usuários com campos de endereço que não podem ser descriptografados
e os remove ou repara, evitando erros na aplicação.
"""

import firebase_admin
from firebase_admin import firestore, credentials
import json
import sys
import os

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

def find_corrupted_addresses(db):
    """
    Encontra usuários com endereços corrompidos que não podem ser descriptografados
    """
    print("🔍 Procurando usuários com endereços corrompidos...")
    
    corrupted_users = []
    
    # Buscar todos os usuários
    users_collection = db.collection('usuarios')
    
    for doc in users_collection.stream():
        user_data = doc.to_dict()
        user_id = doc.id
        
        # Verificar se tem endereço
        endereco = user_data.get('endereco')
        if endereco and isinstance(endereco, dict):
            has_corruption = False
            corrupted_fields = []
            
            for field, encrypted_value in endereco.items():
                if encrypted_value and isinstance(encrypted_value, str):
                    try:
                        # Tentar descriptografar
                        decrypted = decrypt_data(encrypted_value)
                        # Se chegou até aqui, está OK
                    except Exception as e:
                        has_corruption = True
                        corrupted_fields.append(field)
                        print(f"❌ Usuário {user_id}: Campo '{field}' corrompido - {str(e)}")
            
            if has_corruption:
                try:
                    # Tentar descriptografar nome para identificação
                    nome = decrypt_data(user_data.get('nome', 'Nome não disponível'))
                except:
                    nome = '[Erro ao descriptografar nome]'
                
                corrupted_users.append({
                    'id': user_id,
                    'nome': nome,
                    'email': user_data.get('email', 'Email não disponível'),
                    'corrupted_fields': corrupted_fields,
                    'doc_ref': users_collection.document(user_id)
                })
    
    return corrupted_users

def display_corrupted_users(corrupted_users):
    """Exibe informações sobre os usuários com endereços corrompidos"""
    if not corrupted_users:
        print("✅ Nenhum usuário com endereço corrompido encontrado!")
        return False
    
    print(f"\n🚨 Encontrados {len(corrupted_users)} usuários com endereços corrompidos:\n")
    
    for user in corrupted_users:
        print(f"ID: {user['id']}")
        print(f"Nome: {user['nome']}")
        print(f"Email: {user['email']}")
        print(f"Campos corrompidos: {', '.join(user['corrupted_fields'])}")
        print("-" * 80)
    
    return True

def fix_corrupted_addresses(db, corrupted_users, dry_run=True):
    """
    Remove os campos de endereço corrompidos dos usuários
    
    Args:
        db: Cliente do Firestore
        corrupted_users: Lista de usuários com endereços corrompidos
        dry_run: Se True, apenas simula a correção sem executar
    """
    
    if dry_run:
        print("\n🧪 MODO SIMULAÇÃO - Nenhuma alteração será feita no banco")
    else:
        print("\n⚠️ MODO REAL - Endereços corrompidos serão removidos!")
    
    for user in corrupted_users:
        print(f"\nProcessando usuário: {user['nome']} ({user['id']})")
        
        if dry_run:
            print(f"  📋 SIMULAÇÃO: Removeria campo 'endereco' corrompido")
        else:
            try:
                # Remover o campo endereco completamente
                user['doc_ref'].update({'endereco': firestore.DELETE_FIELD})
                print(f"  ✅ Campo 'endereco' removido com sucesso")
            except Exception as e:
                print(f"  ❌ Erro ao remover campo 'endereco': {e}")
    
    print(f"\n📊 RESUMO:")
    print(f"Total de usuários com endereços corrompidos: {len(corrupted_users)}")
    
    if dry_run:
        print("\n💡 Para executar a correção real, execute: python fix_corrupted_addresses.py --execute")
    else:
        print("\n✅ Correção concluída! Os usuários agora podem ser sincronizados normalmente.")

def main():
    """Função principal"""
    
    # Verificar argumentos
    dry_run = '--execute' not in sys.argv
    
    if dry_run:
        print("🧪 Executando em MODO SIMULAÇÃO")
    else:
        print("⚠️ Executando em MODO REAL - CUIDADO!")
        response = input("Tem certeza que deseja remover endereços corrompidos? Digite 'SIM' para confirmar: ")
        if response != 'SIM':
            print("Operação cancelada.")
            return
    
    # Inicializar Firebase
    db = initialize_firebase()
    print("✅ Firebase inicializado com sucesso")
    
    # Encontrar endereços corrompidos
    corrupted_users = find_corrupted_addresses(db)
    
    # Exibir usuários corrompidos
    has_corruption = display_corrupted_users(corrupted_users)
    
    if has_corruption:
        # Corrigir endereços corrompidos
        fix_corrupted_addresses(db, corrupted_users, dry_run)
    
    print("\n✅ Script concluído!")

if __name__ == "__main__":
    main()