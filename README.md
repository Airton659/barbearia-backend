# 🏥📱 API Multi-Tenant para Gestão Clínica e Agendamentos (v3.0)

Bem-vindo ao repositório da API completa de gestão clínica e agendamentos. Este projeto serve como um backend robusto, escalável e genérico, construído com uma arquitetura moderna e multi-tenant, capaz de atender tanto aplicações de agendamento de serviços quanto sistemas completos de gestão clínica e hospitalar.

## 🚀 Sobre o Projeto

Esta API foi desenvolvida para ser o backend de múltiplas aplicações. Ela nasceu suportando negócios de agendamento (como barbearias e salões) e foi expandida para incluir um módulo completo de gestão de pacientes, prontuários médicos, relatórios clínicos e fluxos de trabalho para profissionais de saúde.

O projeto utiliza **FastAPI**, **Firebase Authentication**, **Firestore**, **Google Cloud Storage** e está hospedado no **Google Cloud Run**, garantindo alta performance, escalabilidade e conformidade com LGPD.

**URL Base da API:** `https://barbearia-backend-service-862082955632.southamerica-east1.run.app`

**Documentação Interativa:** `https://barbearia-backend-service-862082955632.southamerica-east1.run.app/docs`

---

## 🔐 Autenticação e Autorização

### 1. Autenticação Firebase
Toda requisição para endpoints protegidos deve conter um **Firebase ID Token** válido:
```
Authorization: Bearer {SEU_ID_TOKEN_AQUI}
```

### 2. Multi-Tenant (Negócio ID)
Para operações dentro de um negócio específico, é obrigatório enviar:
```
negocio-id: {ID_DO_NEGOCIO_AQUI}
```

### 3. Roles e Permissões
- **platform** - Super-administrador da plataforma
- **admin** - Administrador do negócio
- **profissional/enfermeiro** - Profissionais de saúde (enfermeiros)
- **medico** - Médicos (sem login, apenas para vinculação)
- **tecnico** - Técnicos de enfermagem
- **cliente/paciente** - Pacientes

---

## 📋 **ENDPOINTS COMPLETOS DA API**

## **🏢 1. ADMINISTRAÇÃO DA PLATAFORMA**

### Super-Admin (Gestão da Plataforma)
```http
POST   /admin/negocios              # Criar novo negócio na plataforma
GET    /admin/negocios              # Listar todos os negócios
```

### Administração do Negócio
```http
# Gestão de Usuários
GET    /negocios/{id}/usuarios                      # Listar usuários do negócio
GET    /negocios/{id}/clientes                      # Listar clientes 
PATCH  /negocios/{id}/usuarios/{id}/status          # Alterar status do usuário
PATCH  /negocios/{id}/usuarios/{id}/role            # Alterar role do usuário
PATCH  /negocios/{id}/usuarios/{id}/consent         # Atualizar consentimento LGPD

# Gestão de Pacientes
POST   /negocios/{id}/pacientes                     # Criar paciente via admin

# Gestão de Médicos
POST   /negocios/{id}/medicos                       # Criar médico
GET    /negocios/{id}/medicos                       # Listar médicos
PATCH  /negocios/{id}/medicos/{id}                  # Atualizar médico
DELETE /negocios/{id}/medicos/{id}                  # Deletar médico

# Vínculos Paciente-Profissional
POST   /negocios/{id}/vincular-paciente             # Vincular paciente a enfermeiro
DELETE /negocios/{id}/vincular-paciente             # Desvincular paciente
PATCH  /negocios/{id}/pacientes/{id}/vincular-tecnicos    # Vincular técnicos
POST   /negocios/{id}/pacientes/{id}/vincular-medico      # Vincular médico
PATCH  /negocios/{id}/usuarios/{id}/vincular-supervisor   # Vincular supervisor

# Status do Negócio
GET    /negocios/{id}/admin-status                  # Verificar se negócio tem admin
```

---

## **👤 2. AUTENTICAÇÃO E PERFIS**

### Autenticação e Perfil
```http
POST   /users/sync-profile          # Sincronizar perfil do Firebase
GET    /me/profile                  # Obter perfil atual
PUT    /users/update-profile        # Atualizar perfil e foto
PATCH  /me/consent                  # Atualizar consentimento LGPD próprio

# FCM (Notificações Push)
POST   /me/register-fcm-token       # Registrar token FCM
```

