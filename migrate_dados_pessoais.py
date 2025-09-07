#!/usr/bin/env python3
"""
Script de migração: Dados Pessoais da Anamnese para Paciente

Este script migra os campos de dados pessoais básicos (idade, sexo, 
estado_civil, profissao) das anamneses mais recentes para o nível 
do paciente.

Benefícios:
- Centraliza dados no nível correto
- Elimina duplicação 
- Facilita acesso aos dados básicos do paciente
- Melhora consistência dos dados

IMPORTANTE: Execute este script apenas uma vez após backup completo do banco!
"""

import os
import sys
from datetime import datetime, date
from firebase_admin import firestore, initialize_app, credentials
from typing import Dict, List, Optional
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def inicializar_firestore():
    """Inicializa cliente Firestore usando credenciais do ambiente"""
    try:
        # Se já foi inicializado, retorna cliente existente
        app = initialize_app()
        client = firestore.client()
        logger.info("✅ Cliente Firestore inicializado com sucesso")
        return client
    except ValueError:
        # App já inicializado
        client = firestore.client()
        logger.info("✅ Cliente Firestore já inicializado")
        return client
    except Exception as e:
        logger.error(f"❌ Erro ao inicializar Firestore: {e}")
        raise

def buscar_anamnese_mais_recente(db: firestore.client, paciente_id: str) -> Optional[Dict]:
    """Busca a anamnese mais recente de um paciente"""
    try:
        query = db.collection('anamneses') \
            .where('paciente_id', '==', paciente_id) \
            .order_by('created_at', direction=firestore.Query.DESCENDING) \
            .limit(1)
        
        docs = list(query.stream())
        if docs:
            data = docs[0].to_dict()
            data['id'] = docs[0].id
            return data
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar anamnese mais recente do paciente {paciente_id}: {e}")
        return None

def calcular_data_nascimento_de_idade(idade: int) -> datetime:
    """Calcula data de nascimento aproximada baseada na idade"""
    try:
        ano_atual = datetime.now().year
        ano_nascimento = ano_atual - idade
        # Usar 1º de janeiro como data padrão
        return datetime(ano_nascimento, 1, 1)
    except:
        # Fallback para idade 30 se houver erro
        return datetime(datetime.now().year - 30, 1, 1)

def migrar_dados_paciente(db: firestore.client, paciente_id: str, dados_anamnese: Dict, dry_run: bool = True) -> bool:
    """Migra dados pessoais da anamnese mais recente para o paciente"""
    try:
        # Extrair dados relevantes da anamnese
        dados_para_migrar = {}
        
        # Idade -> Data de nascimento (aproximada)
        if 'idade' in dados_anamnese and dados_anamnese['idade']:
            idade = dados_anamnese['idade']
            if isinstance(idade, int) and idade > 0:
                data_nascimento = calcular_data_nascimento_de_idade(idade)
                dados_para_migrar['data_nascimento'] = data_nascimento
                logger.info(f"   📅 Idade {idade} -> Data nascimento {data_nascimento.strftime('%Y-%m-%d')}")
        
        # Campos diretos
        campos_diretos = ['sexo', 'estado_civil', 'profissao']
        for campo in campos_diretos:
            if campo in dados_anamnese and dados_anamnese[campo]:
                valor = str(dados_anamnese[campo]).strip()
                if valor:
                    dados_para_migrar[campo] = valor
                    logger.info(f"   📝 {campo}: {valor}")
        
        if not dados_para_migrar:
            logger.warning(f"   ⚠️ Nenhum dado para migrar do paciente {paciente_id}")
            return False
        
        if dry_run:
            logger.info(f"   🔍 DRY RUN: Dados que seriam migrados: {dados_para_migrar}")
            return True
        
        # Executar migração real
        paciente_ref = db.collection('usuarios').document(paciente_id)
        paciente_doc = paciente_ref.get()
        
        if not paciente_doc.exists:
            logger.error(f"   ❌ Paciente {paciente_id} não encontrado")
            return False
        
        # Adicionar campos ao paciente (sem sobrescrever existentes)
        dados_atuais = paciente_doc.to_dict()
        dados_update = {}
        
        for campo, valor in dados_para_migrar.items():
            if campo not in dados_atuais or not dados_atuais[campo]:
                dados_update[campo] = valor
        
        if dados_update:
            paciente_ref.update(dados_update)
            logger.info(f"   ✅ Paciente {paciente_id} atualizado: {dados_update}")
            return True
        else:
            logger.info(f"   ℹ️ Paciente {paciente_id} já possui todos os dados")
            return False
            
    except Exception as e:
        logger.error(f"   ❌ Erro ao migrar dados do paciente {paciente_id}: {e}")
        return False

