# 📘 API Multi-Tenant para Agendamentos e Gestão Clínica (v2.1)

Bem-vindo ao repositório da API. Este projeto serve como um backend robusto, escalável e genérico, construído com uma arquitetura moderna e multi-tenant, capaz de atender tanto aplicações de agendamento de serviços quanto sistemas de gestão clínica.

## 🚀 Sobre o Projeto

Esta API foi desenvolvida para ser o backend de múltiplas aplicações. Ela nasceu suportando negócios de agendamento (como barbearias e salões) e foi expandida para incluir um módulo completo de gestão de pacientes para clínicas.

O projeto utiliza **FastAPI**, **Firebase Authentication**, **Firestore** e está hospedado no **Google Cloud Run**, garantindo alta performance e escalabilidade.

**URL Base da API:** `https://barbearia-backend-service-198513369137.southamerica-east1.run.app`

-----

## 🛠️ Como Usar a API

A interação com a API segue dois princípios fundamentais da sua arquitetura multi-tenant.

### 1. Autenticação

A autenticação é gerenciada pelo **Firebase Authentication**. Toda requisição para um endpoint protegido deve conter um **Firebase ID Token** válido no cabeçalho (Header):
* **Key**: `Authorization`
* **Value**: `Bearer {SEU_ID_TOKEN_AQUI}`

### 2. Identificação do Negócio (Multi-Tenant)

A maioria das operações ocorre no contexto de um "Negócio" específico (seja uma barbearia ou uma clínica). Para isso, é obrigatório enviar o ID do negócio no cabeçalho da requisição:
* **Key**: `negocio-id`
* **Value**: `{ID_DO_NEGOCIO_AQUI}`

-----

## 🔑 Módulos e Funcionalidades Principais

A documentação interativa completa de todos os endpoints está disponível em `/docs` na URL base.

### Módulo de Agendamentos (Ex: Barbearias)

Este é o módulo original da aplicação, focado em negócios de agendamento de serviços.
* Gestão de Profissionais e Serviços.
* Sistema de Agendamento com cálculo de horários disponíveis.
* Feed de postagens com interações (curtidas e comentários).
* Sistema de avaliações de profissionais.

### Módulo de Gestão Clínica (Ex: Concierge App)

Este módulo expande a API para atender às necessidades de uma clínica no acompanhamento de pacientes.

#### Gestão da Clínica (Perfil: Gestor/Admin)
* **Gestão de Pacientes:**
    * Criação de novos pacientes (incluindo a conta de usuário no Firebase Auth) via `POST /negocios/{id}/pacientes`.
    * Listagem de pacientes com filtros por status (`ativo` ou `arquivado`) via `GET /negocios/{id}/usuarios`.
    * Arquivamento e reativação de pacientes via `PATCH /negocios/{id}/pacientes/{id}/status`.
* **Gestão de Equipe:**
    * Atualização de papéis de usuários para `cliente` (Paciente) ou `profissional` (Enfermeiro) via `PATCH /negocios/{id}/usuarios/{id}/role`.
* **Gestão de Médicos:**
    * CRUD completo para médicos de referência (sem login) nos endpoints `.../medicos`.
* **Vínculo Paciente-Enfermeiro:**
    * Endpoints para vincular (`POST`) e desvincular (`DELETE`) um paciente a um enfermeiro em `.../vincular-paciente`.

#### Atendimento ao Paciente (Perfil: Enfermeiro)
* **Listagem de Pacientes:**
    * Um enfermeiro pode listar todos os pacientes que estão sob sua responsabilidade via `GET /me/pacientes`.
* **Gestão da Ficha Clínica:**
    * CRUD completo para todas as seções da ficha de um paciente vinculado (`/pacientes/{paciente_id}/...`).
    * Endpoint otimizado para carregar a ficha inteira de uma vez: `GET /pacientes/{paciente_id}/ficha-completa`.
* **Notificações:**
    * Agendamento de notificações futuras para pacientes vinculados via `POST /notificacoes/agendar`.

#### Segurança e Privacidade
* O acesso à ficha de um paciente é estritamente controlado. Apenas o **próprio paciente**, o **enfermeiro vinculado** ou o **gestor da clínica** podem visualizar ou modificar os dados, garantido pela dependência `get_paciente_autorizado`.
* Ações administrativas críticas, como mudança de status de paciente ou vínculo, são registradas em uma trilha de auditoria.
