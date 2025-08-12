# 📘 API Multi-Tenant para Agendamentos (v2.0)

Bem-vindo ao repositório da API de Agendamentos. Este projeto serve como um backend robusto, escalável e genérico para aplicações de agendamento de serviços, construído com uma arquitetura moderna e multi-tenant.

## 🚀 Sobre o Projeto

Esta API foi desenvolvida para ser o backend de múltiplas aplicações de agendamento (barbearias, salões de beleza, confeitarias, etc.). Ela permite que donos de negócios gerenciem seus profissionais, serviços e agenda, enquanto os clientes finais podem agendar horários e interagir com o conteúdo do negócio.

O projeto utiliza **FastAPI**, **Firebase Authentication**, **Firestore** e está hospedado no **Google Cloud Run**, garantindo alta performance e escalabilidade.

## ✅ Status Atual do Projeto

**API 100% Migrada e Funcional\!**

A migração da arquitetura original (SQL single-tenant) para a nova arquitetura (Firestore multi-tenant) foi concluída com sucesso. Todas as funcionalidades foram reconstruídas e a base do projeto está estável e pronta para ser consumida por diversas aplicações front-end.

**URL Base da API:** `https://barbearia-backend-service-198513369137.southamerica-east1.run.app`

-----

## 🛠️ Como Usar a API

Para interagir com os endpoints, você pode usar uma ferramenta de cliente HTTP como o [Postman](https://www.postman.com/) ou a documentação interativa do Swagger.

### 1. Autenticação

A autenticação é gerenciada pelo **Firebase Authentication**. Toda requisição para um endpoint protegido deve conter um **Firebase ID Token** válido no cabeçalho (Header):
* **Key**: `Authorization`
* **Value**: `Bearer {SEU_ID_TOKEN_AQUI}`

### 2. Identificação do Negócio (Multi-Tenant)

A maioria das operações ocorre no contexto de um "Negócio" específico. Para isso, é obrigatório enviar o ID do negócio no cabeçalho da requisição:
* **Key**: `negocio-id`
* **Value**: `{ID_DO_NEGOCIO_AQUI}`

-----

## 🔑 Fluxos Principais da API

A documentação completa de todos os endpoints está disponível na **documentação interativa do Swagger**, acessível em `/docs` na URL base. Abaixo estão os fluxos mais importantes.

### Onboarding de Usuários (`POST /users/sync-profile`)

Este é o endpoint central para o cadastro de qualquer usuário. O comportamento muda com base nos dados enviados:
* **Super-Admin:** O primeiro usuário a chamar este endpoint (com a base de dados vazia) se torna o administrador da plataforma.
* **Admin de Negócio:** Um usuário que envia um `codigo_convite` válido é promovido a `admin` do negócio correspondente.
* **Cliente:** Um usuário que envia um `negocio_id` (sem código de convite) é registrado como `cliente` daquele negócio.

### Gerenciamento (Super-Admin)

Endpoints prefixados com `/admin` permitem ao Super-Admin criar e listar negócios na plataforma, gerando os convites para os donos.

### Gerenciamento (Admin de Negócio)

Endpoints prefixados com `/negocios/{negocio_id}` permitem que um `admin` de negócio gerencie sua equipe, como listar clientes e promovê-los a `profissionais`.

### Autogestão (Profissional)

Endpoints prefixados com `/me` (ex: `/me/profissional`, `/me/servicos`) permitem que um usuário `profissional` gerencie seu próprio perfil, catálogo de serviços e agenda.

-----

## 🧪 Testes

A suíte de testes original, baseada em SQL, foi descontinuada. Testes para a nova arquitetura Firestore devem ser desenvolvidos para garantir a cobertura das novas regras de negócio.

-----

**Última atualização:** 11/08/2025 - Migração para arquitetura Firestore multi-tenant concluída.