---

## **👨‍⚕️ 3. PROFISSIONAIS**

### Perfil Profissional
```http
GET    /profissionais                      # Listar todos os profissionais (público)
GET    /profissionais/{id}                 # Detalhes do profissional
GET    /me/profissional                    # Meu perfil profissional
PUT    /me/profissional                    # Atualizar meu perfil

# Gestão de Pacientes
GET    /me/pacientes                       # Listar pacientes vinculados
```

### Serviços
```http
POST   /me/servicos                        # Criar serviço
GET    /me/servicos                        # Listar meus serviços
PUT    /me/servicos/{id}                   # Atualizar serviço
DELETE /me/servicos/{id}                   # Deletar serviço
```

### Horários de Trabalho
```http
POST   /me/horarios-trabalho               # Definir horários de trabalho
GET    /me/horarios-trabalho               # Obter horários de trabalho

# Bloqueios de Agenda
POST   /me/bloqueios                       # Criar bloqueio de horário
DELETE /me/bloqueios/{id}                  # Remover bloqueio
```

---

## **📅 4. AGENDAMENTOS**

### Disponibilidade
```http
GET    /profissionais/{id}/horarios-disponiveis     # Horários disponíveis
```

### Agendamentos do Cliente
```http
POST   /agendamentos                       # Criar agendamento
GET    /agendamentos/me                    # Meus agendamentos
DELETE /agendamentos/{id}                  # Cancelar agendamento
```

### Agendamentos do Profissional
```http
GET    /me/agendamentos                    # Agendamentos do profissional
PATCH  /me/agendamentos/{id}/cancelar      # Cancelar agendamento
```

---

## **🛍️ 5. SERVIÇOS E CATÁLOGO**

### Catálogo Público
```http
GET    /servicos                           # Listar todos os serviços
GET    /servicos/{id}                      # Detalhes do serviço
GET    /servicos/{id}/profissionais        # Profissionais que oferecem o serviço

# Disponibilidade de Serviços
GET    /profissionais/{id}/horarios-disponiveis     # Calcular horários para serviço
```

---

## **🏥 6. GESTÃO DE PACIENTES E PRONTUÁRIOS**

### Prontuário Completo
```http
GET    /pacientes/{id}/ficha-completa              # Ficha médica completa
GET    /pacientes/{id}/dados-completos             # Dados completos do paciente
```

### Exames
```http
POST   /pacientes/{id}/exames                      # Criar exame
GET    /pacientes/{id}/exames                      # Listar exames
PUT    /pacientes/{id}/exames/{id}                 # Atualizar exame
DELETE /pacientes/{id}/exames/{id}                 # Deletar exame
```

### Medicações
```http
POST   /pacientes/{id}/medicacoes                  # Criar medicação
GET    /pacientes/{id}/medicacoes                  # Listar medicações
PATCH  /pacientes/{id}/medicacoes/{id}             # Atualizar medicação
DELETE /pacientes/{id}/medicacoes/{id}             # Deletar medicação
```

### Checklist
```http
POST   /pacientes/{id}/checklist-itens             # Criar item do checklist
GET    /pacientes/{id}/checklist-itens             # Listar checklist
PATCH  /pacientes/{id}/checklist-itens/{id}        # Atualizar item
DELETE /pacientes/{id}/checklist-itens/{id}        # Deletar item
```

### Consultas/Evoluções
```http
POST   /pacientes/{id}/consultas                   # Criar consulta
GET    /pacientes/{id}/consultas                   # Listar consultas
PATCH  /pacientes/{id}/consultas/{id}              # Atualizar consulta
DELETE /pacientes/{id}/consultas/{id}              # Deletar consulta
```

### Orientações
```http
POST   /pacientes/{id}/orientacoes                 # Criar orientação
GET    /pacientes/{id}/orientacoes                 # Listar orientações
PATCH  /pacientes/{id}/orientacoes/{id}            # Atualizar orientação
DELETE /pacientes/{id}/orientacoes/{id}            # Deletar orientação
```

