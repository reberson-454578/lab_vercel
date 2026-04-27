# Sistema de Arquivos da Aula — Deploy na Vercel

Sistema web do **Laboratório de Informática** onde alunos enviam trabalhos e o professor disponibiliza materiais. Esta versão é pronta pra rodar 100% na nuvem da **Vercel**, gratuitamente.

## Stack

- **Flask + Python** rodando como Vercel Function (serverless)
- **Neon Postgres** para o banco de dados (criado pelo Vercel Marketplace, plano gratuito de 0,5 GB)
- **Vercel Blob** para guardar os arquivos (5 GB grátis no plano Hobby)

## ⚠️ Limites do plano Hobby (gratuito)

- **Tamanho máximo por upload:** 4 MB. Esse é um limite da Vercel para uploads via servidor — cobre Word, PDF, planilhas, imagens normais e apresentações pequenas, mas não vídeos grandes.
- **Storage:** 5 GB de arquivos + 0,5 GB de banco. Mais que suficiente para uma turma.
- **Bandwidth:** 100 GB/mês.

Se um dia precisar passar disso, dá pra fazer upgrade pro plano Pro (US$ 20/mês) ou trocar o Vercel Blob por um S3/Cloudflare R2.

## Estrutura

```
lab_vercel/
├── app.py                # toda a lógica Flask
├── requirements.txt      # dependências Python
├── vercel.json           # config da Vercel
├── .gitignore
├── .env.example          # modelo das variáveis de ambiente
├── README.md
├── templates/            # páginas HTML
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── student_dashboard.html
│   ├── admin_dashboard.html
│   └── error.html
└── public/               # arquivos servidos pela CDN
    └── style.css
```

---

## Passo a passo do deploy

### 1. Crie uma conta no GitHub e na Vercel

- GitHub: <https://github.com/signup>
- Vercel: <https://vercel.com/signup> (entre com a conta GitHub para já vincular)

### 2. Suba o código pro GitHub

Crie um repositório novo (privado, se quiser) e faça upload dos arquivos desta pasta. Pelo terminal:

```bash
cd lab_vercel
git init
git add .
git commit -m "Sistema do laboratório de informática"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/lab-informatica.git
git push -u origin main
```

> Se preferir sem terminal, use o GitHub Desktop ou o botão "Upload files" direto no site do GitHub.

### 3. Importe o projeto na Vercel

1. Entre em <https://vercel.com/new>
2. Selecione o repositório que você acabou de criar
3. A Vercel detecta Flask automaticamente — não precisa mexer em nada de "Build Command"
4. **NÃO clique ainda em "Deploy"** — antes de fazer o primeiro deploy, vamos preparar o banco e o storage. Pode clicar em Deploy mesmo assim; o site vai subir mas vai dar erro nas páginas que usam dados, é só seguir os próximos passos e refazer o deploy.

### 4. Crie o banco de dados (Neon Postgres)

1. No painel do projeto na Vercel, vá em **Storage → Create Database**
2. Escolha **Neon (Postgres)** e clique em "Continue"
3. Escolha um nome (ex: `lab-db`) e a região mais próxima (ex: `São Paulo / gru1` ou `Washington D.C. / iad1`)
4. Clique em "Create"
5. Quando aparecer "Connect Project", confirme — isso adiciona automaticamente a variável `DATABASE_URL` no projeto

### 5. Crie o storage de arquivos (Vercel Blob)

1. Mesmo painel **Storage → Create Database → Blob**
2. Escolha um nome (ex: `lab-blob`)
3. Clique em "Create" e em "Connect Project"
4. Pronto: a variável `BLOB_READ_WRITE_TOKEN` foi adicionada ao projeto automaticamente

### 6. Defina a chave secreta dos cookies

1. No projeto Vercel, vá em **Settings → Environment Variables**
2. Adicione uma variável chamada `SECRET_KEY` com um valor aleatório longo (ex: 64 caracteres)
3. Para gerar, no terminal:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Ou simplesmente cole qualquer texto longo e aleatório.

### 7. Faça o redeploy

Em **Deployments**, na linha do último deploy, clique nos três pontinhos → **Redeploy**. Agora o site sobe com banco e storage funcionando.

### 8. Teste

1. Acesse a URL que a Vercel deu (algo como `https://lab-informatica.vercel.app`)
2. Clique em "Cadastre-se aqui" e faça um cadastro de teste
3. Faça logout e entre como **professor**:
   - Usuário: `Reberson Marques`
   - Senha: `256279`
4. O badge "PROFESSOR" deve aparecer no topo

Pronto! Já dá pra mandar o link pros alunos.

---

## Login do professor

| Campo | Valor |
|---|---|
| Usuário | `Reberson Marques` |
| Senha | `256279` |

O sistema reconhece automaticamente esse login e abre o painel do professor.

## Login dos alunos

Cada aluno cria a conta dele acessando "Cadastre-se aqui" na tela de login. O cadastro é aberto. Se algum aluno indesejado se cadastrar, você remove pelo painel do professor.

---

## Rodando localmente antes do deploy (opcional)

Se quiser testar no seu PC antes de subir pra Vercel:

1. Instale Python 3.10 ou superior
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Copie `.env.example` para `.env` e preencha:
   - `DATABASE_URL`: pegue no painel do Neon (mesmo que vai usar em produção, ou crie um banco separado)
   - `BLOB_READ_WRITE_TOKEN`: pegue no painel do Vercel Blob
   - `SECRET_KEY`: qualquer string longa
4. Rode:
   ```bash
   python app.py
   ```
5. Acesse `http://localhost:5000`

---

## Como atualizar o site depois

Toda vez que você fizer `git push` no GitHub, a Vercel rebuilda e faz redeploy automaticamente. Pra modificar algo no código:

1. Edite os arquivos
2. `git add .`
3. `git commit -m "descrição"`
4. `git push`
5. Em ~30 segundos o site atualizado tá no ar

---

## Trocar a senha do administrador

No `app.py`, linhas perto do topo:

```python
ADMIN_USERNAME = 'Reberson Marques'
ADMIN_PASSWORD = '256279'
```

Mude e faça push pro GitHub. Depois disso:

1. **Importante:** o usuário antigo continua existindo no banco com a senha antiga. Pra não dar conflito:
   - Faça login uma vez com as credenciais novas (vai funcionar pelo reconhecimento automático)
   - O sistema vai usar as novas credenciais daí em diante

Se quiser zerar o banco do zero, use o painel do Neon → Tables → drop tables → recarregue o site (ele recria as tabelas e o admin no primeiro acesso).

---

## Solução de problemas

**"Erro ao conectar ao banco de dados"** → A `DATABASE_URL` não foi setada ou o banco está dormindo. Acesse o painel do Neon e veja se o banco está "Idle" (clique em "Wake up").

**Upload falha com "Arquivo muito grande"** → O arquivo passa de 4 MB. Comprima ou divida em partes.

**Site retorna 500 sempre** → Vá em **Deployments → último deploy → Functions → app.py → Logs**. Os erros aparecem ali.

**Aluno esqueceu a senha** → Como professor, remova o aluno pelo painel e peça pra ele cadastrar de novo.

---

## Segurança

- Senhas dos alunos são salvas com hash (Werkzeug, PBKDF2). Nem você consegue vê-las.
- A `SECRET_KEY` mantém os cookies de sessão seguros — não compartilhe.
- O `BLOB_READ_WRITE_TOKEN` dá acesso aos arquivos do Blob — mesma coisa, não compartilhe.
- O `.gitignore` já bloqueia o `.env` de ser enviado pro GitHub por engano.
