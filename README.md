-----

# 📘 API da Barbearia - Documentação do Projeto

Bem-vindo ao repositório da API da Barbearia\! Este documento serve como um guia completo sobre o projeto, desde sua concepção até a documentação detalhada de cada funcionalidade.

## 🚀 Sobre o Projeto

Esta API foi desenvolvida para ser o backend de uma aplicação de agendamento e interação para barbearias. Ela permite que clientes encontrem barbeiros, agendem horários, e que os barbeiros possam gerenciar seus perfis, postar fotos de seus trabalhos e interagir com a comunidade. O projeto utiliza FastAPI, SQLAlchemy e PostgreSQL, e está hospedado na plataforma Render.

## ✅ Status Atual do Projeto

**API 100% Funcional e Testada\!**

Após um ciclo intenso de desenvolvimento e depuração, todos os endpoints planejados foram implementados e validados por uma suíte de 12 testes automatizados. A base do projeto está estável e pronta para ser consumida por uma aplicação frontend.

**URL Base da API:** `https://barbearia-backend-service-198513369137.southamerica-east1.run.app`

-----

## 🛠️ Como Usar a API

Para interagir com os endpoints, você pode usar uma ferramenta de cliente HTTP como o [Postman](https://www.postman.com/) ou [Insomnia](https://insomnia.rest/).

1.  **Copie a URL Base** acima.
2.  Combine-a com um dos endpoints listados abaixo (ex: `https://barbearia-backend-service-198513369137.southamerica-east1.run.app/barbeiros`).
3.  Escolha o método HTTP correto (GET, POST, etc.).
4.  Para endpoints que exigem autenticação, primeiro use o endpoint `POST /login` para obter um `access_token` e adicione-o ao cabeçalho (Header) das suas requisições da seguinte forma:
      * **Key**: `Authorization`
      * **Value**: `Bearer {SEU_TOKEN_AQUI}`

-----

## 🔑 Endpoints da API

Abaixo estão todos os endpoints disponíveis, agrupados por funcionalidade.

### 🔐 Autenticação e Usuários

Endpoints para registro, login, gerenciamento de perfil e recuperação de senha.

#### `POST /usuarios`

  - **Descrição**: Cria um novo usuário (cliente).
  - **Body** (JSON):
    ```json
    {
      "nome": "João da Silva",
      "email": "joao.silva@email.com",
      "senha": "senhaforte123"
    }
    ```
  - **Resposta 200 (Sucesso)**: Retorna o objeto do usuário criado.

#### `POST /login`

  - **Descrição**: Autentica um usuário e retorna um token de acesso JWT.
  - **Body** (form-urlencoded):
      - `username`: o e-mail do usuário
      - `password`: a senha do usuário
  - **Resposta 200 (Sucesso)**:
    ```json
    {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "token_type": "bearer"
    }
    ```

#### `GET /me`

  - **Descrição**: Retorna os dados do usuário atualmente autenticado.
  - **Autenticação**: **Obrigatória**.

#### `POST /recuperar-senha`

  - **Descrição**: Inicia o processo de recuperação de senha.
  - **Body** (JSON):
    ```json
    {
      "email": "joao.silva@email.com"
    }
    ```

#### `POST /resetar-senha`

  - **Descrição**: Define uma nova senha para o usuário usando um token de recuperação válido.
  - **Body** (JSON):
    ```json
    {
      "token": "o_token_recebido_na_etapa_anterior",
      "nova_senha": "minhanovasenha123"
    }
    ```

### 💈 Barbeiros

Endpoints para criar, listar e gerenciar perfis de barbeiros.

#### `GET /barbeiros`

  - **Descrição**: Lista todos os barbeiros ativos.
  - **Parâmetros de Query (Opcional)**:
      - `especialidade` (string): Filtra barbeiros cujo campo de especialidades contenha o texto fornecido (ex: `?especialidade=barba`).

#### `POST /barbeiros`

  - **Descrição**: Converte o usuário autenticado em um perfil de barbeiro.
  - **Autenticação**: **Obrigatória**.
  - **Body** (JSON):
    ```json
    {
      "especialidades": "Cortes modernos, Coloração",
      "foto": "https://url.da.foto/inicial.jpg",
      "ativo": true
    }
    ```

#### `GET /me/barbeiro`

  - **Descrição**: Retorna os dados do perfil de barbeiro do usuário autenticado.
  - **Autenticação**: **Obrigatória**.

#### `PUT /me/barbeiro/foto`

  - **Descrição**: Atualiza a foto de perfil do barbeiro autenticado.
  - **Autenticação**: **Obrigatória**.
  - **Body** (JSON):
    ```json
    {
      "foto_url": "https://nova.url.da/foto.jpg"
    }
    ```

#### `GET /perfil_barbeiro/{barbeiro_id}`

  - **Descrição**: Retorna o perfil público de um barbeiro específico, incluindo suas postagens e avaliações.

### 📅 Agendamentos

Endpoints para criar e visualizar agendamentos.

#### `POST /agendamentos`

  - **Descrição**: Cria um novo agendamento para o usuário autenticado.
  - **Autenticação**: **Obrigatória**.

#### `GET /agendamentos`

  - **Descrição**: Lista todos os agendamentos do usuário autenticado.
  - **Autenticação**: **Obrigatória**.

#### `GET /me/agendamentos`

  - **Descrição**: Lista todos os agendamentos recebidos pelo barbeiro autenticado.
  - **Autenticação**: **Obrigatória**.

### 📸 Feed, Postagens e Interações

Endpoints para o feed social da barbearia.

#### `POST /postagens`

  - **Descrição**: Cria uma nova postagem no feed (apenas para barbeiros).
  - **Autenticação**: **Obrigatória**.

#### `GET /feed`

  - **Descrição**: Retorna o feed de postagens publicadas.

#### `POST /postagens/{postagem_id}/curtir`

  - **Descrição**: Adiciona ou remove uma curtida de uma postagem.
  - **Autenticação**: **Obrigatória**.

#### `POST /comentarios`

  - **Descrição**: Adiciona um comentário a uma postagem.
  - **Autenticação**: **Obrigatória**.

#### `GET /comentarios/{postagem_id}`

  - **Descrição**: Lista todos os comentários de uma postagem.

### ⭐ Avaliações

#### `POST /avaliacoes`

  - **Descrição**: Cria uma avaliação para um barbeiro.
  - **Autenticação**: **Obrigatória**.

#### `GET /avaliacoes/{barbeiro_id}`

  - **Descrição**: Lista todas as avaliações de um barbeiro.

### 📤 Upload de Fotos

#### `POST /upload_foto`

  - **Descrição**: Faz o upload de um arquivo de imagem e retorna a URL pública.
  - **Body** (multipart/form-data): `file`.

-----

## 🧪 Testes Automatizados

O projeto conta com uma suíte de **12 testes automatizados** desenvolvidos com `pytest` e `httpx`. Todos os testes estão passando, garantindo a estabilidade e o correto funcionamento de todos os endpoints.

-----

## 📌 Funcionalidades

Lista de funcionalidades planejadas e o status de cada uma.

  - [x] Recuperação de senha
  - [x] Filtro de barbeiros por especialidade
  - [x] Upload de fotos no perfil
  - [ ] Agenda visual no frontend (próximo passo)
  - [ ] Painel administrativo (próximo passo)

-----

**Última atualização:** 26/07/2025 - API 100% funcional com 12 testes passando.