### Anamnese
```http
POST   /pacientes/{id}/anamnese                    # Criar anamnese
GET    /pacientes/{id}/anamnese                    # Listar anamnese
PUT    /anamnese/{id}                              # Atualizar anamnese
```

### Dados Pessoais
```http
PUT    /pacientes/{id}/dados-pessoais              # Atualizar dados pessoais
PUT    /pacientes/{id}/endereco                    # Atualizar endereço
```

### Suporte Psicológico
```http
POST   /pacientes/{id}/suporte-psicologico         # Criar suporte psicológico
GET    /pacientes/{id}/suporte-psicologico         # Listar suporte
PUT    /pacientes/{id}/suporte-psicologico/{id}    # Atualizar suporte
DELETE /pacientes/{id}/suporte-psicologico/{id}    # Deletar suporte
```

### Supervisão
```http
GET    /pacientes/{id}/tecnicos-supervisionados    # Listar técnicos supervisionados
```

---

## **📝 7. FLUXO DE TÉCNICOS**

### Checklist Diário
```http
GET    /pacientes/{id}/checklist-diario            # Checklist diário
PATCH  /pacientes/{id}/checklist-diario/{id}       # Atualizar item diário
```

### Diário do Técnico
```http
POST   /pacientes/{id}/diario                      # Criar registro no diário
GET    /pacientes/{id}/diario                      # Listar registros do diário
PATCH  /diario/{id}                                # Atualizar registro
```

### Registros Estruturados
```http
POST   /pacientes/{id}/registros                   # Criar registro estruturado
GET    /pacientes/{id}/registros                   # Listar registros
```

---

## **📋 8. RELATÓRIOS MÉDICOS**

### Solicitação de Relatórios
```http
POST   /pacientes/{id}/relatorios                  # Criar solicitação de relatório
GET    /pacientes/{id}/relatorios                  # Listar relatórios do paciente
POST   /relatorios/{id}/fotos                      # Adicionar fotos ao relatório
```

### Fluxo do Médico
```http
GET    /medico/relatorios/pendentes                # Relatórios pendentes
GET    /medico/relatorios                          # Histórico de relatórios
GET    /relatorios/{id}                            # Detalhes completos do relatório
POST   /relatorios/{id}/aprovar                    # Aprovar relatório
POST   /relatorios/{id}/recusar                    # Recusar relatório
PUT    /relatorios/{id}                            # Atualizar relatório
```

---

## **📱 9. FEED SOCIAL E INTERAÇÕES**

### Feed e Postagens
```http
POST   /postagens                                  # Criar postagem
GET    /feed                                       # Feed de postagens
POST   /postagens/{id}/curtir                      # Curtir/descurtir postagem
DELETE /postagens/{id}                             # Deletar postagem
```

### Comentários
```http
POST   /comentarios                                # Criar comentário
GET    /comentarios/{postagem_id}                  # Listar comentários
DELETE /comentarios/{id}                           # Deletar comentário
```

### Avaliações
```http
POST   /avaliacoes                                 # Criar avaliação
GET    /avaliacoes/{profissional_id}               # Listar avaliações
```

---

## **🔔 10. NOTIFICAÇÕES**

### Gestão de Notificações
```http
GET    /notificacoes                               # Listar notificações
GET    /notificacoes/nao-lidas/contagem            # Contar não lidas
POST   /notificacoes/ler-todas                     # Marcar todas como lidas
POST   /notificacoes/marcar-como-lida              # Marcar específica como lida
```

### Notificações Agendadas
```http
POST   /notificacoes/agendar                       # Agendar notificação
```

---

## **🛠️ 11. UTILITÁRIOS**

### Upload de Arquivos
```http
POST   /upload-foto                                # Upload de foto (max 10MB)
POST   /upload-file                                # Upload de arquivo (max 50MB)
```

### Pesquisas de Satisfação
```http
POST   /negocios/{id}/pesquisas/enviar             # Enviar pesquisa
GET    /me/pesquisas                               # Minhas pesquisas disponíveis
POST   /me/pesquisas/{id}/submeter                 # Submeter resposta
GET    /negocios/{id}/pesquisas/resultados         # Resultados das pesquisas
```