def executar_migracao(db: firestore.client, dry_run: bool = True):
    """Executa a migração completa"""
    logger.info("🚀 INICIANDO MIGRAÇÃO DE DADOS PESSOAIS")
    logger.info(f"📋 Modo: {'DRY RUN (apenas simulação)' if dry_run else 'EXECUÇÃO REAL'}")
    logger.info("=" * 60)
    
    # Estatísticas
    stats = {
        'pacientes_processados': 0,
        'pacientes_migrados': 0,
        'pacientes_sem_anamnese': 0,
        'pacientes_com_erro': 0
    }
    
    try:
        # Buscar todos os pacientes (usuários com role 'cliente')
        usuarios_query = db.collection('usuarios')
        
        for usuario_doc in usuarios_query.stream():
            usuario_data = usuario_doc.to_dict()
            paciente_id = usuario_doc.id
            
            # Verificar se é paciente (tem role 'cliente' em algum negócio)
            roles = usuario_data.get('roles', {})
            eh_paciente = any(role == 'cliente' for role in roles.values())
            
            if not eh_paciente:
                continue
            
            stats['pacientes_processados'] += 1
            nome = usuario_data.get('nome', 'Nome não disponível')
            logger.info(f"\n👤 Processando paciente: {nome} (ID: {paciente_id})")
            
            # Buscar anamnese mais recente
            anamnese = buscar_anamnese_mais_recente(db, paciente_id)
            
            if not anamnese:
                stats['pacientes_sem_anamnese'] += 1
                logger.warning(f"   ⚠️ Nenhuma anamnese encontrada")
                continue
            
            logger.info(f"   📋 Anamnese encontrada: {anamnese.get('created_at', 'Data não disponível')}")
            
            # Migrar dados
            sucesso = migrar_dados_paciente(db, paciente_id, anamnese, dry_run)
            
            if sucesso:
                stats['pacientes_migrados'] += 1
            else:
                stats['pacientes_com_erro'] += 1
    
    except Exception as e:
        logger.error(f"❌ Erro durante migração: {e}")
        raise
    
    # Relatório final
    logger.info("\n" + "=" * 60)
    logger.info("📊 RELATÓRIO FINAL DA MIGRAÇÃO")
    logger.info("=" * 60)
    logger.info(f"👥 Pacientes processados: {stats['pacientes_processados']}")
    logger.info(f"✅ Pacientes migrados: {stats['pacientes_migrados']}")
    logger.info(f"⚠️ Pacientes sem anamnese: {stats['pacientes_sem_anamnese']}")
    logger.info(f"❌ Pacientes com erro: {stats['pacientes_com_erro']}")
    
    if dry_run:
        logger.info("\n🔍 Esta foi uma simulação (DRY RUN)")
        logger.info("💡 Para executar a migração real, execute: python migrate_dados_pessoais.py --execute")
    else:
        logger.info("\n🎉 Migração concluída com sucesso!")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Migra dados pessoais da anamnese para o paciente')
    parser.add_argument('--execute', action='store_true', 
                       help='Executa a migração real (padrão é dry run)')
    parser.add_argument('--backup-first', action='store_true',
                       help='Lembra de fazer backup antes da execução')
    
    args = parser.parse_args()
    
    if args.execute and not args.backup_first:
        print("⚠️  ATENÇÃO: Você está prestes a executar a migração real!")
        print("📦 Certifique-se de ter feito backup completo do banco antes de continuar.")
        print("🔄 Para prosseguir, execute com --backup-first também:")
        print("   python migrate_dados_pessoais.py --execute --backup-first")
        return
    
    # Inicializar Firestore
    db = inicializar_firestore()
    
    # Executar migração
    dry_run = not args.execute
    executar_migracao(db, dry_run)

if __name__ == "__main__":
    main()