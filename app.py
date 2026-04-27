"""
Sistema de Arquivos da Aula — Versão Vercel
Professor: Reberson Marques

Stack:
    Flask (Vercel Functions, runtime Python)
    Neon Postgres (banco de dados gerenciado)
    Vercel Blob   (armazenamento de arquivos)

Variáveis de ambiente esperadas:
    DATABASE_URL              -> URL de conexão Postgres do Neon
    BLOB_READ_WRITE_TOKEN     -> token do Vercel Blob (criado automaticamente
                                 ao adicionar Blob Storage ao projeto)
    SECRET_KEY                -> chave para assinar os cookies de sessão
"""
import os
import uuid
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_from_directory, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import psycopg2
from psycopg2.extras import RealDictCursor
import vercel_blob

# Em desenvolvimento local, carrega .env (em produção a Vercel já injeta)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ADMIN_USERNAME = 'Reberson Marques'
ADMIN_PASSWORD = '256279'

DATABASE_URL = (
    os.environ.get('DATABASE_URL')
    or os.environ.get('POSTGRES_URL')
    or os.environ.get('POSTGRES_PRISMA_URL')
)
BLOB_TOKEN = os.environ.get('BLOB_READ_WRITE_TOKEN')

# Limite de upload via servidor na Vercel é 4,5 MB.
# Setamos 4 MB para ter folga; mensagens flash avisam o usuário.
MAX_UPLOAD_MB = 4
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

app = Flask(__name__, template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES


# ---------------------------------------------------------------------------
# Arquivos estáticos (pasta public/)
# ---------------------------------------------------------------------------
@app.route('/<path:filename>')
def serve_static(filename):
    """Serve arquivos da pasta public/ (CSS, JS, imagens)."""
    from flask import send_from_directory
    public_dir = os.path.join(BASE_DIR, 'public')
    return send_from_directory(public_dir, filename)


# ---------------------------------------------------------------------------
# Banco de dados (Postgres)
# ---------------------------------------------------------------------------
_DB_INITIALIZED = False  # criação de schema é feita uma vez por instância


def get_db():
    """Abre uma nova conexão com o Postgres. Cria o schema na primeira chamada."""
    global _DB_INITIALIZED
    if not DATABASE_URL:
        raise RuntimeError(
            'DATABASE_URL não configurada. Defina a variável de ambiente '
            '(no .env localmente ou nas configurações da Vercel).'
        )
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    if not _DB_INITIALIZED:
        _init_schema(conn)
        _DB_INITIALIZED = True
    return conn


def _init_schema(conn):
    """Cria as tabelas e o usuário admin se ainda não existirem."""
    with conn.cursor() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                original_name TEXT NOT NULL,
                blob_url TEXT NOT NULL,
                blob_pathname TEXT NOT NULL,
                file_size BIGINT,
                file_type TEXT,
                is_admin_file BOOLEAN DEFAULT FALSE,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('SELECT id FROM users WHERE username = %s', (ADMIN_USERNAME,))
        if not c.fetchone():
            c.execute(
                '''INSERT INTO users (username, password_hash, is_admin)
                   VALUES (%s, %s, TRUE)''',
                (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD))
            )
    conn.commit()


# ---------------------------------------------------------------------------
# Decorators e utilidades
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def format_size(size):
    if size is None:
        return '—'
    size = float(size)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f'{size:.1f} {unit}'
        size /= 1024
    return f'{size:.1f} TB'


def format_date(value):
    if not value:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y %H:%M')
    try:
        dt = datetime.strptime(str(value)[:19], '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%d/%m/%Y %H:%M')
    except ValueError:
        return str(value)[:16]


# ---------------------------------------------------------------------------
# Rota auxiliar — serve o CSS em desenvolvimento local.
# Em produção (Vercel), o arquivo em /public/style.css é servido pela CDN
# antes desta rota ser invocada.
# ---------------------------------------------------------------------------
@app.route('/style.css')
def style_css():
    return send_from_directory(os.path.join(BASE_DIR, 'public'), 'style.css')