### Confirmações de Leitura (Fluxo Técnico)
```http
POST   /pacientes/{id}/confirmar-leitura-plano     # Confirmar leitura do plano
GET    /pacientes/{id}/verificar-leitura-plano     # Verificar se plano foi lido
POST   /pacientes/{id}/confirmar-leitura           # Confirmar leitura geral
GET    /pacientes/{id}/confirmar-leitura/status    # Status das confirmações
```

---

## **📁 12. ARQUIVOS ESTÁTICOS**

### Servir Arquivos
```http
GET    /uploads/profiles/{filename}                # Imagens de perfil
GET    /uploads/fotos/{filename}                   # Fotos gerais
GET    /uploads/relatorios/{filename}              # Fotos de relatórios médicos
GET    /uploads/arquivos/{filename}                # Arquivos gerais
```

---

## **🔧 Schemas de Dados Principais**

### Schemas de Usuários
- `UsuarioSync` - Sincronização de perfil
- `UserProfileUpdate` - Atualização de perfil
- `UsuarioProfile` - Perfil completo do usuário
- `PacienteCreateByAdmin` - Criação de paciente por admin
- `PacienteUpdateDadosPessoais` - Atualização de dados pessoais

### Schemas Médicos
- `ConsultaCreate/Update` - Consultas/evoluções
- `ExameCreate/Update` - Exames médicos
- `MedicacaoCreate/Update` - Medicações
- `OrientacaoCreate/Update` - Orientações médicas
- `AnamneseCreate/Update` - Anamnese
- `RelatorioMedicoCreate/Update` - Relatórios médicos
- `SuportePsicologicoCreate/Update` - Suporte psicológico

### Schemas de Checklist
- `ChecklistItemCreate/Update` - Itens de checklist
- `ChecklistItemDiarioUpdate` - Checklist diário
- `DiarioTecnicoCreate/Update` - Diário do técnico
- `RegistroDiarioCreate/Update` - Registros estruturados

### Schemas de Agendamentos
- `AgendamentoCreate/Update` - Agendamentos
- `ServicoCreate/Update` - Serviços
- `ProfissionalCreate/Update` - Profissionais
- `HorarioTrabalho` - Horários de trabalho
- `Bloqueio` - Bloqueios de agenda

### Schemas Sociais
- `PostagemCreate` - Postagens do feed
- `ComentarioCreate` - Comentários
- `AvaliacaoCreate` - Avaliações

### Schemas de Notificações
- `NotificacaoAgendadaCreate` - Notificações agendadas
- `FCMTokenRequest` - Registro de token FCM

---

## **🔒 Segurança e Conformidade**

### Criptografia LGPD
- ✅ Dados sensíveis criptografados no Firestore
- ✅ Chaves gerenciadas pelo Google Cloud KMS
- ✅ Consentimento LGPD obrigatório
- ✅ Trilha de auditoria para ações críticas

### Controles de Acesso
- ✅ Autenticação Firebase obrigatória
- ✅ Autorização baseada em roles
- ✅ Isolamento multi-tenant
- ✅ Validação de permissões por endpoint

### Limites e Validações
- ✅ Upload de arquivos limitado (5-50MB)
- ✅ Tipos de arquivo validados
- ✅ Validação de schemas Pydantic
- ✅ Rate limiting por usuário

---

## **📊 Principais Fluxos de Trabalho**

### 1. Fluxo Clínico Completo
1. **Admin** cria paciente e vincula a enfermeiro
2. **Enfermeiro** cria plano de cuidado (consulta/evolução)
3. **Técnico** executa plano e registra no diário
4. **Médico** aprova/recusa relatórios solicitados
5. **Paciente** visualiza seu prontuário e responde pesquisas

### 2. Fluxo de Agendamentos
1. **Cliente** visualiza profissionais e horários disponíveis
2. **Cliente** agenda serviço
3. **Profissional** gerencia sua agenda
4. **Sistema** envia notificações automáticas

### 3. Fluxo Social
1. **Profissional** publica no feed
2. **Usuários** interagem com curtidas e comentários
3. **Clientes** avaliam profissionais
4. **Sistema** consolida reputação

---

## **🚀 Deploy e Infraestrutura**

### Ambiente de Produção
- **Hosting**: Google Cloud Run
- **Database**: Firebase Firestore
- **Storage**: Google Cloud Storage
- **Authentication**: Firebase Auth
- **Encryption**: Google Cloud KMS
- **Monitoring**: Google Cloud Logging

