#!/usr/bin/env python3
"""
Script para migrar imagens de perfil do sistema local para o Google Cloud Storage.

Este script:
1. Busca por usuários que têm URLs locais de imagem
2. Verifica se a imagem existe localmente
3. Faz upload para o Cloud Storage
4. Atualiza o campo profile_image no Firestore
"""

import firebase_admin
from firebase_admin import firestore, credentials
import os
import sys
from google.cloud import storage
import re

# Adicionar o diretório atual ao path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def initialize_firebase():
    """Inicializa o Firebase Admin SDK"""
    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        return firestore.client()
    except Exception as e:
        print(f"Erro ao inicializar Firebase: {e}")
        sys.exit(1)

def find_users_with_local_images(db):
    """
    Encontra usuários que têm URLs locais de imagem de perfil
    """
    print("🔍 Procurando usuários com imagens locais...")
    
    users_with_local_images = []
    local_url_pattern = r'https://barbearia-backend-service-.*\.run\.app/uploads/profiles/'
    
    # Buscar todos os usuários
    users_collection = db.collection('usuarios')
    
    for doc in users_collection.stream():
        user_data = doc.to_dict()
        user_id = doc.id
        profile_image = user_data.get('profile_image')
        
        if profile_image and re.match(local_url_pattern, profile_image):
            # Extrair nome do arquivo da URL
            filename = profile_image.split('/uploads/profiles/')[-1]
            local_path = os.path.join('uploads', 'profiles', filename)
            
            users_with_local_images.append({
                'id': user_id,
                'email': user_data.get('email', 'Email não disponível'),
                'profile_image_url': profile_image,
                'filename': filename,
                'local_path': local_path,
                'doc_ref': users_collection.document(user_id)
            })
            
            print(f"📷 Usuário {user_id}: {profile_image}")
    
    return users_with_local_images

def migrate_image_to_storage(user, storage_client, bucket_name, dry_run=True):
    """
    Migra uma imagem específica para o Cloud Storage
    """
    filename = user['filename']
    local_path = user['local_path']
    
    print(f"\n🔄 Processando: {user['email']} ({filename})")
    
    # Verificar se arquivo existe localmente
    if not os.path.exists(local_path):
        print(f"  ❌ Arquivo local não encontrado: {local_path}")
        return False
    
    if dry_run:
        print(f"  🧪 SIMULAÇÃO: Faria upload de {local_path} para Cloud Storage")
        return True
    
    try:
        # Fazer upload para Cloud Storage
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(f"profiles/{filename}")
        
        # Upload do arquivo
        blob.upload_from_filename(local_path)
        
        # Tornar público
        blob.make_public()
        
        # Nova URL pública
        new_url = blob.public_url
        
        # Atualizar Firestore
        user['doc_ref'].update({
            'profile_image': new_url
        })
        
        print(f"  ✅ Migração concluída: {new_url}")
        return True
        
    except Exception as e:
        print(f"  ❌ Erro na migração: {e}")
        return False

def migrate_images(db, users_with_local_images, dry_run=True):
    """
    Migra todas as imagens encontradas
    """
    if not users_with_local_images:
        print("✅ Nenhuma imagem local encontrada para migrar!")
        return
    
    print(f"\n📊 Encontradas {len(users_with_local_images)} imagens para migrar")
    
    if dry_run:
        print("🧪 MODO SIMULAÇÃO - Nenhuma alteração será feita")
    else:
        print("⚠️ MODO REAL - Imagens serão migradas permanentemente!")
    
    # Configurar Cloud Storage
    bucket_name = os.getenv('CLOUD_STORAGE_BUCKET_NAME', 'barbearia-app-fotoss')
    
    try:
        storage_client = storage.Client()
        
        # Verificar se bucket existe
        bucket = storage_client.bucket(bucket_name)
        if not bucket.exists():
            print(f"❌ Bucket {bucket_name} não existe!")
            return
        
        print(f"✅ Conectado ao bucket: {bucket_name}")
        
    except Exception as e:
        print(f"❌ Erro ao conectar com Cloud Storage: {e}")
        return
    
    # Migrar cada imagem
    success_count = 0
    for user in users_with_local_images:
        if migrate_image_to_storage(user, storage_client, bucket_name, dry_run):
            success_count += 1
    
    print(f"\n📊 RESUMO:")
    print(f"Total de imagens processadas: {len(users_with_local_images)}")
    print(f"Migrações bem-sucedidas: {success_count}")
    
    if dry_run:
        print("\n💡 Para executar a migração real, execute: python migrate_images_to_storage.py --execute")
    else:
        print("\n✅ Migração concluída! As imagens agora estão no Cloud Storage.")

def main():
    """Função principal"""
    
    # Verificar argumentos
    dry_run = '--execute' not in sys.argv
    
    if dry_run:
        print("🧪 Executando em MODO SIMULAÇÃO")
    else:
        print("⚠️ Executando em MODO REAL - CUIDADO!")
        response = input("Tem certeza que deseja migrar as imagens para Cloud Storage? Digite 'SIM' para confirmar: ")
        if response != 'SIM':
            print("Operação cancelada.")
            return
    
    # Inicializar Firebase
    db = initialize_firebase()
    print("✅ Firebase inicializado com sucesso")
    
    # Encontrar usuários com imagens locais
    users_with_local_images = find_users_with_local_images(db)
    
    # Migrar imagens
    migrate_images(db, users_with_local_images, dry_run)
    
    print("\n✅ Script concluído!")

if __name__ == "__main__":
    main()