# ---------------------------------------------------------------------------
# Rotas — Autenticação
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        is_hardcoded_admin = (
            username == ADMIN_USERNAME and password == ADMIN_PASSWORD
        )

        try:
            conn = get_db()
            with conn.cursor() as c:
                c.execute('SELECT * FROM users WHERE username = %s', (username,))
                user = c.fetchone()
            conn.close()
        except Exception as e:
            flash(f'Erro ao conectar ao banco de dados: {e}', 'error')
            return render_template('login.html')

        # Reconhecimento automático do administrador
        if is_hardcoded_admin and user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))

        # Login normal de aluno
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            return redirect(
                url_for('admin_dashboard' if user['is_admin'] else 'student_dashboard')
            )

        flash('Usuário ou senha incorretos.', 'error')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Preencha todos os campos.', 'error')
            return render_template('register.html')
        if len(password) < 4:
            flash('A senha deve ter pelo menos 4 caracteres.', 'error')
            return render_template('register.html')
        if username.lower() == ADMIN_USERNAME.lower():
            flash('Esse nome de usuário não pode ser usado.', 'error')
            return render_template('register.html')

        try:
            conn = get_db()
            with conn.cursor() as c:
                c.execute(
                    '''INSERT INTO users (username, password_hash, is_admin)
                       VALUES (%s, %s, FALSE)''',
                    (username, generate_password_hash(password))
                )
            conn.commit()
            conn.close()
            flash('Cadastro realizado! Agora faça login.', 'success')
            return redirect(url_for('login'))
        except psycopg2.errors.UniqueViolation:
            flash('Este nome de usuário já existe.', 'error')
        except Exception as e:
            flash(f'Erro: {e}', 'error')

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# Rotas — Painéis
# ---------------------------------------------------------------------------
@app.route('/aluno')
@login_required
def student_dashboard():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    conn = get_db()
    with conn.cursor() as c:
        c.execute(
            '''SELECT * FROM files
               WHERE user_id = %s AND is_admin_file = FALSE
               ORDER BY uploaded_at DESC''',
            (session['user_id'],)
        )
        my_files = c.fetchall()

        c.execute(
            '''SELECT f.*, u.username
               FROM files f JOIN users u ON f.user_id = u.id
               WHERE f.is_admin_file = TRUE
               ORDER BY f.uploaded_at DESC'''
        )
        class_files = c.fetchall()
    conn.close()

    return render_template(
        'student_dashboard.html',
        my_files=my_files,
        class_files=class_files,
        format_size=format_size,
        format_date=format_date,
        max_upload_mb=MAX_UPLOAD_MB,
    )


@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    with conn.cursor() as c:
        c.execute(
            '''SELECT f.*, u.username
               FROM files f JOIN users u ON f.user_id = u.id
               WHERE f.is_admin_file = FALSE
               ORDER BY f.uploaded_at DESC'''
        )
        student_files = c.fetchall()

        c.execute(
            '''SELECT * FROM files
               WHERE is_admin_file = TRUE
               ORDER BY uploaded_at DESC'''
        )
        admin_files = c.fetchall()

        c.execute(
            '''SELECT id, username, created_at FROM users
               WHERE is_admin = FALSE ORDER BY username'''
        )
        students = c.fetchall()

        c.execute('SELECT COALESCE(SUM(file_size), 0) AS total FROM files')
        total_size = c.fetchone()['total']
    conn.close()

    return render_template(
        'admin_dashboard.html',
        student_files=student_files,
        admin_files=admin_files,
        students=students,
        total_size=total_size,
        format_size=format_size,
        format_date=format_date,
        max_upload_mb=MAX_UPLOAD_MB,
    )