### Variáveis de Ambiente
```bash
PORT=8080
GCP_PROJECT_ID=teste-notificacao-barbearia
CLOUD_STORAGE_BUCKET_NAME=barbearia-app-fotoss
KMS_CRYPTO_KEY_NAME=projects/.../cryptoKeys/firestore-data-key/...
FIREBASE_ADMIN_CREDENTIALS=<secret>
```

---

## **📝 Notas de Desenvolvimento**

### Estrutura CRUD Modularizada
A aplicação foi completamente modularizada com 185+ funções CRUD distribuídas em:
- `crud/usuarios.py` - Gestão de usuários
- `crud/negocios.py` - Gestão de negócios
- `crud/profissionais.py` - Profissionais e serviços
- `crud/agendamentos.py` - Sistema de agendamento
- `crud/pacientes.py` - Prontuários médicos
- `crud/anamneses.py` - Anamnese e histórico
- `crud/checklist_diario.py` - Checklists e diários
- `crud/medicos.py` - Relatórios médicos
- `crud/feed.py` - Feed social
- `crud/notifications.py` - Sistema de notificações
- `crud/helpers.py` - Funções auxiliares
- `crud/psicologico.py` - Suporte psicológico

### Tecnologias Utilizadas
- **FastAPI** - Framework web moderno
- **Firebase** - Autenticação e Firestore
- **Google Cloud** - Infraestrutura completa
- **Pydantic** - Validação de dados
- **Uvicorn** - Servidor ASGI
- **Python 3.11** - Linguagem de programação

---

## **💡 Funcionalidades Avançadas**

### Sistema de Notificações
- ✅ Push notifications via FCM
- ✅ Notificações agendadas
- ✅ Histórico de notificações
- ✅ Contadores de não lidas

### Feed Social Interno
- ✅ Postagens dos profissionais
- ✅ Sistema de curtidas
- ✅ Comentários aninhados
- ✅ Avaliações de profissionais

### Gestão de Arquivos
- ✅ Upload seguro de imagens
- ✅ Upload de documentos
- ✅ Organização por categorias
- ✅ Servir arquivos estáticos

### Pesquisas de Satisfação
- ✅ Criação de pesquisas personalizadas
- ✅ Envio automático para pacientes
- ✅ Coleta de respostas
- ✅ Análise de resultados

---

## **⚠️ CORREÇÕES DE PERMISSÕES (IMPORTANTE para Frontend)**

### **Problema Identificado e Corrigido (Janeiro 2025)**
Durante a modularização da API, **13 endpoints importantes** tiveram suas permissões alteradas acidentalmente, causando erros 403 para usuários admin:

**Endpoints Afetados:**
- **POST/PATCH/DELETE** `/pacientes/{id}/exames` 
- **POST/PATCH/DELETE** `/pacientes/{id}/medicacoes`
- **POST/PATCH/DELETE** `/pacientes/{id}/checklist-itens`  
- **POST/DELETE** `/pacientes/{id}/consultas`
- **POST/PATCH/DELETE** `/pacientes/{id}/orientacoes`
- **POST** `/pacientes/{id}/diario`

**O que mudou (INCORRETAMENTE):**
- **ANTES**: `get_paciente_autorizado` → Permitia admin, técnico, enfermeiro, paciente
- **DURANTE BUG**: `get_current_admin_or_profissional_user` → Só admin/profissional
- **AGORA (CORRIGIDO)**: `get_paciente_autorizado` → **Volta ao comportamento original**

**Resultado:** Agora admins conseguem novamente acessar todos os endpoints médicos sem erro 403.

**Para o Frontend:** Se você estava recebendo erros 403 inesperados nos endpoints médicos com usuário admin, isso foi corrigido. A API agora funciona exatamente como antes da modularização.

---

## **📞 Suporte e Documentação**

- **Documentação Interativa**: `/docs` (Swagger UI)
- **Documentação Alternativa**: `/redoc` (ReDoc)
- **Health Check**: `/health`
- **Informações da API**: `/` (endpoint raiz)

---

*API desenvolvida com ❤️ para revolucionar a gestão clínica e de agendamentos*