# ---------------------------------------------------------------------------
# Rotas — Operações com arquivos (Vercel Blob)
# ---------------------------------------------------------------------------
@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if not BLOB_TOKEN:
        flash('Storage não configurado (BLOB_READ_WRITE_TOKEN ausente).', 'error')
        return redirect(request.referrer or url_for('index'))

    file = request.files.get('file')
    if not file or file.filename == '':
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(request.referrer or url_for('index'))

    is_admin_file = (
        request.form.get('is_admin_file') == '1'
        and session.get('is_admin')
    )

    original_name = file.filename
    safe_name = secure_filename(original_name) or 'arquivo'
    file_ext = os.path.splitext(original_name)[1].lower().lstrip('.') or 'arquivo'

    # Pathname no Blob: agrupa por finalidade e por usuário, com UUID para evitar
    # colisões caso dois alunos enviem arquivos de mesmo nome.
    folder = 'turma' if is_admin_file else f'alunos/{session["user_id"]}'
    pathname = f'{folder}/{uuid.uuid4().hex}/{safe_name}'

    file_bytes = file.read()
    file_size = len(file_bytes)

    try:
        result = vercel_blob.put(pathname, file_bytes, {
            'addRandomSuffix': 'false',
            'contentType': file.content_type or 'application/octet-stream',
        })
    except Exception as e:
        flash(f'Erro ao enviar para o storage: {e}', 'error')
        return redirect(request.referrer or url_for('index'))

    blob_url = result['url']
    blob_pathname = result.get('pathname', pathname)

    conn = get_db()
    with conn.cursor() as c:
        c.execute(
            '''INSERT INTO files
               (user_id, original_name, blob_url, blob_pathname,
                file_size, file_type, is_admin_file)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (session['user_id'], original_name, blob_url, blob_pathname,
             file_size, file_ext, is_admin_file)
        )
    conn.commit()
    conn.close()

    flash(f'"{original_name}" enviado com sucesso!', 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/download/<int:file_id>')
@login_required
def download(file_id):
    conn = get_db()
    with conn.cursor() as c:
        c.execute('SELECT * FROM files WHERE id = %s', (file_id,))
        f = c.fetchone()
    conn.close()

    if not f:
        abort(404)

    # Permissões:
    #  - Admin baixa qualquer coisa
    #  - Qualquer aluno baixa arquivos da turma
    #  - Aluno só baixa os próprios arquivos pessoais
    if not session.get('is_admin'):
        if not f['is_admin_file'] and f['user_id'] != session['user_id']:
            abort(403)

    # Redireciona direto para a CDN do Vercel Blob, com ?download=1 para
    # forçar download em vez de exibição inline.
    sep = '&' if '?' in f['blob_url'] else '?'
    return redirect(f"{f['blob_url']}{sep}download=1")


@app.route('/delete/<int:file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    conn = get_db()
    with conn.cursor() as c:
        c.execute('SELECT * FROM files WHERE id = %s', (file_id,))
        f = c.fetchone()

    if not f:
        conn.close()
        abort(404)

    if not session.get('is_admin'):
        if f['is_admin_file'] or f['user_id'] != session['user_id']:
            conn.close()
            abort(403)

    # Remove do Blob (silenciosamente; metadata é apagada de qualquer forma)
    try:
        vercel_blob.delete(f['blob_url'])
    except Exception:
        pass

    with conn.cursor() as c:
        c.execute('DELETE FROM files WHERE id = %s', (file_id,))
    conn.commit()
    conn.close()

    flash('Arquivo removido.', 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    conn = get_db()
    with conn.cursor() as c:
        c.execute('SELECT * FROM users WHERE id = %s', (user_id,))
        user = c.fetchone()
    if not user or user['is_admin']:
        conn.close()
        abort(403)

    # Pega URLs antes de deletar (CASCADE remove as linhas mas precisamos
    # apagar os blobs explicitamente)
    with conn.cursor() as c:
        c.execute('SELECT blob_url FROM files WHERE user_id = %s', (user_id,))
        files = c.fetchall()

    for f in files:
        try:
            vercel_blob.delete(f['blob_url'])
        except Exception:
            pass

    with conn.cursor() as c:
        c.execute('DELETE FROM users WHERE id = %s', (user_id,))  # CASCADE
    conn.commit()
    conn.close()

    flash(f'Aluno "{user["username"]}" removido.', 'success')
    return redirect(url_for('admin_dashboard'))


# ---------------------------------------------------------------------------
# Tratamento de erros
# ---------------------------------------------------------------------------
@app.errorhandler(413)
def too_large(e):
    flash(
        f'Arquivo muito grande. Limite de {MAX_UPLOAD_MB} MB '
        '(restrição da Vercel para uploads via servidor).',
        'error'
    )
    return redirect(request.referrer or url_for('index')), 413


@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', code=403,
                           msg='Você não tem permissão para acessar isso.'), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404,
                           msg='Página ou arquivo não encontrado.'), 404


# ---------------------------------------------------------------------------
# Execução em desenvolvimento local
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
